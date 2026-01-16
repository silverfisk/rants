from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from gateway.config import AppConfig
from gateway.errors import build_upstream_error_response
from gateway.models.types import ChatCompletionRequest
from gateway.orchestrator import Orchestrator
from gateway.security import enforce_rate_limit, require_auth
from gateway.state.sqlite_store import SQLiteStore


router = APIRouter()


def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


def _get_store(request: Request) -> SQLiteStore:
    return request.app.state.store


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    request: Request,
    config: AppConfig = Depends(_get_config),
    store: SQLiteStore = Depends(_get_store),
):
    auth = require_auth(request)
    enforce_rate_limit(request)
    rlm_name = config.rlm.rants_one.name
    if payload.model and payload.model != rlm_name:
        raise HTTPException(status_code=400, detail="unknown model")
    orchestrator = Orchestrator(config, store, tenant_id=auth.tenant_id)
    input_text = _messages_to_input(payload.messages)
    try:
        response_obj, transcript = await orchestrator.run_response(
            model=rlm_name,
            input_text=input_text,
            tools=payload.tools,
            tool_choice=payload.tool_choice,
            previous_response_id=None,
            stream=payload.stream,
            execute_tools=False,
        )
    except (httpx.HTTPError, ValueError) as exc:
        return build_upstream_error_response(exc)

    if payload.stream:
        async def event_stream() -> AsyncGenerator[str, None]:
            for chunk in _chunk_text(response_obj.output[0].content[0].text):
                data = {
                    "id": response_obj.id,
                    "object": "chat.completion.chunk",
                    "created": int(response_obj.created_at),
                    "model": response_obj.model,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": chunk},
                            "finish_reason": None,
                        }
                    ],
                }
                yield f"data: {json.dumps(data)}\n\n"
            done = {
                "id": response_obj.id,
                "object": "chat.completion.chunk",
                "created": int(response_obj.created_at),
                "model": response_obj.model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {},
                        "finish_reason": "stop",
                    }
                ],
            }
            yield f"data: {json.dumps(done)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    compiled_tool_calls = transcript.steps[-1].tool_calls if transcript.steps else []
    tool_calls = []
    if compiled_tool_calls:
        for index, call in enumerate(compiled_tool_calls):
            tool_name = call.get("tool")
            parameters = call.get("parameters")
            if not isinstance(tool_name, str) or not isinstance(parameters, dict):
                continue
            tool_calls.append(
                {
                    "id": f"call_{response_obj.id}_{index}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(parameters),
                    },
                }
            )

    if tool_calls:
        finish_reason = "tool_calls"
        message = {"role": "assistant", "content": None, "tool_calls": tool_calls}
    else:
        finish_reason = "stop"
        message = {"role": "assistant", "content": response_obj.output[0].content[0].text}

    data = {
        "id": response_obj.id,
        "object": "chat.completion",
        "created": int(response_obj.created_at),
        "model": response_obj.model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
    }
    return JSONResponse(content=data)


def _messages_to_input(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content")
        if isinstance(content, str):
            parts.append(f"{role}: {content}")
        elif isinstance(content, list):
            for item in content:
                if item.get("type") in {"text", "input_text"}:
                    parts.append(f"{role}: {item.get('text', '')}")
    return "\n".join(parts)


def _chunk_text(text: str, chunk_size: int = 64) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

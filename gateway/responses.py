from __future__ import annotations

import json
from typing import Any, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from gateway.config import AppConfig
from gateway.models.types import ResponseEvent, ResponseRequest
from gateway.orchestrator import Orchestrator
from gateway.state.sqlite_store import SQLiteStore


router = APIRouter()


def _get_config(request: Request) -> AppConfig:
    return request.app.state.config


def _get_store(request: Request) -> SQLiteStore:
    return request.app.state.store


@router.post("/v1/responses")
async def create_response(
    payload: ResponseRequest,
    request: Request,
    config: AppConfig = Depends(_get_config),
    store: SQLiteStore = Depends(_get_store),
):
    orchestrator = Orchestrator(config, store)
    response_obj, transcript = await orchestrator.run_response(
        model=payload.model,
        input_text=_extract_input_text(payload.input),
        tools=payload.tools,
        tool_choice=payload.tool_choice,
        previous_response_id=payload.previous_response_id,
        stream=payload.stream,
    )
    if payload.stream:
        async def event_stream() -> AsyncGenerator[str, None]:
            async for event in orchestrator.stream_response(response_obj, transcript):
                data = event.model_dump(exclude_none=True)
                yield f"data: {json.dumps(data)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    return JSONResponse(content=response_obj.model_dump(exclude_none=True))


def _extract_input_text(value: str | list[dict[str, Any]]) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        parts = []
        for item in value:
            if isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, list):
                    for content_item in content:
                        if content_item.get("type") == "input_text":
                            parts.append(content_item.get("text", ""))
                elif isinstance(content, str):
                    parts.append(content)
        return "\n".join(parts)
    return ""

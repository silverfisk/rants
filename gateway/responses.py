from __future__ import annotations

import json
from typing import Any, AsyncGenerator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from gateway.config import AppConfig
from gateway.errors import build_upstream_error_response
from gateway.models.types import ResponseRequest
from gateway.orchestrator import Orchestrator
from gateway.security import enforce_rate_limit, require_auth
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
    auth = require_auth(request)
    enforce_rate_limit(request)
    if config.auth.enabled:
        tenant_id = auth.tenant_id
    else:
        tenant_id = payload.user or auth.tenant_id
    orchestrator = Orchestrator(config, store, tenant_id=tenant_id)
    rlm_name = config.rlm.rants_one.name
    if payload.model and payload.model != rlm_name:
        raise HTTPException(status_code=400, detail="unknown model")
    try:
        response_obj, transcript = await orchestrator.run_response(
            model=rlm_name,
            input_text=_extract_input_text(payload.input),
            tools=payload.tools,
            tool_choice=payload.tool_choice,
            previous_response_id=payload.previous_response_id,
            stream=payload.stream,
        )
    except httpx.HTTPError as exc:
        return build_upstream_error_response(exc)
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

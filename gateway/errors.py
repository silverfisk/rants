from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse
import httpx


def build_upstream_error_response(exc: httpx.HTTPError) -> JSONResponse:
    message = _format_upstream_error(exc)
    payload = {
        "error": {
            "message": message,
            "type": "upstream_error",
            "code": "upstream_error",
        }
    }
    return JSONResponse(status_code=502, content=payload)


def _format_upstream_error(exc: httpx.HTTPError) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response = exc.response
        detail = _extract_error_message(response)
        status = response.status_code
        if detail:
            return f"Upstream error (status {status}): {detail}"
        return f"Upstream error (status {status})"
    return f"Upstream error: {exc}"


def _extract_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message
        message = data.get("message")
        if isinstance(message, str):
            return message
    return response.text

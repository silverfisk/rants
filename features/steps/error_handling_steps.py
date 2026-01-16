from __future__ import annotations

from typing import Any, Callable

import httpx
from behave import given, then, when
from fastapi.testclient import TestClient

from gateway.app import create_app


class StubAsyncClient:
    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self._handler = handler

    async def __aenter__(self) -> "StubAsyncClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[override]
        return None

    async def post(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        request = httpx.Request("POST", url, headers=headers, json=json)
        return self._handler(request)

    def stream(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        request = httpx.Request(method, url, headers=headers, json=json)
        return self._handler(request)


@given("the upstream responses endpoint returns an error")
def given_upstream_error(context) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            500,
            json={"error": {"message": "Upstream exploded"}},
            request=request,
        )

    context.upstream_handler = handler


@when("I request a chat completion")
def when_request_chat_completion(context) -> None:
    app = create_app()
    with TestClient(app) as client:
        with httpx.MockTransport(context.upstream_handler):
            context._original_client = httpx.AsyncClient

            def factory(*args: Any, **kwargs: Any) -> StubAsyncClient:
                return StubAsyncClient(context.upstream_handler)

            httpx.AsyncClient = factory  # type: ignore[assignment]
            try:
                response = client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "rants_one_name",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "stream": False,
                    },
                )
                context.response = response
            finally:
                httpx.AsyncClient = context._original_client  # type: ignore[assignment]


@when("I request a response")
def when_request_response(context) -> None:
    app = create_app()
    with TestClient(app) as client:
        with httpx.MockTransport(context.upstream_handler):
            context._original_client = httpx.AsyncClient

            def factory(*args: Any, **kwargs: Any) -> StubAsyncClient:
                return StubAsyncClient(context.upstream_handler)

            httpx.AsyncClient = factory  # type: ignore[assignment]
            try:
                response = client.post(
                    "/v1/responses",
                    json={
                        "model": "rants_one_name",
                        "input": "Hello",
                        "stream": False,
                    },
                )
                context.response = response
            finally:
                httpx.AsyncClient = context._original_client  # type: ignore[assignment]


@then("the response status should be 502")
def then_status_502(context) -> None:
    assert context.response.status_code == 502


@then("the response error payload should include the upstream error")
def then_error_payload(context) -> None:
    data = context.response.json()
    assert "error" in data
    error = data["error"]
    assert error.get("type") == "upstream_error"
    assert error.get("code") == "upstream_error"
    assert "Upstream exploded" in error.get("message", "")

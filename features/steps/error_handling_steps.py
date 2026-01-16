from __future__ import annotations

import json
from typing import Any, Callable, Literal

import httpx
from behave import given, then, when
from fastapi.testclient import TestClient
from pydantic import BaseModel

from gateway.app import create_app
from gateway.models.types import ResponseObject, ResponseStatus


class ChatCompletionToolCallFunction(BaseModel):
    name: str
    arguments: str


class ChatCompletionToolCall(BaseModel):
    id: str
    type: Literal["function"]
    function: ChatCompletionToolCallFunction


class ChatCompletionMessage(BaseModel):
    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[ChatCompletionToolCall] = []


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatCompletionMessage
    finish_reason: Literal["stop", "tool_calls"]


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: list[ChatCompletionChoice]


ChatCompletionResponse.model_rebuild()


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


@given("the upstream responses endpoint succeeds")
def given_upstream_success(context) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/responses"):
            body = json.loads(request.content.decode("utf-8") or "{}")
            raw_input = body.get("input", "")
            input_text = raw_input if isinstance(raw_input, str) else ""
            if "tool_intent" in input_text:
                return httpx.Response(
                    200,
                    json={
                        "id": "resp_tool_compiler",
                        "object": "response",
                        "created_at": 123.0,
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "id": "msg_tool_compiler",
                                "status": "completed",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": '{"tool_calls": []}',
                                        "annotations": [],
                                    }
                                ],
                            }
                        ],
                    },
                    request=request,
                )

            return httpx.Response(
                200,
                json={
                    "id": "resp_123",
                    "object": "response",
                    "created_at": 123.0,
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "id": "msg_1",
                            "status": "completed",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "Hello!",
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                },
                request=request,
            )

        return httpx.Response(404, json={"error": {"message": "Not found"}}, request=request)

    context.upstream_handler = handler


@given("the generator requests a tool call")
def given_tool_intent(context) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/responses"):
            body = json.loads(request.content.decode("utf-8") or "{}")
            raw_input = body.get("input", "")

            if isinstance(raw_input, str) and "tool_intent" in raw_input:
                return httpx.Response(
                    200,
                    json={
                        "id": "resp_tool_compiler",
                        "object": "response",
                        "created_at": 123.0,
                        "status": "completed",
                        "output": [
                            {
                                "type": "message",
                                "id": "msg_tool_compiler",
                                "status": "completed",
                                "role": "assistant",
                                "content": [
                                    {
                                        "type": "output_text",
                                        "text": '{"tool_calls":[{"tool":"bash","parameters":{"command":"echo hi"}}]}',
                                        "annotations": [],
                                    }
                                ],
                            }
                        ],
                    },
                    request=request,
                )

            return httpx.Response(
                200,
                json={
                    "id": "resp_generator",
                    "object": "response",
                    "created_at": 123.0,
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "id": "msg_generator",
                            "status": "completed",
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": "I will use a tool.\nTOOL_INTENT: run bash tool_intent",
                                    "annotations": [],
                                }
                            ],
                        }
                    ],
                },
                request=request,
            )

        return httpx.Response(404, json={"error": {"message": "Not found"}}, request=request)

    context.upstream_handler = handler


def _post_chat_completion(context, payload: dict[str, Any]) -> None:
    app = create_app()
    with TestClient(app) as client:
        with httpx.MockTransport(context.upstream_handler):
            context._original_client = httpx.AsyncClient

            def factory(*args: Any, **kwargs: Any) -> StubAsyncClient:
                return StubAsyncClient(context.upstream_handler)

            httpx.AsyncClient = factory  # type: ignore[assignment]
            try:
                response = client.post("/v1/chat/completions", json=payload)
                context.response = response
            finally:
                httpx.AsyncClient = context._original_client  # type: ignore[assignment]


@when("I request a chat completion")
def when_request_chat_completion(context) -> None:
    _post_chat_completion(
        context,
        {
            "model": "rants_one_name",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
        },
    )


@when("I request a chat completion with tool definitions")
def when_request_chat_completion_tools(context) -> None:
    _post_chat_completion(
        context,
        {
            "model": "rants_one_name",
            "messages": [{"role": "user", "content": "Hi"}],
            "stream": False,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "description": "Execute a shell command",
                        "parameters": {
                            "type": "object",
                            "properties": {"command": {"type": "string"}},
                            "required": ["command"],
                        },
                    },
                }
            ],
            "tool_choice": "auto",
        },
    )


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


@then("the chat completion response matches the contract")
def then_chat_completion_contract(context) -> None:
    data = context.response.json()
    ChatCompletionResponse.model_validate(data)


@then("the responses endpoint returns a valid response object")
def then_responses_contract(context) -> None:
    data = context.response.json()
    response = ResponseObject.model_validate(data)
    assert response.status in {ResponseStatus.COMPLETED, ResponseStatus.IN_PROGRESS}


@then("the response includes tool calls")
def then_tool_calls(context) -> None:
    data = context.response.json()
    ChatCompletionResponse.model_validate(data)
    message = data["choices"][0]["message"]
    assert message.get("tool_calls")
    assert message["tool_calls"][0]["function"]["name"] == "bash"

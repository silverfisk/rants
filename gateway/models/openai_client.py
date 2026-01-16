from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncGenerator

import httpx


@dataclass
class OpenAIResponse:
    status_code: int
    data: dict[str, Any]
    headers: httpx.Headers


class OpenAIClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 120.0,
        max_retries: int = 0,
        backoff_seconds: float = 0.5,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    async def post_json(self, path: str, payload: dict[str, Any]) -> OpenAIResponse:
        return await self._with_retries(self._post_json_once, path, payload)

    async def _post_json_once(self, path: str, payload: dict[str, Any]) -> OpenAIResponse:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
            )
            response.raise_for_status()
            return OpenAIResponse(response.status_code, response.json(), response.headers)

    async def stream_json(self, path: str, payload: dict[str, Any]) -> AsyncGenerator[dict[str, Any], None]:
        attempt = 0
        while True:
            try:
                async for item in self._stream_json_once(path, payload):
                    yield item
                return
            except (httpx.TimeoutException, httpx.HTTPError):
                if attempt >= self.max_retries:
                    raise
                wait_time = self.backoff_seconds * (2**attempt)
                await asyncio.sleep(wait_time)
                attempt += 1

    async def _stream_json_once(
        self,
        path: str,
        payload: dict[str, Any],
    ) -> AsyncGenerator[dict[str, Any], None]:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}{path}",
                headers=self._headers(),
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    if line.startswith("data:"):
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        yield json.loads(data)

    async def _with_retries(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        attempt = 0
        while True:
            try:
                return await func(*args, **kwargs)
            except (httpx.TimeoutException, httpx.HTTPError):
                if attempt >= self.max_retries:
                    raise
                wait_time = self.backoff_seconds * (2**attempt)
                await asyncio.sleep(wait_time)
                attempt += 1


async def collect_stream(stream: AsyncGenerator[dict[str, Any], None]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    async for item in stream:
        items.append(item)
    return items

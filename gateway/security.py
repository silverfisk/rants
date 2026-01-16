from __future__ import annotations

import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from gateway.config import AppConfig


@dataclass(frozen=True)
class AuthContext:
    tenant_id: str
    api_key: str | None
    name: str | None


class RateLimiter:
    def __init__(self, requests_per_minute: int, burst: int) -> None:
        self._rate = max(requests_per_minute, 1) / 60
        self._capacity = max(burst, 1)
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        tokens, last_seen = self._buckets.get(key, (self._capacity, now))
        tokens = min(self._capacity, tokens + (now - last_seen) * self._rate)
        if tokens < 1:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1, now)
        return True


def require_auth(request: Request) -> AuthContext:
    config: AppConfig = request.app.state.config
    if not config.auth.enabled:
        context = AuthContext(tenant_id="default", api_key=None, name="anonymous")
        request.state.auth = context
        return context

    api_key = _extract_api_key(request)
    if not api_key:
        raise HTTPException(status_code=401, detail="missing API key")

    for entry in config.auth.api_keys:
        if entry.key == api_key:
            context = AuthContext(tenant_id=entry.tenant_id, api_key=entry.key, name=entry.name)
            request.state.auth = context
            return context

    raise HTTPException(status_code=401, detail="invalid API key")


def enforce_rate_limit(request: Request) -> None:
    config: AppConfig = request.app.state.config
    if not config.rate_limits.enabled:
        return
    limiter: RateLimiter | None = getattr(request.app.state, "rate_limiter", None)
    if limiter is None:
        return
    auth: AuthContext | None = getattr(request.state, "auth", None)
    tenant_id = auth.tenant_id if auth else "default"
    if not limiter.allow(tenant_id):
        raise HTTPException(status_code=429, detail="rate limit exceeded")
    return


def _extract_api_key(request: Request) -> str | None:
    header = request.headers.get("authorization") or request.headers.get("x-api-key")
    if not header:
        return None
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return header.strip()

from __future__ import annotations

from fastapi import FastAPI

from gateway.chat_shim import router as chat_router
from gateway.config import load_config
from gateway.responses import router as responses_router
from gateway.security import RateLimiter
from gateway.state.sqlite_store import SQLiteStore


def create_app(config_path: str = "config.yaml") -> FastAPI:
    config = load_config(config_path)
    store = SQLiteStore(config.state.sqlite_path)

    app = FastAPI(title="RANTS Gateway", version="0.1.0")
    app.state.config = config
    app.state.store = store
    if config.rate_limits.enabled:
        app.state.rate_limiter = RateLimiter(
            requests_per_minute=config.rate_limits.requests_per_minute,
            burst=config.rate_limits.burst,
        )

    @app.on_event("startup")
    async def startup() -> None:
        await store.initialize()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": app.version}

    @app.get("/v1/models")
    async def list_models() -> dict[str, object]:
        return {
            "object": "list",
            "data": [
                {"id": model.name, "object": "model"} for model in config.rlm.list_models()
            ],
        }

    app.include_router(responses_router)
    app.include_router(chat_router)
    return app


app = create_app()

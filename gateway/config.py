from __future__ import annotations

from pathlib import Path
from typing import Any
import os

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict



class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class LimitsConfig(BaseModel):
    max_tool_iterations: int = 6
    max_wallclock_seconds: int = 120
    max_depth: int = 2
    workspace_root: str = "/work"
    tool_output_max_bytes: int = 16384
    webfetch_max_bytes: int = 5 * 1024 * 1024


class AuthKeyConfig(BaseModel):
    key: str
    tenant_id: str = "default"
    name: str | None = None


class AuthConfig(BaseModel):
    enabled: bool = False
    api_keys: list[AuthKeyConfig] = Field(default_factory=list)


class RateLimitConfig(BaseModel):
    enabled: bool = False
    requests_per_minute: int = 120
    burst: int = 60


class ResilienceConfig(BaseModel):
    request_timeout_seconds: float = 120.0
    max_retries: int = 2
    backoff_seconds: float = 0.5


class RLMRuntimeConfig(BaseModel):
    name: str
    environment: str = "docker"
    max_iterations: int = 10
    max_depth: int = 2


class ModelEndpointConfig(BaseModel):
    provider: str = "ollama"
    base_url: str
    model: str
    api_key: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class ModelCatalog(BaseModel):
    generator: ModelEndpointConfig
    tool_compiler: ModelEndpointConfig
    code_interpreter: ModelEndpointConfig | None = None
    vision: ModelEndpointConfig | None = None


class RLMConfig(BaseModel):
    rants_one: RLMRuntimeConfig

    def list_models(self) -> list[RLMRuntimeConfig]:
        return [self.rants_one]


class StateConfig(BaseModel):
    sqlite_path: str = "/work/rants.sqlite"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RANTS_", env_nested_delimiter="__")

    server: ServerConfig = Field(default_factory=ServerConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    rate_limits: RateLimitConfig = Field(default_factory=RateLimitConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    rlm: RLMConfig
    models: ModelCatalog
    state: StateConfig = Field(default_factory=StateConfig)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    data: dict[str, Any] = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}
    data.setdefault("state", {})
    data["state"]["sqlite_path"] = os.environ.get(
        "RANTS_STATE__SQLITE_PATH",
        data["state"].get("sqlite_path", "/work/rants.sqlite"),
    )
    return AppConfig.model_validate(data)

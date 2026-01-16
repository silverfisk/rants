from __future__ import annotations

from pathlib import Path
from typing import Any

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


class RLMConfig(BaseModel):
    environment: str = "docker"
    max_iterations: int = 10
    max_depth: int = 2


class ModelEndpointConfig(BaseModel):
    base_url: str
    temperature: float = 0.2
    model: str
    api_key: str | None = None


class ModelsConfig(BaseModel):
    generator: ModelEndpointConfig
    tool_compiler: ModelEndpointConfig


class StateConfig(BaseModel):
    sqlite_path: str = "/work/rants.sqlite"


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RANTS_", env_nested_delimiter="__")

    server: ServerConfig = Field(default_factory=ServerConfig)
    limits: LimitsConfig = Field(default_factory=LimitsConfig)
    rlm: RLMConfig = Field(default_factory=RLMConfig)
    models: ModelsConfig
    state: StateConfig = Field(default_factory=StateConfig)


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    data: dict[str, Any] = {}
    if config_path.exists():
        data = yaml.safe_load(config_path.read_text()) or {}
    return AppConfig.model_validate(data)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from gateway.models.types import ToolSchema


Executor = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class ToolDefinition:
    name: str
    description: str
    schema: dict[str, Any]
    executor: Executor


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> ToolDefinition | None:
        return self._tools.get(name)

    def schemas(self) -> list[ToolSchema]:
        return [ToolSchema(name=tool.name, description=tool.description, schema=tool.schema) for tool in self._tools.values()]

    def tool_names(self) -> list[str]:
        return list(self._tools.keys())

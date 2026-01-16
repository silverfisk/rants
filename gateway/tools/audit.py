from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from gateway.state.sqlite_store import SQLiteStore


@dataclass(frozen=True)
class AuditEntry:
    tenant_id: str
    response_id: str
    tool_calls: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]

    def to_json(self) -> str:
        payload = {
            "tenant_id": self.tenant_id,
            "response_id": self.response_id,
            "tool_calls": self.tool_calls,
            "tool_results": self.tool_results,
            "timestamp": time.time(),
        }
        return json.dumps(payload)


class AuditLogger:
    def __init__(self, store: SQLiteStore) -> None:
        self.store = store

    async def log_tool_activity(
        self,
        tenant_id: str,
        response_id: str,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> None:
        if not tool_calls and not tool_results:
            return
        entry = AuditEntry(
            tenant_id=tenant_id,
            response_id=response_id,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )
        await self.store.store_audit_entry(entry.to_json())

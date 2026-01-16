from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import aiosqlite

from gateway.models.types import CanonicalTranscript, RecursiveSession


@dataclass
class StoredResponse:
    response_id: str
    session_id: str
    parent_response_id: Optional[str]
    transcript: CanonicalTranscript


class SQLiteStore:
    def __init__(self, path: str) -> None:
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    async def initialize(self) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    parent_id TEXT,
                    depth INTEGER,
                    transcript_json TEXT NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS responses (
                    response_id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    parent_response_id TEXT,
                    tenant_id TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    transcript_json TEXT NOT NULL
                )
                """
            )
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at REAL NOT NULL,
                    entry_json TEXT NOT NULL
                )
                """
            )
            await self._ensure_tenant_column(conn)
            await conn.commit()

    async def _ensure_tenant_column(self, conn: aiosqlite.Connection) -> None:
        cursor = await conn.execute("PRAGMA table_info(responses)")
        columns = [row[1] async for row in cursor]
        if "tenant_id" not in columns:
            await conn.execute("ALTER TABLE responses ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'default'")

    async def create_session(self, transcript: CanonicalTranscript, depth: int, parent_id: str | None) -> RecursiveSession:
        session_id = uuid.uuid4().hex
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                "INSERT INTO sessions(session_id, parent_id, depth, transcript_json) VALUES (?, ?, ?, ?)",
                (session_id, parent_id, depth, transcript.model_dump_json()),
            )
            await conn.commit()
        return RecursiveSession(
            session_id=session_id,
            parent_id=parent_id,
            transcript=transcript,
            depth=depth,
            environment={},
        )

    async def update_session(self, session: RecursiveSession) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                "UPDATE sessions SET transcript_json = ? WHERE session_id = ?",
                (session.transcript.model_dump_json(), session.session_id),
            )
            await conn.commit()

    async def store_response(
        self,
        response_id: str,
        transcript: CanonicalTranscript,
        parent_response_id: str | None,
        tenant_id: str,
    ) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                "INSERT INTO responses(response_id, session_id, parent_response_id, tenant_id, created_at, transcript_json)"
                " VALUES (?, ?, ?, ?, strftime('%s','now'), ?)",
                (response_id, "", parent_response_id, tenant_id, transcript.model_dump_json()),
            )
            await conn.commit()

    async def store_audit_entry(self, entry_json: str) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                "INSERT INTO audit_log(created_at, entry_json) VALUES (strftime('%s','now'), ?)",
                (entry_json,),
            )
            await conn.commit()

    async def load_response_transcript(
        self,
        response_id: str,
        tenant_id: str,
    ) -> CanonicalTranscript | None:
        async with aiosqlite.connect(self.path) as conn:
            cursor = await conn.execute(
                "SELECT transcript_json FROM responses WHERE response_id = ? AND tenant_id = ?",
                (response_id, tenant_id),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        return CanonicalTranscript.model_validate_json(row[0])

    async def load_session(self, session_id: str) -> RecursiveSession | None:
        async with aiosqlite.connect(self.path) as conn:
            cursor = await conn.execute(
                "SELECT parent_id, depth, transcript_json FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = await cursor.fetchone()
        if not row:
            return None
        parent_id, depth, transcript_json = row
        transcript = CanonicalTranscript.model_validate_json(transcript_json)
        return RecursiveSession(
            session_id=session_id,
            parent_id=parent_id,
            transcript=transcript,
            depth=depth,
            environment={},
        )

    async def delete_response(self, response_id: str, tenant_id: str) -> None:
        async with aiosqlite.connect(self.path) as conn:
            await conn.execute(
                "DELETE FROM responses WHERE response_id = ? AND tenant_id = ?",
                (response_id, tenant_id),
            )
            await conn.commit()

    async def new_response_id(self) -> str:
        return f"resp_{uuid.uuid4().hex}"

    async def load_previous_transcript(
        self,
        previous_response_id: str | None,
        tenant_id: str,
    ) -> CanonicalTranscript | None:
        if not previous_response_id:
            return None
        return await self.load_response_transcript(previous_response_id, tenant_id)

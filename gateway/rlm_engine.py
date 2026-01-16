from __future__ import annotations

import hashlib
from typing import Any

from gateway.config import AppConfig
from gateway.models.openai_client import OpenAIClient
from gateway.models.types import CanonicalStep, CanonicalTranscript, RLMOutput


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value)


def _extract_output_text(response: dict[str, Any]) -> str:
    output = response.get("output", [])
    for item in output:
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""


class RLMEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def _build_system_prompt(self) -> str:
        return (
            "You are a generator model for the RANTS gateway. "
            "Respond with user-facing text only. If a tool should be used, append a line: "
            "TOOL_INTENT: <plain English>. Never output JSON or code for tools."
        )

    def _tool_schema_digest(self, tool_schemas: list[dict[str, Any]]) -> str:
        serialized = str(sorted(tool_schemas, key=lambda item: item.get("name", "")))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def parse_output(self, text: str) -> RLMOutput:
        tool_intent = None
        output = text
        if "TOOL_INTENT:" in text:
            parts = text.split("TOOL_INTENT:")
            output = parts[0].rstrip()
            tool_intent = parts[-1].strip()
        return RLMOutput(text=output, tool_intent=tool_intent or None)

    async def generate(self, transcript: CanonicalTranscript) -> RLMOutput:
        client = OpenAIClient(
            self.config.models.generator.base_url,
            api_key=self.config.models.generator.api_key,
        )
        payload = {
            "model": self.config.models.generator.model,
            "temperature": self.config.models.generator.temperature,
            "input": json_dumps(
                {
                    "system": self._build_system_prompt(),
                    "transcript": transcript.model_dump(),
                }
            ),
        }
        response = await client.post_json("/responses", payload)
        text = _extract_output_text(response.data)
        return self.parse_output(text)

    async def initialize_transcript(
        self,
        system: str | None,
        user: str,
        tool_schemas: list[dict[str, Any]],
    ) -> CanonicalTranscript:
        digest = self._tool_schema_digest(tool_schemas)
        return CanonicalTranscript(system=system, user=user, tool_schema_digest=digest, steps=[])

    async def append_step(
        self,
        transcript: CanonicalTranscript,
        output: RLMOutput,
        tool_calls: list[dict[str, Any]],
        tool_results: list[dict[str, Any]],
    ) -> None:
        step = CanonicalStep(
            generator_output=output.text,
            tool_intent=output.tool_intent,
            tool_calls=tool_calls,
            tool_results=tool_results,
        )
        transcript.steps.append(step)



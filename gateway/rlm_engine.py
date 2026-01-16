from __future__ import annotations

import hashlib
from typing import Any

from gateway.config import AppConfig, ModelEndpointConfig
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

    def _select_generator(self, transcript: CanonicalTranscript) -> ModelEndpointConfig:
        if self._has_vision_inputs(transcript) and self.config.models.vision:
            return self.config.models.vision
        if self.config.models.code_interpreter and "code" in self.config.models.code_interpreter.capabilities:
            return self.config.models.code_interpreter
        return self.config.models.generator

    def _has_vision_inputs(self, transcript: CanonicalTranscript) -> bool:
        user_text = transcript.user.lower()
        if "image" in user_text or "img" in user_text:
            return True
        for step in transcript.steps:
            if "image" in step.generator_output.lower():
                return True
        return False

    async def generate(self, transcript: CanonicalTranscript) -> RLMOutput:
        selected = self._select_generator(transcript)
        client = OpenAIClient(
            selected.base_url,
            api_key=selected.api_key,
            timeout=self.config.resilience.request_timeout_seconds,
            max_retries=self.config.resilience.max_retries,
            backoff_seconds=self.config.resilience.backoff_seconds,
        )
        payload = {
            "model": selected.model,
            "input": json_dumps(
                {
                    "system": self._build_system_prompt(),
                    "transcript": transcript.model_dump(),
                }
            ),
        }
        if selected.parameters:
            payload.update(selected.parameters)
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



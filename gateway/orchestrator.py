from __future__ import annotations

import json
import time
from typing import Any, AsyncGenerator

from gateway.config import AppConfig
from gateway.models.types import (
    CanonicalTranscript,
    OutputMessage,
    OutputTextContent,
    ResponseEvent,
    ResponseObject,
    ResponseStatus,
    ToolExecutionResult,
)
from gateway.rlm_engine import RLMEngine
from gateway.state.sqlite_store import SQLiteStore
from gateway.tools.executors import create_default_registry
from gateway.tools.audit import AuditLogger


class Orchestrator:
    def __init__(self, config: AppConfig, store: SQLiteStore, tenant_id: str) -> None:
        self.config = config
        self.store = store
        self.tenant_id = tenant_id
        self.engine = RLMEngine(config)
        self.registry = create_default_registry(config)
        self.audit = AuditLogger(store)

    async def run_response(
        self,
        model: str,
        input_text: str,
        tools: list[dict[str, Any]],
        tool_choice: str | dict[str, Any],
        previous_response_id: str | None,
        stream: bool,
        execute_tools: bool = True,
    ) -> tuple[ResponseObject, CanonicalTranscript]:
        tool_schemas = tools or [schema.model_dump() for schema in self.registry.schemas()]
        transcript = await self._build_transcript(input_text, tool_schemas, previous_response_id)

        start = time.time()
        status = ResponseStatus.IN_PROGRESS
        output_message = OutputMessage(
            id=f"msg_{int(start)}",
            status="in_progress",
            content=[OutputTextContent(text="")],
        )

        response = ResponseObject(
            id=await self.store.new_response_id(),
            created_at=start,
            status=status,
            model=model,
            output=[output_message],
            temperature=self.config.models.generator.parameters.get("temperature"),
            tool_choice=tool_choice,
            tools=tool_schemas,
            previous_response_id=previous_response_id,
            user=self.tenant_id,
        )

        max_iterations = self.config.limits.max_tool_iterations
        iterations = 0
        while iterations < max_iterations:
            output = await self.engine.generate(transcript)
            output_message.content[0].text += output.text
            tool_calls = []
            tool_results = []

            if output.tool_intent:
                tool_calls = await self._compile_tools(transcript, tool_schemas, output.tool_intent)
                if execute_tools:
                    tool_results = await self._execute_tools(transcript, tool_calls)

            await self.engine.append_step(transcript, output, tool_calls, tool_results)
            await self.audit.log_tool_activity(
                tenant_id=self.tenant_id,
                response_id=response.id,
                tool_calls=tool_calls,
                tool_results=tool_results,
            )

            if not output.tool_intent:
                break
            if not execute_tools:
                break
            iterations += 1

        response.status = ResponseStatus.COMPLETED
        response.completed_at = time.time()
        response.output[0].status = "completed"
        await self.store.store_response(
            response.id,
            transcript,
            previous_response_id,
            tenant_id=self.tenant_id,
        )
        return response, transcript

    async def stream_response(
        self,
        response: ResponseObject,
        transcript: CanonicalTranscript,
    ) -> AsyncGenerator[ResponseEvent, None]:
        sequence = 0
        yield ResponseEvent(type="response.created", sequence_number=sequence, response=response)
        sequence += 1

        output_item = response.output[0]
        content = output_item.content[0]
        start_index = 0
        for chunk in _chunk_text(content.text):
            yield ResponseEvent(
                type="response.output_text.delta",
                sequence_number=sequence,
                output_index=0,
                item_id=output_item.id,
                content_index=0,
                delta=chunk,
                logprobs=[],
            )
            sequence += 1
            start_index += len(chunk)

        yield ResponseEvent(
            type="response.output_text.done",
            sequence_number=sequence,
            output_index=0,
            item_id=output_item.id,
            content_index=0,
            text=content.text,
            logprobs=[],
        )
        sequence += 1

        yield ResponseEvent(type="response.completed", sequence_number=sequence, response=response)

    async def _compile_tools(
        self,
        transcript: CanonicalTranscript,
        tool_schemas: list[dict[str, Any]],
        tool_intent: str,
    ) -> list[dict[str, Any]]:
        from gateway.models.openai_client import OpenAIClient

        tool_compiler = self.config.models.tool_compiler
        payload = {
            "model": tool_compiler.model,
            "input": json.dumps(
                {
                    "tool_schemas": tool_schemas,
                    "transcript": transcript.model_dump(),
                    "tool_intent": tool_intent,
                }
            ),
        }
        if tool_compiler.parameters:
            payload.update(tool_compiler.parameters)

        if "tool_compilation" not in tool_compiler.capabilities:
            raise ValueError("Tool compiler missing tool_compilation capability")
        client = OpenAIClient(
            tool_compiler.base_url,
            api_key=tool_compiler.api_key,
            timeout=self.config.resilience.request_timeout_seconds,
            max_retries=self.config.resilience.max_retries,
            backoff_seconds=self.config.resilience.backoff_seconds,
        )
        response = await client.post_json("/responses", payload)
        text = _extract_output_text(response.data).strip()

        if not text:
            raise ValueError("Tool compiler returned empty tool_calls payload")

        parsed = _parse_tool_compiler_output(text)
        if parsed is not None:
            return parsed

        raise ValueError("Tool compiler returned unparseable tool_calls payload")

    async def _execute_tools(
        self,
        transcript: CanonicalTranscript,
        tool_calls: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for call in tool_calls:
            tool_name = call.get("tool")
            parameters = call.get("parameters", {})
            if not isinstance(tool_name, str):
                results.append(
                    ToolExecutionResult(
                        tool="unknown",
                        ok=False,
                        output={"error": "unknown tool"},
                    ).model_dump()
                )
                continue
            definition = self.registry.get(tool_name)
            if not definition:
                results.append(
                    ToolExecutionResult(
                        tool=tool_name,
                        ok=False,
                        output={"error": "unknown tool"},
                    ).model_dump()
                )
                continue
            if tool_name == "task":
                results.append(await self._execute_task(transcript, parameters))
                continue
            try:
                output = definition.executor(parameters)
                results.append(ToolExecutionResult(tool=tool_name, ok=True, output=output).model_dump())
            except Exception as exc:  # noqa: BLE001
                results.append(
                    ToolExecutionResult(
                        tool=tool_name,
                        ok=False,
                        output={"error": str(exc)},
                    ).model_dump()
                )
        return results

    async def _execute_task(
        self,
        transcript: CanonicalTranscript,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        if transcript and transcript.steps:
            if transcript.steps[-1].tool_intent:
                summary_input = transcript.steps[-1].tool_intent
            else:
                summary_input = transcript.steps[-1].generator_output
        else:
            summary_input = ""

        input_text = parameters.get("prompt") or parameters.get("description") or summary_input
        max_depth = int(self.config.limits.max_depth)
        depth = int(parameters.get("depth", 1))
        if depth >= max_depth:
            return ToolExecutionResult(
                tool="task",
                ok=False,
                output={"error": "max depth exceeded"},
            ).model_dump()

        child_transcript = await self.engine.initialize_transcript(None, input_text, [])
        output = await self.engine.generate(child_transcript)
        await self.engine.append_step(child_transcript, output, [], [])
        return ToolExecutionResult(
            tool="task",
            ok=True,
            output={"summary": output.text},
        ).model_dump()

    async def _build_transcript(
        self,
        input_text: str,
        tool_schemas: list[dict[str, Any]],
        previous_response_id: str | None,
    ) -> CanonicalTranscript:
        previous_transcript = await self.store.load_previous_transcript(previous_response_id, self.tenant_id)
        transcript = await self.engine.initialize_transcript(None, input_text, tool_schemas)
        if previous_transcript:
            transcript.steps = previous_transcript.steps
        return transcript



def _extract_output_text(response: dict[str, Any]) -> str:
    output = response.get("output", [])
    for item in output:
        if item.get("type") == "message":
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content.get("text", "")
    return ""


def _parse_tool_compiler_output(text: str) -> list[dict[str, Any]] | None:
    text = text.strip()

    try:
        compiled = json.loads(text)
    except json.JSONDecodeError:
        compiled = None

    if isinstance(compiled, dict):
        tool_calls = compiled.get("tool_calls")
        if isinstance(tool_calls, list):
            return [call for call in tool_calls if isinstance(call, dict)]

    parsed_calls = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue

        if line.startswith("<start_function_call>") and line.endswith("<end_function_call>"):
            inner = line.removeprefix("<start_function_call>").removesuffix("<end_function_call>")
            if inner.startswith("call:"):
                inner = inner.removeprefix("call:")
            name, separator, payload = inner.partition("{")
            if not separator:
                continue
            payload = "{" + payload
            if payload.endswith("}"):
                try:
                    parameters = json.loads(payload)
                except json.JSONDecodeError:
                    continue
            else:
                continue
            if isinstance(parameters, dict) and name:
                parsed_calls.append({"tool": name.strip(), "parameters": parameters})
            continue

        if line.startswith("{") and line.endswith("}"):
            continue

    if parsed_calls:
        return parsed_calls

    return None


def _chunk_text(text: str, chunk_size: int = 64) -> list[str]:
    return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]

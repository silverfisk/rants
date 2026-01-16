from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class CanonicalStep(BaseModel):
    generator_output: str
    tool_intent: Optional[str] = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_results: list[dict[str, Any]] = Field(default_factory=list)


class CanonicalTranscript(BaseModel):
    system: Optional[str] = None
    user: str
    tool_schema_digest: Optional[str] = None
    steps: list[CanonicalStep] = Field(default_factory=list)


class RecursiveSession(BaseModel):
    session_id: str
    parent_id: Optional[str] = None
    transcript: CanonicalTranscript
    depth: int
    environment: dict[str, Any] = Field(default_factory=dict)


class ToolSchema(BaseModel):
    name: str
    description: str
    schema: dict[str, Any]


class ToolCall(BaseModel):
    tool: str
    parameters: dict[str, Any]


class ToolExecutionResult(BaseModel):
    tool: str
    ok: bool
    output: dict[str, Any]


class RLMOutput(BaseModel):
    text: str
    tool_intent: Optional[str] = None


class ResponseStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    IN_PROGRESS = "in_progress"
    CANCELLED = "cancelled"
    QUEUED = "queued"
    INCOMPLETE = "incomplete"


class ResponseError(BaseModel):
    code: str
    message: str
    type: str = "server_error"


class ResponseUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    output_tokens_details: dict[str, int] = Field(default_factory=dict)
    input_tokens_details: dict[str, int] = Field(default_factory=dict)


class OutputTextContent(BaseModel):
    type: Literal["output_text"] = "output_text"
    text: str
    annotations: list[dict[str, Any]] = Field(default_factory=list)


class OutputMessage(BaseModel):
    type: Literal["message"] = "message"
    id: str
    status: Literal["completed", "in_progress"]
    role: Literal["assistant"] = "assistant"
    content: list[OutputTextContent]


class ResponseObject(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str
    object: Literal["response"] = "response"
    created_at: float
    status: ResponseStatus
    error: Optional[ResponseError] = None
    incomplete_details: Optional[dict[str, Any]] = None
    instructions: Optional[str] = None
    max_output_tokens: Optional[int] = None
    model: str
    output: list[OutputMessage]
    parallel_tool_calls: bool = True
    previous_response_id: Optional[str] = None
    reasoning: Optional[dict[str, Any]] = None
    store: bool = True
    temperature: Optional[float] = None
    text: dict[str, Any] = Field(default_factory=lambda: {"format": {"type": "text"}})
    tool_choice: str | dict[str, Any] = "auto"
    tools: list[dict[str, Any]] = Field(default_factory=list)
    top_p: Optional[float] = None
    truncation: str = "disabled"
    usage: Optional[ResponseUsage] = None
    user: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResponseEvent(BaseModel):
    type: str
    sequence_number: int
    response: Optional[ResponseObject] = None
    item_id: Optional[str] = None
    output_index: Optional[int] = None
    content_index: Optional[int] = None
    delta: Optional[str] = None
    text: Optional[str] = None
    logprobs: list[dict[str, Any]] = Field(default_factory=list)


class ResponseRequest(BaseModel):
    model: str | None = None
    input: str | list[dict[str, Any]]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    tool_choice: str | dict[str, Any] = "auto"
    stream: bool = False
    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    previous_response_id: Optional[str] = None
    user: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[dict[str, Any]]
    stream: bool = False
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None

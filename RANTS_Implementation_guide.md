# RANTS: RANTS Are Not Toolsystems

## Purpose

RANTS is an **OpenAI-compatible inference gateway** that implements **Recursive Language Models (RLMs)** as a *context-centric inference strategy*. From the perspective of clients, RANTS behaves like a standard OpenAI API (Responses + Chat Completions). Internally, it enables language models to recursively inspect, decompose, and transform long contexts using isolated sub-inference calls, while keeping **tool execution deterministic and gateway-owned**.

This document is a **complete, implementable specification** for RANTS.

---

## Design principles

1. **Context-centric, not task-centric**

   * Decomposition decisions belong to the model, not hard-coded workflows.
   * The gateway provides an environment, not a plan.

2. **RANTS are not toolsystems**

   * Tools are infrastructure, not reasoning primitives.
   * The model never emits tool JSON directly.

3. **Recursive Language Models (RLMs)**

   * The generator may spawn recursive sub-calls over transformed context views.
   * From the client POV, this is still a single model call.

4. **Gateway-owned determinism**

   * Tool calls are compiled, validated, and executed by the gateway.
   * A dedicated compiler model is used for schema correctness.

5. **OpenAI compatibility first**

   * `/v1/responses` is the primary API.
   * `/v1/chat/completions` is a strict compatibility shim.

6. **No visible reasoning**

   * No chain-of-thought, no hidden traces, no REPL output in responses.

---

## High-level architecture

### Services (Docker Compose recommended)

1. **gateway**

   * FastAPI service
   * Owns streaming, state, tool execution, recursion limits
   * Hosts the RLM engine

2. **generator backend**

   * OpenAI-compatible inference endpoint (vLLM, OpenAI, etc.)
   * Used *only* for language generation

3. **tool compiler backend**

   * Small deterministic model (e.g. functiongemma)
   * Converts plain-English tool intent into strict JSON tool calls

Only the gateway is exposed publicly.

---

## Core abstraction: Recursive Session

Every request is handled inside a **RecursiveSession**.

```python
class RecursiveSession:
    session_id: str
    parent_id: Optional[str]
    transcript: CanonicalTranscript
    depth: int
    environment: RLMEnvironment
```

* Root requests create a root session.
* Recursive calls (`task`) create child sessions.
* Each session has:

  * isolated transcript
  * isolated RLM environment
  * strict depth and wallclock limits

---

## Canonical transcript format

The gateway stores all state explicitly.

```json
{
  "system": "optional system prompt",
  "user": "initial user input",
  "tool_schema_digest": "sha256",
  "steps": [
    {
      "generator_output": "assistant text chunk",
      "tool_intent": "plain English or null",
      "tool_calls": [...],
      "tool_results": [...]
    }
  ]
}
```

This transcript is the **context C** in the RLM formulation.

---

## RLM engine integration

### Role of RLM in RANTS

RLM is used **only** as the generator layer.

Responsibilities of the RLM:

* Inspect and transform the transcript
* Partition long context
* Spawn recursive sub-inference over subsets
* Decide whether tools are needed

Responsibilities *not* given to the RLM:

* Tool execution
* Tool JSON generation
* Streaming protocol
* Safety enforcement

### RLM configuration

Default configuration:

```python
RLM(
  backend="openai-compatible",
  environment="docker",
  max_iterations=10,
  max_depth=2,
  verbose=False
)
```

* `environment=docker` is the production default
* `max_iterations` limits REPL loops
* `max_depth` limits recursion

---

## Generator contract (RLM output)

The gateway enforces a **strict output contract** on the generator.

The generator must:

* Emit **user-facing text only**
* Optionally end with **one** line:

```
TOOL_INTENT: <plain English description>
```

The generator must never:

* Emit JSON tool calls
* Emit reasoning or analysis
* Emit code blocks intended for execution

Tool intent is **not streamed to clients**.

---

## Tool system

### Philosophy

* Tools are side-effectful infrastructure.
* The model describes *intent*, never execution details.

### Tool compiler

A separate model converts tool intent into JSON:

Input:

* tool schemas
* compact transcript
* plain-English tool intent

Output:

```json
{"tool_calls": [{"tool": "bash", "parameters": {...}}]}
```

Rules:

* Temperature 0
* Strict JSON only
* One repair attempt on validation failure

---

## Tool registry

Implement the following tools exactly:

* bash
* read
* write
* edit
* multiedit
* patch
* ls
* glob
* grep
* webfetch
* websearch
* codesearch
* todo_read
* todo_write
* task
* skill
* batch
* invalid

Each tool has:

* name
* description
* JSON schema
* executor(params) -> structured result

---

## The `task` tool (recursive execution)

`task` is the **RLM recursion primitive**.

Execution semantics:

1. Create a child RecursiveSession
2. Run the full RLM + tool loop in that session
3. Summarize the final result
4. Return summary to parent session

Rules:

* Depth limited by `max_depth`
* Wallclock budget enforced globally

---

## Gateway-owned inference loop

For each RecursiveSession:

1. Normalize input into canonical transcript
2. Run RLM completion over transcript
3. Stream user-facing text
4. Extract TOOL_INTENT if present
5. If no tool intent → done
6. Compile tool calls via tool compiler
7. Validate against JSON schema
8. Execute tools
9. Append results to transcript
10. Repeat until stop condition

Stop conditions:

* No TOOL_INTENT
* Max tool iterations reached
* Max wallclock exceeded

---

## API surface

### POST /v1/responses (primary)

Supported fields:

* model
* input
* tools
* tool_choice
* stream
* max_output_tokens
* temperature
* previous_response_id

Unknown fields must be ignored.

#### Streaming (SSE)

Events (minimum):

1. response.created
2. response.output_text.delta (0..n)
3. response.output_text.done
4. response.completed

Rules:

* No reasoning events
* No tool JSON in text

---

### POST /v1/chat/completions (shim)

* Translate chat messages → Responses input
* Reuse the same RLM pipeline
* Stream back ChatCompletion-compatible deltas

---

### GET /v1/models

Return static list from config.

---

### GET /health

Return:

* gateway version
* backend reachability

---

## State management

* Each response has a UUID
* SQLite used for transcript storage
* Lookup supported via `previous_response_id`
* Responses are scoped by tenant ID
* Tool execution audit entries are stored for tracing

---

## Security and sandboxing

* API requests can require API keys
* API keys map to tenant IDs for isolation
* All tools execute inside gateway container
* Workspace root enforced (e.g. /work)
* No filesystem access outside workspace
* Webfetch size capped (e.g. 5 MB)
* Tool output truncated uniformly
* Rate limiting is enforced per tenant
* Tool execution is logged to an audit table

---

## Resilience and rate limits

* Generator/tool compiler requests use timeouts
* Retry with exponential backoff on transient failures
* Gateway rejects requests that exceed rate limits
* Backends are treated as swappable providers

---

## Configuration

Use a single `config.yaml`:

```yaml
server:
  host: 0.0.0.0
  port: 8000

limits:
  max_tool_iterations: 6
  max_wallclock_seconds: 120

rlm:
  rants_one:
    name: rants_one_name
    environment: docker
    max_iterations: 10
    max_depth: 2

models:
  generator:
    provider: ollama
    base_url: http://generator:11434/v1
    model: devstral-small-tu:latest
    capabilities:
      - reasoning
      - text
    parameters:
      temperature: 0.7
      max_tokens: 94000

  tool_compiler:
    provider: ollama
    base_url: http://tool_compiler:11434/v1
    model: functiongemma:latest
    capabilities:
      - tool_compilation
    parameters:
      temperature: 0.0

  vision:
    provider: ollama
    base_url: http://generator:11434/v1
    model: qwen3-vl:8b
    capabilities:
      - vision
    parameters: {}

auth:
  enabled: false
  api_keys: []

rate_limits:
  enabled: false
  requests_per_minute: 120
  burst: 60

resilience:
  request_timeout_seconds: 120.0
  max_retries: 2
  backoff_seconds: 0.5
```

---

## Internal module layout

```
/gateway
  app.py
  responses.py
  chat_shim.py
  orchestrator.py
  rlm_engine.py
  security.py
  tools/
    registry.py
    executors.py
    audit.py
  models/
    openai_client.py
  state/
    sqlite_store.py
```

---

## Done definition

RANTS is complete when:

1. `/v1/responses` works with streaming
2. Recursive `task` calls execute correctly
3. Tools execute deterministically via compiler
4. No reasoning text is ever exposed
5. Long-context queries outperform flat calls on hard benchmarks

---

## Summary

RANTS is a **Recursive Language Model gateway**, not an agent framework.

* Recursion belongs to the model
* Execution belongs to the gateway
* Compatibility belongs to the API

This separation is the core of the system.

# RANTS: RANTS Are Not Toolsystems.

RANTS is an RLM runtime.
It implements Recursive Language Models by providing a thin execution environment around a base language model.
The first reference client is opencode.

## Stack
- Python 3.13
- uv for dependency and environment management

## Design
- See `RANTS_Implementation_guide.md` for the design and implementation plan.
- Clients see a single RLM model; backends are internal.

## Architecture
RANTS exposes an OpenAI-compatible `/v1` API (`/v1/responses` + `/v1/chat/completions`).
From the client perspective it behaves like a single model (`rants_one_name`), but internally the
gateway runs an RLM-style inference loop that can:
- Persist the canonical transcript ("context C")
- Delegate to specialized internal model backends (generator, code interpreter, vision)
- Compile tool intent into schema-valid tool calls via a dedicated tool compiler model
- Execute gateway-owned internal tools (RLM environment)
- Recurse when needed (`task`)

The gateway never calls its own `/v1` API internally; it talks directly to configured model providers
via their `base_url` settings.

```mermaid
flowchart LR
  OC[opencode<br/>(agent runtime)] -->|POST /v1/chat/completions| GW[RANTS Gateway<br/>FastAPI /v1]
  GW -->|assistant text<br/>+ tool_calls (optional)| OC
  OC -->|exec local tools<br/>(bash/read/edit/...)| WORK[(Project workspace)]
  OC -->|tool results<br/>(role=tool)| GW

  GW --> ORCH

  subgraph RLM[RLM runtime inside gateway]
    ORCH[Orchestrator<br/>(RLM loop)] <--> STATE[(SQLite transcript store)]

    ORCH -->|generation| GEN[Generator model]
    ORCH -->|code tasks| CODE[Code interpreter model]
    ORCH -->|vision tasks| VISION[Vision model]

    ORCH -->|TOOL_INTENT| TC[Tool compiler model]
    TC -->|JSON tool_calls| ORCH

    ORCH -->|/v1/responses mode:<br/>execute internal tools| TOOLRT[Gateway tool runtime]
    ORCH -->|task recursion| ORCH
  end
```

Notes:
- opencode's tools (editing files, running local commands, etc.) are executed by opencode on the
  client machine. These are distinct from the internal "RLM tools" described in the RLM paper.
- `/v1/responses` is the primary API and runs the full gateway-owned loop (including tool execution).
- `/v1/chat/completions` is a compatibility shim (used by opencode) that can return OpenAI-style
  `tool_calls` so opencode can run its local tools.

## Quick Start
- `uv venv` then `uv sync`
- `uv run uvicorn gateway.app:app --reload`

## Configuration
- Default config: `config.yaml`
- SQLite state path: `RANTS_STATE__SQLITE_PATH`
- RLM model name: `RANTS_RLM__RANTS_ONE__NAME`
- Generator endpoint: `RANTS_MODELS__GENERATOR__BASE_URL`
- Tool compiler endpoint: `RANTS_MODELS__TOOL_COMPILER__BASE_URL`
- Provider name: `RANTS_MODELS__GENERATOR__PROVIDER`
- Auth enabled: `RANTS_AUTH__ENABLED`
- API keys: `RANTS_AUTH__API_KEYS__0__KEY`
- Tenant IDs: `RANTS_AUTH__API_KEYS__0__TENANT_ID`
- Rate limit toggle: `RANTS_RATE_LIMITS__ENABLED`
- Retry timeout: `RANTS_RESILIENCE__REQUEST_TIMEOUT_SECONDS`

## Docker
- `docker build -t rants-gateway .`
- `docker run -p 8000:8000 -v $(pwd)/config.yaml:/app/config.yaml -v $(pwd)/work:/work rants-gateway`
- `docker compose up`
- Docker services are reference backends only; swap providers as needed.

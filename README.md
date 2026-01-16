# RANTS: RANTS Are Not Toolsystems.

RANTS is an RLM runtime.
It implements Recursive Language Models by providing a thin execution environment around a base language model.
The first reference client is opencode.

## Stack
- Python 3.13
- uv for dependency and environment management

## Design
- See `RANTS_Implementation_guide.md` for the design and implementation plan.

## Quick Start
- `uv venv` then `uv sync`
- `uv run uvicorn gateway.app:app --reload`

## Configuration
- Default config: `config.yaml`
- SQLite state path: `RANTS_STATE__SQLITE_PATH`
- Generator endpoint: `RANTS_MODELS__GENERATOR__BASE_URL`
- Tool compiler endpoint: `RANTS_MODELS__TOOL_COMPILER__BASE_URL`

## Docker
- `docker build -t rants-gateway .`
- `docker run -p 8000:8000 -v $(pwd)/config.yaml:/app/config.yaml -v $(pwd)/work:/work rants-gateway`
- `docker compose up`

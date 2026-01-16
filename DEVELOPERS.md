# Developers

## Setup
- `uv venv`
- `uv sync`

## Tests
- `RANTS_STATE__SQLITE_PATH=./work/rants.sqlite uv run behave`
- If using `/work` in Docker, keep `config.yaml` as-is.

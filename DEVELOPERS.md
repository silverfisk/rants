# Developers

## Setup
- `uv venv`
- `uv sync`

## Tests
- `RANTS_STATE__SQLITE_PATH=./work/rants.sqlite uv run behave`
- Run `RANTS_STATE__SQLITE_PATH=./work/rants.sqlite uv run behave -t @contract` to validate response schemas.
- If using `/work` in Docker, keep `config.yaml` as-is.

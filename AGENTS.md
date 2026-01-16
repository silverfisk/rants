# AGENTS: RANTS Repository Guidelines

## Scope
- Applies to the entire repository unless superseded.
- This repo currently contains design/spec documentation only.
- When code is added, follow these guidelines unless updated.

## Sources Checked
- `README.md`
- `RANTS_Implementation_guide.md`
- `.cursor/rules/**` (none found)
- `.cursorrules` (none found)
- `.github/copilot-instructions.md` (none found)

## Build / Lint / Test Commands
> No build, lint, or test commands are defined yet.
> Prefer updating this section when tooling is added.

### Environment Setup
- Python version: **3.13** (from `README.md`).
- Dependency manager: **uv** (from `README.md`).
- Recommended workflow (when a `pyproject.toml` exists):
  - `uv venv` to create a virtualenv.
  - `uv sync` to install dependencies.
  - `uv run <cmd>` to execute tools.

### Build
- Not defined.
- If a build step is introduced, document it here.

### Lint
- Not defined.
- If a linter is added (e.g., `ruff`), document:
  - `uv run ruff check .`
  - Single-file lint: `uv run ruff check path/to/file.py`

### Format
- Not defined.
- If a formatter is added (e.g., `black`), document:
  - `uv run black .`
  - Single-file format: `uv run black path/to/file.py`

### Test
- `RANTS_STATE__SQLITE_PATH=./work/rants.sqlite uv run behave`

## Code Style Guidelines
> These are repository defaults until codebase-specific
> conventions or tools are introduced.

### General
- Favor clear, explicit code over clever shortcuts.
- Keep functions small and single-purpose.
- Prefer composition over deep inheritance.
- Keep modules focused; avoid circular imports.
- Add docstrings only when behavior is non-obvious.

### Python Version & Compatibility
- Target Python **3.13** features where appropriate.
- Avoid backport compatibility shims.

### Imports
- Use absolute imports within the project.
- Order imports: standard library, third-party, local.
- Group import blocks with a single blank line.
- Avoid unused imports; remove them immediately.

### Formatting
- Follow PEP 8 style conventions.
- Keep line length reasonable (target 88–100 chars).
- Use trailing commas in multi-line literals.
- Prefer single quotes for simple strings unless
  double quotes improve readability.
- Avoid trailing whitespace; end files with newline.

### Types
- Use type hints for public functions and methods.
- Prefer `typing` aliases for complex types.
- Use `Optional[T]` only when `None` is valid.
- Avoid `Any` unless strictly required.
- Keep return types explicit for clarity.

### Naming Conventions
- Modules: `snake_case.py`.
- Classes: `PascalCase`.
- Functions/variables: `snake_case`.
- Constants: `UPPER_SNAKE_CASE`.
- Use descriptive names; avoid single-letter names
  except in tight local scopes (e.g., indices).

### Error Handling
- Raise specific exceptions; avoid bare `except`.
- Prefer `ValueError`, `TypeError`, or custom
  domain exceptions over generic `Exception`.
- Include actionable context in error messages.
- Use `try/except` sparingly and narrowly.

### Logging
- Use the standard `logging` module.
- Prefer structured, informative messages.
- Avoid printing in library code.

### Data Structures
- Use `dataclasses` for simple data containers.
- Prefer `Enum` for fixed-choice values.
- Avoid large mutable default arguments.

### API & HTTP Conventions (when implemented)
- Keep handlers thin; push logic to services.
- Validate input early and consistently.
- Return explicit error responses with
  stable schemas.

### Testing Style (when tests exist)
- Name tests `test_*.py` and functions `test_*`.
- Favor small, focused tests over large fixtures.
- Use explicit fixtures for shared setup.
- Avoid inter-test dependencies.

## Documentation
- Update `README.md` when CLI or services change.
- Keep `RANTS_Implementation_guide.md` as the
  source of truth for architecture.

## Cursor/Copilot Rules
- No `.cursor/rules/` files found.
- No `.cursorrules` file found.
- No `.github/copilot-instructions.md` found.

## Agent Behavior
- Prefer minimal diffs and targeted changes.
- Do not introduce new tooling without request.
- Keep edits consistent with any existing style.
- Document new commands in this file.

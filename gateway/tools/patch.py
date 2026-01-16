from __future__ import annotations

from typing import Any

from gateway.config import AppConfig
from gateway.tools.executors import _workspace_path


def apply_patch(patch_text: str, config: AppConfig) -> dict[str, Any]:
    lines = patch_text.splitlines()
    if not lines or not lines[0].startswith("*** Begin Patch"):
        raise ValueError("Invalid patch header")

    current_path: str | None = None
    buffer: list[str] = []
    results: list[dict[str, Any]] = []

    def flush() -> None:
        nonlocal buffer, current_path
        if current_path is None:
            return
        _apply_to_file(current_path, "\n".join(buffer), config)
        results.append({"file": current_path, "ok": True})
        buffer = []
        current_path = None

    for line in lines[1:]:
        if line.startswith("*** Update File:"):
            flush()
            current_path = line.replace("*** Update File:", "").strip()
        elif line.startswith("*** End Patch"):
            flush()
            break
        else:
            buffer.append(line)

    return {"results": results}


def _apply_to_file(path: str, patch_body: str, config: AppConfig) -> None:
    target = _workspace_path(config.limits.workspace_root, path)
    content = target.read_text()
    lines = content.splitlines()
    patch_lines = patch_body.splitlines()

    new_lines: list[str] = []
    index = 0
    patch_index = 0

    while patch_index < len(patch_lines):
        patch_line = patch_lines[patch_index]
        if patch_line.startswith("@@"):
            patch_index += 1
            continue
        if patch_line.startswith("+"):
            new_lines.append(patch_line[1:])
        elif patch_line.startswith("-"):
            index += 1
        else:
            if index < len(lines):
                new_lines.append(lines[index])
            index += 1
        patch_index += 1

    new_lines.extend(lines[index:])
    target.write_text("\n".join(new_lines) + "\n")

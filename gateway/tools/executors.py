from __future__ import annotations

import glob as globlib
import re
import subprocess
from pathlib import Path
from typing import Any

import httpx

from gateway.config import AppConfig
from gateway.tools.registry import ToolRegistry


def _truncate_output(value: str, max_bytes: int) -> str:
    data = value.encode("utf-8")
    if len(data) <= max_bytes:
        return value
    truncated = data[:max_bytes]
    return truncated.decode("utf-8", errors="ignore")


def _workspace_path(root: str, requested: str) -> Path:
    candidate = (Path(root) / requested).resolve()
    root_path = Path(root).resolve()
    if not str(candidate).startswith(str(root_path)):
        raise ValueError("Path escapes workspace root")
    return candidate


def exec_bash(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    command = params.get("command")
    if not command:
        raise ValueError("Missing command")
    timeout = params.get("timeout", 120000)
    workdir = params.get("workdir")
    cwd = None
    if workdir:
        cwd = str(_workspace_path(config.limits.workspace_root, workdir))
    result = subprocess.run(
        command,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout / 1000,
    )
    stdout = _truncate_output(result.stdout, config.limits.tool_output_max_bytes)
    stderr = _truncate_output(result.stderr, config.limits.tool_output_max_bytes)
    return {
        "exit_code": result.returncode,
        "stdout": stdout,
        "stderr": stderr,
    }


def exec_read(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    file_path = params.get("filePath")
    if not file_path:
        raise ValueError("Missing filePath")
    path = _workspace_path(config.limits.workspace_root, file_path)
    offset = int(params.get("offset", 0))
    limit = int(params.get("limit", 2000))
    lines = path.read_text().splitlines()
    chunk = lines[offset : offset + limit]
    output = "\n".join(f"{i + 1 + offset:05d}| {line}" for i, line in enumerate(chunk))
    return {"file": output}


def exec_write(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    file_path = params.get("filePath")
    content = params.get("content", "")
    if not file_path:
        raise ValueError("Missing filePath")
    path = _workspace_path(config.limits.workspace_root, file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return {"ok": True}


def exec_edit(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    file_path = params.get("filePath")
    old = params.get("oldString")
    new = params.get("newString")
    replace_all = bool(params.get("replaceAll", False))
    if not file_path or old is None or new is None:
        raise ValueError("Missing edit parameters")
    path = _workspace_path(config.limits.workspace_root, file_path)
    content = path.read_text()
    if replace_all:
        if old not in content:
            raise ValueError("oldString not found in content")
        content = content.replace(old, new)
    else:
        if content.count(old) != 1:
            raise ValueError("oldString must match exactly once")
        content = content.replace(old, new, 1)
    path.write_text(content)
    return {"ok": True}


def exec_multiedit(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    file_path = params.get("filePath")
    edits = params.get("edits", [])
    if not file_path or not isinstance(edits, list):
        raise ValueError("Missing edits")
    path = _workspace_path(config.limits.workspace_root, file_path)
    content = path.read_text()
    for edit in edits:
        old = edit.get("oldString")
        new = edit.get("newString")
        replace_all = bool(edit.get("replaceAll", False))
        if old is None or new is None:
            raise ValueError("Invalid edit")
        if replace_all:
            if old not in content:
                raise ValueError("oldString not found in content")
            content = content.replace(old, new)
        else:
            if content.count(old) != 1:
                raise ValueError("oldString must match exactly once")
            content = content.replace(old, new, 1)
    path.write_text(content)
    return {"ok": True}


def exec_patch(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    from gateway.tools.patch import apply_patch

    patch_text = params.get("patch")
    if not patch_text:
        raise ValueError("Missing patch")
    return apply_patch(patch_text, config)


def exec_ls(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    path = params.get("path", ".")
    resolved = _workspace_path(config.limits.workspace_root, path)
    items = [p.name for p in resolved.iterdir()]
    return {"entries": items}


def exec_glob(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    pattern = params.get("pattern")
    path = params.get("path")
    if not pattern:
        raise ValueError("Missing pattern")
    base = config.limits.workspace_root if not path else str(_workspace_path(config.limits.workspace_root, path))
    matches = globlib.glob(str(Path(base) / pattern), recursive=True)
    matches = [str(Path(match).relative_to(Path(config.limits.workspace_root))) for match in matches]
    return {"matches": matches}


def exec_grep(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    pattern = params.get("pattern")
    include = params.get("include")
    path = params.get("path", ".")
    if not pattern:
        raise ValueError("Missing pattern")
    base = _workspace_path(config.limits.workspace_root, path)
    regex = re.compile(pattern)
    results: list[dict[str, Any]] = []
    for file_path in base.rglob("*"):
        if not file_path.is_file():
            continue
        if include and not file_path.match(include):
            continue
        try:
            text = file_path.read_text()
        except UnicodeDecodeError:
            continue
        for index, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                results.append(
                    {
                        "file": str(file_path.relative_to(config.limits.workspace_root)),
                        "line": index,
                        "text": line,
                    }
                )
    return {"results": results}


def exec_webfetch(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    url = params.get("url")
    if not url:
        raise ValueError("Missing url")
    max_bytes = config.limits.webfetch_max_bytes
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url)
        response.raise_for_status()
        content = response.content[:max_bytes]
    return {"url": url, "content": content.decode("utf-8", errors="ignore")}


def exec_websearch(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    raise NotImplementedError("websearch not configured")


def exec_codesearch(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    raise NotImplementedError("codesearch not configured")


def exec_todo_read(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    return {"todos": []}


def exec_todo_write(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    return {"ok": True}


def exec_task(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    return {"error": "task tool must be executed by orchestrator"}


def exec_skill(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    return {"error": "skill tool not configured"}


def exec_batch(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    return {"error": "batch tool not configured"}


def exec_invalid(params: dict[str, Any], config: AppConfig) -> dict[str, Any]:
    return {"error": "invalid tool"}


def tool_schema(name: str, description: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {"name": name, "description": description, "schema": schema}


def get_default_schemas() -> dict[str, dict[str, Any]]:
    return {
        "bash": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer"},
                "workdir": {"type": "string"},
            },
            "required": ["command"],
        },
        "read": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string"},
                "offset": {"type": "integer"},
                "limit": {"type": "integer"},
            },
            "required": ["filePath"],
        },
        "write": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["filePath", "content"],
        },
        "edit": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string"},
                "oldString": {"type": "string"},
                "newString": {"type": "string"},
                "replaceAll": {"type": "boolean"},
            },
            "required": ["filePath", "oldString", "newString"],
        },
        "multiedit": {
            "type": "object",
            "properties": {
                "filePath": {"type": "string"},
                "edits": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "oldString": {"type": "string"},
                            "newString": {"type": "string"},
                            "replaceAll": {"type": "boolean"},
                        },
                        "required": ["oldString", "newString"],
                    },
                },
            },
            "required": ["filePath", "edits"],
        },
        "patch": {
            "type": "object",
            "properties": {
                "patch": {"type": "string"},
            },
            "required": ["patch"],
        },
        "ls": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
        },
        "glob": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["pattern"],
        },
        "grep": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "include": {"type": "string"},
            },
            "required": ["pattern"],
        },
        "webfetch": {
            "type": "object",
            "properties": {"url": {"type": "string"}},
            "required": ["url"],
        },
        "websearch": {"type": "object", "properties": {}},
        "codesearch": {"type": "object", "properties": {}},
        "todo_read": {"type": "object", "properties": {}},
        "todo_write": {
            "type": "object",
            "properties": {
                "todos": {"type": "array", "items": {"type": "object"}},
            },
        },
        "task": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "prompt": {"type": "string"},
                "subagent_type": {"type": "string"},
                "session_id": {"type": "string"},
            },
            "required": ["description", "prompt", "subagent_type"],
        },
        "skill": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        "batch": {
            "type": "object",
            "properties": {
                "tool_uses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "recipient_name": {"type": "string"},
                            "parameters": {"type": "object"},
                        },
                        "required": ["recipient_name", "parameters"],
                    },
                }
            },
            "required": ["tool_uses"],
        },
        "invalid": {"type": "object", "properties": {}},
    }


def create_default_registry(config: AppConfig) -> ToolRegistry:
    from gateway.tools.registry import ToolDefinition, ToolRegistry

    registry = ToolRegistry()
    schemas = get_default_schemas()
    registry.register(
        ToolDefinition(
            name="bash",
            description="Execute a shell command",
            schema=schemas["bash"],
            executor=lambda params: exec_bash(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="read",
            description="Read a file from disk",
            schema=schemas["read"],
            executor=lambda params: exec_read(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="write",
            description="Write a file to disk",
            schema=schemas["write"],
            executor=lambda params: exec_write(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="edit",
            description="Edit a file with string replacement",
            schema=schemas["edit"],
            executor=lambda params: exec_edit(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="multiedit",
            description="Apply multiple edits to a file",
            schema=schemas["multiedit"],
            executor=lambda params: exec_multiedit(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="patch",
            description="Apply a unified diff patch",
            schema=schemas["patch"],
            executor=lambda params: exec_patch(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="ls",
            description="List directory entries",
            schema=schemas["ls"],
            executor=lambda params: exec_ls(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="glob",
            description="Match file paths",
            schema=schemas["glob"],
            executor=lambda params: exec_glob(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="grep",
            description="Search file contents",
            schema=schemas["grep"],
            executor=lambda params: exec_grep(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="webfetch",
            description="Fetch web content",
            schema=schemas["webfetch"],
            executor=lambda params: exec_webfetch(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="websearch",
            description="Search the web",
            schema=schemas["websearch"],
            executor=lambda params: exec_websearch(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="codesearch",
            description="Search code",
            schema=schemas["codesearch"],
            executor=lambda params: exec_codesearch(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="todo_read",
            description="Read todo list",
            schema=schemas["todo_read"],
            executor=lambda params: exec_todo_read(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="todo_write",
            description="Write todo list",
            schema=schemas["todo_write"],
            executor=lambda params: exec_todo_write(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="task",
            description="Run a recursive task",
            schema=schemas["task"],
            executor=lambda params: exec_task(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="skill",
            description="Load a skill module",
            schema=schemas["skill"],
            executor=lambda params: exec_skill(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="batch",
            description="Execute multiple tools",
            schema=schemas["batch"],
            executor=lambda params: exec_batch(params, config),
        )
    )
    registry.register(
        ToolDefinition(
            name="invalid",
            description="Invalid tool placeholder",
            schema=schemas["invalid"],
            executor=lambda params: exec_invalid(params, config),
        )
    )
    return registry

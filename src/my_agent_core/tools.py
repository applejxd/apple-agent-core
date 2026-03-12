import json
import subprocess
from pathlib import Path
from typing import Any


MAX_OUTPUT_BYTES = 100_000
DEFAULT_BASH_TIMEOUT = 30


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _tool(
        "read",
        "Read file contents. Returns text content with line numbers.",
        {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "offset": {
                "type": "integer",
                "description": "Start line (1-indexed, optional)",
            },
            "limit": {
                "type": "integer",
                "description": "Max lines to return (optional)",
            },
        },
        ["path"],
    ),
    _tool(
        "write",
        "Create or overwrite a file with the given content.",
        {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Full file content"},
        },
        ["path", "content"],
    ),
    _tool(
        "edit",
        "Make a surgical text replacement in a file. By default old_str must match exactly once; use occurrence_index to target a specific duplicate.",
        {
            "path": {"type": "string", "description": "File path to edit"},
            "old_str": {
                "type": "string",
                "description": "Exact text to find and replace",
            },
            "new_str": {"type": "string", "description": "Replacement text"},
            "occurrence_index": {
                "type": "integer",
                "description": "1-based index of the occurrence to replace (optional; omit to require exactly one match)",
            },
        },
        ["path", "old_str", "new_str"],
    ),
    _tool(
        "bash",
        "Execute a bash command. Returns combined stdout and stderr.",
        {
            "command": {"type": "string", "description": "Bash command to execute"},
            "timeout": {
                "type": "integer",
                "description": f"Timeout in seconds (default: {DEFAULT_BASH_TIMEOUT})",
            },
        },
        ["command"],
    ),
]


def _resolve(path: str, cwd: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd) / p
    return p


def tool_read(
    path: str, cwd: str, offset: int | None = None, limit: int | None = None
) -> str:
    p = _resolve(path, cwd)
    try:
        lines = p.read_text(errors="replace").splitlines(keepends=True)
    except FileNotFoundError:
        return f"Error: file not found: {path}"
    except PermissionError:
        return f"Error: permission denied: {path}"

    start = max(0, (offset or 1) - 1)
    end = start + limit if limit else len(lines)
    chunk = lines[start:end]

    numbered = "".join(f"{start + i + 1:4d} | {line}" for i, line in enumerate(chunk))
    truncated = numbered.encode()[:MAX_OUTPUT_BYTES].decode(errors="replace")
    return truncated or "(empty file)"


def tool_write(path: str, content: str, cwd: str) -> str:
    p = _resolve(path, cwd)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written {len(content)} bytes to {path}"


def tool_edit(
    path: str, old_str: str, new_str: str, cwd: str, occurrence_index: int | None = None
) -> str:
    """Replace old_str with new_str in the file.

    If occurrence_index is given (1-based), replace only that occurrence.
    Otherwise old_str must appear exactly once.
    """
    p = _resolve(path, cwd)
    try:
        original = p.read_text(errors="replace")
    except FileNotFoundError:
        return f"Error: file not found: {path}"

    count = original.count(old_str)
    if count == 0:
        return "Error: old_str not found in file. Make sure it matches exactly (whitespace, indentation)."

    if occurrence_index is not None:
        if occurrence_index < 1 or occurrence_index > count:
            return f"Error: occurrence_index {occurrence_index} out of range (file has {count} matches)."
        # Replace only the Nth occurrence
        parts = original.split(old_str)
        result = (
            old_str.join(parts[:occurrence_index])
            + new_str
            + old_str.join(parts[occurrence_index:])
        )
        p.write_text(result)
        return f"Edited {path} (occurrence {occurrence_index}/{count})"

    if count > 1:
        return (
            f"Error: old_str found {count} times. "
            "Make old_str more specific or use occurrence_index to target a particular match."
        )

    p.write_text(original.replace(old_str, new_str, 1))
    return f"Edited {path}"


def tool_bash(command: str, cwd: str, timeout: int = DEFAULT_BASH_TIMEOUT) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            cwd=cwd,
            timeout=timeout,
        )
        combined = result.stdout + result.stderr
        output = combined[:MAX_OUTPUT_BYTES].decode(errors="replace")
        if result.returncode != 0:
            output += f"\n[exit code: {result.returncode}]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def execute_tool(name: str, arguments: str, cwd: str) -> str:
    try:
        args: dict[str, Any] = json.loads(arguments)
    except json.JSONDecodeError as e:
        return f"Error: invalid tool arguments JSON: {e}"

    match name:
        case "read":
            return tool_read(args["path"], cwd, args.get("offset"), args.get("limit"))
        case "write":
            return tool_write(args["path"], args["content"], cwd)
        case "edit":
            return tool_edit(
                args["path"],
                args["old_str"],
                args["new_str"],
                cwd,
                args.get("occurrence_index"),
            )
        case "bash":
            return tool_bash(
                args["command"], cwd, args.get("timeout", DEFAULT_BASH_TIMEOUT)
            )
        case _:
            return f"Error: unknown tool '{name}'"

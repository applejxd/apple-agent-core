"""ファイル操作・コマンド実行のツール定義モジュール。

LLM に提供する 4 つのツール（read / write / edit / bash）の実装と
JSON Schema 定義を提供する。
"""

import json
import subprocess
from pathlib import Path
from typing import Any

#: bash ツールが返す最大出力サイズ（バイト）。
MAX_OUTPUT_BYTES = 100_000

#: bash ツールのデフォルトタイムアウト秒数。
DEFAULT_BASH_TIMEOUT = 30


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str]
) -> dict[str, Any]:
    """LLM 向けツール定義辞書を組み立てるヘルパー。

    :param name: ツール名。
    :param description: ツールの説明文（英語）。
    :param properties: パラメータの JSON Schema プロパティ定義。
    :param required: 必須パラメータ名のリスト。
    :return: OpenAI function-calling 形式のツール定義辞書。
    """
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
"""LLM に提供するツール定義のリスト（JSON Schema 形式）。"""


def _resolve(path: str, cwd: str) -> Path:
    """相対パスを絶対パスに解決する。

    :param path: ファイルパス（絶対または相対）。
    :param cwd: 相対パスの基準となる作業ディレクトリ。
    :return: 解決済みの絶対パス。
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path(cwd) / p
    return p


def tool_read(
    path: str, cwd: str, offset: int | None = None, limit: int | None = None
) -> str:
    """ファイルの内容を読み込み、行番号付きで返す。

    :param path: 読み込むファイルのパス（絶対パスまたは相対パス）。
    :param cwd: 相対パスの基準となる作業ディレクトリ。
    :param offset: 読み込み開始行（1-indexed）。省略時は先頭から。
    :param limit: 返す最大行数。省略時は全行。
    :return: 行番号付きのファイル内容。エラー時はエラーメッセージ文字列。
    """
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
    """ファイルを新規作成または上書きする。

    :param path: 書き込み先のファイルパス。
    :param content: ファイルに書き込む内容。
    :param cwd: 相対パスの基準となる作業ディレクトリ。
    :return: 書き込み結果を示すメッセージ。
    """
    p = _resolve(path, cwd)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return f"Written {len(content)} bytes to {path}"


def tool_edit(
    path: str, old_str: str, new_str: str, cwd: str, occurrence_index: int | None = None
) -> str:
    """ファイル内の文字列を置換する。

    ``occurrence_index`` を指定した場合は指定番目のマッチのみを置換する。
    省略した場合は ``old_str`` がファイル内にちょうど 1 回だけ出現する必要がある。

    :param path: 編集対象のファイルパス。
    :param old_str: 置換前の文字列（完全一致）。
    :param new_str: 置換後の文字列。
    :param cwd: 相対パスの基準となる作業ディレクトリ。
    :param occurrence_index: 置換対象のマッチ番号（1-indexed）。省略時は 1 回のみ許容。
    :return: 編集結果を示すメッセージ。エラー時はエラーメッセージ文字列。
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
    """bash コマンドを実行し、標準出力と標準エラーを結合して返す。

    :param command: 実行する bash コマンド文字列。
    :param cwd: コマンドを実行する作業ディレクトリ。
    :param timeout: タイムアウト秒数。デフォルトは :data:`DEFAULT_BASH_TIMEOUT`。
    :return: 標準出力 + 標準エラーの結合文字列。エラー時はエラーメッセージ。
    """
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
    """ツール名と JSON 引数文字列からツールを実行して結果を返す。

    :param name: ツール名（ ``"read"`` / ``"write"`` / ``"edit"`` / ``"bash"``）。
    :param arguments: JSON 文字列形式のツール引数。
    :param cwd: 相対パスの基準となる作業ディレクトリ。
    :return: ツール実行結果の文字列。
    """
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

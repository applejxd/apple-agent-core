"""tool_runner.py のテスト。

subprocess.run で tool_runner.py を直接呼び出し、
stdin JSON → stdout JSON プロトコルを検証する。
"""

import json
import subprocess
import sys
from pathlib import Path


#: tool_runner.py のパス
TOOL_RUNNER = Path(__file__).parent.parent / "src" / "apple_agent_core" / "tool_runner.py"


def run_tool_runner(request: dict, cwd: Path | None = None) -> dict:
    """tool_runner.py に JSON リクエストを送り、JSON レスポンスを返す。

    :param request: ツールリクエスト辞書（name, arguments, cwd）。
    :param cwd: subprocess の作業ディレクトリ（省略時は現在のディレクトリ）。
    :return: stdout の JSON をパースした辞書。
    """
    stdin_data = json.dumps(request).encode()
    result = subprocess.run(
        [sys.executable, str(TOOL_RUNNER)],
        input=stdin_data,
        capture_output=True,
        timeout=10,
        cwd=str(cwd) if cwd else None,
    )
    assert result.returncode == 0, f"tool_runner failed: {result.stderr.decode()}"
    return json.loads(result.stdout.decode())


class TestToolRunnerRead:
    def test_read_existing_file(self, tmp_path):
        test_file = tmp_path / "hello.txt"
        test_file.write_text("line1\nline2\n")

        req = {
            "name": "read",
            "arguments": json.dumps({"path": "hello.txt"}),
            "cwd": str(tmp_path),
        }
        resp = run_tool_runner(req)
        assert "result" in resp
        assert "line1" in resp["result"]
        assert "line2" in resp["result"]

    def test_read_nonexistent_file_returns_error(self, tmp_path):
        req = {
            "name": "read",
            "arguments": json.dumps({"path": "no_such_file.txt"}),
            "cwd": str(tmp_path),
        }
        resp = run_tool_runner(req)
        assert "result" in resp
        # エラーメッセージが返る（例外は発生しない）
        assert "Error" in resp["result"] or "error" in resp["result"].lower() or "no_such_file" in resp["result"]


class TestToolRunnerWrite:
    def test_write_creates_file(self, tmp_path):
        req = {
            "name": "write",
            "arguments": json.dumps({"path": "out.txt", "content": "hello world"}),
            "cwd": str(tmp_path),
        }
        resp = run_tool_runner(req)
        assert "result" in resp
        assert (tmp_path / "out.txt").read_text() == "hello world"

    def test_write_creates_parent_dirs(self, tmp_path):
        req = {
            "name": "write",
            "arguments": json.dumps({"path": "a/b/c.txt", "content": "nested"}),
            "cwd": str(tmp_path),
        }
        resp = run_tool_runner(req)
        assert "result" in resp
        assert (tmp_path / "a" / "b" / "c.txt").read_text() == "nested"


class TestToolRunnerBash:
    def test_bash_runs_command(self, tmp_path):
        req = {
            "name": "bash",
            "arguments": json.dumps({"command": "echo hello_from_bash"}),
            "cwd": str(tmp_path),
        }
        resp = run_tool_runner(req)
        assert "result" in resp
        assert "hello_from_bash" in resp["result"]

    def test_bash_nonzero_exit_includes_exit_code(self, tmp_path):
        req = {
            "name": "bash",
            "arguments": json.dumps({"command": "exit 1"}),
            "cwd": str(tmp_path),
        }
        resp = run_tool_runner(req)
        assert "result" in resp
        # 終了コードが含まれるかエラーメッセージが返る
        assert "1" in resp["result"] or "exit" in resp["result"].lower()


class TestToolRunnerUnknown:
    def test_unknown_tool_returns_error(self, tmp_path):
        req = {
            "name": "nonexistent_tool",
            "arguments": json.dumps({}),
            "cwd": str(tmp_path),
        }
        resp = run_tool_runner(req)
        assert "result" in resp
        assert "Error" in resp["result"] or "unknown" in resp["result"].lower()

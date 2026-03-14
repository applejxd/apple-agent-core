"""tools.py の execute_tool() のテスト。

ローカル実行（APPLE_AGENT_SKIP_DOCKER=1）と
docker exec 委譲（通常モード）の両ルートを検証する。
"""

import json
from unittest.mock import patch

import pytest

from apple_agent_core.docker import SKIP_DOCKER_ENV
from apple_agent_core.tools import execute_tool


SESSION_ID = "20260101-120000-abcd1234"


class TestExecuteToolLocal:
    """APPLE_AGENT_SKIP_DOCKER=1 時はローカルで実行される。"""

    @pytest.mark.anyio
    async def test_read_local(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_DOCKER_ENV, "1")
        f = tmp_path / "test.txt"
        f.write_text("hello local")
        result = await execute_tool(
            "read",
            json.dumps({"path": str(f)}),
            str(tmp_path),
            session_id=SESSION_ID,
        )
        assert "hello local" in result

    @pytest.mark.anyio
    async def test_write_local(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_DOCKER_ENV, "1")
        result = await execute_tool(
            "write",
            json.dumps({"path": "out.txt", "content": "written"}),
            str(tmp_path),
            session_id=SESSION_ID,
        )
        assert (tmp_path / "out.txt").read_text() == "written"
        assert "written" in result or "ok" in result.lower() or "out.txt" in result

    @pytest.mark.anyio
    async def test_bash_local(self, tmp_path, monkeypatch):
        monkeypatch.setenv(SKIP_DOCKER_ENV, "1")
        result = await execute_tool(
            "bash",
            json.dumps({"command": "echo test_output"}),
            str(tmp_path),
            session_id=SESSION_ID,
        )
        assert "test_output" in result

    @pytest.mark.anyio
    async def test_no_session_id_always_runs_local(self, tmp_path, monkeypatch):
        """session_id 未指定の場合は常にローカル実行。"""
        monkeypatch.delenv(SKIP_DOCKER_ENV, raising=False)
        result = await execute_tool(
            "bash",
            json.dumps({"command": "echo no_session"}),
            str(tmp_path),
        )
        assert "no_session" in result


class TestExecuteToolDockerExec:
    """通常モード（コンテナ外）では docker_exec_tool に委譲される。"""

    @pytest.mark.anyio
    async def test_delegates_to_docker_exec_tool(self, tmp_path, monkeypatch):
        monkeypatch.delenv(SKIP_DOCKER_ENV, raising=False)
        monkeypatch.delenv("APPLE_AGENT_CONTAINER", raising=False)

        async def mock_docker_exec(session_id, name, arguments, cwd):
            return f"docker:{name}:{session_id}"

        # _should_run_locally() が False を返すようにし、
        # docker_exec_tool の遅延インポート元をパッチして委譲先を差し替える
        with patch("apple_agent_core.tools._should_run_locally", return_value=False):
            with patch("apple_agent_core.docker.docker_exec_tool", side_effect=mock_docker_exec):
                result = await execute_tool(
                    "read",
                    json.dumps({"path": "x"}),
                    "/cwd",
                    session_id=SESSION_ID,
                )

        assert result == f"docker:read:{SESSION_ID}"

"""docker.py のテスト。

コンテナ管理関数（start/stop/ensure_session_container, docker_exec_tool など）を
subprocess.run / asyncio.create_subprocess_exec をモックして検証する。
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from apple_agent_core.docker import (
    CONTAINER_FLAG_ENV,
    DEFAULT_IMAGE,
    IMAGE_ENV,
    SKIP_DOCKER_ENV,
    docker_exec_tool,
    ensure_session_container,
    get_container_name,
    get_image_name,
    is_inside_container,
    should_skip_docker,
    start_session_container,
    stop_session_container,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SESSION_ID = "20260101-120000-abcd1234"


def _make_completed_process(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    """subprocess.CompletedProcess のモックを返す。"""
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# is_inside_container
# ---------------------------------------------------------------------------


class TestIsInsideContainer:
    def test_true_when_env_set(self, monkeypatch):
        monkeypatch.setenv(CONTAINER_FLAG_ENV, "1")
        assert is_inside_container() is True

    def test_false_when_env_not_set_and_no_dockerenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv(CONTAINER_FLAG_ENV, raising=False)
        # /.dockerenv が存在しない環境（通常のホスト）
        with patch("apple_agent_core.docker.Path") as mock_path:
            instance = MagicMock()
            instance.exists.return_value = False
            mock_path.return_value = instance
            assert is_inside_container() is False

    def test_true_when_dockerenv_exists(self, monkeypatch):
        monkeypatch.delenv(CONTAINER_FLAG_ENV, raising=False)
        with patch("apple_agent_core.docker.Path") as mock_path:
            instance = MagicMock()
            instance.exists.return_value = True
            mock_path.return_value = instance
            assert is_inside_container() is True


# ---------------------------------------------------------------------------
# should_skip_docker
# ---------------------------------------------------------------------------


class TestShouldSkipDocker:
    def test_true_when_env_set(self, monkeypatch):
        monkeypatch.setenv(SKIP_DOCKER_ENV, "1")
        assert should_skip_docker() is True

    def test_false_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv(SKIP_DOCKER_ENV, raising=False)
        assert should_skip_docker() is False

    def test_false_when_env_is_zero(self, monkeypatch):
        monkeypatch.setenv(SKIP_DOCKER_ENV, "0")
        assert should_skip_docker() is False


# ---------------------------------------------------------------------------
# get_image_name
# ---------------------------------------------------------------------------


class TestGetImageName:
    def test_default(self, monkeypatch):
        monkeypatch.delenv(IMAGE_ENV, raising=False)
        assert get_image_name() == DEFAULT_IMAGE

    def test_custom_image_from_env(self, monkeypatch):
        monkeypatch.setenv(IMAGE_ENV, "my-image:v2")
        assert get_image_name() == "my-image:v2"


# ---------------------------------------------------------------------------
# get_container_name
# ---------------------------------------------------------------------------


class TestGetContainerName:
    def test_format(self):
        assert get_container_name(SESSION_ID) == f"agent-{SESSION_ID}"


# ---------------------------------------------------------------------------
# start_session_container
# ---------------------------------------------------------------------------


class TestStartSessionContainer:
    def test_calls_docker_run_with_correct_args(self, tmp_path, monkeypatch):
        monkeypatch.delenv(IMAGE_ENV, raising=False)
        with patch("apple_agent_core.docker.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(returncode=0, stdout="abc123\n")
            result = start_session_container(SESSION_ID, tmp_path)

        assert result == get_container_name(SESSION_ID)
        cmd = mock_run.call_args[0][0]
        assert "docker" in cmd
        assert "run" in cmd
        assert "-d" in cmd
        assert "--name" in cmd
        assert get_container_name(SESSION_ID) in cmd
        assert DEFAULT_IMAGE in cmd

    def test_raises_on_failure(self, tmp_path):
        with patch("apple_agent_core.docker.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(returncode=1, stderr="error msg")
            with pytest.raises(RuntimeError, match="error msg"):
                start_session_container(SESSION_ID, tmp_path)

    def test_volume_mount_in_args(self, tmp_path, monkeypatch):
        monkeypatch.delenv(IMAGE_ENV, raising=False)
        with patch("apple_agent_core.docker.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(returncode=0)
            start_session_container(SESSION_ID, tmp_path)

        cmd = mock_run.call_args[0][0]
        assert "-v" in cmd
        # ホストパスがマウント引数に含まれる
        mount_args = " ".join(cmd)
        assert str(tmp_path.resolve()) in mount_args


# ---------------------------------------------------------------------------
# stop_session_container
# ---------------------------------------------------------------------------


class TestStopSessionContainer:
    def test_calls_stop_and_rm(self):
        container_name = get_container_name(SESSION_ID)
        with patch("apple_agent_core.docker.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(returncode=0)
            stop_session_container(SESSION_ID)

        assert mock_run.call_count == 2
        calls = [mock_run.call_args_list[i][0][0] for i in range(2)]
        assert any(container_name in c and "stop" in c for c in calls)
        assert any(container_name in c and "rm" in c for c in calls)

    def test_does_not_raise_on_error(self):
        """コンテナが存在しなくてもエラーを出さない。"""
        with patch("apple_agent_core.docker.subprocess.run") as mock_run:
            mock_run.return_value = _make_completed_process(returncode=1, stderr="no such container")
            stop_session_container(SESSION_ID)  # エラーなく完了すること


# ---------------------------------------------------------------------------
# ensure_session_container
# ---------------------------------------------------------------------------


class TestEnsureSessionContainer:
    def test_starts_container_when_not_running(self, tmp_path):
        with patch("apple_agent_core.docker._is_container_running", return_value=False):
            with patch("apple_agent_core.docker.start_session_container") as mock_start:
                mock_start.return_value = get_container_name(SESSION_ID)
                result = ensure_session_container(SESSION_ID, tmp_path)

        mock_start.assert_called_once_with(SESSION_ID, tmp_path)
        assert result == get_container_name(SESSION_ID)

    def test_does_not_start_when_already_running(self, tmp_path):
        with patch("apple_agent_core.docker._is_container_running", return_value=True):
            with patch("apple_agent_core.docker.start_session_container") as mock_start:
                result = ensure_session_container(SESSION_ID, tmp_path)

        mock_start.assert_not_called()
        assert result == get_container_name(SESSION_ID)


# ---------------------------------------------------------------------------
# docker_exec_tool
# ---------------------------------------------------------------------------


class TestDockerExecTool:
    def test_calls_local_when_skip_docker(self, monkeypatch):
        monkeypatch.setenv(SKIP_DOCKER_ENV, "1")
        # should_skip_docker() が True なので docker_exec_tool 内で _execute_tool_local が呼ばれる
        with patch("apple_agent_core.tools._execute_tool_local", return_value="local result") as mock_exec:
            result = asyncio.run(docker_exec_tool(SESSION_ID, "read", '{"path": "x"}', "/cwd"))

        mock_exec.assert_called_once_with("read", '{"path": "x"}', "/cwd")
        assert result == "local result"

    def test_returns_result_from_container(self, monkeypatch):
        monkeypatch.delenv(SKIP_DOCKER_ENV, raising=False)
        response_json = json.dumps({"result": "file content"}) + "\n"

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        mock_proc.communicate = AsyncMock(return_value=(response_json.encode(), b""))

        with patch("apple_agent_core.docker.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = asyncio.run(docker_exec_tool(SESSION_ID, "read", '{"path": "x"}', "/cwd"))

        assert result == "file content"

    def test_returns_error_on_nonzero_exit(self, monkeypatch):
        monkeypatch.delenv(SKIP_DOCKER_ENV, raising=False)

        mock_proc = AsyncMock()
        mock_proc.returncode = 1
        mock_proc.communicate = AsyncMock(return_value=(b"", b"some stderr"))

        with patch("apple_agent_core.docker.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = asyncio.run(docker_exec_tool(SESSION_ID, "bash", '{"command": "x"}', "/cwd"))

        assert "[docker exec]" in result
        assert "some stderr" in result

    def test_returns_error_on_timeout(self, monkeypatch):
        monkeypatch.delenv(SKIP_DOCKER_ENV, raising=False)

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())

        with patch("apple_agent_core.docker.asyncio.create_subprocess_exec", return_value=mock_proc):
            result = asyncio.run(docker_exec_tool(SESSION_ID, "bash", '{"command": "x"}', "/cwd"))

        assert "タイムアウト" in result or "timeout" in result.lower()

    def test_stdin_receives_correct_json(self, monkeypatch):
        monkeypatch.delenv(SKIP_DOCKER_ENV, raising=False)
        response_json = json.dumps({"result": "ok"}) + "\n"

        mock_proc = AsyncMock()
        mock_proc.returncode = 0
        captured_stdin = []

        async def fake_communicate(input_bytes):
            captured_stdin.append(input_bytes)
            return (response_json.encode(), b"")

        mock_proc.communicate = fake_communicate

        with patch("apple_agent_core.docker.asyncio.create_subprocess_exec", return_value=mock_proc):
            asyncio.run(docker_exec_tool(SESSION_ID, "write", '{"path": "f", "content": "c"}', "/cwd"))

        assert len(captured_stdin) == 1
        sent = json.loads(captured_stdin[0].decode())
        assert sent["name"] == "write"
        assert sent["cwd"] == "/cwd"

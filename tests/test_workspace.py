"""Tests for the workspace module."""

from pathlib import Path


from apple_agent_core.types import Session
from apple_agent_core.workspace import (
    DEFAULT_WORKSPACE_BASE,
    WORKSPACE_BASE_ENV,
    get_files_dir,
    get_session_dir,
    get_workspace_base,
    list_sessions,
    prepare_agent,
    setup_workspace,
)


class TestGetWorkspaceBase:
    def test_default_returns_workspace(self, monkeypatch):
        monkeypatch.delenv(WORKSPACE_BASE_ENV, raising=False)
        assert get_workspace_base() == Path(DEFAULT_WORKSPACE_BASE)

    def test_respects_env_var(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path / "custom"))
        assert get_workspace_base() == tmp_path / "custom"


class TestGetFilesDir:
    def test_returns_files_subdir(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        assert get_files_dir(sid) == tmp_path / sid / "files"


class TestGetSessionDir:
    def test_returns_session_subdir(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        assert get_session_dir(sid) == tmp_path / sid / "session"


class TestSetupWorkspace:
    def test_creates_files_and_session_dirs(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        info = setup_workspace(sid)
        assert info.files_dir.is_dir()
        assert info.session_dir.is_dir()

    def test_is_new_true_on_first_call(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        info = setup_workspace(sid)
        assert info.is_new is True

    def test_is_new_false_on_second_call(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        setup_workspace(sid)
        info = setup_workspace(sid)
        assert info.is_new is False

    def test_copies_templates_on_first_call(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        templates_src = tmp_path / "templates"
        templates_src.mkdir()
        (templates_src / "AGENTS.md").write_text("# Template")
        (templates_src / "README.md").write_text("# Readme")

        sid = "20260101-120000-abcd1234"
        info = setup_workspace(sid, templates_src=templates_src)

        assert (info.files_dir / "AGENTS.md").read_text() == "# Template"
        assert (info.files_dir / "README.md").read_text() == "# Readme"

    def test_does_not_copy_templates_on_second_call(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        templates_src = tmp_path / "templates"
        templates_src.mkdir()
        (templates_src / "AGENTS.md").write_text("# Template")

        sid = "20260101-120000-abcd1234"
        info = setup_workspace(sid, templates_src=templates_src)

        # Modify file in workspace; second call should not overwrite it
        (info.files_dir / "AGENTS.md").write_text("# Modified")
        (templates_src / "extra.md").write_text("# Extra")

        setup_workspace(sid, templates_src=templates_src)

        assert (info.files_dir / "AGENTS.md").read_text() == "# Modified"
        assert not (info.files_dir / "extra.md").exists()

    def test_copies_subdirectory_templates(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        templates_src = tmp_path / "templates"
        templates_src.mkdir()
        subdir = templates_src / "subdir"
        subdir.mkdir()
        (subdir / "nested.txt").write_text("nested")

        sid = "20260101-120000-abcd1234"
        info = setup_workspace(sid, templates_src=templates_src)

        assert (info.files_dir / "subdir" / "nested.txt").read_text() == "nested"


class TestListSessions:
    def test_returns_empty_when_base_missing(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path / "nonexistent"))
        assert list_sessions() == []

    def test_returns_sessions_with_messages_json(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        session_dir = tmp_path / sid / "session"
        session_dir.mkdir(parents=True)
        (session_dir / "messages.json").write_text("[]")

        result = list_sessions()
        assert result == [sid]

    def test_ignores_dirs_without_messages_json(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        # Dir with messages.json
        sid_valid = "20260101-120000-abcd1234"
        session_dir = tmp_path / sid_valid / "session"
        session_dir.mkdir(parents=True)
        (session_dir / "messages.json").write_text("[]")

        # Dir without messages.json
        sid_invalid = "20260101-110000-deadbeef"
        (tmp_path / sid_invalid / "session").mkdir(parents=True)

        result = list_sessions()
        assert result == [sid_valid]
        assert sid_invalid not in result

    def test_sorted_newest_first(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sids = [
            "20260101-100000-aaaaaaaa",
            "20260103-120000-cccccccc",
            "20260102-110000-bbbbbbbb",
        ]
        for sid in sids:
            d = tmp_path / sid / "session"
            d.mkdir(parents=True)
            (d / "messages.json").write_text("[]")

        result = list_sessions()
        assert result == sorted(sids, reverse=True)


class TestPrepareAgent:
    def test_returns_three_tuple(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        result = prepare_agent(sid)
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_cwd_is_absolute_string(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        cwd, _, _ = prepare_agent(sid)
        assert isinstance(cwd, str)
        assert Path(cwd).is_absolute()

    def test_cwd_points_to_files_dir(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        cwd, _, _ = prepare_agent(sid)
        assert Path(cwd) == get_files_dir(sid).absolute()

    def test_session_has_correct_session_id(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        _, session, _ = prepare_agent(sid)
        assert isinstance(session, Session)
        assert session.session_id == sid

    def test_system_prompt_is_string(self, monkeypatch, tmp_path):
        monkeypatch.setenv(WORKSPACE_BASE_ENV, str(tmp_path))
        sid = "20260101-120000-abcd1234"
        _, _, system_prompt = prepare_agent(sid)
        assert isinstance(system_prompt, str)
        assert len(system_prompt) > 0

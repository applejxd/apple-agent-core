"""Tests for prompt.build_system_prompt (Agentic Context Engineering)."""

from pathlib import Path

from my_agent_core.prompt import build_system_prompt, _discover_skills, CONTEXT_FILES


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


# ---------------------------------------------------------------------------
# _discover_skills
# ---------------------------------------------------------------------------

class TestDiscoverSkills:
    def test_no_skills_dir(self, tmp_path):
        result = _discover_skills(str(tmp_path))
        assert result is None

    def test_empty_skills_dir(self, tmp_path):
        (tmp_path / ".agent" / "skills").mkdir(parents=True)
        result = _discover_skills(str(tmp_path))
        assert result is None

    def test_lists_skill_names(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _write(skills_dir / "testing.md", "# Testing Skill\nRun pytest properly.")
        _write(skills_dir / "refactor.md", "# Refactor Skill\nClean up code.")
        result = _discover_skills(str(tmp_path))
        assert result is not None
        assert "testing" in result
        assert "refactor" in result
        # Full body should NOT appear
        assert "Run pytest properly" not in result
        assert "Clean up code" not in result

    def test_first_nonempty_line_used(self, tmp_path):
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        _write(skills_dir / "myskill.md", "\n\n# My Skill Title\ndetails here")
        result = _discover_skills(str(tmp_path))
        assert result is not None
        assert "My Skill Title" in result

    def test_symlinks_skipped(self, tmp_path):
        """Symlinks are skipped to prevent traversal attacks."""
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        real_file = tmp_path / "secret.txt"
        real_file.write_text("SECRET=abc123")
        symlink = skills_dir / "evil.md"
        symlink.symlink_to(real_file)
        result = _discover_skills(str(tmp_path))
        # Either None or doesn't contain the secret
        assert result is None or "SECRET" not in result

    def test_dotdot_filenames_skipped(self, tmp_path):
        """Filenames with '..' are skipped to prevent path traversal."""
        skills_dir = tmp_path / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        evil = skills_dir / "..evil.md"
        evil.write_text("# Evil\nmalicious content")
        result = _discover_skills(str(tmp_path))
        assert result is None or "..evil" not in result


# ---------------------------------------------------------------------------
# build_system_prompt — local context files
# ---------------------------------------------------------------------------

class TestBuildSystemPromptLocal:
    def test_no_context_files(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path))
        assert "Project Context" not in prompt
        assert "Current working directory" in prompt

    def test_agents_md_injected(self, tmp_path):
        _write(tmp_path / "AGENTS.md", "# My Project\nDo things correctly.")
        prompt = build_system_prompt(str(tmp_path))
        assert "My Project" in prompt
        assert "Project Context" in prompt

    def test_user_md_injected(self, tmp_path):
        _write(tmp_path / "USER.md", "Language: Japanese")
        prompt = build_system_prompt(str(tmp_path))
        assert "Language: Japanese" in prompt

    def test_tools_md_injected(self, tmp_path):
        _write(tmp_path / "TOOLS.md", "uv run pytest -x")
        prompt = build_system_prompt(str(tmp_path))
        assert "uv run pytest -x" in prompt

    def test_memory_md_injected(self, tmp_path):
        _write(tmp_path / "MEMORY.md", "## Learnings\n- Use foo() not bar()")
        prompt = build_system_prompt(str(tmp_path))
        assert "Use foo() not bar()" in prompt

    def test_system_md_injected(self, tmp_path):
        _write(tmp_path / "SYSTEM.md", "Custom system config")
        prompt = build_system_prompt(str(tmp_path))
        assert "Custom system config" in prompt

    def test_agent_instructions_injected(self, tmp_path):
        _write(tmp_path / ".agent" / "instructions.md", "Special instructions")
        prompt = build_system_prompt(str(tmp_path))
        assert "Special instructions" in prompt

    def test_claude_md_NOT_injected(self, tmp_path):
        """CLAUDE.md is model-specific and must not be in CONTEXT_FILES."""
        assert "CLAUDE.md" not in CONTEXT_FILES
        _write(tmp_path / "CLAUDE.md", "This should not appear")
        prompt = build_system_prompt(str(tmp_path))
        assert "This should not appear" not in prompt

    def test_empty_file_skipped(self, tmp_path):
        _write(tmp_path / "AGENTS.md", "   ")
        prompt = build_system_prompt(str(tmp_path))
        assert "Project Context" not in prompt

    def test_skills_section_present(self, tmp_path):
        _write(tmp_path / ".agent" / "skills" / "testing.md", "# Testing Skill")
        prompt = build_system_prompt(str(tmp_path))
        assert "Skills" in prompt
        assert "testing" in prompt

    def test_skills_section_absent_when_no_skills(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path))
        assert "# Skills" not in prompt

    def test_metadata_always_present(self, tmp_path):
        prompt = build_system_prompt(str(tmp_path))
        assert "Current date and time" in prompt
        assert str(tmp_path) in prompt


# ---------------------------------------------------------------------------
# build_system_prompt — global context files
# ---------------------------------------------------------------------------

class TestBuildSystemPromptGlobal:
    def test_global_agents_md_merged(self, tmp_path, monkeypatch):
        """Global AGENTS.md is prepended before local context."""
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        _write(global_dir / "AGENTS.md", "Global agent instructions")

        project_dir = tmp_path / "project"
        project_dir.mkdir()
        _write(project_dir / "AGENTS.md", "Local agent instructions")

        from my_agent_core import prompt as prompt_module
        monkeypatch.setattr(prompt_module, "GLOBAL_CONFIG_DIRS", [global_dir])

        result = build_system_prompt(str(project_dir))
        assert "Global agent instructions" in result
        assert "Local agent instructions" in result
        # Global appears before local in the prompt
        assert result.index("Global agent instructions") < result.index("Local agent instructions")

    def test_global_user_md_merged(self, tmp_path, monkeypatch):
        """Global USER.md is loaded alongside global AGENTS.md."""
        global_dir = tmp_path / "global"
        global_dir.mkdir()
        _write(global_dir / "USER.md", "Global user preferences")

        from my_agent_core import prompt as prompt_module
        monkeypatch.setattr(prompt_module, "GLOBAL_CONFIG_DIRS", [global_dir])

        result = build_system_prompt(str(tmp_path / "project"))
        assert "Global user preferences" in result

    def test_first_global_dir_wins(self, tmp_path, monkeypatch):
        """First matching GLOBAL_CONFIG_DIR wins; second is not read."""
        dir1 = tmp_path / "dir1"
        dir2 = tmp_path / "dir2"
        dir1.mkdir()
        dir2.mkdir()
        _write(dir1 / "AGENTS.md", "From dir1")
        _write(dir2 / "AGENTS.md", "From dir2")

        from my_agent_core import prompt as prompt_module
        monkeypatch.setattr(prompt_module, "GLOBAL_CONFIG_DIRS", [dir1, dir2])

        result = build_system_prompt(str(tmp_path / "project"))
        assert "From dir1" in result
        assert "From dir2" not in result

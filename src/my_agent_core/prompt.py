"""System prompt builder with Agentic Context Engineering support."""

from datetime import datetime
from pathlib import Path

CONTEXT_FILES = ["AGENTS.md", "SYSTEM.md", "CLAUDE.md", ".agent/instructions.md"]

# Candidate directories for global user-level AGENTS.md (checked in order)
GLOBAL_CONFIG_DIRS = [
    Path.home() / ".config" / "my-agent-core",
    Path.home() / ".agents",
]

BASE_PROMPT = """You are an expert coding assistant. You help users by reading files, executing commands, editing code, and writing new files.

Available tools:
- read: Read file contents (with optional line range)
- write: Create or overwrite files
- edit: Make surgical text replacements (old_str must match exactly once; use occurrence_index for duplicates)
- bash: Execute bash commands (stdout + stderr returned)

Guidelines:
- Use read to examine files before editing
- Use edit for precise changes, write for new files or complete rewrites
- Use bash for ls, grep, find, and other shell operations
- Be concise in responses; show file paths clearly
- When done with a task, summarize what you did in plain text
- **Complex tasks**: create a plan.md first, then implement step by step
- **Skill/reference docs**: load on demand with read (e.g. read('.agent/skills/testing.md')) rather than assuming they are in context"""


def build_system_prompt(cwd: str) -> str:
    """Build the system prompt, merging global and local context files."""
    prompt = BASE_PROMPT

    context_sections: list[str] = []

    # 1. Global user-level AGENTS.md (first match wins)
    for config_dir in GLOBAL_CONFIG_DIRS:
        global_agents = config_dir / "AGENTS.md"
        if global_agents.exists():
            try:
                content = global_agents.read_text(errors="replace").strip()
                if content:
                    context_sections.append(f"## Global AGENTS.md\n\n{content}")
            except OSError:
                pass
            break

    # 2. Local project context files
    for filename in CONTEXT_FILES:
        path = Path(cwd) / filename
        if path.exists():
            try:
                content = path.read_text(errors="replace").strip()
                if content:
                    context_sections.append(f"## {filename}\n\n{content}")
            except OSError:
                pass

    if context_sections:
        prompt += "\n\n# Project Context\n\n" + "\n\n".join(context_sections)

    # Metadata
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    prompt += f"\n\nCurrent date and time: {now}"
    prompt += f"\nCurrent working directory: {cwd}"

    return prompt

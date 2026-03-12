"""System prompt builder with Agentic Context Engineering support."""

import os
from datetime import datetime
from pathlib import Path

CONTEXT_FILES = ["AGENTS.md", "SYSTEM.md", "CLAUDE.md", ".agent/instructions.md"]

BASE_PROMPT = """You are an expert coding assistant. You help users by reading files, executing commands, editing code, and writing new files.

Available tools:
- read: Read file contents (with optional line range)
- write: Create or overwrite files
- edit: Make surgical text replacements (old_str must match exactly once)
- bash: Execute bash commands (stdout + stderr returned)

Guidelines:
- Use read to examine files before editing
- Use edit for precise changes, write for new files or complete rewrites
- Use bash for ls, grep, find, and other shell operations
- Be concise in responses; show file paths clearly
- When done with a task, summarize what you did in plain text"""


def build_system_prompt(cwd: str) -> str:
    prompt = BASE_PROMPT

    # Load context engineering files
    context_sections: list[str] = []
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

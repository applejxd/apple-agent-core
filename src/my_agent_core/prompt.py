"""システムプロンプトビルダーモジュール（Agentic Context Engineering 対応）。

cwd の AGENTS.md・USER.md・TOOLS.md・MEMORY.md・SYSTEM.md・.agent/instructions.md と
グローバル設定ディレクトリのファイルを自動注入し、スキル一覧もシステムプロンプトに含める。
"""

from datetime import datetime
from pathlib import Path

#: システムプロンプトに自動注入するプロジェクトローカルファイル名リスト（優先度順）。
CONTEXT_FILES = [
    "AGENTS.md",
    "USER.md",
    "TOOLS.md",
    "MEMORY.md",
    "SYSTEM.md",
    ".agent/instructions.md",
]

#: グローバル設定ディレクトリから読み込むファイル名リスト。
GLOBAL_FILES = ["AGENTS.md", "USER.md"]

#: グローバル設定ファイルを探索するディレクトリ候補（先頭から順に検索）。
GLOBAL_CONFIG_DIRS = [
    Path.home() / ".config" / "my-agent-core",
    Path.home() / ".agents",
]

#: エージェントへの基本指示文。ツール説明・ガイドラインを含む。
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
- Update MEMORY.md with new project knowledge discovered during the task
- **Complex tasks**: create a plan.md first, then implement step by step
- **Skill/reference docs**: load on demand with read (e.g. read('.agent/skills/testing.md')) rather than assuming they are in context"""


def _read_file(path: Path) -> str | None:
    """ファイルを読み込んでトリム済み内容を返す。

    :param path: 読み込むファイルパス。
    :return: トリム済みのファイル内容。空またはエラー時は ``None``。
    """
    try:
        content = path.read_text(errors="replace").strip()
        return content if content else None
    except OSError:
        return None


def _discover_skills(cwd: str) -> str | None:
    """.agent/skills/*.md を走査してスキル一覧テキストを返す。

    各ファイルの最初の非空行のみを説明として使用する。
    シンボリックリンクや不正なファイル名はスキップする。

    :param cwd: スキルディレクトリを探索する基準ディレクトリ。
    :return: スキル一覧の文字列。スキルが見つからない場合は ``None``。
    """
    skills_dir = Path(cwd) / ".agent" / "skills"
    if not skills_dir.is_dir():
        return None

    entries: list[str] = []
    for skill_file in sorted(skills_dir.glob("*.md")):
        if skill_file.is_symlink():
            continue
        name = skill_file.stem
        if ".." in name or "/" in name or "\\" in name:
            continue
        description = ""
        try:
            for line in skill_file.read_text(errors="replace").splitlines():
                line = line.strip().lstrip("#").strip()
                if line:
                    description = line
                    break
        except OSError:
            pass
        entries.append(
            f"- **{name}**: {description}" if description else f"- **{name}**"
        )

    if not entries:
        return None

    lines = [
        "Available skills (load full content with read('.agent/skills/<name>.md')):"
    ]
    lines.extend(entries)
    return "\n".join(lines)


def build_system_prompt(cwd: str) -> str:
    """グローバルおよびローカルのコンテキストファイルを結合してシステムプロンプトを構築する。

    :param cwd: エージェントの作業ディレクトリ。
    :return: 完成したシステムプロンプト文字列。
    """
    prompt = BASE_PROMPT

    context_sections: list[str] = []

    # 1. Global user-level files (AGENTS.md and USER.md, first matching dir wins)
    for config_dir in GLOBAL_CONFIG_DIRS:
        found_any = False
        for filename in GLOBAL_FILES:
            global_file = config_dir / filename
            if global_file.exists():
                content = _read_file(global_file)
                if content:
                    context_sections.append(f"## Global {filename}\n\n{content}")
                    found_any = True
        if found_any:
            break

    # 2. Local project context files
    for filename in CONTEXT_FILES:
        path = Path(cwd) / filename
        if path.exists():
            content = _read_file(path)
            if content:
                context_sections.append(f"## {filename}\n\n{content}")

    if context_sections:
        prompt += "\n\n# Project Context\n\n" + "\n\n".join(context_sections)

    # 3. Skills index (on-demand; full content loaded by agent with read tool)
    skills_index = _discover_skills(cwd)
    if skills_index:
        prompt += f"\n\n# Skills\n\n{skills_index}"

    # Metadata
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z").strip()
    prompt += f"\n\nCurrent date and time: {now}"
    prompt += f"\nCurrent working directory: {cwd}"

    return prompt

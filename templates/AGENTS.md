# Project Instructions (AGENTS.md)

## Overview

<!-- Describe your project here. What does it do? What are the main components? -->

## Directory Structure

```
.
├── src/          # Source code
├── tests/        # Tests
└── docs/         # Documentation
```

## Common Commands

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Lint
uv run ruff check .
```

## Coding Guidelines

- Use clear, descriptive variable names
- Add docstrings to public functions and classes
- Write tests for new functionality
- Keep functions small and focused

## Agent Instructions

- Read relevant files before making changes
- Use edit for small surgical changes, write for new files or complete rewrites
- Run tests after making changes: `bash('uv run pytest -x')`
- Update MEMORY.md with new project knowledge discovered during the task
- Summarize what you did at the end of each task

## Agentic Context Engineering (ACE)

エージェントは以下のファイルをシステムプロンプトに**自動注入**します（存在する場合のみ）:

| ファイル | 目的 | グローバル対応 |
|---|---|---|
| `AGENTS.md` | プロジェクト指示・規約（本ファイル） | ✓ |
| `USER.md` | ユーザー好み・言語・コーディングスタイル | ✓ |
| `TOOLS.md` | ローカルコマンド・ツール規約 | ✗ |
| `MEMORY.md` | 長期メモリ・プロジェクト知見の蓄積 | ✗ |
| `SYSTEM.md` | システム設定（pi-mono 互換） | ✗ |
| `.agent/instructions.md` | 追加の詳細指示 | ✗ |

グローバルファイル（`~/.config/my-agent-core/` または `~/.agents/`）はプロジェクト設定より先に読み込まれ、全プロジェクト共通の設定として機能します。

### オンデマンド・スキル

`.agent/skills/` に `*.md` ファイルを置くと、スキル名と説明のみがシステムプロンプトに列挙されます。
エージェントは必要に応じて `read('.agent/skills/<name>.md')` でスキルの詳細を取得します。

```bash
# スキルファイルの例
.agent/skills/
├── testing.md       # テスト作成・実行のガイドライン
├── refactoring.md   # リファクタリング手順
└── code-review.md   # コードレビューの観点
```


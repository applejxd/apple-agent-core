# my-agent-core

pi-coding-agent の Python (uv) 超シンプル版。OpenRouter API を使い、read/write/edit/bash の 4 ツールで動作する AI コーディングエージェント。CLI モードと Web UI（FastAPI + WebSocket）の両方を提供する。

## Tech Stack

- Language: Python 3.13+
- Framework: FastAPI (Web UI), httpx (SSE streaming)
- Package Manager: uv
- Tool Manager: mise
- Build: hatchling

## Build & Test

```bash
uv sync                  # 依存インストール
uv run pytest            # テスト実行
uv run ruff check .      # Lint
uv run ruff format .     # フォーマット
```

## Project Structure

- `src/my_agent_core/` — エージェント本体
  - `types.py`   — Message/Session dataclass
  - `tools.py`   — 4 ツール実装（JSON Schema 付き）
  - `llm.py`     — OpenRouter SSE streaming client
  - `prompt.py`  — システムプロンプトビルダー
  - `session.py` — JSON セッション永続化
  - `loop.py`    — エージェントループ
  - `server.py`  — FastAPI + WebSocket サーバー
  - `main.py`    — CLI エントリポイント
- `templates/AGENTS.md` — ユーザーワークスペース向けテンプレート
- `docker/`             — Dockerfile & entrypoint

## Entry Points

```bash
uv run agent       # ターミナル CLI
uv run agent-ui    # Web UI (http://localhost:8000)
uv run agent --ui  # 同上
```

## Code Style

- フォーマッター: ruff (Black スタイル、ダブルクォート、88文字)
- インデント: 4 スペース
- 型ヒント: 必須（Python 3.13+ ネイティブ型を使用）
- docstring: 公開関数・クラスに記述

## Architecture

- エージェントループ: LLM call → tool call → execute → append → repeat（完了宣言まで）
- セッション: `/workspace/.session/<session_id>/messages.json` に永続化
- コンテキスト注入: cwd の AGENTS.md / SYSTEM.md / CLAUDE.md を自動読み込み
- システムプロンプト < 1000 トークン維持を目標とする

## Workflow

- ブランチ戦略: GitHub flow（`main` + `feature/*` / `fix/*`）
- コミットメッセージ: 日本語 OK、変更内容を簡潔に記述
- PR → main へのマージ前にテスト・lint が通ること

## Security

- `OPENROUTER_API_KEY` など秘密情報は `.env` から読み込み、コードに直書き禁止
- `.env` は `.gitignore` に含め、リポジトリにコミットしない
- `mise.toml` にも API キーを直書きしない（環境変数参照に留める）

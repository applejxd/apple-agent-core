# ADR 0003: Agentic Context Engineering (ACE) ファイル設計

日付: 2026-03-12
更新日: 2026-03-12
ステータス: Accepted

## 背景

このリポジトリ（apple-agent-core）の ACE は、ワークスペース内の Markdown ファイルをシステムプロンプトに注入する仕組みで動作する。pi-mono（pi-coding-agent）と OpenClaw を DeepWiki で調査した結果、類似のエコシステムが複数存在し、各プロジェクトが独自のファイル命名規則を持つことが確認された。

本 ADR では、これらの調査を踏まえてどのファイルを採用・不採用とするかを確定し、全体のロジック設計を記録する。

## 調査サマリー

### pi-mono / pi-coding-agent
- 自動注入: `AGENTS.md` / `CLAUDE.md`（一般指示）、`SYSTEM.md`（プロンプト置換）、`APPEND_SYSTEM.md`（追記）
- オンデマンド: `SKILL.md`（`.pi/skills/`、`~/.pi/agent/skills/`）、`prompts/*.md`
- 発見ロジック: グローバル（`~/.pi/agent/`）→プロジェクト（`.pi/`）→パッケージの順

### OpenClaw
- 自動注入: `AGENTS.md`、`SOUL.md`（ペルソナ）、`TOOLS.md`（ツール規約）、`IDENTITY.md`（識別情報）、`USER.md`（ユーザープロファイル）、`HEARTBEAT.md`（定期チェックリスト）、`BOOTSTRAP.md`（初回儀式）、`MEMORY.md`（長期メモリ）
- オンデマンド: `skills/SKILL.md`、`prompts/*.md`、`memory/YYYY-MM-DD.md`
- デフォルトワークスペース: `~/.openclaw/workspace`

## 決定：採用・不採用

### 採用（自動注入）

| ファイル | 目的 | グローバル | 新規/既存 |
|---|---|---|---|
| `AGENTS.md` | プロジェクト指示・規約 | ✓ | 既存 |
| `USER.md` | ユーザー好み・言語・スタイル | ✓ | **新規** |
| `TOOLS.md` | ローカルコマンド・ツール規約 | ✗ | **新規** |
| `MEMORY.md` | 長期メモリ・プロジェクト知見 | ✗ | **新規** |
| `SYSTEM.md` | システム設定（pi-mono 互換） | ✗ | 既存 |
| `.agent/instructions.md` | 追加の詳細指示 | ✗ | 既存 |

グローバルファイル（`~/.config/apple-agent-core/` または `~/.agents/`）は `AGENTS.md` と `USER.md` のみ。プロジェクト設定より先に読み込まれる。

### 不採用

| ファイル | 由来 | 理由 |
|---|---|---|
| `CLAUDE.md` | 本リポジトリ既存 | **モデル特有のため除外**（ユーザー指示） |
| `SOUL.md` | OpenClaw | ペルソナ定義 → コーディングエージェントには不要 |
| `IDENTITY.md` | OpenClaw | エージェント識別情報 → スコープ外 |
| `HEARTBEAT.md` | OpenClaw | 定期実行チェックリスト → スコープ外 |
| `BOOTSTRAP.md` | OpenClaw | 初回儀式ファイル → テンプレートブートで代替済み |
| `APPEND_SYSTEM.md` | pi-mono | `SYSTEM.md` および `AGENTS.md` で代替可能 |

### オンデマンド（自動注入しない）

- `.agent/skills/*.md` — スキル名と説明行のみシステムプロンプトに列挙。本文はエージェントが `read('.agent/skills/<name>.md')` で取得
- `memory/YYYY-MM-DD.md` — 日次メモリログ（将来拡張）

## 全体ロジック設計（prompt.py）

```
build_system_prompt(cwd):
  1. BASE_PROMPT（コーディング指示・ガイドライン）
  2. # Project Context
     a. Global AGENTS.md  ← GLOBAL_CONFIG_DIRS の先頭一致ディレクトリ
     b. Global USER.md    ← 同ディレクトリ（なければスキップ）
     c. Local AGENTS.md, USER.md, TOOLS.md, MEMORY.md, SYSTEM.md, .agent/instructions.md
  3. # Skills（.agent/skills/*.md が存在する場合のみ）
     - skill-name: <ファイル先頭の非空行>
  4. メタデータ（現在日時、cwd）
```

グローバルコンテキストはプロジェクトローカルより前に挿入される。同じ名前のファイルがグローバルとローカルの両方に存在する場合、両者が別々に注入される（上書きではなく結合）。

## 実装変更点

### prompt.py
- `CONTEXT_FILES` から `CLAUDE.md` を削除、`USER.md`/`TOOLS.md`/`MEMORY.md` を追加
- `GLOBAL_FILES = ["AGENTS.md", "USER.md"]` を追加し、グローバル探索対象を明示
- `_read_file(path)` ヘルパーを抽出（OSError 処理を集約）
- `_discover_skills(cwd)` を追加：`.agent/skills/*.md` を走査し名前+説明一覧を生成
- `build_system_prompt` にスキル列挙セクション追加

### templates/（新規追加）
- `templates/USER.md` — ユーザープロファイルテンプレート
- `templates/TOOLS.md` — ツール規約テンプレート
- `templates/MEMORY.md` — 長期メモリテンプレート
- `templates/.agent/skills/example.md` — スキルファイルの記述例

### templates/AGENTS.md（更新）
- ACE ファイル一覧・グローバル設定パス・スキル利用ガイドを追記

### README.md（更新）
- Context Engineering テーブルを新ファイル一覧に更新
- templates/ ファイル構成を更新

### tests/test_prompt.py（新規追加）
- `_discover_skills` の単体テスト
- `build_system_prompt` のローカル・グローバルコンテキスト結合テスト
- `CLAUDE.md` が注入されないことの確認テスト

## 影響

### ポジティブ
- `USER.md` により全プロジェクト共通のユーザー設定が可能になる
- `TOOLS.md` でプロジェクト固有のコマンドをエージェントが確実に把握できる
- `MEMORY.md` によりセッションをまたいだ知識の蓄積が促進される
- スキル列挙により、エージェントが利用可能なスキルを発見できる
- `CLAUDE.md` の除去でモデル非依存の設計になる

### ネガティブ
- 既存ユーザーが `CLAUDE.md` を利用している場合、自動注入されなくなる（移行が必要）
- テンプレートファイルの増加により初期ワークスペースのファイル数が増える（軽微）

## 参考
- ADR 0001: pi-mono からの軽量機能強化
- DeepWiki: badlogic/pi-mono（pi-coding-agent）
- DeepWiki: openclaw/openclaw


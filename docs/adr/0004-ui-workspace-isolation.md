# ADR 0004: UIモードでのワークスペース分離の統一実装

## ステータス
承認済み (Accepted)

## コンテキスト
現在の実装では、CLIモード (`uv run agent`) で起動した場合にのみ、セッションごとに独立したワークスペースディレクトリ (`workspace/<session_id>/files`) が作成され、そこに `templates` がコピーされるロジックが `main.py` に記述されています。

しかし、UIモード (`uv run agent --ui`) で起動した場合、`server.py` の WebSocket ハンドラはこの初期化ロジックを通らず、デフォルトの作業ディレクトリ (`os.getcwd()`) や `$WORKSPACE_DIR` を使用します。これにより、以下の問題が発生しています：

1. UIモードでエージェントが生成・編集したファイルが、CLIモードと異なる場所に配置される（「マウント先がズレている」感覚の正体）。
2. UIモードのセッション間でファイルが分離されない。
3. `AGENTS.md` などのコンテキスト用テンプレートが UI モードのワークスペースにコピーされない。
4. `session.py` と `main.py` の間での `SESSION_DIR` 環境変数の扱いに一貫性がなく、パスが二重になるケースがある（例: `.../session/<session_id>/messages.json`）。

## 決定
ワークスペースの初期化とパス解決のロジックを独立したモジュール (`workspace.py`) に抽出し、CLI と UI の両方のエントリポイントからこれを呼び出すように統一しました。

1. **`workspace.py` の新設**:
   - `WorkspaceInfo` dataclass でワークスペース情報を保持。
   - `setup_workspace(session_id)` 関数でディレクトリ作成（`files/`, `session/`）およびテンプレートのコピーを実施。
   - `get_files_dir(session_id)` および `get_session_dir(session_id)` を通じて、一貫したパス解決を提供。
   - `list_sessions()` で統一された `workspace` フォルダ構造からセッション一覧をスキャン。
   - `prepare_agent(session_id)` で `(cwd, session, system_prompt)` を返す共通初期化関数を提供。
2. **`session.py` のリファクタリング**:
   - 独自のパス解決ロジックを廃止し、`workspace.get_session_dir()` を使用するように変更。
   - 環境変数 `SESSION_DIR` および `WORKSPACE_DIR` を廃止。新しい環境変数は `WORKSPACE_BASE`（デフォルト: `"workspace"`）のみ。
3. **`main.py` (CLI) のリファクタリング**:
   - インラインで記述されていたワークスペース作成ロジックを `prepare_agent(session_id)` の呼び出しに置き換え。
4. **`server.py` (UI) の修正**:
   - `/ws/{session_id}` 接続確立時に `prepare_agent(session_id)` を実行し、返された `(cwd, session, system_prompt)` を使用。
   - `/api/sessions` を修正し、`list_sessions()` で統一されたワークスペース構造からセッション一覧を取得。

## 実装結果
- **ディレクトリ構造**: `workspace/<session_id>/files/`（作業ディレクトリ）と `workspace/<session_id>/session/messages.json`（セッション永続化）
- **共通初期化**: CLI・UI ともに `prepare_agent(session_id)` → `(cwd, session, system_prompt)` の形で初期化を統一。
- **環境変数**: `SESSION_DIR`・`WORKSPACE_DIR` を廃止し、`WORKSPACE_BASE`（デフォルト: `"workspace"`）に一本化。
- **テスト**: 既存のすべてのテストがパスすることを確認済み。

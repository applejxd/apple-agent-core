"""ワークスペース管理モジュール。

CLI・UI 両モードで共通利用するワークスペースのディレクトリ作成・
テンプレートコピー・セッション一覧取得を提供する。
"""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

#: ワークスペースのベースディレクトリを指定する環境変数名。
WORKSPACE_BASE_ENV = "WORKSPACE_BASE"

#: WORKSPACE_BASE 未設定時のデフォルト値。
DEFAULT_WORKSPACE_BASE = "workspace"


@dataclass
class WorkspaceInfo:
    """セットアップ済みワークスペースの情報。

    :param files_dir: エージェントの作業ディレクトリ（agent cwd）。
    :param session_dir: セッションデータの保存ディレクトリ。
    :param is_new: このセッションが新規かどうか。
    """

    files_dir: Path
    """エージェントの作業ディレクトリ（agent cwd）。"""

    session_dir: Path
    """セッションデータの保存ディレクトリ。"""

    is_new: bool
    """このセッションが新規かどうか。"""


def get_workspace_base() -> Path:
    """ワークスペースのベースディレクトリを返す。

    環境変数 :data:`WORKSPACE_BASE_ENV` が設定されていればその値を、
    未設定の場合は :data:`DEFAULT_WORKSPACE_BASE` を使用する。

    :return: ワークスペースのベースディレクトリパス。
    """
    return Path(os.environ.get(WORKSPACE_BASE_ENV, DEFAULT_WORKSPACE_BASE))


def get_files_dir(session_id: str) -> Path:
    """指定セッションのファイルディレクトリパスを返す。

    エージェントの作業ディレクトリ（cwd）として使用される。

    :param session_id: セッション ID。
    :return: ``<workspace_base>/<session_id>/files`` のパス。
    """
    return get_workspace_base() / session_id / "files"


def get_session_dir(session_id: str) -> Path:
    """指定セッションのセッションデータディレクトリパスを返す。

    会話履歴（``messages.json``）の保存先として使用される。

    :param session_id: セッション ID。
    :return: ``<workspace_base>/<session_id>/session`` のパス。
    """
    return get_workspace_base() / session_id / "session"


def setup_workspace(
    session_id: str,
    templates_src: Path | None = None,
) -> WorkspaceInfo:
    """ワークスペースをセットアップする。

    必要なディレクトリを作成し、新規セッションの場合はテンプレートを
    ファイルディレクトリにコピーする。

    :param session_id: セットアップ対象のセッション ID。
    :param templates_src: テンプレートのソースディレクトリ。
        ``None`` の場合はパッケージ同梱の ``templates/`` を使用する。
    :return: セットアップ済みワークスペースの情報。
    """
    files_dir = get_files_dir(session_id)
    session_dir = get_session_dir(session_id)

    is_new = not files_dir.exists()

    files_dir.mkdir(parents=True, exist_ok=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    if is_new:
        if templates_src is None:
            # パッケージルートを基準に templates/ を探す
            templates_src = Path(__file__).parent.parent.parent / "templates"

        if templates_src.is_dir():
            print(
                f"[workspace] Initializing workspace with templates from {templates_src}"
            )
            for item in templates_src.iterdir():
                dest = files_dir / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_dir():
                    shutil.copytree(item, dest, dirs_exist_ok=True)

    return WorkspaceInfo(files_dir=files_dir, session_dir=session_dir, is_new=is_new)


def list_sessions() -> list[str]:
    """保存済みセッションの ID 一覧を返す。

    ワークスペースベースディレクトリをスキャンし、
    ``session/messages.json`` が存在するセッション ID を収集する。
    辞書順（＝時刻順）でソートして返す。

    :return: セッション ID 文字列のリスト（新しい順）。
    """
    base = get_workspace_base()
    if not base.is_dir():
        return []

    sessions: list[str] = []
    for entry in base.iterdir():
        if entry.is_dir() and (entry / "session" / "messages.json").exists():
            sessions.append(entry.name)

    # 辞書順ソート = 時刻順ソート（YYYYMMDD-HHMMSS-hex8 形式前提）
    return sorted(sessions, reverse=True)


def prepare_agent(session_id: str) -> tuple[str, object, str]:
    """エージェント実行に必要なセッション情報を準備する。

    CLI・UI 両モードで共通利用する初期化ヘルパー。
    ワークスペースのセットアップ、セッション履歴のロード、
    システムプロンプトの構築を一括して行う。

    :param session_id: 準備対象のセッション ID。
    :return: ``(cwd, session, system_prompt)`` のタプル。
        ``cwd`` はエージェントの作業ディレクトリ（絶対パス文字列）、
        ``session`` は :class:`~apple_agent_core.types.Session` インスタンス、
        ``system_prompt`` はシステムプロンプト文字列。
    """
    # 循環インポートを避けるため遅延インポートを使用する
    from .prompt import build_system_prompt
    from .session import load_session

    info = setup_workspace(session_id)
    cwd = str(info.files_dir.absolute())
    session = load_session(session_id, cwd)
    system_prompt = build_system_prompt(cwd)
    return cwd, session, system_prompt

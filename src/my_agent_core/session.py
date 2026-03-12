"""セッション管理モジュール。

会話履歴を JSON ファイルとしてディスクに永続化し、セッションの
ロード・セーブ・追記保存を提供する。
"""

import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .types import Message, Session

#: セッション保存先ディレクトリを指定する環境変数名。
SESSION_DIR_ENV = "SESSION_DIR"

#: SESSION_DIR 未設定時のデフォルトセッション保存先ディレクトリ。
DEFAULT_SESSION_BASE = str(
    Path.home() / ".local" / "share" / "my-agent-core" / "session"
)


def new_session_id() -> str:
    """時刻順ソート可能な人間可読のセッション ID を生成する。

    形式（UTC）: ``YYYYMMDD-HHMMSS-xxxxxxxx`` （16 進 8 文字のランダムサフィックス）

    辞書順ソートが時刻順ソートと一致するため、ワークスペースの
    ディレクトリ管理が容易になる。

    :return: 新しいセッション ID 文字列（例: ``20260312-114537-a3b4c5d8``）。
    """
    ts = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{ts}-{suffix}"


def _session_dir(session_id: str) -> Path:
    """セッションのデータディレクトリパスを返す。

    :param session_id: セッション ID。
    :return: セッションデータを保存するディレクトリパス。
    """
    base = os.environ.get(SESSION_DIR_ENV, DEFAULT_SESSION_BASE)
    return Path(base) / session_id


def load_session(session_id: str, cwd: str) -> Session:
    """既存セッションを読み込む。存在しない場合は新規セッションを作成する。

    :param session_id: 読み込むセッションの ID。
    :param cwd: エージェントの作業ディレクトリ。
    :return: 読み込まれた（または新規の） :class:`~my_agent_core.types.Session` インスタンス。
    """
    session = Session(session_id=session_id, cwd=cwd)
    messages_file = _session_dir(session_id) / "messages.json"

    if messages_file.exists():
        try:
            data = json.loads(messages_file.read_text())
            session.messages = [Message.from_dict(m) for m in data]
            print(
                f"[session] Restored {len(session.messages)} messages from {messages_file}"
            )
        except Exception as e:
            print(f"[session] Warning: could not load session: {e}")

    return session


def save_session(session: Session) -> None:
    """セッションのメッセージ履歴をディスクに保存する。

    :param session: 保存するセッションインスタンス。
    """
    d = _session_dir(session.session_id)
    d.mkdir(parents=True, exist_ok=True)
    messages_file = d / "messages.json"
    messages_file.write_text(
        json.dumps(
            [m.to_dict() for m in session.messages], ensure_ascii=False, indent=2
        )
    )


def append_and_save(session: Session, message: Message) -> None:
    """メッセージをセッションに追記してすぐに永続化する（クラッシュセーフ）。

    :param session: 追記対象のセッションインスタンス。
    :param message: 追記するメッセージ。
    """
    session.messages.append(message)
    save_session(session)

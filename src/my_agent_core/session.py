"""Session management: persist message history as JSON."""

import json
import os
from pathlib import Path

from .types import Message, Session

SESSION_DIR_ENV = "SESSION_DIR"
DEFAULT_SESSION_BASE = str(
    Path.home() / ".local" / "share" / "my-agent-core" / "session"
)


def _session_dir(session_id: str) -> Path:
    base = os.environ.get(SESSION_DIR_ENV, DEFAULT_SESSION_BASE)
    return Path(base) / session_id


def load_session(session_id: str, cwd: str) -> Session:
    """Load an existing session or create a new one."""
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
    """Persist session messages to disk."""
    d = _session_dir(session.session_id)
    d.mkdir(parents=True, exist_ok=True)
    messages_file = d / "messages.json"
    messages_file.write_text(
        json.dumps(
            [m.to_dict() for m in session.messages], ensure_ascii=False, indent=2
        )
    )


def append_and_save(session: Session, message: Message) -> None:
    """Append a message and immediately persist (crash-safe)."""
    session.messages.append(message)
    save_session(session)

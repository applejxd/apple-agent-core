"""my-agent-core パッケージ。

OpenRouter API を使った AI コーディングエージェント。
read / write / edit / bash の 4 ツールで動作し、
CLI モードと Web UI（FastAPI + WebSocket）の両方を提供する。
"""

from .llm import LLMClient, create_client
from .loop import run_loop
from .prompt import build_system_prompt
from .session import append_and_save, load_session, new_session_id, save_session
from .tools import TOOL_DEFINITIONS, execute_tool
from .types import Message, Session

__all__ = [
    "LLMClient",
    "create_client",
    "run_loop",
    "build_system_prompt",
    "new_session_id",
    "load_session",
    "save_session",
    "append_and_save",
    "TOOL_DEFINITIONS",
    "execute_tool",
    "Message",
    "Session",
]

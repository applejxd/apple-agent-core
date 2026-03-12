"""CLI エントリポイントモジュール。

ターミナルからエージェントを起動する ``agent`` コマンドを実装する。
WebUI（FastAPI サーバー）の起動にも対応する。
"""

import asyncio
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from .llm import create_client
from .loop import run_loop
from .session import append_and_save, new_session_id
from .types import Message
from .workspace import get_workspace_base, prepare_agent


def _expand_file_refs(text: str, cwd: str) -> str:
    """ユーザー入力内の ``@パス`` 参照をファイル内容に展開する。

    ``cwd`` の外部へのパス（例: ``@../etc/passwd``）は展開せずそのまま返す。

    :param text: ユーザーの入力テキスト。
    :param cwd: 参照を解決する基準となる作業ディレクトリ。
    :return: ``@パス`` をファイル内容に置換した文字列。
    """
    pattern = re.compile(r"@([\w./~-]+(?:/[\w./~-]*)*)")
    cwd_resolved = Path(cwd).resolve()

    def replace(match: re.Match) -> str:
        # パストラバーサルガード: cwd の外側は展開しない
        ref = match.group(1)
        p = Path(ref) if Path(ref).is_absolute() else Path(cwd) / ref
        p = p.resolve()
        try:
            p.relative_to(cwd_resolved)
        except ValueError:
            return match.group(0)
        if p.exists() and p.is_file():
            try:
                content = p.read_text(errors="replace")
                return f"\n--- @{ref} ---\n{content}\n---"
            except OSError:
                pass
        return match.group(0)

    return pattern.sub(replace, text)


def serve() -> None:
    """Web UI サーバー（FastAPI）を起動する。

    ``HOST`` / ``PORT`` 環境変数でバインドアドレスとポートを指定できる。
    """
    load_dotenv()
    from .server import serve as _serve

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    print(f"\033[1;32m[my-agent-core]\033[0m Web UI → http://localhost:{port}")
    _serve(host=host, port=port)


def main() -> None:
    """CLI エントリポイント。

    ``--ui`` / ``-u`` フラグが渡された場合は Web UI サーバーを起動する。
    それ以外はターミナルのインタラクティブ REPL として動作する。
    """
    if "--ui" in sys.argv or "-u" in sys.argv:
        serve()
        return
    load_dotenv()

    # 1. Determine Session ID
    session_id = os.environ.get("SESSION_ID") or new_session_id()

    # 2. Setup workspace, load session, build system prompt
    cwd, session, system_prompt = prepare_agent(session_id)

    try:
        client = create_client()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    workspace_path = get_workspace_base() / session_id
    print(
        f"\033[1;32m[my-agent-core]\033[0m session={session.session_id} model={client.model}"
    )
    print(f"  workspace={workspace_path.absolute()}")
    print(f"  cwd={cwd}")
    print("  Type your message, or 'exit' / Ctrl+C to quit.\n")

    async def _run() -> None:
        """インタラクティブ REPL のメインループ（非同期）。"""
        try:
            while True:
                try:
                    user_input = input("\033[1;34m[you]\033[0m ").strip()
                except EOFError:
                    print("\n[EOF] Exiting.")
                    break

                if not user_input:
                    continue
                if user_input.lower() in {"exit", "quit", "/exit", "/quit"}:
                    print("Goodbye.")
                    break

                user_input = _expand_file_refs(user_input, cwd)
                user_msg = Message(role="user", content=user_input)
                append_and_save(session, user_msg)

                await run_loop(client, session, system_prompt)

        except KeyboardInterrupt:
            print("\n\nInterrupted. Session saved.")
        finally:
            await client.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()

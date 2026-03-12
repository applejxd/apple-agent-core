"""CLI エントリポイントモジュール。

ターミナルからエージェントを起動する ``agent`` コマンドを実装する。
WebUI（FastAPI サーバー）の起動にも対応する。
"""

import asyncio
import os
import re
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

from .llm import create_client
from .loop import run_loop
from .prompt import build_system_prompt
from .session import append_and_save, load_session, new_session_id
from .types import Message


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

    # 2. Setup Session Workspace
    # We use a base 'workspace' directory, partitioned by session_id
    base_workspace = Path("workspace") / session_id
    files_dir = base_workspace / "files"
    session_dir = base_workspace / "session"

    is_new_session = not files_dir.exists()

    files_dir.mkdir(parents=True, exist_ok=True)
    session_dir.mkdir(parents=True, exist_ok=True)

    # 2.5 Copy templates to the workspace if it's a new session
    if is_new_session:
        templates_src = Path("templates")
        if templates_src.exists() and templates_src.is_dir():
            print(f"[main] Initializing workspace with templates from {templates_src}")
            for item in templates_src.iterdir():
                if item.is_file():
                    shutil.copy2(item, files_dir / item.name)
                elif item.is_dir():
                    shutil.copytree(item, files_dir / item.name, dirs_exist_ok=True)

    # 3. Configure paths for the app
    # Set SESSION_DIR env for session.py to pick up
    os.environ["SESSION_DIR"] = str(session_dir.absolute())
    # Set cwd for the agent to the 'files' directory
    cwd = str(files_dir.absolute())

    session = load_session(session_id, cwd)
    system_prompt = build_system_prompt(cwd)

    try:
        client = create_client()
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(
        f"\033[1;32m[my-agent-core]\033[0m session={session.session_id} model={client.model}"
    )
    print(f"  workspace={base_workspace.absolute()}")
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

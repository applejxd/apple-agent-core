"""CLI entry point for my-agent-core."""

import asyncio
import os
import shutil
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from .llm import create_client
from .loop import run_loop
from .prompt import build_system_prompt
from .session import append_and_save, load_session
from .types import Message


def serve() -> None:
    """Launch the web UI server."""
    load_dotenv()
    from .server import serve as _serve
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    print(f"\033[1;32m[my-agent-core]\033[0m Web UI → http://localhost:{port}")
    _serve(host=host, port=port)


def main() -> None:
    if "--ui" in sys.argv or "-u" in sys.argv:
        serve()
        return
    load_dotenv()

    # 1. Determine Session ID
    session_id = os.environ.get("SESSION_ID") or str(uuid.uuid4())

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

    print(f"\033[1;32m[my-agent-core]\033[0m session={session.session_id} model={client.model}")
    print(f"  workspace={base_workspace.absolute()}")
    print(f"  cwd={cwd}")
    print("  Type your message, or 'exit' / Ctrl+C to quit.\n")

    async def _run() -> None:
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

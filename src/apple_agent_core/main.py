"""CLI エントリポイントモジュール。

ターミナルからエージェントを起動する ``agent`` コマンドを実装する。
WebUI（FastAPI サーバー）の起動にも対応する。

コンテナ外で実行された場合は、セッションごとに Docker コンテナを起動して
エージェントを隔離実行する。コンテナ内では従来通りに直接実行する。
"""

import asyncio
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

from .llm import create_client
from .loop import run_loop
from .session import append_and_save, new_session_id
from .tools import TOOL_DEFINITIONS, execute_tool
from .types import Message, ToolCall
from .workspace import get_workspace_base, prepare_agent, setup_workspace


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
    print(f"\033[1;32m[apple-agent-core]\033[0m Web UI → http://localhost:{port}")
    _serve(host=host, port=port)


def main() -> None:
    """CLI エントリポイント。

    ``--ui`` / ``-u`` フラグが渡された場合は Web UI サーバーを起動する。
    ``--stdio`` フラグが渡された場合は JSON-line stdin/stdout モードで動作する
    （コンテナ内 Web UI エージェント用）。
    それ以外はターミナルのインタラクティブ REPL として動作する。

    コンテナ外で実行された場合（かつ ``APPLE_AGENT_SKIP_DOCKER`` が未設定の場合）は、
    Docker コンテナを起動してプロセスを置換する。
    """
    if "--ui" in sys.argv or "-u" in sys.argv:
        serve()
        return

    if "--stdio" in sys.argv:
        load_dotenv()
        asyncio.run(_run_stdio())
        return

    load_dotenv()

    from .docker import exec_cli_container, ensure_image, is_inside_container, should_skip_docker

    # コンテナ外での実行 → Docker コンテナを起動してプロセスを置換
    if not is_inside_container() and not should_skip_docker():
        session_id = os.environ.get("SESSION_ID") or new_session_id()
        workspace_base = get_workspace_base()
        # ホスト側でワークスペースを作成してからコンテナに渡す
        setup_workspace(session_id)
        if not ensure_image():
            print("Error: Docker イメージのビルドに失敗しました。", file=sys.stderr)
            sys.exit(1)
        # os.execvp でプロセスを docker run に置換（この関数は戻らない）
        exec_cli_container(session_id, workspace_base)
        return  # 到達しない

    # コンテナ内、または APPLE_AGENT_SKIP_DOCKER=1 の場合は直接実行
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
        f"\033[1;32m[apple-agent-core]\033[0m session={session.session_id} model={client.model}"
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


async def _run_stdio() -> None:
    """JSON-line stdin/stdout プロトコルでエージェントを実行する。

    Web UI の Docker コンテナ内で使用される。ホスト側の FastAPI サーバーが
    WebSocket メッセージをこのプロセスの stdin に転送し、stdout の JSON を
    WebSocket クライアントに中継する。

    プロトコル（1 行 = 1 JSON オブジェクト）:

    入力 (stdin):
        ``{"type": "user_message", "text": "..."}``

    出力 (stdout):
        ``{"type": "assistant_start"}``
        ``{"type": "text_delta", "text": "..."}``
        ``{"type": "tool_start", "tool_call_id": "...", "name": "...", "args": "..."}``
        ``{"type": "tool_end", "tool_call_id": "...", "result": "..."}``
        ``{"type": "assistant_end"}``
        ``{"type": "error", "message": "..."}``
    """
    session_id = os.environ.get("SESSION_ID") or new_session_id()
    cwd, session, system_prompt = prepare_agent(session_id)

    try:
        client = create_client()
    except ValueError as e:
        _stdio_write({"type": "error", "message": str(e)})
        return

    loop = asyncio.get_event_loop()

    try:
        while True:
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
            except (EOFError, OSError):
                break
            if not line:
                break

            try:
                data = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            if data.get("type") != "user_message":
                continue

            user_text: str = data.get("text", "").strip()
            if not user_text:
                continue

            user_msg = Message(role="user", content=user_text)
            append_and_save(session, user_msg)

            await _run_agent_stdio(client, session, system_prompt)

    except KeyboardInterrupt:
        pass
    finally:
        await client.close()


def _stdio_write(obj: dict) -> None:
    """JSON オブジェクトを stdout に 1 行で書き出す。

    :param obj: 書き出す JSON シリアライズ可能なオブジェクト。
    """
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def _run_agent_stdio(client, session, system_prompt: str) -> None:
    """エージェントの 1 ターンを実行し、結果を JSON-line 形式で stdout に書き出す。

    :param client: LLM クライアント。
    :param session: 現在の会話セッション。
    :param system_prompt: LLM に渡すシステムプロンプト。
    """
    from .loop import _trim_messages

    context = _trim_messages(session.messages)
    messages = [Message(role="system", content=system_prompt)] + context

    while True:
        text_chunks: list[str] = []
        tool_calls: list[ToolCall] = []

        _stdio_write({"type": "assistant_start"})

        async for chunk in client.stream(messages, TOOL_DEFINITIONS):
            if isinstance(chunk, str):
                text_chunks.append(chunk)
                _stdio_write({"type": "text_delta", "text": chunk})
            elif isinstance(chunk, list):
                tool_calls = chunk

        assistant_msg = Message(
            role="assistant",
            content="".join(text_chunks) or None,
            tool_calls=tool_calls if tool_calls else None,
        )
        append_and_save(session, assistant_msg)
        messages.append(assistant_msg)

        _stdio_write({"type": "assistant_end"})

        if not tool_calls:
            break

        for tc in tool_calls:
            _stdio_write(
                {
                    "type": "tool_start",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "args": tc.function.arguments,
                }
            )

            result = await asyncio.to_thread(
                execute_tool, tc.function.name, tc.function.arguments, session.cwd
            )

            _stdio_write(
                {
                    "type": "tool_end",
                    "tool_call_id": tc.id,
                    "result": result,
                }
            )

            tool_msg = Message(
                role="tool",
                content=result,
                tool_call_id=tc.id,
                name=tc.function.name,
            )
            append_and_save(session, tool_msg)
            messages.append(tool_msg)


if __name__ == "__main__":
    main()

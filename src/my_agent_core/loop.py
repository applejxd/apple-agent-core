"""コアエージェントループモジュール。

LLM 呼び出し → ツール実行 → 追記 → 繰り返し のループを実装する。
完了宣言（ツール呼び出しなし）まで継続する。
"""

from .llm import LLMClient
from .session import Session, append_and_save
from .tools import TOOL_DEFINITIONS, execute_tool
from .types import Message, ToolCall

#: コンテキストウィンドウに保持する最大メッセージ数（system メッセージを除く）。
MAX_CONTEXT_MESSAGES = 40


def _trim_messages(
    messages: list[Message], max_count: int = MAX_CONTEXT_MESSAGES
) -> list[Message]:
    """メッセージリストを最大件数に切り詰める。

    ターン境界（user → assistant → tool 結果）で削除するため、
    LLM には常に構造的に正しい会話が渡される。

    :param messages: 切り詰め対象のメッセージリスト。
    :param max_count: 保持するメッセージの最大件数。
    :return: 切り詰め後のメッセージリスト。
    """
    if len(messages) <= max_count:
        return messages

    trimmed = list(messages)
    while len(trimmed) > max_count:
        # Drop the first message
        trimmed.pop(0)
        # Keep removing until we land on a user message (start of a turn)
        while trimmed and trimmed[0].role != "user":
            trimmed.pop(0)

    # Fallback: if no user-message boundary was found, return the last max_count messages
    if not trimmed:
        return messages[-max_count:]

    return trimmed


async def run_loop(client: LLMClient, session: Session, system_prompt: str) -> None:
    """ツール呼び出しがなくなるまでエージェントループを実行する。

    :param client: LLM との通信に使用する :class:`~my_agent_core.llm.LLMClient`。
    :param session: 現在の会話セッション。
    :param system_prompt: LLM に渡すシステムプロンプト文字列。
    """
    context = _trim_messages(session.messages)
    messages = [Message(role="system", content=system_prompt)] + context

    while True:
        text_chunks: list[str] = []
        tool_calls: list[ToolCall] = []

        print("\n\033[36m[assistant]\033[0m ", end="", flush=True)

        async for chunk in client.stream(messages, TOOL_DEFINITIONS):
            if isinstance(chunk, str):
                print(chunk, end="", flush=True)
                text_chunks.append(chunk)
            elif isinstance(chunk, list):
                tool_calls = chunk

        print()  # newline after streaming

        # Build and save assistant message
        assistant_text = "".join(text_chunks) or None
        assistant_msg = Message(
            role="assistant",
            content=assistant_text,
            tool_calls=tool_calls if tool_calls else None,
        )
        append_and_save(session, assistant_msg)
        messages.append(assistant_msg)

        # If no tool calls, the agent is done
        if not tool_calls:
            break

        # Execute each tool call and collect results
        for tc in tool_calls:
            fn_name = tc.function.name
            fn_args = tc.function.arguments
            print(f"\n\033[33m[tool: {fn_name}]\033[0m ", end="", flush=True)

            result_text = execute_tool(fn_name, fn_args, session.cwd)

            # Show truncated preview
            preview = result_text[:200].replace("\n", " ")
            print(f"{preview}{'...' if len(result_text) > 200 else ''}")

            tool_msg = Message(
                role="tool",
                content=result_text,
                tool_call_id=tc.id,
                name=fn_name,
            )
            append_and_save(session, tool_msg)
            messages.append(tool_msg)

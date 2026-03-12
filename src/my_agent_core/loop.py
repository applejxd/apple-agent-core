"""Core agent loop: LLM call → tool execution → repeat."""

import sys
from typing import Any

from .llm import LLMClient
from .session import Session, append_and_save
from .tools import TOOL_DEFINITIONS, execute_tool
from .types import Message, ToolCall


async def run_loop(client: LLMClient, session: Session, system_prompt: str) -> None:
    """Run the agent loop until the LLM makes no more tool calls."""
    messages = [Message(role="system", content=system_prompt)] + session.messages

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

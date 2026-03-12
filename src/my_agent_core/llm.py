import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from .types import Message, ToolCall, ToolCallFunction

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-opus-4-5"


class LLMClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        self.api_key = api_key
        self.model = model
        self._client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/my-agent-core",
                "X-Title": "my-agent-core",
            },
            timeout=300.0,
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[str | list[ToolCall], None]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        # Accumulate tool_calls across chunks
        tool_calls_acc: dict[int, dict[str, Any]] = {}
        text_acc = ""

        async with self._client.stream("POST", OPENROUTER_URL, json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[6:]
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                choices = chunk.get("choices", [])
                if not choices:
                    continue
                delta = choices[0].get("delta", {})
                finish_reason = choices[0].get("finish_reason")

                # Text content
                if content := delta.get("content"):
                    text_acc += content
                    yield content  # stream text incrementally

                # Tool calls
                for tc_delta in delta.get("tool_calls", []):
                    idx = tc_delta["index"]
                    if idx not in tool_calls_acc:
                        tool_calls_acc[idx] = {
                            "id": tc_delta.get("id", ""),
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    acc = tool_calls_acc[idx]
                    if tc_delta.get("id"):
                        acc["id"] = tc_delta["id"]
                    fn = tc_delta.get("function", {})
                    if fn.get("name"):
                        acc["function"]["name"] += fn["name"]
                    if fn.get("arguments"):
                        acc["function"]["arguments"] += fn["arguments"]

                if finish_reason == "tool_calls" and tool_calls_acc:
                    yield [
                        ToolCall(
                            id=v["id"],
                            type=v["type"],
                            function=ToolCallFunction(
                                name=v["function"]["name"],
                                arguments=v["function"]["arguments"],
                            ),
                        )
                        for _, v in sorted(tool_calls_acc.items())
                    ]

    async def close(self) -> None:
        await self._client.aclose()


def create_client() -> LLMClient:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")
    model = os.environ.get("MODEL", DEFAULT_MODEL)
    return LLMClient(api_key=api_key, model=model)

"""OpenRouter SSE ストリーミングを使った LLM クライアントモジュール。

httpx を使って OpenRouter API と通信し、非同期ジェネレータとして
テキストチャンクおよびツール呼び出しをストリーミングする。
"""

import asyncio
import json
import os
from collections.abc import AsyncGenerator
from typing import Any

import httpx

from .types import Message, ToolCall, ToolCallFunction

#: OpenRouter API のエンドポイント URL。
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

#: デフォルトで使用する LLM モデル名。
DEFAULT_MODEL = "anthropic/claude-opus-4-5"

#: API リクエストの最大リトライ回数。
MAX_RETRIES = 3

#: リトライ時の待機秒数リスト（指数バックオフ）。
RETRY_DELAYS = [1.0, 2.0, 4.0]

#: リトライ対象とする HTTP ステータスコードのセット。
RETRY_STATUS_CODES = {429, 500, 502, 503, 504}


class LLMClient:
    """OpenRouter API クライアント。

    SSE ストリーミングと自動リトライをサポートする非同期 LLM クライアント。
    """

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL) -> None:
        """クライアントを初期化する。

        :param api_key: OpenRouter の API キー。
        :param model: 使用する LLM モデル名。デフォルトは :data:`DEFAULT_MODEL`。
        """
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
        """LLM レスポンスをストリーミングし、テキストチャンクまたはツール呼び出しを順次 yield する。

        トランジェントエラー（HTTP 429 / 5xx、ネットワークエラー）に対して
        最大 :data:`MAX_RETRIES` 回まで指数バックオフでリトライする。

        :param messages: LLM に送信する会話メッセージのリスト。
        :param tools: LLM に提供するツール定義のリスト（省略可）。
        :return: テキストチャンク（文字列）またはツール呼び出しリストを順次 yield する非同期ジェネレータ。
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [m.to_dict() for m in messages],
            "stream": True,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        for attempt in range(MAX_RETRIES + 1):
            try:
                # Accumulate tool_calls across chunks (reset each attempt)
                tool_calls_acc: dict[int, dict[str, Any]] = {}
                streaming_started = False  # track whether any content has been yielded

                async with self._client.stream(
                    "POST", OPENROUTER_URL, json=payload
                ) as response:
                    response.raise_for_status()  # raises before any yields
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

                        if content := delta.get("content"):
                            streaming_started = True
                            yield content

                        for tc_delta in delta.get("tool_calls", []):
                            streaming_started = True
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
                return  # success — stop retry loop

            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if (
                    status in RETRY_STATUS_CODES
                    and attempt < MAX_RETRIES
                    and not streaming_started
                ):
                    delay = RETRY_DELAYS[attempt]
                    print(
                        f"\n\033[33m[retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s"
                        f" (HTTP {status})]\033[0m",
                        flush=True,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

            except httpx.TransportError as e:
                if attempt < MAX_RETRIES and not streaming_started:
                    delay = RETRY_DELAYS[attempt]
                    print(
                        f"\n\033[33m[retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s"
                        f" ({type(e).__name__})]\033[0m",
                        flush=True,
                    )
                    await asyncio.sleep(delay)
                else:
                    raise

    async def close(self) -> None:
        """HTTP クライアントを閉じてリソースを解放する。"""
        await self._client.aclose()


def create_client() -> LLMClient:
    """環境変数から設定を読み込んで LLMClient インスタンスを生成する。

    :return: 設定済みの :class:`LLMClient` インスタンス。
    :raises ValueError: ``OPENROUTER_API_KEY`` 環境変数が未設定の場合。
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set")
    model = os.environ.get("MODEL", DEFAULT_MODEL)
    return LLMClient(api_key=api_key, model=model)

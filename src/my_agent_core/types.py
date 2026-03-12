"""LLM との会話に使うデータ型モジュール。

Message や Session など、エージェントループで用いる
dataclass を定義する。
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextContent:
    """テキスト形式のコンテンツブロック。"""

    type: str = "text"
    """コンテンツタイプ。常に ``"text"``。"""

    text: str = ""
    """テキスト本文。"""


@dataclass
class ToolCallFunction:
    """ツール呼び出しの関数名と引数を保持するデータクラス。"""

    name: str
    """呼び出す関数名。"""

    arguments: str
    """JSON 文字列形式の引数。"""


@dataclass
class ToolCall:
    """LLM が要求するツール呼び出しを表すデータクラス。"""

    id: str
    """ツール呼び出しの一意 ID。"""

    type: str = "function"
    """呼び出しタイプ。常に ``"function"``。"""

    function: ToolCallFunction = field(default_factory=lambda: ToolCallFunction("", ""))
    """呼び出す関数の名前と引数。"""


@dataclass
class Message:
    """LLM との会話の 1 ターンを表すメッセージ。

    OpenAI API の messages 配列の 1 要素に対応する。
    """

    role: str
    """メッセージの送信者ロール（ ``"system"`` / ``"user"`` / ``"assistant"`` / ``"tool"``）。"""

    content: str | list[Any] | None = None
    """メッセージ本文。テキスト文字列またはコンテンツブロックのリスト。"""

    tool_calls: list[ToolCall] | None = None
    """アシスタントが要求するツール呼び出しのリスト。"""

    tool_call_id: str | None = None
    """ツール結果メッセージのとき、対応するツール呼び出し ID。"""

    name: str | None = None
    """ツール名（ ``role="tool"`` のときに使用）。"""

    def to_dict(self) -> dict[str, Any]:
        """メッセージを API 送信用の辞書に変換する。

        :return: OpenAI API の messages 要素として使用できる辞書。
        """
        d: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            d["name"] = self.name
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Message":
        """辞書から Message インスタンスを復元する。

        :param d: OpenAI API レスポンスの messages 要素。
        :return: 復元された Message インスタンス。
        """
        tool_calls = None
        if d.get("tool_calls"):
            tool_calls = [
                ToolCall(
                    id=tc["id"],
                    type=tc.get("type", "function"),
                    function=ToolCallFunction(
                        name=tc["function"]["name"],
                        arguments=tc["function"]["arguments"],
                    ),
                )
                for tc in d["tool_calls"]
            ]
        return cls(
            role=d["role"],
            content=d.get("content"),
            tool_calls=tool_calls,
            tool_call_id=d.get("tool_call_id"),
            name=d.get("name"),
        )


@dataclass
class Session:
    """エージェントのセッション状態を保持するデータクラス。"""

    session_id: str
    """セッションの一意 ID（例: ``20260312-114537-a3b4c5d8``）。"""

    messages: list[Message] = field(default_factory=list)
    """セッション中の会話メッセージ履歴。"""

    cwd: str = "/workspace"
    """エージェントの作業ディレクトリ。"""

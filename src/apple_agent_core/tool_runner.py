"""コンテナ内ツール実行ランナー。

``docker exec`` 経由でホストから呼び出される薄いラッパー。
stdin から JSON リクエストを読み込み、:func:`~apple_agent_core.tools.execute_tool`
を実行して、結果を JSON として stdout に書き出す。

プロトコル:

入力 (stdin, 1 行):
    ``{"name": "read", "arguments": "{...}", "cwd": "/workspace/..."}``

出力 (stdout, 1 行):
    ``{"result": "..."}``
"""

import json
import sys


def main() -> None:
    """stdin からリクエストを読み込み、ツールを実行して stdout に結果を書く。"""
    from apple_agent_core.tools import execute_tool

    try:
        raw = sys.stdin.read()
        req = json.loads(raw)
        result = execute_tool(req["name"], req["arguments"], req["cwd"])
    except Exception as e:
        result = f"[tool_runner] エラー: {e}"

    sys.stdout.write(json.dumps({"result": result}, ensure_ascii=False) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()

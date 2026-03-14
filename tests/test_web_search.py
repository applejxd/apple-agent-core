"""tools.py の tool_web_search() のテスト。

ネットワーク呼び出しを DDGS().text をモックして検証する。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from apple_agent_core.tools import execute_tool, tool_web_search


FAKE_RESULTS = [
    {"title": "Python 公式", "href": "https://python.org", "body": "Python の公式サイト。"},
    {"title": "Python チュートリアル", "href": "https://docs.python.org", "body": "入門ガイド。"},
    {"title": "PyPI", "href": "https://pypi.org", "body": "パッケージ一覧。"},
]


def _mock_ddgs(results):
    """DDGS をモックして指定の結果を返すコンテキストマネージャを返す。"""
    mock_instance = MagicMock()
    mock_instance.text.return_value = results
    mock_cls = MagicMock(return_value=mock_instance)
    return patch("apple_agent_core.tools.DDGS", mock_cls)


class TestToolWebSearch:
    def test_returns_numbered_list(self):
        with _mock_ddgs(FAKE_RESULTS):
            result = tool_web_search("python", max_results=3)

        assert "1. Python 公式" in result
        assert "URL: https://python.org" in result
        assert "2. Python チュートリアル" in result
        assert "3. PyPI" in result

    def test_no_results(self):
        with _mock_ddgs([]):
            result = tool_web_search("xyzzy_nonexistent")

        assert "No results found" in result

    def test_exception_returns_error(self):
        mock_cls = MagicMock(side_effect=Exception("rate limit"))
        with patch("apple_agent_core.tools.DDGS", mock_cls):
            result = tool_web_search("test")

        assert "Error" in result
        assert "rate limit" in result

    def test_body_truncated_at_200_chars(self):
        long_body = "x" * 500
        with _mock_ddgs([{"title": "T", "href": "http://t.com", "body": long_body}]):
            result = tool_web_search("q")

        # body は 200 文字で切り詰められる
        assert "x" * 200 in result
        assert "x" * 201 not in result

    def test_max_results_passed_to_ddgs(self):
        mock_instance = MagicMock()
        mock_instance.text.return_value = FAKE_RESULTS[:2]
        mock_cls = MagicMock(return_value=mock_instance)
        with patch("apple_agent_core.tools.DDGS", mock_cls):
            tool_web_search("python", max_results=2)

        mock_instance.text.assert_called_once_with("python", max_results=2)


class TestExecuteToolWebSearch:
    """execute_tool() 経由での web_search ディスパッチ確認。"""

    @pytest.mark.anyio
    async def test_dispatches_web_search(self, monkeypatch, tmp_path):
        monkeypatch.setenv("APPLE_AGENT_SKIP_DOCKER", "1")
        with _mock_ddgs(FAKE_RESULTS):
            result = await execute_tool(
                "web_search",
                json.dumps({"query": "python", "max_results": 3}),
                str(tmp_path),
            )

        assert "Python 公式" in result

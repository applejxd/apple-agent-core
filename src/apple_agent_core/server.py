"""FastAPI + WebSocket サーバーモジュール（組み込みチャット UI 付き）。

ブラウザから使える Web チャット UI を HTML として組み込み、
WebSocket 経由でエージェントループとリアルタイム通信する。

エージェントループはホスト上で直接実行する。ツール実行は
``docker exec`` 経由でセッション用常駐コンテナに委譲する。
"""

import asyncio
import json
import os
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from .llm import LLMClient, create_client
from .session import append_and_save, new_session_id
from .tools import TOOL_DEFINITIONS, execute_tool
from .types import Message, Session
from .workspace import get_session_dir
from .workspace import list_sessions as ws_list_sessions
from .workspace import get_workspace_base, prepare_agent, setup_workspace

# ---------------------------------------------------------------------------
# HTML UI (embedded)
# ---------------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>apple-agent-core</title>
<style>
  :root {
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #8b949e;
    --accent: #58a6ff;
    --user-bg: #1f3c5c;
    --assistant-bg: #1a2332;
    --tool-bg: #1c1408;
    --tool-border: #bb8009;
    --result-bg: #0d1a0d;
    --result-border: #388bfd22;
    --error: #f85149;
    --success: #3fb950;
    --radius: 8px;
    --font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 14px;
    height: 100dvh;
    display: flex;
    flex-direction: column;
  }

  /* Header */
  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 10px 20px;
    display: flex;
    align-items: center;
    gap: 12px;
    flex-shrink: 0;
  }
  header .logo { font-size: 18px; font-weight: 700; color: var(--accent); }
  header .meta { color: var(--muted); font-size: 12px; font-family: var(--font-mono); }
  header .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #555; margin-left: auto; transition: background .3s;
  }
  header .dot.connected { background: var(--success); }

  /* Chat area */
  #chat {
    flex: 1;
    overflow-y: auto;
    padding: 20px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }
  #chat::-webkit-scrollbar { width: 6px; }
  #chat::-webkit-scrollbar-track { background: transparent; }
  #chat::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

  .msg { display: flex; flex-direction: column; gap: 4px; max-width: 860px; width: 100%; }
  .msg.user { align-self: flex-end; align-items: flex-end; }
  .msg.assistant, .msg.tool { align-self: flex-start; align-items: flex-start; }

  .msg-label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .05em;
    color: var(--muted);
    padding: 0 4px;
  }
  .msg.user .msg-label { color: var(--accent); }
  .msg.assistant .msg-label { color: var(--success); }
  .msg.tool .msg-label { color: var(--tool-border); }

  .bubble {
    padding: 12px 16px;
    border-radius: var(--radius);
    line-height: 1.6;
    white-space: pre-wrap;
    word-break: break-word;
    border: 1px solid var(--border);
  }
  .msg.user .bubble { background: var(--user-bg); border-color: #3373aa44; }
  .msg.assistant .bubble { background: var(--assistant-bg); }
  .msg.tool .bubble {
    background: var(--tool-bg);
    border-color: var(--tool-border);
    font-family: var(--font-mono);
    font-size: 12.5px;
  }

  /* Tool call card */
  .tool-card {
    background: var(--tool-bg);
    border: 1px solid var(--tool-border);
    border-radius: var(--radius);
    overflow: hidden;
    max-width: 860px;
    width: 100%;
  }
  .tool-card-header {
    background: #2b1f0088;
    padding: 8px 14px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: var(--font-mono);
    font-size: 12px;
  }
  .tool-card-header .tool-name { color: var(--tool-border); font-weight: 700; }
  .tool-card-header .tool-args { color: var(--muted); }
  .tool-card-body {
    padding: 10px 14px;
    font-family: var(--font-mono);
    font-size: 12px;
    line-height: 1.5;
    color: #adbac7;
    white-space: pre-wrap;
    word-break: break-all;
    max-height: 300px;
    overflow-y: auto;
  }
  .tool-card-body::-webkit-scrollbar { width: 4px; }
  .tool-card-body::-webkit-scrollbar-thumb { background: var(--border); }

  /* Streaming cursor */
  .cursor::after {
    content: '▋';
    animation: blink .8s step-end infinite;
    color: var(--accent);
  }
  @keyframes blink { 50% { opacity: 0; } }

  /* Input bar */
  footer {
    background: var(--surface);
    border-top: 1px solid var(--border);
    padding: 14px 20px;
    flex-shrink: 0;
  }
  .input-row {
    display: flex;
    gap: 10px;
    max-width: 860px;
    margin: 0 auto;
  }
  #input {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 10px 14px;
    color: var(--text);
    font-size: 14px;
    resize: none;
    height: 44px;
    max-height: 200px;
    outline: none;
    transition: border-color .2s;
    font-family: inherit;
    overflow-y: auto;
  }
  #input:focus { border-color: var(--accent); }
  #input::placeholder { color: var(--muted); }
  #send {
    background: var(--accent);
    color: #000;
    border: none;
    border-radius: var(--radius);
    padding: 0 20px;
    font-weight: 700;
    font-size: 14px;
    cursor: pointer;
    transition: opacity .2s;
    flex-shrink: 0;
  }
  #send:hover { opacity: .85; }
  #send:disabled { opacity: .4; cursor: not-allowed; }
  .hint { text-align: center; color: var(--muted); font-size: 11px; margin-top: 8px; }
</style>
</head>
<body>
<header>
  <span class="logo">⚡ apple-agent-core</span>
  <span class="meta" id="meta">connecting...</span>
  <span class="dot" id="dot"></span>
</header>

<div id="chat"></div>

<footer>
  <div class="input-row">
    <textarea id="input" placeholder="メッセージを入力... (Enter で送信、Shift+Enter で改行)" rows="1"></textarea>
    <button id="send">送信</button>
  </div>
  <div class="hint">read / write / edit / bash ツール使用可能 &nbsp;·&nbsp; YOLO mode</div>
</footer>

<script>
const chat = document.getElementById('chat');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send');
const meta = document.getElementById('meta');
const dot = document.getElementById('dot');

let sessionId;
let ws;
let streaming = false;
let currentBubble = null;
let currentText = '';

function connect() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  ws = new WebSocket(`${proto}//${location.host}/ws/${sessionId}`);

  ws.onopen = () => {
    dot.className = 'dot connected';
    meta.textContent = `session: ${sessionId.slice(0, 8)}...`;
    sendBtn.disabled = false;
  };

  ws.onclose = () => {
    dot.className = 'dot';
    meta.textContent = 'disconnected – reload to reconnect';
    sendBtn.disabled = true;
    setTimeout(connect, 3000);
  };

  ws.onerror = () => ws.close();

  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    handleMessage(msg);
  };
}

function scrollBottom() {
  chat.scrollTop = chat.scrollHeight;
}

function addMsg(role, label) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const lbl = document.createElement('div');
  lbl.className = 'msg-label';
  lbl.textContent = label;
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  div.appendChild(lbl);
  div.appendChild(bubble);
  chat.appendChild(div);
  scrollBottom();
  return bubble;
}

function addToolCard(name, args) {
  const card = document.createElement('div');
  card.className = 'tool-card msg';
  const header = document.createElement('div');
  header.className = 'tool-card-header';
  let argsPreview = '';
  try {
    const a = JSON.parse(args);
    const first = Object.entries(a)[0];
    if (first) argsPreview = `${first[0]}="${String(first[1]).slice(0, 60)}"`;
  } catch {}
  header.innerHTML = `<span>🔧</span><span class="tool-name">${escHtml(name)}</span><span class="tool-args">${escHtml(argsPreview)}</span>`;
  const body = document.createElement('div');
  body.className = 'tool-card-body';
  body.textContent = '⌛ executing...';
  card.appendChild(header);
  card.appendChild(body);
  chat.appendChild(card);
  scrollBottom();
  return body;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

let toolBodies = {};

function handleMessage(msg) {
  switch (msg.type) {
    case 'assistant_start':
      currentBubble = addMsg('assistant', '🤖 assistant');
      currentBubble.classList.add('cursor');
      currentText = '';
      streaming = true;
      sendBtn.disabled = true;
      break;

    case 'text_delta':
      currentText += msg.text;
      currentBubble.textContent = currentText;
      scrollBottom();
      break;

    case 'assistant_end':
      if (currentBubble) {
        currentBubble.classList.remove('cursor');
        if (!currentText.trim() && Object.keys(toolBodies).length === 0) {
          currentBubble.parentElement?.remove();
        }
      }
      streaming = false;
      sendBtn.disabled = false;
      input.focus();
      break;

    case 'tool_start':
      toolBodies[msg.tool_call_id] = addToolCard(msg.name, msg.args);
      break;

    case 'tool_end': {
      const body = toolBodies[msg.tool_call_id];
      if (body) {
        body.textContent = msg.result;
        delete toolBodies[msg.tool_call_id];
      }
      break;
    }

    case 'error':
      addMsg('tool', '❌ error').textContent = msg.message;
      sendBtn.disabled = false;
      streaming = false;
      break;
  }
}

function send() {
  const text = input.value.trim();
  if (!text || streaming || ws.readyState !== WebSocket.OPEN) return;

  addMsg('user', '🧑 you').textContent = text;
  ws.send(JSON.stringify({ type: 'user_message', text }));
  input.value = '';
  input.style.height = '44px';
  sendBtn.disabled = true;
  scrollBottom();
}

sendBtn.addEventListener('click', send);
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    send();
  }
});
// Auto-resize textarea
input.addEventListener('input', () => {
  input.style.height = '44px';
  input.style.height = Math.min(input.scrollHeight, 200) + 'px';
});

(async () => {
  const fromUrl = new URLSearchParams(location.search).get('session');
  if (fromUrl) {
    sessionId = fromUrl;
  } else {
    try {
      const resp = await fetch('/api/new-session');
      const data = await resp.json();
      sessionId = data.session_id;
    } catch {
      sessionId = crypto.randomUUID();
    }
  }
  history.replaceState({}, '', `?session=${sessionId}`);
  connect();
})();
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

app = FastAPI(title="apple-agent-core")

_clients: dict[str, LLMClient] = {}


def get_client() -> LLMClient:
    """API キーとモデルをキーとしてキャッシュした LLMClient を返す。

    :return: キャッシュ済みの :class:`~apple_agent_core.llm.LLMClient` インスタンス。
    :raises ValueError: ``OPENROUTER_API_KEY`` 環境変数が未設定の場合。
    """
    key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("MODEL", "")
    cache_key = f"{key}:{model}"
    if cache_key not in _clients:
        _clients[cache_key] = create_client()
    return _clients[cache_key]


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    """チャット UI の HTML を返す。

    :return: 組み込みチャット UI の HTML 文字列。
    """
    return HTML


@app.get("/api/sessions")
async def list_sessions() -> dict[str, Any]:
    """保存済みセッションの一覧を返す。

    :return: セッション情報（ID・メッセージ件数）のリストを含む辞書。
    """
    sessions = []
    for session_id in ws_list_sessions():
        msgs_file = get_session_dir(session_id) / "messages.json"
        try:
            data = json.loads(msgs_file.read_text())
            sessions.append({"id": session_id, "message_count": len(data)})
        except Exception:
            pass
    return {"sessions": sessions}


@app.get("/api/new-session")
async def api_new_session() -> dict[str, str]:
    """時刻順ソート可能な新しいセッション ID を返す。

    :return: 新規セッション ID を含む辞書（キー: ``session_id``）。
    """
    return {"session_id": new_session_id()}


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    """WebSocket 接続を受け付けてエージェントループを実行する。

    エージェントループはホストで直接実行する。
    ``APPLE_AGENT_SKIP_DOCKER=1`` が未設定の場合は、セッション用の常駐コンテナを起動して
    ツール実行をコンテナ内に委譲する。

    :param websocket: FastAPI WebSocket 接続オブジェクト。
    :param session_id: 接続するセッションの ID。
    """
    await websocket.accept()

    from .docker import ensure_image, ensure_session_container, should_skip_docker, stop_session_container

    if not should_skip_docker():
        setup_workspace(session_id)
        if not ensure_image():
            await websocket.send_json(
                {"type": "error", "message": "Docker イメージのビルドに失敗しました。"}
            )
            await websocket.close()
            return
        workspace_base = get_workspace_base()
        try:
            ensure_session_container(session_id, workspace_base)
        except Exception as e:
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.close()
            return

    cwd, session, system_prompt = prepare_agent(session_id)

    try:
        client = get_client()
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        return

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") != "user_message":
                continue

            user_text: str = data.get("text", "").strip()
            if not user_text:
                continue

            user_msg = Message(role="user", content=user_text)
            append_and_save(session, user_msg)

            await _run_agent(websocket, client, session, system_prompt)

    except WebSocketDisconnect:
        pass
    finally:
        if not should_skip_docker():
            stop_session_container(session_id)


async def _run_agent(
    ws: WebSocket,
    client: LLMClient,
    session: Session,
    system_prompt: str,
) -> None:
    """エージェントの 1 ターン（LLM 呼び出し → ツール実行）を WebSocket にストリーミングする。

    ツール呼び出しがなくなるまでループを継続する。

    :param ws: ストリーミング先の WebSocket 接続。
    :param client: LLM との通信に使用するクライアント。
    :param session: 現在の会話セッション。
    :param system_prompt: LLM に渡すシステムプロンプト。
    """
    messages = [Message(role="system", content=system_prompt)] + session.messages

    while True:
        text_chunks: list[str] = []
        tool_calls = []

        await ws.send_json({"type": "assistant_start"})

        async for chunk in client.stream(messages, TOOL_DEFINITIONS):
            if isinstance(chunk, str):
                text_chunks.append(chunk)
                await ws.send_json({"type": "text_delta", "text": chunk})
            else:
                tool_calls = chunk

        assistant_msg = Message(
            role="assistant",
            content="".join(text_chunks) or None,
            tool_calls=tool_calls if tool_calls else None,
        )
        append_and_save(session, assistant_msg)
        messages.append(assistant_msg)

        await ws.send_json({"type": "assistant_end"})

        if not tool_calls:
            break

        for tc in tool_calls:
            await ws.send_json(
                {
                    "type": "tool_start",
                    "tool_call_id": tc.id,
                    "name": tc.function.name,
                    "args": tc.function.arguments,
                }
            )

            result = await asyncio.to_thread(
                execute_tool, tc.function.name, tc.function.arguments, session.cwd, session.session_id
            )

            await ws.send_json(
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


def serve(host: str = "0.0.0.0", port: int = 8000) -> None:
    """uvicorn で FastAPI アプリを起動する。

    :param host: バインドするホストアドレス。デフォルトは全インターフェース。
    :param port: バインドするポート番号。デフォルトは 8000。
    """
    import uvicorn
    from dotenv import load_dotenv

    load_dotenv()
    uvicorn.run(app, host=host, port=port)

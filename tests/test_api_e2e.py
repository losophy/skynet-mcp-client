"""端到端集成验证（mock MCP server + fake LLM，不需真实 key/网络）。

验证：/api/chat SSE 流（progress/result）→ 工具执行 → 落库（sessions/messages/calls）。
运行：.venv\\Scripts\\python.exe tests/test_api_e2e.py
"""
from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time

sys.path.insert(0, r"\\wsl.localhost\Ubuntu\home\losophy\skynet-mcp")
sys.path.insert(0, r"D:\AgentProjects\skynet-mcp-client")

import uvicorn
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from skynet_mcp import tools as st
from skynet_mcp.config import Config
from skynet_mcp.main import build_mcp
from tests.mock_console import MockSkynetConsole

from backend import routes, state
from backend.agent import SkynetAgent
from backend.db import Database
from backend.mcp_client import McpConnection
from backend.tools_adapter import build_langchain_tools

PORT = 18768


def wait_port(port: int, tries: int = 60) -> bool:
    for _ in range(tries):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> None:
    # 1) 起 mock skynet console + HTTP MCP server
    mock = MockSkynetConsole()
    st.configure(Config(host=mock.host, port=mock.port))
    srv = uvicorn.Server(
        uvicorn.Config(
            build_mcp().streamable_http_app(),
            host="127.0.0.1",
            port=PORT,
            log_level="warning",
        )
    )
    threading.Thread(target=srv.run, daemon=True).start()
    assert wait_port(PORT), "MCP server 未启动"

    # 2) 注入 fake LLM 配置 + 临时 db + 真实 MCP 连接
    routes.LLM_MODEL = "fake-model"
    routes.LLM_API_KEY = "fake-key"
    state.db = Database(os.path.join(tempfile.mkdtemp(), "e2e.db"))

    async def build():
        conn = McpConnection(f"http://127.0.0.1:{PORT}/mcp")
        await conn.connect()
        meta = await conn.list_tools()
        tools, danger_map = build_langchain_tools(conn, meta)
        return conn, tools, danger_map

    conn, tools, danger_map = asyncio.run(build())
    state.mcp_conn = conn

    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "list", "args": {}, "id": "c_list"}],
            ),
            AIMessage(content="共 2 个服务：cmaster、cslave"),
        ]
    )
    routes._agent = SkynetAgent(tools, danger_map, model=model)

    # 3) 调 /api/chat（SSE）
    client = TestClient(routes.app) if hasattr(routes, "app") else None
    from backend.app import app

    client = TestClient(app)
    events: list[dict] = []
    session_id: str | None = None
    with client.stream("POST", "/api/chat", json={"message": "列出所有服务"}) as r:
        assert r.status_code == 200, r.text
        for line in r.iter_lines():
            if line.startswith("data: "):
                ev = json.loads(line[6:])
                events.append(ev)
                if ev["type"] == "session_created":
                    session_id = ev["session_id"]

    types = [e["type"] for e in events]
    print("chat events:", types)
    assert "session_created" in types
    assert "progress" in types, "缺少 progress 流"
    result = [e for e in events if e["type"] == "result"]
    assert result and "cmaster" in result[-1]["text"]
    assert session_id

    # 4) 落库验证
    calls = state.db.list_calls(session_id=session_id)
    print("calls:", [(c["tool"], c["status"], c["danger_level"]) for c in calls])
    assert any(c["tool"] == "list" and c["status"] == "ok" for c in calls)
    msgs = state.db.list_messages(session_id)
    roles = [m["role"] for m in msgs]
    print("messages roles:", roles)
    assert "user" in roles and "assistant" in roles

    print("E2E PASS")


if __name__ == "__main__":
    main()

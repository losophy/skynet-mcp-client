"""服务冒烟：真实起 mock MCP server + 客户端后端（uvicorn），httpx 验证 API。

运行：.venv\\Scripts\\python.exe tests/test_server_smoke.py
"""
from __future__ import annotations

import os
import socket
import sys
import threading
import time

sys.path.insert(0, r"\\wsl.localhost\Ubuntu\home\losophy\skynet-mcp")
sys.path.insert(0, r"D:\AgentProjects\skynet-mcp-client")

import httpx
import uvicorn

from skynet_mcp import tools as st
from skynet_mcp.config import Config
from skynet_mcp.main import build_mcp
from tests.mock_console import MockSkynetConsole

MCP_PORT = 18769
CLIENT_PORT = 8101


def wait_port(port: int, tries: int = 80) -> bool:
    for _ in range(tries):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> None:
    # mock skynet console + HTTP MCP server
    mock = MockSkynetConsole()
    st.configure(Config(host=mock.host, port=mock.port))
    threading.Thread(
        target=uvicorn.Server(
            uvicorn.Config(
                build_mcp().streamable_http_app(),
                host="127.0.0.1",
                port=MCP_PORT,
                log_level="warning",
            )
        ).run,
        daemon=True,
    ).start()
    assert wait_port(MCP_PORT)

    # 客户端后端（真实 uvicorn，独立进程级服务）
    os.environ["MCP_URL"] = f"http://127.0.0.1:{MCP_PORT}/mcp"
    import backend.app as app  # noqa: F401  确保加载

    from backend import state

    # 用临时 db 避免污染 data/
    import tempfile

    from backend.db import Database

    state.db = Database(os.path.join(tempfile.mkdtemp(), "smoke.db"))
    state.mcp_conn = type(state.mcp_conn)(state.mcp_conn.url)  # 用新连接（MCP_URL 指向 mock）

    srv = uvicorn.Server(
        uvicorn.Config(app.app, host="127.0.0.1", port=CLIENT_PORT, log_level="warning")
    )
    threading.Thread(target=srv.run, daemon=True).start()
    assert wait_port(CLIENT_PORT)

    # 验证
    with httpx.Client(timeout=10) as c:
        r = c.get(f"http://127.0.0.1:{CLIENT_PORT}/api/status")
        s = r.json()
        print("status:", s)
        assert s["connected"] is True and s["tool_count"] == 32

        r = c.get(f"http://127.0.0.1:{CLIENT_PORT}/api/tools")
        tools = r.json()["tools"]
        print("tools:", len(tools), "| kill danger:", [t["danger"] for t in tools if t["name"] == "kill"])
        assert len(tools) == 32
        assert any(t["name"] == "kill" and t["danger"] == "high" for t in tools)

        r = c.get(f"http://127.0.0.1:{CLIENT_PORT}/")
        print("index status:", r.status_code, "| has root div:", 'id="root"' in r.text)
        assert r.status_code == 200 and 'id="root"' in r.text

    srv.should_exit = True
    print("SMOKE PASS")


if __name__ == "__main__":
    main()

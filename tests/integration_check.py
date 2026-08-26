"""集成验证：本地 uvicorn 起 MCP server（skynet-mcp build_mcp + mock console），
客户端 McpConnection 连接并调用。

运行（Windows 侧，客户端 venv）：
    .venv\\Scripts\\python.exe tests/integration_check.py
"""
from __future__ import annotations

import asyncio
import socket
import sys
import threading
import time

import uvicorn

# 让客户端能 import skynet-mcp（WSL 内）的 build_mcp / mock console
sys.path.insert(0, r"\\wsl.localhost\Ubuntu\home\losophy\skynet-mcp")
sys.path.insert(0, r"D:\AgentProjects\skynet-mcp-client")

from skynet_mcp import tools  # noqa: E402
from skynet_mcp.config import Config  # noqa: E402
from skynet_mcp.main import build_mcp  # noqa: E402
from tests.mock_console import MockSkynetConsole  # noqa: E402

from backend.mcp_client import McpConnection  # noqa: E402

PORT = 18765


def wait_port(port: int, tries: int = 60) -> bool:
    for _ in range(tries):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> None:
    mock = MockSkynetConsole()
    tools.configure(Config(host=mock.host, port=mock.port))
    server = build_mcp()
    app = server.streamable_http_app()
    cfg = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    srv = uvicorn.Server(cfg)
    threading.Thread(target=srv.run, daemon=True).start()
    if not wait_port(PORT):
        print("FAIL: uvicorn server did not start")
        return

    async def run() -> None:
        conn = McpConnection(f"http://127.0.0.1:{PORT}/mcp")
        await conn.connect()
        print("server_name:", conn.server_name)
        listed = await conn.list_tools()
        print("tool_count:", len(listed))
        res = await conn.call_tool("list", {})
        print("call list -> ok:", res["ok"], "| first line:", res["text"].splitlines()[0] if res["text"] else "")
        res2 = await conn.call_tool("kill", {"addr": "3"})
        print("call kill(unknown) -> ok:", res2["ok"], "| text:", res2["text"].strip()[:60])
        await conn.close()
        print("close ok; connected after close:", conn.connected)

    asyncio.run(run())
    mock.close()


if __name__ == "__main__":
    main()

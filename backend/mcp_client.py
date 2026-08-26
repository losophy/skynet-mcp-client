"""MCP 连接层：经 streamable-http 连接 WSL 内的 skynet MCP server。

单条长连接复用；server 重启导致 session 失效或断连时懒重连并刷新工具缓存。
工具级失败（skynet <CMD Error>）在 MCP 协议里表现为 isError=True，不是异常，
这里统一转成 {ok: bool, text: str}，由上层决定如何展示。
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)

# stat/mem 等命令要广播到全服，read 超时调大
READ_TIMEOUT = 120.0


class McpError(Exception):
    """MCP 调用/连接错误（断连、重连后仍失败等）。"""


class McpConnection:
    """管理到 MCP server 的 HTTP 连接与工具缓存。"""

    def __init__(self, url: str) -> None:
        self.url = url
        self._client: httpx.AsyncClient | None = None
        self._ctx: object | None = None
        self._session: ClientSession | None = None
        self._tools_cache: list[dict] | None = None
        self._server_name: str | None = None
        self._lock = asyncio.Lock()

    # -- 连接管理 ----------------------------------------------------------

    async def connect(self) -> None:
        """建立连接并完成 initialize（幂等：已连接则跳过）。"""
        if self._session is not None:
            return
        async with self._lock:
            if self._session is not None:
                return
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=5.0, read=READ_TIMEOUT, write=30.0, pool=10.0
                )
            )
            ctx = streamable_http_client(self.url, http_client=client)
            try:
                read, write, _ = await ctx.__aenter__()
                session = ClientSession(read, write)
                await session.__aenter__()
                init = await session.initialize()
            except Exception:
                await ctx.__aexit__(None, None, None)
                await client.aclose()
                raise
            self._client, self._ctx, self._session = client, ctx, session
            self._server_name = init.serverInfo.name
            logger.info("MCP connected: %s (%s)", self._server_name, self.url)

    async def close(self) -> None:
        """关闭连接（清理顺序：先 session 后 transport）。"""
        session, ctx, client = self._session, self._ctx, self._client
        self._session, self._ctx, self._client = None, None, None
        self._tools_cache, self._server_name = None, None
        if session is not None:
            await session.__aexit__(None, None, None)
        if ctx is not None:
            await ctx.__aexit__(None, None, None)
        if client is not None:
            await client.aclose()

    async def reconnect(self) -> None:
        await self.close()
        await self.connect()

    @property
    def connected(self) -> bool:
        return self._session is not None

    @property
    def server_name(self) -> str | None:
        return self._server_name

    # -- 工具 --------------------------------------------------------------

    async def list_tools(self, force: bool = False) -> list[dict]:
        """返回 [{name, description, inputSchema}]，缓存复用。"""
        if self._tools_cache is not None and not force:
            return self._tools_cache
        await self.connect()
        try:
            listed = await self._session.list_tools()
        except Exception as exc:
            logger.warning("list_tools failed (%s), reconnecting...", exc)
            await self.reconnect()
            listed = await self._session.list_tools()
        tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema or {},
            }
            for t in listed.tools
        ]
        self._tools_cache = tools
        return tools

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用工具，返回 {ok, text}。断连时自动重连重试一次。"""
        await self.connect()
        try:
            result = await self._session.call_tool(name, arguments)
        except Exception as exc:
            logger.warning("call_tool(%s) failed (%s), reconnecting once...", name, exc)
            await self.reconnect()
            try:
                result = await self._session.call_tool(name, arguments)
            except Exception as exc2:
                raise McpError(f"MCP 调用失败（重连后仍失败）：{exc2}") from exc
        text = "".join(
            c.text for c in result.content if getattr(c, "text", None) is not None
        )
        return {"ok": not result.isError, "text": text}

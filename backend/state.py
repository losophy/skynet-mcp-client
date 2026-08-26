"""共享实例（避免 app ↔ routes 循环导入）：settings / MCP 连接 / DB。"""
from __future__ import annotations

from .config import Settings
from .db import Database
from .mcp_client import McpConnection

settings = Settings()
mcp_conn = McpConnection(settings.mcp_url)
db = Database(settings.db_path)

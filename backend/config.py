"""客户端配置：MCP 连接、HTTP 服务、数据库路径、LLM（.env 可配）。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_MCP_URL = os.getenv("MCP_URL", "http://127.0.0.1:8765/mcp")
DEFAULT_HTTP_PORT = int(os.getenv("CLIENT_HTTP_PORT", "8100"))
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "skynet_mcp_client.db"

# LLM 配置（OpenAI 兼容，.env 里配；留空则对话功能不可用但工具面板可用）
LLM_MODEL = os.getenv("LLM_MODEL_NAME", "")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")


@dataclass(frozen=True)
class Settings:
    """客户端运行配置。"""

    mcp_url: str = DEFAULT_MCP_URL
    http_port: int = DEFAULT_HTTP_PORT
    db_path: Path = DEFAULT_DB_PATH

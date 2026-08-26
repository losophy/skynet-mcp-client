"""FastAPI 入口：路由挂载、前端静态托管、MCP 连接生命周期。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from . import state

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
DIST_DIR = FRONTEND_DIR / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时尝试连接；失败不阻塞（/api/status 会显示未连接，前端提示重连）
    try:
        await state.mcp_conn.connect()
        logging.info("MCP connected: %s", state.mcp_conn.server_name)
    except Exception as exc:
        logging.warning("MCP connect failed at startup: %s", exc)
    yield
    await state.mcp_conn.close()
    state.db.close()


app = FastAPI(title="skynet-mcp-client", lifespan=lifespan)

from . import routes  # noqa: E402  (需要 app 实例)

app.include_router(routes.router)

# 前端静态托管（同源部署，无 CORS 问题）：优先 build 产物 dist，其次 dev 入口
if DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="frontend")
elif (FRONTEND_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

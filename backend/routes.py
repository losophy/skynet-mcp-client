"""REST + SSE 路由：状态、工具、对话（SSE 流式）、危险审批、会话历史、审计。

SSE 事件类型（对齐前端 agentApi.ts）：
  progress / tool_call / human_approval / result / error / session_created
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from pydantic import BaseModel, Field

from . import state
from . import danger as danger_mod
from .agent import OUT_OF_SCOPE_HINT, SkynetAgent
from .config import LLM_API_KEY, LLM_MODEL
from .parsers import parse_tool_output
from .tools_adapter import build_langchain_tools

router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# 状态 / 工具
# ---------------------------------------------------------------------------


@router.get("/status")
async def status() -> dict:
    try:
        tools = await state.mcp_conn.list_tools()
    except Exception as exc:
        return {
            "connected": False,
            "mcp_url": state.settings.mcp_url,
            "server_name": None,
            "tool_count": 0,
            "llm_configured": bool(LLM_MODEL and LLM_API_KEY),
            "last_error": str(exc),
        }
    return {
        "connected": True,
        "mcp_url": state.settings.mcp_url,
        "server_name": state.mcp_conn.server_name,
        "tool_count": len(tools),
        "llm_configured": bool(LLM_MODEL and LLM_API_KEY),
        "last_error": None,
    }


@router.get("/tools")
async def tools_list() -> dict:
    try:
        meta = await state.mcp_conn.list_tools()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"MCP 连接失败：{exc}")
    enriched = [
        {
            **t,
            "danger": danger_mod.danger_from_description(t.get("description", "")),
        }
        for t in meta
    ]
    return {"tools": enriched}


# ---------------------------------------------------------------------------
# Agent 生命周期
# ---------------------------------------------------------------------------

_agent: SkynetAgent | None = None
_agent_lock = asyncio.Lock()


async def get_agent() -> SkynetAgent:
    """懒加载：连接 MCP → 拉工具 → 构建 LangChain 工具 + Agent。"""
    global _agent
    if _agent is None:
        async with _agent_lock:
            if _agent is None:
                if not (LLM_MODEL and LLM_API_KEY):
                    raise HTTPException(
                        status_code=503,
                        detail="LLM 未配置：请在 .env 设置 LLM_MODEL_NAME / LLM_API_KEY / LLM_BASE_URL",
                    )
                meta = await state.mcp_conn.list_tools()
                tools, danger_map = build_langchain_tools(state.mcp_conn, meta)
                _agent = SkynetAgent(tools, danger_map)
    return _agent


# ---------------------------------------------------------------------------
# 对话（SSE）
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str | None = None


class FeedbackRequest(BaseModel):
    session_id: str
    decision: str = Field(..., pattern="^(approve|reject)$")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _attach_chart(render: dict, tool: str) -> dict:
    """给可图形化工具附加 chart 配置（前端据此画图）。"""
    if tool == "mem" and render.get("rows"):
        render["chart"] = {
            "type": "bar",
            "xField": "addr",
            "yField": "size_bytes",
            "title": "各服务 lua 内存",
        }
    elif tool == "stat" and render.get("rows"):
        render["chart"] = {
            "type": "bar",
            "xField": "addr",
            "yField": "queue",
            "title": "消息队列长度",
        }
    return render


def _record_tool_calls(
    agent: SkynetAgent, messages: list, session_id: str | None
) -> dict | None:
    """从最终 state.messages 配对 AIMessage.tool_calls 与 ToolMessage，全量落库。

    返回最后一个成功工具调用的 render（供前端图形化展示），没有则 None。
    """
    msgs = list(messages)
    last_render: dict | None = None
    for i, m in enumerate(msgs):
        tcs = getattr(m, "tool_calls", None)
        if not tcs:
            continue
        for tc in tcs:
            name = tc["name"]
            args = tc.get("args", {})
            danger = agent._danger_of(name, args)
            confirm_required = 1 if danger != danger_mod.DANGER_SAFE else 0

            tm = next(
                (
                    x
                    for x in msgs[i + 1 :]
                    if getattr(x, "tool_call_id", None) == tc["id"]
                ),
                None,
            )
            call_id = state.db.add_call(
                session_id=session_id,
                tool=name,
                params=args,
                danger_level=danger,
                confirm_required=confirm_required,
                source="agent",
                status="pending",
            )
            if tm is None:
                continue  # interrupt 挂起未执行（resume 后会再走这里）
            content = getattr(tm, "content", "") or ""
            if "拒绝" in content:
                state.db.update_call(call_id, confirmed="reject", status="rejected", result={"text": content})
                continue
            render = _attach_chart(parse_tool_output(name, content), name)
            state.db.update_call(
                call_id,
                ok=1,
                confirmed="approve" if confirm_required else None,
                status="ok",
                duration_ms=None,
                result={"text": content, "render": render},
            )
            last_render = render
    return last_render


async def _emit_stream(
    agent: SkynetAgent, config: dict, initial: dict | Command, session_id: str | None
):
    """驱动 graph.astream，转 SSE 事件；结束后落库工具调用与 AI 回复。

    兜底：本次执行未调用任何工具却直接作答（LLM 违规自由发挥）时，
    把最终文本替换为 OUT_OF_SCOPE_HINT，保证用户只看到工具结果或提示。
    """
    last_text = ""
    start_n = len((agent.graph.get_state(config).values or {}).get("messages", []))
    try:
        async for mode, chunk in agent.graph.astream(
            initial,
            config,
            stream_mode=["messages", "updates"],
        ):
            if mode == "messages":
                msg, _meta = chunk
                # 只推 LLM 生成的 token（AIMessage）；ToolMessage 等工具原始输出不进对话流
                if getattr(msg, "type", "") == "ai" and getattr(msg, "content", None):
                    last_text += msg.content
                    yield _sse({"type": "progress", "content": msg.content})
            elif mode == "updates":
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        for item in update:
                            value = getattr(item, "value", item) or {}
                            yield _sse(
                                {
                                    "type": "human_approval",
                                    "pending_calls": value.get("pending_calls", []),
                                }
                            )
    except Exception as exc:
        yield _sse({"type": "error", "message": f"Agent 执行失败：{exc}"})
        return

    # 结束：落库 + 取最终 AI 回复
    gs = agent.graph.get_state(config)
    values = gs.values or {}
    msgs = values.get("messages", [])
    if not gs.next and not values.get("__interrupt__"):
        # 落库（call/messages），但不再把原始表格传给前端：
        # LLM 已基于工具真实输出翻译为中文 markdown 表格，统一由前端 MarkdownMessage 渲染，避免重复。
        _record_tool_calls(agent, msgs, session_id)
    last_render = None
    if msgs:
        final = msgs[-1]
        if hasattr(final, "content") and final.content:
            last_text = final.content
    # 兜底：本次执行未产生任何 ToolMessage（LLM 没调工具直接自由作答）→ 替换为固定提示
    if not gs.next and not values.get("__interrupt__"):
        if not any(isinstance(m, ToolMessage) for m in msgs[start_n:]) and last_text.strip():
            last_text = OUT_OF_SCOPE_HINT
        # 正常完成才发 result；interrupt 挂起时对话未结束（等用户审批），
        # 不发 result 以免前端清掉审批卡，resume 后由下一轮 _emit_stream 出结果。
        yield _sse({"type": "result", "text": last_text, "render": last_render})


@router.post("/chat")
async def chat(req: ChatRequest) -> StreamingResponse:
    if not (LLM_MODEL and LLM_API_KEY):
        raise HTTPException(
            status_code=503,
            detail="LLM 未配置：请在 .env 设置 LLM_MODEL_NAME / LLM_API_KEY / LLM_BASE_URL",
        )
    agent = await get_agent()
    session_id = req.session_id or uuid.uuid4().hex[:16]
    state.db.create_session(session_id)
    state.db.add_message(session_id, "user", req.message)

    async def gen():
        if req.session_id is None:
            yield _sse({"type": "session_created", "session_id": session_id})
        config = {"configurable": {"thread_id": session_id}}
        async for ev in _emit_stream(
            agent, config, {"messages": [HumanMessage(content=req.message)]}, session_id
        ):
            yield ev
        # 落库 AI 回复（result 事件里已含最终文本）
        gs = agent.graph.get_state(config)
        msgs = (gs.values or {}).get("messages", [])
        if msgs and hasattr(msgs[-1], "content"):
            state.db.add_message(session_id, "assistant", msgs[-1].content or "")

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/human-feedback")
async def human_feedback(req: FeedbackRequest) -> StreamingResponse:
    if not (LLM_MODEL and LLM_API_KEY):
        raise HTTPException(status_code=503, detail="LLM 未配置")
    agent = await get_agent()
    config = {"configurable": {"thread_id": req.session_id}}

    async def gen():
        async for ev in _emit_stream(
            agent, config, Command(resume={"decision": req.decision}), req.session_id
        ):
            yield ev
        gs = agent.graph.get_state(config)
        msgs = (gs.values or {}).get("messages", [])
        if msgs and hasattr(msgs[-1], "content"):
            state.db.add_message(req.session_id, "assistant", msgs[-1].content or "")

    return StreamingResponse(gen(), media_type="text/event-stream")


# ---------------------------------------------------------------------------
# 会话历史
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def sessions_list() -> list[dict]:
    return state.db.list_sessions()


@router.get("/sessions/{session_id}")
async def session_detail(session_id: str) -> dict:
    s = state.db.get_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {**s, "messages": state.db.list_messages(session_id)}


@router.delete("/sessions/{session_id}")
async def session_delete(session_id: str) -> dict:
    state.db.delete_session(session_id)
    return {"ok": True}


# ---------------------------------------------------------------------------
# 调用历史 / 审计
# ---------------------------------------------------------------------------


@router.get("/calls")
async def calls_list(
    session_id: str | None = None,
    tool: str | None = None,
    danger: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    return state.db.list_calls(
        session_id=session_id, tool=tool, danger=danger, status=status, limit=limit
    )


@router.get("/audit")
async def audit_list(
    tool: str | None = None,
    danger: str | None = None,
    status: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """危险命令审计：默认只看 medium/high。"""
    if danger is None:
        rows = state.db.list_calls(
            tool=tool, status=status, limit=limit
        )
        rows = [r for r in rows if r["danger_level"] != "safe"]
        return rows
    return state.db.list_calls(tool=tool, danger=danger, status=status, limit=limit)

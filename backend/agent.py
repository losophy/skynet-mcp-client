"""LangGraph Agent：对话 → LLM 决策 → MCP 工具执行，危险工具 HITL 拦截。

节点：
  call_model     LLM（bind_tools）产出 AIMessage（可能带 tool_calls）
  execute_tools  若含危险调用 → interrupt() 暂停等用户审批（approve/reject）；
                 否则执行全部工具并回填 ToolMessage，回到 call_model

由 routes 层用 graph.astream(stream_mode="messages") 驱动，流式输出 token；
interrupt 时 graph 停在 execute_tools，SSE 层把 __interrupt__ 转成 human_approval
事件，用户审批后用 Command(resume={"decision": ...}) 恢复。
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from . import danger as danger_mod
from .config import LLM_API_KEY, LLM_BASE_URL, LLM_MODEL

SYSTEM_PROMPT = """你是 skynet 游戏服务器的调试助手，通过 MCP 工具控制 skynet debug console。
- 用中文回答，简洁直接；工具返回原始文本时，提炼关键信息呈现。
- 需要服务地址时，先用 list 工具获取真实地址，再调用需要地址的工具。
- 危险命令（kill/exit/signal/inject/call/raw_command 等）会被系统拦截并要求用户审批，
  你正常发起调用即可，审批由用户完成。
- 涉及多个服务的结果用列表/表格形式组织。"""


class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    pending: dict[str, Any] | None


def _build_model(tools: list[StructuredTool]) -> ChatOpenAI:
    """构造 OpenAI 兼容 LLM（.env 配置）。未配置时调用会报错，由上层转 503。"""
    return ChatOpenAI(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        temperature=0,
    ).bind_tools(tools)


class SkynetAgent:
    """持有一组 MCP 工具的 LangGraph 对话 Agent（含危险工具 HITL 拦截）。"""

    def __init__(
        self,
        tools: list[StructuredTool],
        danger_map: dict[str, str] | None = None,
        model: Any | None = None,
    ) -> None:
        self.tools = tools
        self._by_name = {t.name: t for t in tools}
        self.danger_map = danger_map or {}
        # 测试可注入 fake model；生产 None → 每次从 .env 构建
        self._model = model
        self.graph = self._build_graph()

    def _danger_of(self, name: str, arguments: dict | None) -> str:
        lvl = self.danger_map.get(name)
        if lvl is None:
            return danger_mod.DANGER_SAFE
        if name == "raw_command":
            # danger_map 里 raw_command 是 high（工具级），实际按命令行首词细化
            cmdline = (arguments or {}).get("command_line", "")
            return danger_mod.danger_for_raw_command(cmdline)
        return lvl

    def _get_model(self) -> Any:
        if self._model is not None:
            return self._model
        return _build_model(self.tools)

    def _build_graph(self) -> Any:
        async def call_model(state: AgentState) -> dict:
            messages = [SystemMessage(content=SYSTEM_PROMPT), *state["messages"]]
            resp = await self._get_model().ainvoke(messages)
            return {"messages": [resp], "pending": None}

        def should_continue(state: AgentState) -> str:
            last = state["messages"][-1]
            return "tools" if getattr(last, "tool_calls", None) else END

        async def execute_tools(state: AgentState) -> dict:
            last = state["messages"][-1]
            tool_calls = getattr(last, "tool_calls", []) or []
            if not tool_calls:
                return {"pending": None}

            pending = [
                {
                    "id": tc["id"],
                    "name": tc["name"],
                    "arguments": tc.get("args", {}),
                    "danger": self._danger_of(tc["name"], tc.get("args", {})),
                }
                for tc in tool_calls
            ]

            # HITL：任一危险调用 → interrupt 暂停，等用户 approve/reject
            if any(p["danger"] != danger_mod.DANGER_SAFE for p in pending):
                decision = interrupt({"pending_calls": pending})
                if not isinstance(decision, dict) or decision.get("decision") != "approve":
                    msgs = [
                        ToolMessage(
                            content="用户拒绝了该命令的执行。请向用户说明并询问下一步。",
                            tool_call_id=p["id"],
                        )
                        for p in pending
                    ]
                    return {"messages": msgs, "pending": None}

            # 执行全部工具（含审批通过的危险调用）
            msgs = []
            for p in pending:
                tool = self._by_name.get(p["name"])
                if tool is None:
                    msgs.append(
                        ToolMessage(content=f"未知工具：{p['name']}", tool_call_id=p["id"])
                    )
                    continue
                try:
                    out = await tool.ainvoke(p["arguments"])
                    content = out if isinstance(out, str) else str(out)
                except Exception as exc:
                    content = f"工具执行失败：{exc}"
                msgs.append(ToolMessage(content=content, tool_call_id=p["id"]))
            return {"messages": msgs, "pending": None}

        g = StateGraph(AgentState)
        g.add_node("call_model", call_model)
        g.add_node("execute_tools", execute_tools)
        g.add_edge(START, "call_model")
        g.add_conditional_edges(
            "call_model", should_continue, {"tools": "execute_tools", END: END}
        )
        g.add_edge("execute_tools", "call_model")
        # interrupt()/Command(resume) 需要 checkpointer（thread_id 标识会话）；
        # P3 用内存版，P5 换 SQLite 持久化
        return g.compile(checkpointer=MemorySaver())

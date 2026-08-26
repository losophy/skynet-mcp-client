"""Graph 行为验证（fake LLM，不需真实 key/网络）：
1. 正常工具调用流（list → 结果 → 最终回复）
2. 危险工具触发 interrupt，approve 后执行
3. 危险工具 interrupt，reject 后不执行

运行：.venv\\Scripts\\python.exe tests/test_agent_graph.py
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, r"D:\AgentProjects\skynet-mcp-client")

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.types import Command
from pydantic import BaseModel

from backend.agent import SkynetAgent

executed: list[str] = []


class Args(BaseModel):
    pass


class KillArgs(BaseModel):
    addr: str


async def fake_list(**kw) -> str:
    executed.append("list")
    return ":01000004\tsnlua cmaster\n:01000005\tsnlua cslave"


async def fake_kill(**kw) -> str:
    executed.append("kill:" + str(kw.get("addr")))
    return "killed " + str(kw.get("addr"))


def build_agent(model):
    list_tool = StructuredTool.from_function(
        name="list", description="列出所有服务", coroutine=fake_list, args_schema=Args
    )
    kill_tool = StructuredTool.from_function(
        name="kill",
        description="【危险】强制中止一个 lua 服务",
        coroutine=fake_kill,
        args_schema=KillArgs,
    )
    danger_map = {"list": "safe", "kill": "high"}
    return SkynetAgent([list_tool, kill_tool], danger_map, model=model)


def collect_events(graph, initial, config):
    """跑完 astream，返回 (events, interrupts, final_text)。"""
    interrupts = []

    async def run():
        out = []
        async for mode, chunk in graph.astream(
            initial, config, stream_mode=["messages", "updates"]
        ):
            if mode == "updates":
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        for item in update:
                            value = getattr(item, "value", item) or {}
                            interrupts.append(value)
            out.append(mode)
        state = graph.get_state(config)
        msgs = (state.values or {}).get("messages", [])
        final_text = msgs[-1].content if msgs and hasattr(msgs[-1], "content") else ""
        return out, final_text

    out, final_text = asyncio.run(run())
    return out, interrupts, final_text


def test_normal_tool_call() -> None:
    executed.clear()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "list", "args": {}, "id": "call_list"}],
            ),
            AIMessage(content="当前共有 2 个服务：cmaster、cslave"),
        ]
    )
    agent = build_agent(model)
    config = {"configurable": {"thread_id": "t-normal"}}
    events, interrupts, final = collect_events(
        agent.graph, {"messages": [HumanMessage(content="列出所有服务")]}, config
    )
    assert "list" in executed, f"list 未执行: {executed}"
    assert interrupts == [], f"不应触发 interrupt: {interrupts}"
    assert "cmaster" in final, f"最终回复异常: {final!r}"
    # 工具结果应回填成 ToolMessage
    state = agent.graph.get_state(config)
    msgs = state.values["messages"]
    assert any(isinstance(m, ToolMessage) for m in msgs), "缺少 ToolMessage"
    print("PASS 1 正常工具调用")


def test_danger_interrupt_approve() -> None:
    executed.clear()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "kill", "args": {"addr": ":01000004"}, "id": "call_kill"}
                ],
            ),
            AIMessage(content="已执行 kill"),
        ]
    )
    agent = build_agent(model)
    config = {"configurable": {"thread_id": "t-approve"}}
    events, interrupts, final = collect_events(
        agent.graph, {"messages": [HumanMessage(content="杀掉 :01000004")]}, config
    )
    assert interrupts, "应触发 interrupt"
    pc = interrupts[0].get("pending_calls", [])
    assert pc and pc[0]["name"] == "kill" and pc[0]["danger"] == "high"
    assert not executed, "approve 前不应执行 kill"
    # 审批通过 → resume
    events2, interrupts2, final = collect_events(
        agent.graph, Command(resume={"decision": "approve"}), config
    )
    assert "kill::01000004" in executed, f"approve 后应执行 kill: {executed}"
    assert interrupts2 == []
    print("PASS 2 危险工具 interrupt + approve")


def test_danger_interrupt_reject() -> None:
    executed.clear()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {"name": "kill", "args": {"addr": "3"}, "id": "call_kill2"}
                ],
            ),
            AIMessage(content="明白了，我不执行 kill"),
        ]
    )
    agent = build_agent(model)
    config = {"configurable": {"thread_id": "t-reject"}}
    _, interrupts, _ = collect_events(
        agent.graph, {"messages": [HumanMessage(content="杀掉 3")]}, config
    )
    assert interrupts, "应触发 interrupt"
    # 拒绝 → resume reject
    _, _, final = collect_events(
        agent.graph, Command(resume={"decision": "reject"}), config
    )
    assert not executed, f"reject 后不应执行 kill: {executed}"
    assert "kill" not in final.lower() or "不执行" in final
    print("PASS 3 危险工具 interrupt + reject")


def test_out_of_scope_llm_free_text_replaced() -> None:
    """LLM 未调工具直接自由作答 → routes 兜底替换为固定提示。"""
    import json
    import os
    import tempfile

    from backend import routes, state
    from backend.agent import OUT_OF_SCOPE_HINT
    from backend.db import Database

    state.db = Database(os.path.join(tempfile.mkdtemp(), "scope.db"))
    executed.clear()
    model = FakeMessagesListChatModel(
        responses=[AIMessage(content="你好呀，有什么可以帮你？")]
    )
    agent = build_agent(model)
    config = {"configurable": {"thread_id": "t-out-of-scope"}}

    async def run():
        events = []
        async for ev in routes._emit_stream(
            agent, config, {"messages": [HumanMessage(content="你好")]}, None
        ):
            events.append(ev)
        return events

    events = asyncio.run(run())
    parsed = [json.loads(ev.replace("data: ", "", 1)) for ev in events]
    texts = [p["text"] for p in parsed if p["type"] == "result"]
    assert texts and texts[-1] == OUT_OF_SCOPE_HINT, f"应替换为提示: {texts!r}"
    print("PASS 4 LLM 自由发挥被替换为提示")


async def fake_help(**kw) -> str:
    executed.append("help")
    return (
        "Command|Description\n"
        "|---|---|\n"
        "help|This help message\n"
        "list|List all the service\n"
        "kill|kill address : kill service\n"
    )


def build_agent_with_help(model):
    list_tool = StructuredTool.from_function(
        name="list", description="列出所有服务", coroutine=fake_list, args_schema=Args
    )
    kill_tool = StructuredTool.from_function(
        name="kill",
        description="【危险】强制中止一个 lua 服务",
        coroutine=fake_kill,
        args_schema=KillArgs,
    )
    help_tool = StructuredTool.from_function(
        name="help", description="显示帮助", coroutine=fake_help, args_schema=Args
    )
    danger_map = {"list": "safe", "kill": "high", "help": "safe"}
    return SkynetAgent([list_tool, kill_tool, help_tool], danger_map, model=model)


def test_help_call_suppresses_render() -> None:
    """LLM 调了 help → result.render 应为 None（前端不渲染英文原表，让 LLM 翻译呈现）。"""
    import json
    import os
    import tempfile

    from backend import routes, state
    from backend.db import Database

    state.db = Database(os.path.join(tempfile.mkdtemp(), "help.db"))
    executed.clear()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "help", "args": {}, "id": "c_help"}],
            ),
            AIMessage(content="以下是所有命令的中文说明：..."),
        ]
    )
    agent = build_agent_with_help(model)
    config = {"configurable": {"thread_id": "t-help-suppress"}}

    async def run():
        events = []
        async for ev in routes._emit_stream(
            agent, config,
            {"messages": [HumanMessage(content="查看支持的全部命令")]},
            None,
        ):
            events.append(ev)
        return events

    events = asyncio.run(run())
    parsed = [json.loads(ev.replace("data: ", "", 1)) for ev in events]
    results = [p for p in parsed if p["type"] == "result"]
    assert results, "应产生 result 事件"
    assert results[-1]["render"] is None, f"help 后 render 应被抑制: {results[-1]!r}"
    assert "help" in executed, "help 应被执行"
    print("PASS 5 调 help 时不渲染原表")


def test_progress_does_not_leak_tool_output() -> None:
    """progress 事件只含 LLM token，不含 ToolMessage 原始输出（如 list 的 `snlua ...`）。"""
    import json
    import os
    import tempfile

    from backend import routes, state
    from backend.db import Database

    state.db = Database(os.path.join(tempfile.mkdtemp(), "progress.db"))
    executed.clear()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "list", "args": {}, "id": "c_list"}],
            ),
            AIMessage(content="共 2 个服务：cmaster、cslave"),
        ]
    )
    agent = build_agent(model)
    config = {"configurable": {"thread_id": "t-progress"}}

    async def run():
        events = []
        async for ev in routes._emit_stream(
            agent, config, {"messages": [HumanMessage(content="列出所有服务")]}, None
        ):
            events.append(ev)
        return events

    events = asyncio.run(run())
    parsed = [json.loads(ev.replace("data: ", "", 1)) for ev in events]
    progress = [p["content"] for p in parsed if p["type"] == "progress"]
    joined = "".join(progress)
    assert "snlua" not in joined, f"progress 泄漏了工具原始输出: {joined!r}"
    assert "cmaster" in joined or "共 2 个服务" in joined, f"progress 应有 LLM 回复: {joined!r}"
    print("PASS 6 progress 不泄漏工具原始输出")


def test_interrupt_pending_no_result() -> None:
    """interrupt 挂起时不发 result（前端保留审批卡）；resume approve 后才发 result。"""
    import json
    import os
    import tempfile

    from backend import routes, state
    from backend.db import Database

    state.db = Database(os.path.join(tempfile.mkdtemp(), "int.db"))
    executed.clear()
    model = FakeMessagesListChatModel(
        responses=[
            AIMessage(
                content="我来杀掉它",
                tool_calls=[{"name": "kill", "args": {"addr": "3"}, "id": "c_kill"}],
            ),
            AIMessage(content="已执行 kill"),
        ]
    )
    agent = build_agent(model)
    config = {"configurable": {"thread_id": "t-int-noresult"}}

    async def run(initial):
        events = []
        async for ev in routes._emit_stream(agent, config, initial, None):
            events.append(ev)
        return events

    events = asyncio.run(run({"messages": [HumanMessage(content="杀掉 3")]}))
    parsed = [json.loads(e.replace("data: ", "", 1)) for e in events]
    assert any(p["type"] == "human_approval" for p in parsed), "应触发 human_approval"
    assert not any(p["type"] == "result" for p in parsed), "interrupt 挂起不应发 result"
    assert not executed, "审批前不应执行"

    events2 = asyncio.run(run(Command(resume={"decision": "approve"})))
    parsed2 = [json.loads(e.replace("data: ", "", 1)) for e in events2]
    assert any(p["type"] == "result" for p in parsed2), "resume 后应发 result"
    assert "kill:3" in executed, "approve 后应执行 kill"
    print("PASS 7 interrupt 挂起不发 result")


if __name__ == "__main__":
    test_normal_tool_call()
    test_danger_interrupt_approve()
    test_danger_interrupt_reject()
    test_out_of_scope_llm_free_text_replaced()
    test_help_call_suppresses_render()
    test_progress_does_not_leak_tool_output()
    test_interrupt_pending_no_result()
    print("ALL PASS")

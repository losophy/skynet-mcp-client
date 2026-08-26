"""MCP 工具 → LangChain StructuredTool 适配。

inputSchema（JSON Schema）动态转 Pydantic 模型，作为工具的 args_schema；
执行走 async（StructuredTool.from_function 的 coroutine），内部调用 McpConnection。
危险等级不塞进工具对象（LangChain tool 无此字段），由 agent 层按名称查询 danger.py。
"""
from __future__ import annotations

from typing import Any, Literal

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, create_model

from .danger import danger_from_description
from .mcp_client import McpConnection

_TYPE_MAP: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _json_type_to_annotation(prop: dict) -> Any:
    t = prop.get("type")
    if "enum" in prop:
        return Literal[tuple(v for v in prop["enum"] if v is not None)]
    if "anyOf" in prop:
        # Optional/联合类型：FastMCP 对 `Literal[...] | None` 生成
        # {"anyOf": [{"enum": [...]}, {"type": "null"}]}
        branches = [b for b in prop.get("anyOf", []) if isinstance(b, dict)]
        enums = [
            v for b in branches for v in b.get("enum", []) if v is not None
        ]
        if enums:
            return Literal[tuple(enums)]
        for b in branches:
            if b.get("type") != "null":
                return _TYPE_MAP.get(b.get("type"), str)
    return _TYPE_MAP.get(t, str)


def json_schema_to_model(schema: dict, model_name: str) -> type[BaseModel]:
    """把 MCP inputSchema（JSON Schema）转成 Pydantic 模型。

    必填：不在 required 且无默认值的参数给 None 默认（LangChain 传参宽松处理）；
    数组参数保持 list[str]（可空时无默认值）。enum 转 Literal 便于下拉。
    """
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    fields: dict[str, tuple[Any, Any]] = {}
    for name, prop in properties.items():
        ann = _json_type_to_annotation(prop)
        kwargs: dict[str, Any] = {}
        if prop.get("description"):
            kwargs["description"] = prop["description"]
        if "default" in prop:
            kwargs["default"] = prop["default"]
        elif name not in required:
            kwargs["default"] = None
        fields[name] = (ann, Field(**kwargs))
    return create_model(model_name, **fields)


def _make_tool(
    mcp: McpConnection, name: str, description: str, args_model: type[BaseModel]
) -> StructuredTool:
    async def _call(**kwargs: Any) -> str:
        res = await mcp.call_tool(name, kwargs)
        if not res["ok"]:
            raise ValueError(res["text"])
        return res["text"]

    return StructuredTool.from_function(
        name=name,
        description=description,
        coroutine=_call,
        args_schema=args_model,
        handle_tool_error=True,
    )


def build_langchain_tools(
    mcp: McpConnection, tools_meta: list[dict]
) -> tuple[list[StructuredTool], dict[str, str]]:
    """把 MCP 工具元数据转成 (LangChain 工具列表, 工具名→危险等级映射)。"""
    lc_tools: list[StructuredTool] = []
    danger_map: dict[str, str] = {}
    for meta in tools_meta:
        name = meta["name"]
        desc = meta["description"] or ""
        schema = meta.get("inputSchema") or {}
        args_model = json_schema_to_model(schema, f"{name}Args")
        lc_tools.append(_make_tool(mcp, name, desc, args_model))
        danger_map[name] = danger_from_description(desc)
    return lc_tools, danger_map

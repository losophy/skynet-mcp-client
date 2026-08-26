"""parsers 单元测试。"""
from __future__ import annotations

import sys

sys.path.insert(0, r"D:\AgentProjects\skynet-mcp-client")

from backend.parsers import parse_tool_output  # noqa: E402


def test_list_parses_addr_and_detail() -> None:
    r = parse_tool_output("list", ":01000004\tsnlua cmaster\n:01000005\tsnlua cslave\n")
    assert r["columns"] == ["addr", "detail"]
    assert len(r["rows"]) == 2
    assert r["rows"][0]["addr"] == ":01000004"
    assert r["rows"][0]["detail"] == "snlua cmaster"
    assert r["fallback"] is False


def test_mem_parses_size_bytes() -> None:
    r = parse_tool_output("mem", "1\t1024K\n2\t512M\n3\t64\n")
    assert [x["size_bytes"] for x in r["rows"]] == [1048576, 536870912, 64]
    assert r["rows"][0]["size"] == "1024K"


def test_stat_parses_columns() -> None:
    r = parse_tool_output("stat", "1\t0\t0\t100\n2\t5\t1\t200\n")
    assert r["columns"] == ["addr", "queue", "pending", "total"]
    assert r["rows"][1]["pending"] == "1"


def test_stat_with_header_row() -> None:
    r = parse_tool_output("stat", "addr\tqueue\tpending\ttotal\n1\t0\t0\t100\n")
    assert r["columns"] == ["addr", "queue", "pending", "total"]
    assert r["rows"][0]["addr"] == "1"


def test_getenv_parses_key_value() -> None:
    r = parse_tool_output("getenv", "standalone\t0.0.0.0:2013\n")
    assert r["rows"][0] == {"key": "standalone", "value": "0.0.0.0:2013"}


def test_unknown_tool_falls_back() -> None:
    r = parse_tool_output("info", "some\nmulti-line\ntext")
    assert r["fallback"] is True
    assert "multi-line" in r["raw"]


def test_malformed_line_does_not_crash() -> None:
    # stat 列数不足：补空列而非抛异常
    r = parse_tool_output("stat", "1\t0\n2\t0\t0\t100\n")
    assert len(r["rows"]) == 2
    assert r["rows"][0]["pending"] == ""


def test_help_parses_markdown_table() -> None:
    r = parse_tool_output(
        "help",
        "【命令】|用途\n|---|---|\n**help**|显示帮助信息\n**list**|列出所有服务\n",
    )
    assert r["columns"] == ["【命令】", "用途"]
    assert r["rows"][0]["【命令】"] == "help"
    assert r["rows"][1]["用途"] == "列出所有服务"
    assert r["fallback"] is False


def test_help_parses_ascii_md_separator() -> None:
    # skynet-mcp help 实际输出：`+--------+--------+` 分隔线
    r = parse_tool_output(
        "help",
        "【命令】|用途\n+--------+--------+\n**help**|显示帮助信息\n**list**|列出所有服务\n",
    )
    assert r["columns"] == ["【命令】", "用途"]
    assert len(r["rows"]) == 2
    assert r["rows"][0]["【命令】"] == "help"
    assert r["fallback"] is False


def test_help_parses_tab_still_works() -> None:
    # tab 分隔兼容：既有行为是首行当列名
    r = parse_tool_output("help", "help\t显示帮助信息\nlist\t列出所有服务\n")
    assert r["fallback"] is False
    assert r["columns"] == ["help", "显示帮助信息"]
    assert r["rows"][0]["help"] == "list"


def test_unknown_tool_with_markdown_table_falls_back_to_table() -> None:
    # 未注册工具 + markdown 表格：不再回落原文，而是解析成表格
    r = parse_tool_output("info", "字段|值\n|---|---|\na|1\nb|2\n")
    assert r["fallback"] is False
    assert r["columns"] == ["字段", "值"]
    assert len(r["rows"]) == 2

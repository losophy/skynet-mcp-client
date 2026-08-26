"""工具输出文本 → 结构化数据 {columns, rows, raw, fallback}。

行格式参考 skynet_mcp/tools.py 的 docstring 与 tests/mock_console.py 示例输出：
- list：`addr\\t启动方式 参数`
- stat：`addr\\t队列\\t挂起\\t消息总数`（列数可能随 profile 变化）
- mem：`addr\\t1024K/M`
- getenv：`名\\t值`、help：`命令\\t说明`
- netstat/service/info/task 等格式未在项目内定义 → 启发式/回落原文

任何解析都不抛异常：单行格式异常进 unparsed，整体失败回落原文。
"""
from __future__ import annotations

import re
from typing import Any


def _split_lines(text: str) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()]


def _tab_rows(text: str) -> list[list[str]]:
    return [ln.split("\t") for ln in _split_lines(text)]


def _to_table(columns: list[str], rows: list[list[str]]) -> dict:
    return {
        "columns": columns,
        "rows": [dict(zip(columns, r)) for r in rows],
    }


def _pad_rows(cols: list[str], rows: list[list[str]]) -> list[list[str]]:
    n = len(cols)
    return [r[:n] + [""] * (n - len(r)) for r in rows]


def parse_list(text: str) -> dict:
    """list / service：每行 `addr\\t描述` → 两列表格。"""
    rows = []
    for ln in _split_lines(text):
        addr, _, rest = ln.partition("\t")
        rows.append([addr, rest])
    return _to_table(["addr", "detail"], rows)


def parse_stat(text: str) -> dict:
    """stat：`addr\\t队列\\t挂起\\t消息总数`；首行为含字母的表头时按表头解析。"""
    raw = _tab_rows(text)
    if raw and any(ch.isalpha() for ch in raw[0][0]):
        cols, body = raw[0], raw[1:]
    else:
        cols = ["addr", "queue", "pending", "total"]
        body = raw
    return _to_table(cols, _pad_rows(cols, body))


def parse_mem(text: str) -> dict:
    """mem：`addr\\t1024K/M` → 表格 + size_bytes（数值化，供排序/柱状图）。"""
    rows = []
    for ln in _split_lines(text):
        parts = ln.split("\t")
        if len(parts) < 2:
            continue
        addr, raw_size = parts[0], parts[1]
        rows.append({"addr": addr, "size": raw_size, "size_bytes": _parse_size(raw_size)})
    return {"columns": ["addr", "size"], "rows": rows}


def _parse_size(s: str) -> int | None:
    m = re.match(r"^\s*([\d.]+)\s*([KMG]?)\s*$", s, re.IGNORECASE)
    if not m:
        return None
    num = float(m.group(1))
    mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3}.get(m.group(2).upper(), 1)
    return int(num * mult)


def parse_getenv(text: str) -> dict:
    rows = []
    for ln in _split_lines(text):
        key, _, value = ln.partition("\t")
        rows.append([key, value])
    return _to_table(["key", "value"], rows)


def parse_help(text: str) -> dict:
    raw = _tab_rows(text)
    if raw and len(raw[0]) >= 2:
        return _to_table(raw[0], _pad_rows(raw[0], raw[1:]))
    return _to_table(["command", "description"], raw)


def parse_netstat(text: str) -> dict:
    """netstat 格式未定义：首行含字母且第二行 tab 列数一致时按表头解析，否则回落。"""
    raw = _tab_rows(text)
    if len(raw) >= 2 and any(ch.isalpha() for ch in raw[0][0]):
        cols = raw[0]
        if all(len(r) == len(cols) for r in raw[1:]):
            return _to_table(cols, raw[1:])
    return {"columns": [], "rows": [], "raw": text, "fallback": True}


PARSERS: dict[str, Any] = {
    "list": parse_list,
    "service": parse_list,
    "stat": parse_stat,
    "mem": parse_mem,
    "getenv": parse_getenv,
    "help": parse_help,
    "netstat": parse_netstat,
}


def parse_tool_output(tool: str, text: str) -> dict:
    """入口：返回 {columns, rows, raw, fallback}。未注册/解析失败回落原文。"""
    fn = PARSERS.get(tool)
    if fn is None:
        return {"columns": [], "rows": [], "raw": text, "fallback": True}
    try:
        out = fn(text)
    except Exception:
        return {"columns": [], "rows": [], "raw": text, "fallback": True}
    out.setdefault("raw", text)
    out.setdefault("fallback", False)
    return out

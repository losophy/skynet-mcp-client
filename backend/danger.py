"""危险等级判定：工具 description 解析 + raw_command 首词命令级表。

服务端把危险标注写在 docstring（= MCP tools/list 的 description）里：
- 【危险】 → high（kill/exit/signal/inject/call/raw_command）
- ⚠ → medium（start/log/snax/clearcache/killtask/dbgcmd/logon/setenv）
- 其它 → safe

raw_command 是兜底工具（工具级 high），实际危险度取决于命令行首词，
这里用命令级表细化：强杀/注入/调用类 → high，启动/设值类 → medium，
只读类 → safe。
"""
from __future__ import annotations

DANGER_HIGH = "high"
DANGER_MEDIUM = "medium"
DANGER_SAFE = "safe"

# raw_command 首词 → 危险度（镜像 skynet_mcp/backend.py 的 READONLY/SIDE_EFFECT 集合，
# 并按 skynet_mcp/tools.py 的【危险】/⚠ 标注细分）
_RAW_HIGH_COMMANDS = frozenset({"kill", "exit", "signal", "inject", "call"})
_RAW_MEDIUM_COMMANDS = frozenset(
    {"start", "log", "snax", "killtask", "dbgcmd", "logon", "logoff", "setenv", "clearcache"}
)
# 其余首词（只读命令/未知命令）按 safe 处理：只读命令本就安全，
# 未知命令服务端会返回 <CMD Error>，不产生副作用


def danger_from_description(description: str) -> str:
    """从工具 description 文本识别危险等级。"""
    if "【危险】" in description:
        return DANGER_HIGH
    if "⚠" in description:
        return DANGER_MEDIUM
    return DANGER_SAFE


def danger_for_raw_command(command_line: str) -> str:
    """raw_command 按命令行首词细化危险度。"""
    stripped = command_line.lstrip()
    first = stripped.split(None, 1)[0].lower() if stripped else ""
    if first in _RAW_HIGH_COMMANDS:
        return DANGER_HIGH
    if first in _RAW_MEDIUM_COMMANDS:
        return DANGER_MEDIUM
    return DANGER_SAFE


def danger_for_tool(
    name: str, description: str, arguments: dict | None = None
) -> str:
    """给定工具名/描述/参数，返回危险等级。raw_command 特殊处理。"""
    if name == "raw_command":
        cmdline = (arguments or {}).get("command_line", "")
        return danger_for_raw_command(cmdline)
    return danger_from_description(description)

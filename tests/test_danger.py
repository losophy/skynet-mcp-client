"""danger 单元测试。"""
from __future__ import annotations

import sys

sys.path.insert(0, r"D:\AgentProjects\skynet-mcp-client")

from backend.danger import (  # noqa: E402
    DANGER_HIGH,
    DANGER_MEDIUM,
    DANGER_SAFE,
    danger_for_raw_command,
    danger_for_tool,
    danger_from_description,
)


def test_description_classification() -> None:
    assert danger_from_description("列出所有服务") == DANGER_SAFE
    assert danger_from_description("【危险】强制中止服务") == DANGER_HIGH
    assert danger_from_description("⚠ 会启动新服务") == DANGER_MEDIUM


def test_tool_level_classification() -> None:
    assert danger_for_tool("list", "列出服务") == DANGER_SAFE
    assert danger_for_tool("kill", "【危险】强制中止") == DANGER_HIGH
    assert danger_for_tool("start", "⚠ 启动新服务") == DANGER_MEDIUM


def test_raw_command_readonly_is_safe() -> None:
    assert (
        danger_for_tool("raw_command", "【危险】", {"command_line": "list"})
        == DANGER_SAFE
    )
    assert (
        danger_for_tool("raw_command", "【危险】", {"command_line": "  stat 300"})
        == DANGER_SAFE
    )


def test_raw_command_dangerous_first_word() -> None:
    assert danger_for_raw_command("kill 3") == DANGER_HIGH
    assert danger_for_raw_command("inject 3 /tmp/x.lua") == DANGER_HIGH
    assert danger_for_raw_command("start watchdog") == DANGER_MEDIUM
    assert danger_for_raw_command("setenv testflag 1") == DANGER_MEDIUM
    assert danger_for_raw_command("") == DANGER_SAFE


def test_raw_command_unknown_word_is_safe() -> None:
    # 未知命令服务端返回 <CMD Error>，无副作用 → safe
    assert danger_for_raw_command("nonexistent_cmd arg") == DANGER_SAFE

# ported from: src/agent/tools/mcp-tool-provider.ts
"""The original has no test file for ``mcp-tool-provider.ts`` (it is covered through the registry tests of D4).
These tests pin its contract: the default is EMPTY, the source is replaceable, and ``tools_for_agent`` never
raises (``McpToolProvider`` of the contract)."""

from __future__ import annotations

from collections.abc import Sequence

from pema.mcp.mcp_tool_provider import (
    SwitchableMcpToolProvider,
    get_mcp_tools_for_agent,
    mcp_tool_provider,
    set_mcp_tool_source,
)
from pema_contracts.tools import AgentTool, ToolContext, ToolGroup, ToolSpec


def _spec(key: str) -> ToolSpec:
    def build(ctx: ToolContext) -> AgentTool:
        raise AssertionError("not built in this test")

    return ToolSpec(key=key, label=key, description="d", group=ToolGroup.ACTION, build=build)


def test_mcp_tool_provider_default_is_empty() -> None:
    """mặc định rỗng -> chưa có manager thì không tool ngoài nào"""
    assert SwitchableMcpToolProvider().tools_for_agent("a1") == []


def test_mcp_tool_provider_reads_the_registered_source_and_none_restores_the_empty_default() -> None:
    """manager đăng ký nguồn lúc khởi động; test đăng ký một hàm thuần"""
    provider = SwitchableMcpToolProvider()
    provider.set_source(lambda agent_id: [_spec(f"mcp__x__{agent_id}")])
    assert [s.key for s in provider.tools_for_agent("a1")] == ["mcp__x__a1"]
    provider.set_source(None)
    assert provider.tools_for_agent("a1") == []


def test_mcp_tool_provider_a_failing_source_yields_no_tool_and_does_not_raise() -> None:
    """nguồn nổ -> không tool ngoài, không làm hỏng lượt"""

    def explode(agent_id: str) -> Sequence[ToolSpec]:
        raise RuntimeError("boom")

    provider = SwitchableMcpToolProvider()
    provider.set_source(explode)
    assert provider.tools_for_agent("a1") == []


def test_mcp_tool_provider_module_level_functions_drive_the_default_instance() -> None:
    """datNguonToolMcp / layToolMcpChoAgent điều khiển instance mặc định của tiến trình"""
    try:
        set_mcp_tool_source(lambda agent_id: [_spec("mcp__y__t")])
        assert [s.key for s in get_mcp_tools_for_agent("a1")] == ["mcp__y__t"]
        assert [s.key for s in mcp_tool_provider.tools_for_agent("a1")] == ["mcp__y__t"]
    finally:
        set_mcp_tool_source(None)
    assert get_mcp_tools_for_agent("a1") == []

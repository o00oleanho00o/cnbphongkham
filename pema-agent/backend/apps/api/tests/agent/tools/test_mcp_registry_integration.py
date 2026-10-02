# ported from: src/agent/tools/mcp-registry-integration.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Registry x MCP provider integration. The provider is a fake ``McpToolProvider`` (package D5 owns the real one):
``tools_for_agent(agent_id)`` returns ordinary ``ToolSpec``s, so external tools inherit every filter.
"""

from __future__ import annotations

from collections.abc import Sequence

from pema.agent.tools.function_tool import FunctionTool, NoArgs
from pema.agent.tools.testing import make_scope, make_tool_deps
from pema.agent.tools.tool_registry import DefaultToolRegistry
from pema_contracts.tools import ToolContext, ToolGroup, ToolSpec


async def _ok(_args: NoArgs) -> object:
    return "ok"


def _build(_ctx: ToolContext) -> FunctionTool[NoArgs]:
    return FunctionTool(name="mcp__notion__tra_cuu", description="x", input_model=NoArgs, handler=_ok)


DEF_GIA = ToolSpec(
    key="mcp__notion__tra_cuu",
    label="Notion: tra_cuu",
    description="x",
    group=ToolGroup.ACTION,
    runs_in_scheduled_turn=False,
    counts_as_capability=False,
    available=lambda _scope: True,
    build=_build,
)


class _Provider:
    """The pure function of the original test: ``ag1`` is bound to the server, others are not."""

    def __init__(self, bound: dict[str, list[ToolSpec]]) -> None:
        self.bound = bound

    def tools_for_agent(self, agent_id: str) -> Sequence[ToolSpec]:
        return self.bound.get(agent_id, [])


def _registry(provider: _Provider | None) -> DefaultToolRegistry:
    return DefaultToolRegistry(make_tool_deps(), mcp_provider=provider)


def _co_tool(specs: Sequence[ToolSpec]) -> bool:
    return any(s.key == "mcp__notion__tra_cuu" for s in specs)


def test_merge_external_tools_into_the_registry_assigned_agent_has_the_tool_another_agent_does_not() -> None:
    """agent ĐƯỢC gán -> có tool ngoài; agent khác -> không"""
    registry = _registry(_Provider({"ag1": [DEF_GIA]}))
    assert _co_tool(registry.list_available(make_scope(agent_id="ag1")))
    assert not _co_tool(registry.list_available(make_scope(agent_id="ag2")))


def test_merge_external_tools_into_the_registry_scheduled_turn_drops_the_external_tool() -> None:
    """lượt theo lịch (isolated) -> tool ngoài biến mất (runsInScheduledTurn=false)"""
    registry = _registry(_Provider({"ag1": [DEF_GIA]}))
    assert not _co_tool(registry.list_available(make_scope(agent_id="ag1"), isolated=True))


def test_merge_external_tools_into_the_registry_account_disabling_the_tool_removes_it() -> None:
    """account tắt tool đó -> biến mất"""
    registry = _registry(_Provider({"ag1": [DEF_GIA]}))
    scope = make_scope(agent_id="ag1", account_disabled=["mcp__notion__tra_cuu"])
    assert not _co_tool(registry.list_available(scope))


def test_merge_external_tools_into_the_registry_no_provider_means_no_external_tool() -> None:
    """chưa có manager thì không tool ngoài nào (mặc định rỗng); đổi provider có hiệu lực ngay (ca bổ sung)"""
    registry = _registry(None)
    assert not _co_tool(registry.list_available(make_scope(agent_id="ag1")))
    registry.set_mcp_provider(_Provider({"ag1": [DEF_GIA]}))
    assert _co_tool(registry.list_available(make_scope(agent_id="ag1")))

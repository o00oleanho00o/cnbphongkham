"""Built-in tools of the core: the date, and the web (public addresses only, through ``netguard``). An
agent has only those its profile or an admin switches on."""

from __future__ import annotations

from agentcore.harness.tools.builtin.get_datetime import make_get_datetime_tool
from agentcore.harness.tools.builtin.web import make_web_fetch_tool, make_web_search_tool
from agentcore.harness.tools.registry import ToolRegistry


def builtin_tools(*, timezone: str = "UTC") -> ToolRegistry:
    return ToolRegistry(
        [make_get_datetime_tool(default_timezone=timezone), make_web_search_tool(), make_web_fetch_tool()]
    )


__all__ = ["builtin_tools", "make_get_datetime_tool", "make_web_fetch_tool", "make_web_search_tool"]

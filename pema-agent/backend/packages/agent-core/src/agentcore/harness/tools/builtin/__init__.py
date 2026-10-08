"""Built-in tools of the core. They depend on nothing outside the agent process."""

from __future__ import annotations

from agentcore.harness.tools.builtin.get_datetime import make_get_datetime_tool
from agentcore.harness.tools.registry import ToolRegistry


def builtin_tools(*, timezone: str = "UTC") -> ToolRegistry:
    return ToolRegistry([make_get_datetime_tool(default_timezone=timezone)])


__all__ = ["builtin_tools", "make_get_datetime_tool"]

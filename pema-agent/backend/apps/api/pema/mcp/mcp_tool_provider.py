# ported from: src/agent/tools/mcp-tool-provider.ts
"""A thin layer so the external tools (``pema.mcp``) flow into the registry WITHOUT making the tool registry
import a chain that touches the database at module scope. The manager registers a source at start-up; a test
registers a pure function. The default is EMPTY: with no manager there is no external tool.

Forced deviation: ``ToolDefinition`` becomes ``ToolSpec`` and the module-level variable becomes the class
``SwitchableMcpToolProvider``, which implements the ``McpToolProvider`` Protocol of the contract. D4's
registry takes any ``McpToolProvider``; ``mcp_tool_provider`` below is the process-wide default instance the
manager installs itself into (``datNguonToolMcp`` is ``set_mcp_tool_source``, ``layToolMcpChoAgent`` is
``get_mcp_tools_for_agent``).

``tools_for_agent`` never raises (contract): a source that blows up yields no external tool, never a broken
turn.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pema.shared.logger import create_logger
from pema_contracts.tools import ToolSpec

_log = create_logger("mcp.tool-provider")

type McpToolSource = Callable[[str], Sequence[ToolSpec]]


def _empty_source(agent_id: str) -> Sequence[ToolSpec]:
    return []


class SwitchableMcpToolProvider:
    def __init__(self) -> None:
        self._source: McpToolSource = _empty_source

    def set_source(self, source: McpToolSource | None) -> None:
        """The manager calls it at start; a test injects a fake function. ``None`` restores the empty
        default."""
        self._source = source or _empty_source

    def tools_for_agent(self, agent_id: str) -> Sequence[ToolSpec]:
        """Read by the registry on every turn: current source, no database access of its own."""
        try:
            return list(self._source(agent_id))
        except Exception as exc:  # contract: never raises
            _log.error("mcp tool source failed", err=exc, agent_id=agent_id)
            return []


mcp_tool_provider = SwitchableMcpToolProvider()


def set_mcp_tool_source(source: McpToolSource | None) -> None:
    mcp_tool_provider.set_source(source)


def get_mcp_tools_for_agent(agent_id: str) -> Sequence[ToolSpec]:
    return mcp_tool_provider.tools_for_agent(agent_id)

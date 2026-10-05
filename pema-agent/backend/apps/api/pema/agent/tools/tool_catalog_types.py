# ported from: src/agent/tools/tool-catalog-types.ts
"""Shape of the data shared by the tool catalogue.

Forced deviation: the types themselves live in ``pema_contracts.tools`` (package A), because package D1
(the engine) and D5 (MCP) build against them before this package lands: ``ToolContext``, ``ToolScope``,
``ToolGroup`` and ``ToolSpec`` (the port of ``ToolDefinition``). This module re-exports them under the
original names so the rest of the tool package reads like the original, and keeps ``api_ca_nhan``.

Differences of the contract worth knowing when reading the original comments:

* ``ToolContext.api`` (the zca-js API, ``null`` on the Bot channel) is ``ToolContext.channel``
  (``ChannelPort | None``). The original wrote down why 8 tools may assume the personal API: the 8 tools
  that use ``api`` are EXACTLY the 8 tools blocked on the Bot channel (``TOOL_KHONG_CHAY_TREN_BOT``),
  because they need the very sending ability the Bot API lacks. Here that is data:
  ``ChannelCapabilities.blocked_tools``; the checks of the optional abilities are ``isinstance(channel,
  MediaChannel)`` etc.
* ``ToolScope`` carries the channel capabilities instead of ``account.loai``: mandatory for the same reason as
  before (forgetting it silently grants tools the channel cannot run).
* ``ToolContext.ghiNhanDaGui`` is ``record_sent``; ``ToolContext.policy`` (the ``PolicyContext`` of the
  turn) is new, so a tool can ask the policy hooks."""

from __future__ import annotations

from pema.agent.tools.tool_failure_result import KetQuaLoiTool
from pema.agent.tools.tool_send import require_channel
from pema_contracts.channel import ChannelPort
from pema_contracts.tools import ToolAvailability, ToolContext, ToolGroup, ToolScope, ToolSpec

ToolDefinition = ToolSpec
"""``ToolDefinition`` of the original."""


def api_ca_nhan(ctx: ToolContext) -> ChannelPort | KetQuaLoiTool:
    """``apiCaNhan``: the channel of the turn, or a marked failure when the turn has none.

    The original threw an ``Error`` that could not be reached in a normal run (``listAvailableTools``
    already removed the 8 tools from a Bot-channel turn). Here a tool must not raise, so the unreachable
    branch returns the failure the model can read."""
    return require_channel(ctx)


__all__ = [
    "ToolAvailability",
    "ToolContext",
    "ToolDefinition",
    "ToolGroup",
    "ToolScope",
    "ToolSpec",
    "api_ca_nhan",
]

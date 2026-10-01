# ported from: src/agent/tools/index.ts
"""Entry point of the tool system. The catalogue and the on/off logic live in ``tool_registry`` /
``tool_catalog``; this file only re-exports them so a tool file can import ``ToolContext`` from here as before
(import of types only, no import cycle at run time).
"""

from __future__ import annotations

from pema.agent.tools.tool_catalog import TOOL_KEYS, build_tool_definitions
from pema.agent.tools.tool_registry import DefaultToolRegistry, scope_of_context
from pema_contracts.tools import ToolContext, ToolGroup, ToolScope, ToolSpec

ToolDefinition = ToolSpec

__all__ = [
    "TOOL_KEYS",
    "DefaultToolRegistry",
    "ToolContext",
    "ToolDefinition",
    "ToolGroup",
    "ToolScope",
    "build_tool_definitions",
    "scope_of_context",
]

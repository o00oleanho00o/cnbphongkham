# ported from: src/agent/tools/tool-catalog.ts
"""The one tool catalogue: the dashboard reads the list from here through the API (one source, the
frontend does not copy it and drift: same reason as ``reaction-icons``).

The real list sits in two files by GROUP (``tool_catalog_read``, ``tool_catalog_action``); the types are in
``tool_catalog_types`` (contracts).

Forced deviation: ``TOOL_DEFINITIONS`` was a module constant built at import time from singletons; the
entries now need a ``ToolDeps`` (the stores and ports of other packages), so the catalogue is built by
``build_tool_definitions(deps)``. ``TOOL_KEYS`` stays a constant: it is ``BUILTIN_TOOL_KEYS`` of the
contract (names never change: a renamed tool makes the model forget it) and a test checks that the
catalogue matches it."""

from __future__ import annotations

from pema.agent.tools.clinic_tools import clinic_tool_definitions
from pema.agent.tools.tool_catalog_action import action_tool_definitions
from pema.agent.tools.tool_catalog_read import read_tool_definitions
from pema.agent.tools.tool_catalog_types import ToolContext, ToolDefinition, ToolGroup
from pema.agent.tools.tool_deps import ToolDeps
from pema_contracts.tools import BUILTIN_TOOL_KEYS, ToolSpec

TOOL_KEYS: tuple[str, ...] = BUILTIN_TOOL_KEYS


def build_tool_definitions(deps: ToolDeps) -> list[ToolSpec]:
    """``TOOL_DEFINITIONS``: the READ group then the ACTION group, as in the original."""
    return [*read_tool_definitions(deps), *action_tool_definitions(deps), *clinic_tool_definitions(deps)]


__all__ = ["TOOL_KEYS", "ToolContext", "ToolDefinition", "ToolGroup", "build_tool_definitions"]

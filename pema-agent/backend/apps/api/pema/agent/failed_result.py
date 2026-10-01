# ported from: src/agent/tools/tool-failure-result.ts (the SHAPE CHECK only: ``laKetQuaLoi``)
"""Is this tool result the machine-readable "this call FAILED" shape ``{"ok": False, "loi": str}``?

Why it is here and not imported from ``pema.agent.tools.tool_failure_result``: that module belongs to package
D4 and is not on this branch yet, while ``agent_step_trace``, ``agent_step_observer`` and ``tool_loop_guard``
(package D1) must read the shape. The rule is the same one-liner and MUST stay equal to D4's
``la_ket_qua_loi`` (package G: make this module re-export D4's, or the other way round).

Looks at the SHAPE only: no text matching, no guessing from the tool name. Checks BOTH ``ok`` and ``loi``,
not only ``ok``: the repository has other ``{ok: False, ...}`` types with other field names (``reason``,
``error``), and a slip that returns one of those instead of ``ket_qua_loi(...)`` must not pass for a failure
the guard counts, with the instruction text sitting in a key the model was never told to read.

Pure module: no log, no env, no DB.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeGuard


def la_ket_qua_loi(ket_qua: object) -> TypeGuard[Mapping[str, Any]]:
    """``laKetQuaLoi``: ``{"ok": False, "loi": <str>}``; any other object, list or scalar is not a failure."""
    if not isinstance(ket_qua, Mapping):
        return False
    return ket_qua.get("ok") is False and isinstance(ket_qua.get("loi"), str)  # type: ignore[reportUnknownMemberType]

# ported from: src/mcp/mcp-tool-drift.ts
"""Stop an MCP server from changing its tools silently between two connections ("rug pull": the description
or the schema of a tool an operator already approved changes while the tool NAME stays the same, so nobody
notices unless the baseline is compared).

Forced deviation (Vercel AI SDK -> Python): the original used ``fingerprintTools`` and ``detectToolDrift`` of
the ``ai`` package (a hash of the fields that matter for security: description, input schema, title) and said
"do not rewrite them". Python has no such package, so the two functions are re-implemented here with the same
contract: ``fingerprint_tools`` returns ``{tool name: sha256 hex}`` over ``description``, ``inputSchema`` and
``title`` (canonical JSON: sorted keys, no whitespace); ``detect_tool_drift`` returns the names ``added``,
``removed`` and ``changed`` between the current set and the baseline. The baseline stored in
``agent.mcp_servers.fingerprint`` is that mapping as a JSON string.

Kept: an EMPTY baseline (a server never approved) is NOT drift, because "nothing to compare" differs from
"compared and found different"; the caller (manager) stores the first baseline itself in that branch.

One difference, on the safe side: the original ``JSON.parse`` of a corrupt baseline threw, which the manager
turned into status ``loi`` retried by the health loop forever with no way out in the UI. A baseline that
cannot be parsed is now treated as DRIFT (every current tool counts as ``added``): the server goes to
``can_duyet_lai``, the tools stay withheld and an operator can re-approve, which writes a fresh baseline. Fail
closed and recoverable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

from pema.mcp.mcp_types import McpRemoteTool


@dataclass(frozen=True)
class DriftResult:
    drift: bool
    added: list[str] = field(default_factory=list[str])
    """``them``"""
    changed: list[str] = field(default_factory=list[str])
    """``doi``"""
    removed: list[str] = field(default_factory=list[str])
    """``bo``"""


def _tool_hash(tool: McpRemoteTool) -> str:
    canonical = json.dumps(
        {"description": tool.description, "inputSchema": tool.input_schema, "title": tool.title},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8", errors="replace")).hexdigest()


def fingerprint_tools(tools: Sequence[McpRemoteTool]) -> dict[str, str]:
    """``fingerprintTools``: ``{name: hash}`` of the security-relevant fields of each tool."""
    return {tool.name: _tool_hash(tool) for tool in tools}


def detect_tool_drift(current: dict[str, str], baseline: dict[str, str]) -> DriftResult:
    """``detectToolDrift``."""
    added = [name for name in current if name not in baseline]
    removed = [name for name in baseline if name not in current]
    changed = [name for name in current if name in baseline and current[name] != baseline[name]]
    return DriftResult(drift=bool(added or removed or changed), added=added, changed=changed, removed=removed)


def snapshot_fingerprint(tools: Sequence[McpRemoteTool]) -> str:
    """``chupFingerprint``: hash the current tool set into a JSON string to store as the approved baseline."""
    return json.dumps(fingerprint_tools(tools), sort_keys=True, separators=(",", ":"))


def compare_with_baseline(tools: Sequence[McpRemoteTool], baseline_json: str) -> DriftResult:
    """``soDrift``: compare the current tool set with the stored baseline (see the module docstring for the
    empty and the corrupt baseline)."""
    if not baseline_json:
        return DriftResult(drift=False)
    current = fingerprint_tools(tools)
    try:
        parsed = cast(object, json.loads(baseline_json))
    except ValueError:
        return DriftResult(drift=True, added=list(current))
    if not isinstance(parsed, dict):
        return DriftResult(drift=True, added=list(current))
    baseline = {str(k): str(v) for k, v in cast(dict[object, object], parsed).items()}
    return detect_tool_drift(current, baseline)

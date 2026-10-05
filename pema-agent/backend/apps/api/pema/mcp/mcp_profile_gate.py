"""Which policy profiles may use external MCP tools at all (NEW in Pema, not in zalo-agent).

PLAN-AI01 section 2 rule 2: clinic safety is a policy profile, never a deleted feature. External MCP tools are
the one place where an agent can reach a system the clinic does not control, and their output is untrusted
text. Under ``patient_channel`` they are therefore OFF by default, however many servers an admin binds to the
agent. ``staff_assistant`` keeps the behaviour of the original.

This is a default, not a hard-coded rule: ``MCP_ALLOWED_PROFILES`` is the one place that decides it and every
function takes an ``allowed`` argument, so package P (or a later product decision, for example a
doctor-approved per-agent opt-in) can narrow or widen it without touching the manager.

Three places enforce it, so no single mistake opens the door:

1. ``PgMcpPolicyStore.policy_for_agent`` returns an EMPTY ``McpPolicy`` for an agent whose own profile is not
   allowed (the effective permission of the contract);
2. package P attaches ``filter_mcp_tool_keys`` to ``PolicyHooks.filter_tool_keys`` so the tools never reach
   the model schema (the tool registry of D4 calls that hook every turn);
3. ``create_mcp_tool_spec`` re-checks ``ctx.policy.profile`` when the tool RUNS (account and agent combined,
   the restrictive one wins), fail-closed.
"""

from __future__ import annotations

from collections.abc import Collection

from pema_contracts.policy import PolicyProfileKey

MCP_TOOL_KEY_PREFIX = "mcp__"
"""Every external tool key starts with this (``mcp__<server slug>__<tool>``, see ``mcp_tool_definition``)."""

MCP_ALLOWED_PROFILES: frozenset[PolicyProfileKey] = frozenset({PolicyProfileKey.STAFF_ASSISTANT})
"""Profiles that may use MCP. ``patient_channel`` is absent on purpose."""


def is_mcp_tool_key(key: str) -> bool:
    return key.startswith(MCP_TOOL_KEY_PREFIX)


def mcp_allowed_for_profile(
    profile: PolicyProfileKey, allowed: Collection[PolicyProfileKey] = MCP_ALLOWED_PROFILES
) -> bool:
    return profile in allowed


def filter_mcp_tool_keys(
    profile: PolicyProfileKey,
    keys: frozenset[str],
    allowed: Collection[PolicyProfileKey] = MCP_ALLOWED_PROFILES,
) -> frozenset[str]:
    """For package P's ``filter_tool_keys``: drops every MCP tool key when the profile may not use MCP."""
    if mcp_allowed_for_profile(profile, allowed):
        return keys
    return frozenset(k for k in keys if not is_mcp_tool_key(k))

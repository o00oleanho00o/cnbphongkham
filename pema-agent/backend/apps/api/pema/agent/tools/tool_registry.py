# ported from: src/agent/tools/tool-registry.ts
"""Logic that filters and builds the tools of one agent turn. The shape of the data (types + the
``TOOL_DEFINITIONS`` catalogue) sits in ``tool_catalog``.

* ``agent`` declares CAPABILITY: what this agent knows how to do.
* ``account`` applies POLICY: what this Zalo account is allowed to do.

Both store a DISABLED list, and the result is the part NEITHER disables. Neither can switch the other back
on, so adding a new agent can never widen the rights of an account, even when that agent was created
carelessly.

Forced deviations:

* the module functions (``buildAgentTools``, ``listAvailableTools``, ``kiemTraKhaDung``) are the methods
  of ``DefaultToolRegistry``, the implementation of ``pema_contracts.tools.ToolRegistry``; the catalogue
  it filters is built from a ``ToolDeps`` (package G injects the real ports);
* ``buildAgentTools`` is async: the policy hook ``filter_tool_keys`` is async (package P reads the database);
* ``TOOL_KHONG_CHAY_TREN_BOT`` (the table of the Bot channel) became data of the channel:
  ``ChannelCapabilities.blocked_tools``, read from ``ToolScope.channel``;
* ``layToolMcpChoAgent`` (``mcp-tool-provider.ts``, now package D5) is the ``McpToolProvider`` given to the
  constructor; a registry with no provider has no MCP tool, like the original default of an empty source.

NEW (PLAN-AI01 section 5, hook table of CONTRACTS-AI01 section 3): after the original filters,
``build_agent_tools`` asks ``PolicyHooks.filter_tool_keys`` and ALSO removes the keys the policy profile
of the turn lists as disabled (``PolicyProfile.disabled_tool_keys``). ``patient_channel`` switches off
images, video, documents and the web this way, so even with the default ``PermissivePolicyHooks`` a
patient-channel turn never receives them; ``staff_assistant`` disables nothing and behaves exactly like
zalo-agent. Nothing is deleted: the tools stay in the catalogue and on the Tools page (flagged
``blocked_by_policy``)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pema.agent.tools.tool_catalog import build_tool_definitions
from pema.agent.tools.tool_deps import ToolDeps
from pema.shared.logger import create_logger
from pema_contracts.channel import ChannelCapabilities
from pema_contracts.tools import (
    AgentTool,
    McpToolProvider,
    ToolAvailability,
    ToolContext,
    ToolScope,
    ToolSpec,
)

log = create_logger("tool-registry")


def scope_of_context(ctx: ToolContext) -> ToolScope:
    """The ``ToolScope`` of a running turn. A turn with no channel object (tests, a scheduled turn of an
    account that is not running) falls back to capabilities that block nothing by themselves: the tools
    that need a channel ability then answer a marked failure when they run (``require_channel``)."""
    if ctx.channel is not None:
        caps = ctx.channel.capabilities()
    else:
        caps = ChannelCapabilities(channel=ctx.account.channel, can_send_proactive=False)
    return ToolScope(
        agent_id=ctx.agent.id,
        agent_disabled_tools=ctx.agent.disabled_tools,
        account_disabled_tools=ctx.account.disabled_tools,
        channel=caps,
    )


class DefaultToolRegistry:
    """Implements ``pema_contracts.tools.ToolRegistry``."""

    def __init__(
        self,
        deps: ToolDeps,
        *,
        mcp_provider: McpToolProvider | None = None,
        definitions: Sequence[ToolSpec] | None = None,
    ) -> None:
        self._deps = deps
        self._mcp_provider = mcp_provider
        self._definitions: list[ToolSpec] = (
            list(definitions) if definitions is not None else build_tool_definitions(deps)
        )

    def set_mcp_provider(self, provider: McpToolProvider | None) -> None:
        """``datNguonToolMcp``: the MCP manager registers itself at start-up; tests inject a pure fake."""
        self._mcp_provider = provider

    def definitions(self) -> Sequence[ToolSpec]:
        """The static catalogue (``TOOL_DEFINITIONS``). The MCP tools of an agent are added by
        ``definitions_for_agent`` because they depend on the agent."""
        return tuple(self._definitions)

    def definitions_for_agent(self, agent_id: str) -> list[ToolSpec]:
        """Internal tools (static catalogue) plus the external tools of the MCP servers bound to this
        agent, merged HERE so the external tools inherit the whole filter below, with no shortcut."""
        external: Sequence[ToolSpec] = ()
        if self._mcp_provider is not None and agent_id != "":
            external = self._mcp_provider.tools_for_agent(agent_id)
        return [*self._definitions, *external]

    def check_availability(self, spec: ToolSpec, scope: ToolScope) -> ToolAvailability:
        """Can this tool BE USED in the scope under consideration, and if not, why.

        ONE single source for both ``list_available`` (decides whether the model receives the tool) and
        ``GET /admin/tools`` (decides what the dashboard shows). Computing them separately sooner or later
        drifts, and drifting the bad way means the UI says "usable" while the model never received the
        tool: exactly the class of bug the ``available`` flag exists to stop."""
        # The channel FIRST: a platform limit beats every configuration. The Zalo Bot API has no method to
        # send a file / react / tag a member, so enabling them cannot work, and it fails in a way that
        # makes the sender think the agent is broken.
        hint = scope.channel.blocked_tools.get(spec.key)
        if hint is not None:
            return ToolAvailability(usable=False, hint=hint)
        # Checked every turn: a setting changed on the dashboard applies at once with no restart
        if spec.available is not None and not spec.available(scope):
            return ToolAvailability(usable=False, hint=spec.unavailable_hint)
        return ToolAvailability(usable=True)

    def list_available(self, scope: ToolScope, *, isolated: bool = False) -> Sequence[ToolSpec]:
        """The tools the agent REALLY receives in this turn. Same filter as ``build_agent_tools`` (which
        calls this), because the system prompt also needs the list to answer "what can you do": two places
        filtering on their own sooner or later differ, and differing means the bot promises a tool the
        model never received.

        ``isolated`` (a SCHEDULED turn) drops the tools with ``runs_in_scheduled_turn=False``: BOTH the
        schema sent to the model AND the persona prompt must see exactly the same filtered list."""
        # Merge the two DISABLED lists into one set: a tool in the set is out, whichever side disabled it.
        # This is exactly the intersection of the two ENABLED sets, written from the disabled-list side to
        # match how it is stored in the database.
        disabled = {*scope.agent_disabled_tools, *scope.account_disabled_tools}
        return [
            spec
            for spec in self.definitions_for_agent(scope.agent_id)
            if spec.key not in disabled
            and not (isolated and not spec.runs_in_scheduled_turn)
            and self.check_availability(spec, scope).usable
        ]

    async def build_agent_tools(self, ctx: ToolContext) -> Mapping[str, AgentTool]:
        """The tool set put into the agent turn: without the tools the agent disabled, the tools the
        account disabled on the dashboard, the tools the channel cannot run, (for a scheduled turn) the
        tools with ``runs_in_scheduled_turn=False``, and what the policy profile switches off. A removed
        tool is not in the schema: the model does not know it exists, it costs no description tokens, and
        a prompt injection cannot lure the model into calling it."""
        available = self.list_available(scope_of_context(ctx), isolated=ctx.isolated)
        keys = frozenset(spec.key for spec in available)
        allowed = await self._deps.policy.filter_tool_keys(ctx.policy, keys)
        # Defence in depth: the profile data is applied even when the hook is the permissive default
        allowed = allowed - ctx.policy.profile.disabled_tool_keys
        tools: dict[str, AgentTool] = {}
        for spec in available:
            if spec.key in allowed:
                tools[spec.key] = spec.build(ctx)
        removed = keys - allowed
        if removed:
            log.info(
                "Chính sách gỡ tool khỏi lượt",
                profile=ctx.policy.profile.key.value,
                removed=sorted(removed),
            )
        return tools

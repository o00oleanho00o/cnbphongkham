"""Tool registry contract (package D4 implements, D1 consumes, D5 contributes MCP tools).

Port of ``src/agent/tools/tool-catalog-types.ts`` and ``tool-registry.ts``. The two filtering layers
are normative and kept from the original:

* the agent declares CAPABILITY (``AgentProfile.disabled_tools``), the account applies POLICY
  (``AccountConfig.disabled_tools``); a tool is usable when NEITHER disables it, so a new agent can
  never widen the rights of an account;
* the channel can block a tool outright (``ChannelCapabilities.blocked_tools``, the port of
  ``TOOL_KHONG_CHAY_TREN_BOT``), and a profile can switch keys off (``PolicyProfile.disabled_tool_keys``,
  applied through ``PolicyHooks.filter_tool_keys``);
* a scheduled (isolated) turn drops tools with ``runs_in_scheduled_turn=False``;
* tools that are filtered out never reach the model schema, so they cost no tokens and a prompt
  injection cannot call them. ``list_available`` is the ONE function both the schema builder and the
  system prompt use, so the persona never promises a tool the model did not receive.

``ToolSpec`` is the port of ``ToolDefinition``; the Vercel AI SDK ``Tool`` becomes ``AgentTool``
(OpenAI-style function: name, description, JSON-Schema parameters, async ``execute``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pema_contracts.agents import AccountConfig, AgentProfile
from pema_contracts.channel import ChannelCapabilities, ChannelPort, InboundMessage
from pema_contracts.common import JsonObject
from pema_contracts.policy import PolicyContext


class ToolGroup(StrEnum):
    READ = "read"
    """Lookup, no effect outside."""
    ACTION = "action"
    """Sends or changes something."""


BUILTIN_TOOL_KEYS: tuple[str, ...] = (
    "add_reaction",
    "send_file",
    "create_word_document",
    "create_excel_file",
    "create_image",
    "tai_video",
    "tag_member",
    "save_memory",
    "schedule_task",
    "get_datetime",
    "web_search",
    "web_fetch",
    "read_image",
    "get_group_info",
    "kb_search",
)
"""The 15 zalo-agent tools (tool-catalog-action.ts + tool-catalog-read.ts). Names never change: a
renamed tool makes the model forget it."""

CLINIC_TOOL_KEYS: tuple[str, ...] = (
    "patient.get_care_context",
    "appointment.book",
    "review_item.create",
)
"""Clinic tools (PLAN-AI01 principle 3): each one calls the very action the REST route calls."""


class AgentTool(Protocol):
    """A built tool, as handed to the model."""

    @property
    def name(self) -> str: ...

    @property
    def description(self) -> str: ...

    @property
    def parameters(self) -> JsonObject:
        """JSON Schema of the arguments (``type: object``)."""
        ...

    async def execute(self, args: JsonObject) -> object:
        """Run the tool. The result must be JSON-serialisable. A failure is a normal return value
        built by ``tool_failure_result`` (ported from tool-failure-result.ts), not an exception, so
        the loop can mark it and the guard can count it."""
        ...


@dataclass(frozen=True)
class ToolScope:
    """``ToolScope``: agent (capability) x account (policy) x channel. All fields mandatory by design:
    forgetting one must be a type error, not a silently widened tool set."""

    agent_id: str
    agent_disabled_tools: Sequence[str]
    account_disabled_tools: Sequence[str]
    channel: ChannelCapabilities


@dataclass
class ToolContext:
    """Context of one turn. Port of ``ToolContext``.

    ``channel`` is None only in tests and in scheduled turns of an account that is not running; the
    tools that need a channel ability check ``isinstance(ctx.channel, MediaChannel)`` etc.
    """

    clinic_id: UUID
    account: AccountConfig
    agent: AgentProfile
    channel: ChannelPort | None
    message: InboundMessage
    batch: Sequence[InboundMessage]
    policy: PolicyContext
    isolated: bool = False
    record_sent: Callable[[str], None] | None = None
    """``ghiNhanDaGui``: tools that send directly report the text so it enters history."""
    extras: dict[str, object] = field(default_factory=dict[str, object])


@dataclass(frozen=True)
class ToolSpec:
    """Port of ``ToolDefinition``."""

    key: str
    label: str
    description: str
    group: ToolGroup
    build: Callable[[ToolContext], AgentTool]
    has_settings: bool = False
    available: Callable[[ToolScope], bool] | None = None
    unavailable_hint: str | None = None
    counts_as_capability: bool = True
    """``keTrongKhaNang``: worth listing when someone asks 'what can you do'."""
    runs_in_scheduled_turn: bool = True


@dataclass(frozen=True)
class ToolAvailability:
    usable: bool
    hint: str | None = None


class McpToolProvider(Protocol):
    """Implemented by package D5 (``pema.mcp``); consumed by the tool registry (D4).

    Returns the tools of the MCP servers bound to the agent (per-agent default-deny) as ordinary
    ``ToolSpec``s, so external tools inherit every filter above. Must never raise: a broken server
    yields an empty list.
    """

    def tools_for_agent(self, agent_id: str) -> Sequence[ToolSpec]: ...


class ToolRegistry(Protocol):
    """Implemented by package D4 in ``pema.agent.tools.tool_registry``."""

    def definitions(self) -> Sequence[ToolSpec]:
        """Static catalogue plus the MCP tools of the agent when a provider is wired."""
        ...

    def check_availability(self, spec: ToolSpec, scope: ToolScope) -> ToolAvailability:
        """The ONE source of truth for the engine AND ``GET /admin/tools`` (``kiemTraKhaDung``)."""
        ...

    def list_available(self, scope: ToolScope, *, isolated: bool = False) -> Sequence[ToolSpec]: ...

    async def build_agent_tools(self, ctx: ToolContext) -> Mapping[str, AgentTool]:
        """Specs that survive ``list_available`` AND ``PolicyHooks.filter_tool_keys``, built for ``ctx``."""
        ...

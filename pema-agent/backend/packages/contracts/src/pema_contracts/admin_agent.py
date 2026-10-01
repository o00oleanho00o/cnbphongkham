"""Admin DTOs of the agent engine: the screens of the zalo-agent dashboard (``/api/*`` routes of
src/server/routes) as clinic-scoped REST payloads, consumed by the Next.js admin screens (package E).

Mapping (zalo-agent route -> this API, all under ``/api/v1/admin``):
accounts, accounts/:id/login, bot-token, friends -> ``/accounts``, ``/friends``;
agents -> ``/agents``; provider/vision/image-gen -> ``/model/*``; tools -> ``/tools``;
tuning -> ``/tuning``; kb -> ``/kb``; schedule -> ``/schedules``; mcp -> ``/mcp``;
overview/traces/logs -> ``/usage``, ``/traces``, ``/logs/app``; threads/memories/contacts -> ``/threads``,
``/memories``, ``/contacts``.

Field names are the snake_case of the original camelCase; secrets are write-only.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import Field

from pema_contracts.agents import (
    AccountConfig,
    AgentProfile,
    Allowlist,
    LlmProviderKind,
    ReasoningEffort,
)
from pema_contracts.channel import ChannelKind
from pema_contracts.common import ApiModel, JsonObject, VnDatetime
from pema_contracts.conversation import AccountStats, DailyUsage
from pema_contracts.knowledge import KbHit
from pema_contracts.policy import PolicyProfile, PolicyProfileKey
from pema_contracts.scheduler import JobKind, ScheduleInput

# ----------------------------------------------------------------------------- accounts


class AccountCreate(ApiModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64, description="kebab-case")
    label: str = Field(min_length=1, max_length=100)
    agent_id: str | None = None
    channel: ChannelKind = Field(
        default=ChannelKind.ZALO_PERSONAL,
        description="Fixed at creation. Changing it would change the meaning of the stored credential.",
    )
    policy_profile: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL


class AccountUpdate(ApiModel):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    agent_id: str | None = None
    allowlist: Allowlist | None = None
    group_require_mention: bool | None = None
    respond_to_groups: bool | None = None
    group_passive_listen: bool | None = None
    auto_react_enabled: bool | None = None
    auto_react_icon: str | None = None
    typing_indicator_enabled: bool | None = None
    disabled_tools: list[str] | None = None
    auto_accept_friends: bool | None = None
    auto_accept_friend_delay_minutes: int | None = Field(default=None, ge=0, le=1440)


class AccountOut(AccountConfig):
    running: bool = Field(default=False, description="Listener is up.")
    has_credentials: bool = Field(
        default=False, description="A Zalo credential (personal) or token (bot) is stored."
    )


class BotTokenSet(ApiModel):
    token: str = Field(
        min_length=10,
        max_length=500,
        pattern=r"^\d+:[A-Za-z0-9_-]+$",
        description="``<numeric id>:<secret>``, write-only.",
    )


class QrLoginState(StrEnum):
    IDLE = "idle"
    WAITING_SCAN = "waiting_scan"
    SCANNED = "scanned"
    SUCCESS = "success"
    EXPIRED = "expired"
    ERROR = "error"


class QrLoginStatus(ApiModel):
    state: QrLoginState
    qr_png_base64: str | None = Field(default=None, description="Present while waiting for a scan.")
    detail: str | None = None


class ReactionIcon(ApiModel):
    key: str
    emoji: str


class FriendRequestOut(ApiModel):
    from_uid: str
    message: str = ""
    sender_name: str | None = None
    avatar_url: str | None = None
    received_at: VnDatetime


class FriendOut(ApiModel):
    user_id: str
    display_name: str
    avatar_url: str | None = None


class FriendDecision(ApiModel):
    uid: str


# ----------------------------------------------------------------------------- agents


class AgentCreate(ApiModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=64)
    name: str = Field(min_length=1, max_length=100)
    icon: str = "🤖"
    persona: str = Field(default="", max_length=20000)
    policy_profile: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL


class AgentUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    icon: str | None = None
    persona: str | None = Field(default=None, max_length=20000)
    model_provider: LlmProviderKind | None = None
    model_name: str | None = None
    max_steps: int | None = Field(default=None, ge=1)
    reasoning_effort: ReasoningEffort | None = None
    disabled_tools: list[str] | None = None
    context_window: int | None = Field(default=None, ge=1000)
    clear_model_override: bool = Field(
        default=False, description="True resets provider/model/steps to shared config."
    )
    policy_profile: PolicyProfileKey | None = None


class AgentOut(AgentProfile):
    account_count: int = 0


# ----------------------------------------------------------------------------- model settings


class LlmSettingsOut(ApiModel):
    provider: LlmProviderKind
    base_url: str = ""
    model: str = ""
    api_key_masked: str = Field(default="", description="Never the key. 'chua nhap' or masked tail.")
    has_override: bool = False


class LlmSettingsUpdate(ApiModel):
    provider: LlmProviderKind | None = None
    base_url: str | None = Field(
        default=None, description="None keeps the stored value. Empty string clears it (direct vendor)."
    )
    model: str | None = None
    api_key: str | None = Field(default=None, description="Write-only. Omitted keeps the stored key.")


class LlmTestResult(ApiModel):
    ok: bool
    reply: str | None = None
    error: str | None = None


class VisionSettingsOut(ApiModel):
    enabled: bool
    provider: LlmProviderKind | None = None
    base_url: str = ""
    model: str = ""
    api_key_masked: str = ""
    has_override: bool = False


class VisionSettingsUpdate(ApiModel):
    enabled: bool | None = None
    provider: LlmProviderKind | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class ImageGenSettingsOut(ApiModel):
    enabled: bool
    base_url: str = ""
    model: str = ""
    api_key_masked: str = ""
    has_override: bool = False


class ImageGenSettingsUpdate(ApiModel):
    enabled: bool | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


# ----------------------------------------------------------------------------- tools


class ToolOut(ApiModel):
    key: str
    label: str
    description: str
    group: Literal["read", "action"]
    has_settings: bool = False
    usable: bool = Field(description="Infrastructure + channel + policy let the model receive it.")
    hint: str | None = Field(default=None, description="Why it is not usable and where to fix it.")
    disabled_for_account: bool = False
    disabled_for_agent: bool = False
    blocked_by_policy: bool = Field(default=False, description="Switched off by the policy profile.")


class ToolSourceStep(ApiModel):
    id: str
    label: str
    enabled: bool


class ToolChainSettings(ApiModel):
    """``web_search`` / ``web_fetch`` source chain (Extractor Chain). The Brave key is write-only."""

    steps: list[ToolSourceStep] = Field(default_factory=list[ToolSourceStep])
    fallback_enabled: bool | None = None
    brave_api_key_set: bool = False


class ToolChainUpdate(ApiModel):
    steps: list[ToolSourceStep] | None = None
    fallback_enabled: bool | None = None
    brave_api_key: str | None = None


# ----------------------------------------------------------------------------- tuning


class TuningItem(ApiModel):
    """One of the ~70 tuning parameters (src/config/tuning-definitions.ts). The key equals the env name."""

    key: str
    group: str
    label: str
    hint: str
    kind: Literal["number", "boolean", "text", "select"]
    value: float | int | bool | str
    default: float | int | bool | str
    overridden: bool = False
    min: float | None = None
    max: float | None = None
    presets: list[float] | None = None
    options: list[str] | None = None
    token_estimate_hint: bool = False


class TuningGroup(ApiModel):
    id: str
    title: str
    hint: str
    nav_hint: str


class TuningOut(ApiModel):
    groups: list[TuningGroup]
    items: list[TuningItem]


class TuningUpdate(ApiModel):
    values: dict[str, float | int | bool | str | None] = Field(
        description="key -> new value; null removes the override."
    )


# ----------------------------------------------------------------------------- knowledge base


class KbTextSourceCreate(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2_000_000)


class KbApprove(ApiModel):
    approved: bool = Field(
        description="Doctor sign-off. Unapproved sources are not cited in patient_channel."
    )


class KbSearchRequest(ApiModel):
    query: str = Field(min_length=1, max_length=1000)
    agent_id: str
    limit: int = Field(default=5, ge=1, le=20)


class KbSearchResponse(ApiModel):
    hits: list[KbHit]


# ----------------------------------------------------------------------------- schedules


class ScheduleCreate(ApiModel):
    account_id: str
    thread_id: str
    thread_type: int = 0
    name: str = Field(min_length=1, max_length=200)
    kind: JobKind
    payload: str = Field(min_length=1, max_length=4000)
    schedule: ScheduleInput
    timezone: str = ""
    max_runs: int | None = Field(default=None, ge=1)


class ScheduleUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    payload: str | None = Field(default=None, min_length=1, max_length=4000)
    schedule: ScheduleInput | None = None
    timezone: str | None = None
    max_runs: int | None = Field(default=None, ge=1)
    enabled: bool | None = None


# ----------------------------------------------------------------------------- mcp


class McpServerCreate(ApiModel):
    name: str = Field(min_length=1, max_length=100)
    url: str = Field(pattern=r"^https?://")
    headers: dict[str, str] = Field(
        default_factory=dict[str, str], description="Write-only (often bearer tokens)."
    )
    enabled: bool = True


class McpServerUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    url: str | None = Field(default=None, pattern=r"^https?://")
    headers: dict[str, str] | None = None
    enabled: bool | None = None


class IdList(ApiModel):
    """Body of the binding endpoints (``PUT .../agents``, ``PUT .../sources``, ``PUT .../servers``)."""

    ids: list[str]


# ----------------------------------------------------------------------------- usage, traces, logs


class AccountOverview(ApiModel):
    id: str
    label: str
    enabled: bool
    online: bool


class AccountUsage(ApiModel):
    account_id: str
    daily: list[DailyUsage]


class SystemInfo(ApiModel):
    version: str
    uptime_seconds: int
    python: str


class OverviewOut(ApiModel):
    accounts: list[AccountOverview]
    usage_by_account: list[AccountUsage]
    stats_by_account: list[AccountStats]
    system: SystemInfo
    today_key: str
    timezone: str
    days: Literal[7, 14, 30]


class TraceTurnRow(ApiModel):
    id: int
    account_id: str
    thread_id: str
    source: Literal["message", "schedule"]
    input_tokens: int
    output_tokens: int
    total_tokens: int
    steps: int
    created_at: VnDatetime
    thread_name: str | None = None


class TraceTurnPage(ApiModel):
    turns: list[TraceTurnRow]
    next_cursor: int | None = Field(default=None, description="Pass as ?before= for the next page.")


class LogEntry(ApiModel):
    time: VnDatetime
    level: Literal["trace", "debug", "info", "warn", "error", "fatal"]
    scope: str
    message: str = Field(description="Never contains PII: loggers log ids and codes only.")
    fields: JsonObject | None = None


class LogPage(ApiModel):
    entries: list[LogEntry]
    scopes: list[str] = Field(default_factory=list[str])
    next_cursor: str | None = None
    disabled: bool = False
    hint: str | None = None


# ----------------------------------------------------------------------------- threads and memory


class ThreadUpdate(ApiModel):
    display_name: str | None = Field(default=None, max_length=200)
    bot_enabled: bool | None = None


# ----------------------------------------------------------------------------- policy admin


class PolicyProfilesOut(ApiModel):
    profiles: list[PolicyProfile]


class AccountPolicyUpdate(ApiModel):
    policy_profile: PolicyProfileKey


class IdentityConfirm(ApiModel):
    """Staff confirm that ``external_user_id`` on ``channel`` is this patient (admin.policy)."""

    channel: ChannelKind
    external_user_id: str
    patient_id: UUID
    reject: bool = False

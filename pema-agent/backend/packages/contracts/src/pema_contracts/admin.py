"""Admin DTOs for clinic-level operations: channel settings (kill switch, proactive cap) and audit log.

CRM rule admin DTOs live in ``pema_contracts.crm`` (``CrmRuleOut`` / ``CrmRuleUpdate``). Agent-side
admin DTOs (accounts, agents, model, tools, KB, schedules, MCP, usage, logs) live in
``pema_contracts.admin_agent``. Secrets (bot token, Zalo credential) never appear in any DTO; they live
in encrypted columns and are write-only.

``clinic.channel_setting`` is the CLINIC-WIDE switchboard per channel kind (one row per kind); the
per-account settings (allowlist, reactions, ...) are ``agent.accounts``. A proactive send is allowed
only when BOTH say yes (kill switch off in the channel row, account enabled).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from pema_contracts.channel import ZALO_PERSONAL_DEFAULT_DAILY_CAP, ChannelKind
from pema_contracts.common import ApiModel, JsonObject, VnDatetime
from pema_contracts.roles import ActorType, Role

__all__ = [
    "ZALO_PERSONAL_DEFAULT_DAILY_CAP",
    "AuditLogOut",
    "BridgeState",
    "ChannelSettingsOut",
    "ChannelSettingsUpdate",
    "KillSwitchRequest",
]


class BridgeState(StrEnum):
    """State of the personal-account bridge as seen by the API."""

    NOT_CONFIGURED = "not_configured"
    AWAITING_QR = "awaiting_qr"
    CONNECTED = "connected"
    BLOCKED = "blocked"
    """Account locked or rate-limited by Zalo: proactive sends fall back to manual."""
    DOWN = "down"


class ChannelSettingsOut(ApiModel):
    channel: ChannelKind
    enabled: bool = Field(description="Feature flag (e.g. ZALO_PERSONAL_ENABLED); off means no traffic.")
    kill_switch_on: bool = Field(
        description="When on, every proactive send is rejected with channel_kill_switch_on."
    )
    kill_switch_reason: str | None = None
    kill_switch_changed_at: VnDatetime | None = None
    kill_switch_changed_by: UUID | None = None
    daily_cap: int | None = Field(default=None, ge=0, description="Proactive messages per day.")
    proactive_sent_today: int = 0
    send_window_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    send_window_end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    min_gap_seconds: int = 0
    max_gap_seconds: int = 0
    requires_friend: bool = False
    bridge_state: BridgeState | None = Field(default=None, description="Only meaningful for zalo_personal.")
    updated_at: VnDatetime | None = None
    version: int


class ChannelSettingsUpdate(ApiModel):
    version: int
    enabled: bool | None = None
    daily_cap: int | None = Field(default=None, ge=0, le=1000)
    send_window_start: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    send_window_end: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    min_gap_seconds: int | None = Field(default=None, ge=0, le=3600)
    max_gap_seconds: int | None = Field(default=None, ge=0, le=3600)


class KillSwitchRequest(ApiModel):
    on: bool
    reason: str | None = Field(default=None, max_length=500)


class AuditLogOut(ApiModel):
    id: int
    occurred_at: VnDatetime
    actor_type: ActorType
    actor_user_id: UUID | None
    actor_role: Role | None
    action: str = Field(description="Dotted verb, e.g. 'review_item.approve'.")
    entity_type: str
    entity_id: str | None
    request_id: str | None = None
    details: JsonObject | None = Field(
        default=None, description="Field names and ids only; no message text, no PII values."
    )

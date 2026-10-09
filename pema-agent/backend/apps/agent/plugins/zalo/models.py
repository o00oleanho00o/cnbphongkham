"""The accounts of the Zalo plugin and what the admin routes take and give.

An account is one Zalo identity the agent speaks through: a Zalo Bot (``zalo_bot``, token), a personal account
(``zalo_personal``, QR login through the bridge) or an Official Account (``zalo_oa``, not available yet). Its
kind is fixed at creation: the stored credential means something different for each. The shapes follow the
earlier admin API (``AccountCreate``, ``AccountUpdate``, ``AccountOut``) so the dashboard pages carry over;
``clinic_id``, ``agent_id`` and ``policy_profile`` are gone (one agent per service, no policy profiles).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, Field

MAX_ACCOUNT_ID_CHARS: Final = 58
"""The channel of an account is ``zalo-<id>``, and a channel name has at most 64 characters."""

ToolName = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{1,100}$")]


class ChannelKind(StrEnum):
    ZALO_BOT = "zalo_bot"
    ZALO_PERSONAL = "zalo_personal"
    ZALO_OA = "zalo_oa"


class AllowlistMode(StrEnum):
    ALL = "all"
    LIST = "list"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Allowlist(_Model):
    mode: AllowlistMode = AllowlistMode.ALL
    user_ids: list[str] = Field(default_factory=list[str], max_length=1000)


class AccountConfig(_Model):
    id: str
    label: str
    channel: ChannelKind
    enabled: bool = True
    allowlist: Allowlist = Field(default_factory=Allowlist)
    group_require_mention: bool = True
    respond_to_groups: bool = True
    group_passive_listen: bool = True
    auto_react_enabled: bool = True
    auto_react_icon: str = "heart"
    typing_indicator_enabled: bool = True
    disabled_tools: list[ToolName] = Field(
        default_factory=list[ToolName],
        description="Tool names switched OFF (deny list, so a newly added tool is on for old accounts).",
    )
    auto_accept_friends: bool = False
    auto_accept_friend_delay_minutes: int = Field(default=1, ge=0, le=1440)


class AccountCreate(_Model):
    id: str = Field(
        pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=MAX_ACCOUNT_ID_CHARS, description="kebab-case"
    )
    label: str = Field(min_length=1, max_length=100)
    channel: ChannelKind = Field(
        default=ChannelKind.ZALO_PERSONAL,
        description="Fixed at creation. Changing it would change the meaning of the stored credential.",
    )


class AccountUpdate(_Model):
    label: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None
    allowlist: Allowlist | None = None
    group_require_mention: bool | None = None
    respond_to_groups: bool | None = None
    group_passive_listen: bool | None = None
    auto_react_enabled: bool | None = None
    auto_react_icon: str | None = None
    typing_indicator_enabled: bool | None = None
    disabled_tools: list[ToolName] | None = Field(default=None, max_length=200)
    auto_accept_friends: bool | None = None
    auto_accept_friend_delay_minutes: int | None = Field(default=None, ge=0, le=1440)


class AccountOut(AccountConfig):
    running: bool = Field(default=False, description="The account's channel is listening.")
    has_credentials: bool = Field(
        default=False, description="A login (personal), a token (bot) or app keys (OA) are stored."
    )
    warning: str | None = Field(
        default=None,
        description="Set when the change was saved but the channel did not come up. Plain text, no secret.",
    )


class ReactionIconOut(_Model):
    key: str
    emoji: str
    label: str


class QrLoginState(StrEnum):
    IDLE = "idle"
    WAITING_SCAN = "waiting_scan"
    SCANNED = "scanned"
    SUCCESS = "success"
    EXPIRED = "expired"
    ERROR = "error"


class QrLoginStatus(_Model):
    state: QrLoginState
    qr_png_base64: str | None = Field(default=None, description="Present while waiting for a scan.")
    detail: str | None = None


class BotTokenSet(_Model):
    token: str = Field(
        min_length=10,
        max_length=500,
        pattern=r"^\d+:[A-Za-z0-9_-]+$",
        description="``<numeric id>:<secret>`` from Zalo Bot Creator, write-only.",
    )


class OaKeysSet(_Model):
    """The keys of an Official Account, write-only (stored sealed, never answered back)."""

    app_id: str = Field(pattern=r"^\d{1,30}$")
    app_secret: str = Field(min_length=8, max_length=200)
    oa_secret_key: str = Field(min_length=8, max_length=200, description="Checks the OA webhook signature.")
    refresh_token: str = Field(min_length=8, max_length=2000, description="OAuth v4; renewed on each use.")


ZALO_ID_PATTERN: Final = r"^[A-Za-z0-9_.-]{1,100}$"
"""A Zalo user or group id as it may appear in a path or a body (part of a storage key)."""


class ContactOut(_Model):
    account_id: str
    user_id: str
    display_name: str
    first_seen: datetime
    last_seen: datetime
    message_count: int


class GroupOut(_Model):
    account_id: str
    thread_id: str
    name: str


class FriendRequestOut(_Model):
    from_uid: str
    message: str = ""
    sender_name: str | None = None
    avatar_url: str | None = None
    received_at: datetime


class FriendOut(_Model):
    user_id: str
    display_name: str
    avatar_url: str | None = None


class FriendDecision(_Model):
    uid: str = Field(pattern=ZALO_ID_PATTERN)

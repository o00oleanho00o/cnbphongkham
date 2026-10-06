"""Shared inbox DTOs, package O: channel identities, their own send limits, and the roster.

New module (O1). One INSTALLATION is one clinic (single tenant). Nothing here ever carries a credential: an
identity is described by its label, channel, purpose, state and limits only; the bot token, the zca-js
cookie and the webhook secret stay encrypted on the server (``tests/ops/test_credential_boundary.py`` pins
it).
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from pema_contracts.channel import ChannelKind
from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.roles import Role

HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"


class IdentityPurpose(StrEnum):
    CUSTOMER = "customer"
    """Faces customers: "Long" on Zalo, a Zalo bot, a Zalo OA."""
    INTERNAL = "internal"
    """The clinic's own notifier (rings operators, posts to the team group). Never sends to a customer and can
    never be the identity of a conversation."""


class Weekday(StrEnum):
    """The keys of the weekly shift of ``clinic.staff_profiles`` (``mon`` .. ``sun``)."""

    MON = "mon"
    TUE = "tue"
    WED = "wed"
    THU = "thu"
    FRI = "fri"
    SAT = "sat"
    SUN = "sun"


WEEKDAY_ORDER: tuple[Weekday, ...] = tuple(Weekday)


class LimitOverrides(ApiModel):
    """Per-identity overrides. ``None`` = use the row of the channel (``clinic.channel_setting``)."""

    send_gap_min_s: int | None = Field(default=None, ge=0, le=86400)
    send_gap_max_s: int | None = Field(default=None, ge=0, le=86400)
    daily_cap: int | None = Field(default=None, ge=0, le=100000)


class EffectiveLimits(ApiModel):
    """What the send path applies to this identity: the override, else the channel row, else no limit."""

    send_gap_min_s: int = Field(ge=0)
    send_gap_max_s: int = Field(ge=0)
    daily_cap: int | None = Field(default=None, ge=0, description="None: no cap.")


class IdentityOut(ApiModel):
    """A channel account as a clinic identity. No credential, no cookie, no QR, no token: not even a flag
    beyond the state the operator already sees (enabled, channel state)."""

    id: str
    label: str
    channel: ChannelKind
    purpose: IdentityPurpose
    enabled: bool
    channel_enabled: bool = Field(description="``clinic.channel_setting.enabled`` of this channel.")
    kill_switch_on: bool = Field(description="The kill switch of this channel is on: nothing is sent.")
    bridge_state: str | None = Field(default=None, description="Zalo bridge state of the channel, if any.")
    overrides: LimitOverrides
    effective: EffectiveLimits


class IdentityUpdate(ApiModel):
    """``PATCH /identities/{id}``. A field that is left out stays; a limit sent as ``null`` clears its
    override
    (back to the channel row). Any other field is refused (``extra = forbid``)."""

    purpose: IdentityPurpose | None = None
    label: str | None = Field(default=None, min_length=1, max_length=100)
    send_gap_min_s: int | None = Field(default=None, ge=0, le=86400)
    send_gap_max_s: int | None = Field(default=None, ge=0, le=86400)
    daily_cap: int | None = Field(default=None, ge=0, le=100000)

    @model_validator(mode="after")
    def _purpose_and_label_are_not_null(self) -> IdentityUpdate:
        for name in ("purpose", "label"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be cleared")
        return self


class RosterEntryBase(ApiModel):
    weekdays: list[Weekday] | None = Field(
        default=None, description="Days of the week the slot repeats on. Exactly one of weekdays and on_date."
    )
    on_date: date | None = Field(default=None, description="One explicit date (a cover for a day).")
    note: str | None = Field(default=None, max_length=200)

    @field_validator("weekdays")
    @classmethod
    def _unique_days(cls, value: list[Weekday] | None) -> list[Weekday] | None:
        if value is None:
            return None
        ordered = [day for day in WEEKDAY_ORDER if day in set(value)]
        if not ordered:
            raise ValueError("weekdays cannot be empty")
        return ordered


class RosterEntryCreate(RosterEntryBase):
    account_id: str = Field(min_length=1, max_length=100)
    user_id: UUID
    start: str = Field(pattern=HHMM_PATTERN)
    end: str = Field(
        pattern=HHMM_PATTERN,
        description="Earlier than the start: the slot ends the next morning (the +07:00 clock).",
    )

    @model_validator(mode="after")
    def _one_kind(self) -> RosterEntryCreate:
        if (self.weekdays is None) == (self.on_date is None):
            raise ValueError("give exactly one of weekdays and on_date")
        if self.start == self.end:
            raise ValueError("start and end must differ")
        return self


class RosterEntryUpdate(RosterEntryBase):
    """``PATCH /roster/{id}``. ``version`` is the one the client read. Switching between ``weekdays`` and
    ``on_date`` is done by sending the new one and ``null`` for the other."""

    version: int = Field(ge=1)
    user_id: UUID | None = None
    start: str | None = Field(default=None, pattern=HHMM_PATTERN)
    end: str | None = Field(default=None, pattern=HHMM_PATTERN)


class RosterEntryOut(ApiModel):
    id: UUID
    account_id: str
    user_id: UUID
    user_name: str
    user_role: Role
    weekdays: list[Weekday] | None
    on_date: date | None
    start: str
    end: str
    note: str | None
    version: int


class OnDutyOperator(ApiModel):
    id: UUID
    name: str
    role: Role


class OnDutyOut(ApiModel):
    """Who covers an identity at a moment (``GET /identities/{id}/on-duty``)."""

    account_id: str
    at: VnDatetime
    operators: list[OnDutyOperator]

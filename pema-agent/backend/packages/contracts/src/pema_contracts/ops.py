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


# ------------------------------------------------------------------------------ assignment (step O2)
class AssignmentKind(StrEnum):
    """Why a row of ``clinic.conversation_assignment`` exists."""

    CLAIM = "claim"
    """An operator took an unassigned conversation (or the first reply claimed it)."""
    TAKEOVER = "takeover"
    """An operator took the conversation from the colleague who held it; a reason is required."""
    RELEASE = "release"
    """The holder gave it back: to the queue, or to the care agent."""
    SHIFT_END = "shift_end"
    """The holder's shift ended: it went to whoever is on duty, or back to the queue."""
    ASSIGN = "assign"
    """An owner or manager put someone on it (or took it off the holder)."""


class AssignmentRequestBase(ApiModel):
    assignment_version: int | None = Field(
        default=None,
        ge=1,
        description="The ``assignment_version`` the client saw. When it is no longer the stored one the call "
        "answers 409 ``version_conflict``. Left out: the action uses the version it reads itself.",
    )


class ClaimRequest(AssignmentRequestBase):
    """``POST /conversations/{id}/claim`` (the body is optional)."""


class TakeoverRequest(AssignmentRequestBase):
    """``POST /conversations/{id}/takeover``. The reason is kept in the history (staff only) and never in an
    audit row or a notification."""

    reason: str = Field(min_length=1, max_length=500)


class ReleaseRequest(AssignmentRequestBase):
    """``POST /conversations/{id}/release``."""

    to_agent: bool = Field(
        default=False,
        description="Hand the conversation back to the care agent (the patient is in the STAFF state of "
        "package M). False: only back to the queue.",
    )
    note: str | None = Field(
        default=None,
        max_length=500,
        description="With ``to_agent``: the note the care agent reads (M's release note).",
    )


class AssignRequest(AssignmentRequestBase):
    """``POST /conversations/{id}/assign``: owner and manager. ``user_id`` null puts it back in the queue."""

    user_id: UUID | None = None


class EndShiftResult(ApiModel):
    """What ``POST /staff/{user_id}/end-shift`` did, thread by thread."""

    user_id: UUID
    rerouted: int = Field(ge=0, description="Moved to an operator who is on duty.")
    to_queue: int = Field(ge=0, description="Nobody on duty (or no identity known): back to the queue.")
    skipped: int = Field(ge=0, description="Changed hands while the shift was being ended: left alone.")


class AssignmentEventOut(ApiModel):
    """One line of the history of a conversation (``GET /conversations/{id}/assignments``, newest first)."""

    id: UUID
    kind: AssignmentKind
    user_id: UUID | None = Field(description="Who holds it after the change; null: back in the queue.")
    user_name: str | None = None
    previous_user_id: UUID | None = None
    previous_user_name: str | None = None
    reason: str | None = Field(default=None, description="Takeover reason or release note; staff only.")
    at: VnDatetime
    by: UUID | None = Field(default=None, description="Who made the change; null: the system.")


# --------------------------------------------------------------------------- notification outbox (O2)
class NotificationRecipientKind(StrEnum):
    USER = "user"
    TEAM_GROUP = "team_group"


class NotificationState(StrEnum):
    """Lifecycle of an outbox row. O2 only writes ``pending``; O3 delivers and moves it on."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class NotificationUrgency(StrEnum):
    NORMAL = "normal"
    URGENT = "urgent"


SHORT_CODE_PATTERN = r"^#[0-9A-F]{4}$"
DEEP_LINK_PATTERN = r"^/inbox\?conversation=[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


class NotificationPayload(ApiModel):
    """What a notification may say, and nothing else (``extra = forbid``): a short code, the identity label,
    an urgency, a one-line summary the action composes from a template (never the text of a message), a deep
    link that needs a login, and ids. No phone number, no patient or customer name, no message text: the
    serializer in ``pema.clinic.actions.notifications`` also runs the free-text fields through the PII mask
    and refuses the payload when anything is found."""

    event: AssignmentKind
    short_code: str = Field(pattern=SHORT_CODE_PATTERN)
    identity_label: str | None = Field(default=None, max_length=100)
    urgency: NotificationUrgency = NotificationUrgency.NORMAL
    summary: str = Field(min_length=1, max_length=160)
    deep_link: str = Field(pattern=DEEP_LINK_PATTERN)
    from_user_id: UUID | None = None
    to_user_id: UUID | None = None

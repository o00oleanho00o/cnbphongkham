"""Vocabulary of staff routing, the 24/7 on-call contact and the reminder pause (PLAN-AI01-M sections 7, 8).

New module (not a port). Pure data and no import of another ``pema.care`` module except the two vocabulary
modules (``handoff_types``, ``events``), so ``ports`` can use it.

``Candidate`` is one entry of ``agent.handoff_requests.candidates`` (a jsonb array; the table of M1 is final,
so everything the routing needs to remember about a candidate lives inside its own object: status, when it was
notified, the SLA deadline, the decline reason). ``to_json`` / ``from_json`` are the only two places that
know the layout. The LAST candidate of every chain is the 24/7 on-call contact (``kind = "on_call"``).

``RoutingConfig`` is the ``classifier_config`` jsonb of the row ``agent.skills.name = 'routing'`` (there is no
``clinic.settings`` table: the clinic's tunables of package M live in ``agent.skills`` rows, like the ones of
``handoff``). EVERY number of M2c is a field here (SLA minutes, number of candidates, the depth from which an
out-of-hours handoff goes straight to the on-call number, the "past its meaning" windows of the reminders and
the doctor-approved template texts). The defaults are TEMPORARY and flagged ``pending_doctor_approval``.

Logs and audit lines that use these types carry ids and codes only; never a name, a phone number or a text.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from pema.care.events import EventKind
from pema.care.handoff_types import Depth
from pema_contracts.common import JsonObject

ROUTING_SKILL_NAME = "routing"
"""Name of the ``agent.skills`` row that holds the ``RoutingConfig``."""

DECLINE_REASON_MAX_CHARS = 500


# ----------------------------------------------------------------------------------------- candidates
class CandidateKind(StrEnum):
    STAFF = "staff"
    ON_CALL = "on_call"


class CandidateStatus(StrEnum):
    PENDING = "pending"
    """In the chain, not asked yet."""
    NOTIFIED = "notified"
    DECLINED = "declined"
    EXPIRED = "expired"
    """Did not answer inside the SLA."""


class RankReason(StrEnum):
    """Why a person is in the chain (codes, shown to the clinic on the dashboard)."""

    CS_OWNER = "cs_owner"
    TREATING_DOCTOR = "treating_doctor"
    ON_SHIFT = "on_shift"
    SUGGESTED = "suggested_by_decline"
    ON_CALL = "on_call"


@dataclass(frozen=True)
class Candidate:
    kind: CandidateKind
    user_id: UUID | None
    """The staff member; ``None`` for the on-call contact (a Zalo number outside the app)."""
    rank_reason: RankReason
    status: CandidateStatus = CandidateStatus.PENDING
    notified_at: datetime | None = None
    sla_due_at: datetime | None = None
    next_shift_at: datetime | None = None
    """Start of this person's next shift when the chain was built (the SLA when the clinic is closed)."""
    declined_at: datetime | None = None
    decline_reason: str | None = None
    """PII-masked free text of the person who declined; input of the later skill-profile update."""
    oncall_id: UUID | None = None
    """``clinic.on_call_contacts.id`` that was current when the chain was built (audit only; the number is
    read again from the database whenever it is used)."""

    def with_status(self, status: CandidateStatus, **changes: Any) -> Candidate:
        return replace(self, status=status, **changes)

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "user_id": str(self.user_id) if self.user_id is not None else None,
            "rank_reason": self.rank_reason.value,
            "status": self.status.value,
            "notified_at": _iso(self.notified_at),
            "sla_due_at": _iso(self.sla_due_at),
            "next_shift_at": _iso(self.next_shift_at),
            "declined_at": _iso(self.declined_at),
            "decline_reason": self.decline_reason,
            "oncall_id": str(self.oncall_id) if self.oncall_id is not None else None,
        }

    @staticmethod
    def from_json(raw: object) -> Candidate:
        if not isinstance(raw, Mapping):
            raise ValueError("a candidate is a JSON object")
        data: Mapping[str, Any] = raw  # pyright: ignore[reportUnknownVariableType]
        user = data.get("user_id")
        oncall = data.get("oncall_id")
        reason = data.get("decline_reason")
        return Candidate(
            kind=CandidateKind(str(data["kind"])),
            user_id=UUID(str(user)) if user else None,
            rank_reason=RankReason(str(data["rank_reason"])),
            status=CandidateStatus(str(data.get("status", CandidateStatus.PENDING.value))),
            notified_at=_dt(data.get("notified_at")),
            sla_due_at=_dt(data.get("sla_due_at")),
            next_shift_at=_dt(data.get("next_shift_at")),
            declined_at=_dt(data.get("declined_at")),
            decline_reason=str(reason) if reason is not None else None,
            oncall_id=UUID(str(oncall)) if oncall else None,
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _dt(value: object) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


def candidates_from_json(raw: Sequence[object]) -> list[Candidate]:
    return [Candidate.from_json(item) for item in raw]


def candidates_to_json(candidates: Sequence[Candidate]) -> list[dict[str, Any]]:
    return [candidate.to_json() for candidate in candidates]


# ------------------------------------------------------------------------------------ directory data
@dataclass(frozen=True)
class StaffInfo:
    """One row of ``clinic_agent.staff_profile`` plus the number of conversations the person is handling."""

    user_id: UUID
    role: str
    skills: tuple[str, ...] = ()
    shift: Mapping[str, object] = field(default_factory=dict[str, object])
    """``{"mon": [["08:00", "17:00"]], ...}`` (keys ``mon``..``sun``; an empty object: never on shift)."""
    capacity: int = 5
    load: int = 0
    """Conversations in ``STAFF`` state owned by this person."""
    languages: tuple[str, ...] = ("vi",)


@dataclass(frozen=True)
class Ownership:
    cs_owner: UUID | None = None
    doctor: UUID | None = None


@dataclass(frozen=True)
class OnCallRow:
    """A row of ``clinic_agent.on_call_contact``."""

    id: UUID
    zalo_number: str
    owner: str
    valid_from: datetime
    valid_to: datetime | None = None
    active: bool = True
    is_fixture: bool = False


@dataclass(frozen=True)
class OnCallInfo:
    """The 24/7 contact that is current right now. Never written to a log or to the repository."""

    id: UUID
    zalo_number: str
    owner: str
    is_fixture: bool = False


@dataclass(frozen=True)
class HandoffNotice:
    """What a staff member (or the on-call contact) is shown for one routing request."""

    request_id: UUID
    patient_id: UUID
    depth: str
    urgency: str
    summary: str
    """PII-masked summary built by ``pema.care.control.build_summary``."""
    sla_due_at: datetime | None
    position: int
    """Index in the chain (the app shows "you are number N")."""
    is_on_call: bool = False


@dataclass(frozen=True)
class SlaCheck:
    """ "Look at this request again at ``due_at``": scheduled through S, never a sleep."""

    request_id: UUID
    idx: int
    due_at: datetime
    dedupe_key: str


@dataclass(frozen=True)
class DeclineRecord:
    """One decline, for the later update of the skill profiles (never applied automatically)."""

    request_id: UUID
    user_id: UUID | None
    required_skill: str | None
    depth: str
    reason: str | None
    declined_at: datetime | None


# ------------------------------------------------------------------------------------------ reminders
class ReminderStatus(StrEnum):
    PAUSED = "paused"
    RESUMED = "resumed"
    """Handed back to the agent on release (sent at the nearest slot with the late label)."""
    DROPPED = "dropped"
    """Past its meaning when the conversation was released."""
    SENT_BY_STAFF = "sent_by_staff"


@dataclass(frozen=True)
class DueReminder:
    """A reminder that is already queued for the patient when a conversation leaves ``AUTO`` (S, B2)."""

    kind: EventKind
    rule: str | None
    due_at: datetime
    dedupe_key: str
    patient_ref: str
    """Pseudonym patient code (the event bus finds the care agent by it)."""
    payload: JsonObject = field(default_factory=dict[str, Any])


@dataclass(frozen=True)
class NewPausedReminder:
    clinic_id: UUID
    care_agent_id: UUID
    patient_id: UUID
    patient_ref: str
    kind: EventKind
    rule: str | None
    due_at: datetime
    dedupe_key: str
    prepared_text: str | None
    owner_user_id: UUID | None
    payload: JsonObject = field(default_factory=dict[str, Any])
    paused_at: datetime | None = None


@dataclass(frozen=True)
class PausedReminder:
    id: UUID
    care_agent_id: UUID
    patient_id: UUID
    patient_ref: str
    kind: EventKind
    rule: str | None
    due_at: datetime
    dedupe_key: str
    prepared_text: str | None
    owner_user_id: UUID | None
    status: ReminderStatus
    payload: JsonObject = field(default_factory=dict[str, Any])
    paused_at: datetime | None = None
    resolved_at: datetime | None = None
    resolution: str | None = None

    @property
    def meaning_key(self) -> str:
        """The key of the "past its meaning" rule: the CRM rule (``d1``, ``d3`` ...) or the event kind."""
        return self.rule if self.rule is not None else self.kind.value

    @property
    def anchor(self) -> object:
        return self.payload.get("anchor")


# --------------------------------------------------------------------------------------------- config
HOLDING_OUT_OF_HOURS = (
    "Cảm ơn anh/chị đã nhắn cho phòng khám. Hiện ngoài giờ làm việc, em đã chuyển tin nhắn đến "
    "nhân viên trực. Bên em sẽ phản hồi anh/chị vào khoảng {eta} ạ."
)
"""TEMPLATE for a D3-D4 handoff outside clinic hours; ``{eta}`` is the next opening time (code, not model
text). The wording awaits the doctor's approval."""

EMERGENCY_OUT_OF_HOURS = (
    "Em đã báo ngay cho nhân viên trực của phòng khám. Nếu anh/chị đang có dấu hiệu nặng "
    "(khó thở, chảy máu nhiều, ngất, đau dữ dội), vui lòng đến cơ sở cấp cứu gần nhất hoặc gọi 115 ngay. "
    "Số liên hệ trực 24/24 của phòng khám: {oncall_number}."
)
"""TEMPLATE for a D5 handoff outside clinic hours: the on-call number from the database and GENERIC
emergency guidance only (no medical content written by a model). Awaits the doctor's approval."""


def _default_max_late_hours() -> dict[str, int]:
    return {
        "d1": 48,
        "d3": 120,
        "d7": 168,
        "due": 72,
        "overdue": 336,
        "no_show": 72,
        "abandoned": 720,
        "dormant90": 720,
        "dormant180": 720,
        "session_completed": 24,
        "birthday": 24,
        "milestone_due": 72,
        "visit_overdue": 336,
        "dormant": 720,
    }


def _default_series_order() -> tuple[str, ...]:
    return ("d1", "d3", "d7")


def _default_prepared_texts() -> dict[str, str]:
    return {
        "d1": "Chào anh/chị, hôm qua anh/chị đã làm dịch vụ tại phòng khám. Anh/chị thấy thế nào ạ?",
        "d3": "Chào anh/chị, đã 3 ngày kể từ buổi làm dịch vụ. Anh/chị cho em biết tình trạng hiện tại nhé.",
        "d7": "Chào anh/chị, đã 1 tuần kể từ buổi làm dịch vụ. Anh/chị cần phòng khám hỗ trợ gì thêm ạ?",
        "due": "Chào anh/chị, đến hẹn tái khám theo lịch. Anh/chị muốn đặt giờ nào ạ?",
        "overdue": "Chào anh/chị, lịch tái khám của anh/chị đã quá hạn. Phòng khám hỗ trợ đặt lại lịch ạ.",
        "no_show": "Chào anh/chị, hôm nay phòng khám chưa gặp anh/chị. Anh/chị muốn đổi giờ khác không ạ?",
        "dormant90": "Chào anh/chị, lâu rồi phòng khám chưa gặp anh/chị. Anh/chị có cần hỗ trợ gì không ạ?",
        "dormant180": "Chào anh/chị, lâu rồi phòng khám chưa gặp anh/chị. Anh/chị có cần hỗ trợ gì không ạ?",
    }


class ReminderRules(BaseModel):
    """How a reminder ages while a person has the conversation. TEMPORARY defaults, doctor to confirm."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    max_late_hours: dict[str, int] = Field(default_factory=_default_max_late_hours)
    """A paused reminder later than this when the conversation is released is dropped ."""
    default_max_late_hours: int = Field(default=72, ge=0)
    series_order: tuple[str, ...] = Field(default_factory=_default_series_order)
    """A reminder is dropped when a LATER one of the same series (same ``anchor``) is already due: D+1 is
    meaningless once D+3 has passed."""
    prepared_texts: dict[str, str] = Field(default_factory=_default_prepared_texts)
    """Doctor-approved wording shown to staff with a paused reminder (a template, never model text)."""

    def max_late(self, key: str) -> timedelta:
        return timedelta(hours=self.max_late_hours.get(key, self.default_max_late_hours))


class RoutingConfig(BaseModel):
    """``agent.skills.classifier_config`` of the row ``routing``. Defaults are TEMPORARY."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    pending_doctor_approval: bool = True

    sla_urgent_minutes: int = Field(default=5, ge=1)
    """``urgent`` and ``critical``."""
    sla_normal_minutes: int = Field(default=30, ge=1)
    max_candidates: int = Field(default=5, ge=2, le=10)
    """Length of the chain INCLUDING the on-call contact at the end."""

    oncall_direct_from_depth: Depth = Depth.D3
    """Outside clinic hours a handoff of this depth or deeper goes straight to the on-call contact; a
    shallower one waits for the next shift (SLA = start of the next shift)."""
    doctor_roles: tuple[str, ...] = ("doctor",)
    generic_skills: tuple[str, ...] = ("general", "medical")
    """``required_skill`` values that name a kind of person, not a skill of a profile: ``medical`` means a
    doctor, ``general`` anybody."""
    medical_skill: str = "medical"

    holding_out_of_hours: str = HOLDING_OUT_OF_HOURS
    emergency_out_of_hours: str = EMERGENCY_OUT_OF_HOURS

    reminders: ReminderRules = Field(default_factory=ReminderRules)


def routing_config_from_row(raw: Mapping[str, Any] | None) -> RoutingConfig:
    return RoutingConfig.model_validate(dict(raw) if raw else {})

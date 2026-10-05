"""Vocabulary of the skill ``handoff`` and of the control state machine (PLAN-AI01-M sections 5 and 6).

New module (not a port). Pure data and no import of another ``pema.care`` module, so ``ports`` can use it.

``HandoffDecision`` is the structured output of the skill: ``{action: answer|handoff, reason, depth,
confidence, required_skill, urgency}`` (PLAN-M section 6). ``signals`` lists every signal that fired, in the
order the skill weighed them; ``reason`` is the first one (the one that decided). All values are codes, never
patient text.

``urgency`` has three values in the skill (``critical`` for a red flag) while
``agent.handoff_requests.urgency`` only knows ``urgent`` and ``normal`` (the table of M1 is final):
``critical`` is stored as ``urgent`` and the
``depth`` (D5) keeps the difference. ``db_urgency`` does that mapping in one place.

``HandoffConfig`` is the ``classifier_config`` jsonb of the row ``agent.skills.name = 'handoff'``: EVERY
threshold of the skill is a field here (the code never holds a number of its own). The defaults are TEMPORARY
and flagged ``pending_doctor_approval = True``: the doctor decides the final matrix (PLAN-M section 15,
decision 1). They are the defaults of PLAN-M section 6: D1 and D2 are answered, D3 is a draft for
review, D4 is
always a person, D5 a doctor at once; plus the more careful values for the patient states the plan lists.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HandoffAction(StrEnum):
    ANSWER = "answer"
    HANDOFF = "handoff"


class Depth(StrEnum):
    """How deep a question goes (PLAN-M section 6): D1 administrative ... D5 red flag."""

    D1 = "D1"
    D2 = "D2"
    D3 = "D3"
    D4 = "D4"
    D5 = "D5"

    @property
    def rank(self) -> int:
        return int(self.value[1:])


class Urgency(StrEnum):
    NORMAL = "normal"
    URGENT = "urgent"
    CRITICAL = "critical"


def db_urgency(urgency: Urgency) -> str:
    """``agent.handoff_requests.urgency`` allows ``urgent`` and ``normal`` only."""
    return "normal" if urgency is Urgency.NORMAL else "urgent"


class HandoffDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: HandoffAction
    reason: str
    depth: Depth
    confidence: float = Field(ge=0.0, le=1.0)
    required_skill: str
    urgency: Urgency = Urgency.NORMAL
    signals: tuple[str, ...] = ()


class DepthLlmOutput(BaseModel):
    """The JSON schema the depth classifier asks the model to fill (D2-D4 only: D1 is decided by rules, D5 by
    the red-flag rules, never by a model). A reply that does not validate counts as "no answer"."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    depth: Depth
    confidence: float = Field(ge=0.0, le=1.0)
    intent: str | None = None
    required_skill: str | None = None
    asks_for_human: bool = False
    negative_sentiment: bool = False
    repeated_question: bool = False
    answer_rejected: bool = False


def level_number(value: object) -> int | None:
    """Autonomy level as a number 0..2 from what the tables store (``"L0"``..``"L2"``) or a plain int."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if 0 <= value <= MAX_LEVEL else None
    if isinstance(value, str) and len(value) == 2 and value[0] == "L" and value[1] in "012":
        return int(value[1])
    return None


def level_code(level: int) -> str:
    return f"L{level}"


MAX_LEVEL = 2
"""Autonomy levels are L0..L2 (PLAN-M section 4)."""


class InvalidTransitionError(Exception):
    """The conversation is not in the state the call needs (a second accept, a release from AUTO, ...)."""


class ControlConfigError(Exception):
    """A switch that the clinic has not turned on (``auto_release_after`` without ``allow_auto_release``)."""


HOLDING_MESSAGE = (
    "Cảm ơn anh/chị đã nhắn cho phòng khám. Em đã chuyển tin nhắn đến nhân viên phụ trách, "
    "bên em sẽ phản hồi anh/chị sớm nhất ạ."
)
"""TEMPLATE, not model text; the wording awaits the doctor's approval (``pending_doctor_approval``)."""

HOLDING_MESSAGE_URGENT = (
    "Em đã báo ngay tin nhắn của anh/chị đến bác sĩ phụ trách. Bên em sẽ liên hệ lại anh/chị sớm nhất ạ."
)
"""Template for ``urgent`` and ``critical``; says nothing medical."""


def _default_intent_levels() -> dict[str, int | None]:
    return {"medical_judgement": None, "medication_change": None}


def _default_skill_by_intent() -> dict[str, str]:
    return {
        "booking": "dat_lich",
        "payment": "thanh_toan",
        "complaint": "khieu_nai",
        "acne": "mun",
        "melasma": "nam",
        "laser": "laser",
    }


def _default_skill_by_depth() -> dict[str, str]:
    return {"D1": "general", "D2": "general", "D3": "general", "D4": "medical", "D5": "medical"}


class HandoffConfig(BaseModel):
    """``agent.skills.classifier_config`` of the skill ``handoff``. Defaults are TEMPORARY."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    pending_doctor_approval: bool = True

    # confidence of the classifier below which a person decides, whatever the depth
    confidence_threshold: float = Field(default=0.6, ge=0.0, le=1.0)

    # "hand off from depth X": the lowest depth that goes to a person under that signal. The lowest applicable
    # one wins (a VIP who is also within 48h of a procedure uses the more careful of the two).
    default_handoff_from_depth: Depth = Depth.D4
    vip_handoff_from_depth: Depth = Depth.D2
    complex_history_handoff_from_depth: Depth = Depth.D3
    past_complaint_handoff_from_depth: Depth = Depth.D3
    pending_doctor_work_handoff_from_depth: Depth = Depth.D3
    unverified_max_depth: Depth = Depth.D1
    """An unverified patient gets D1 (administrative) answers only; anything deeper goes to a person."""
    post_procedure_window_hours: int = Field(default=48, ge=0)
    post_procedure_handoff_from_depth: Depth = Depth.D3
    out_of_hours_handoff_from_depth: Depth = Depth.D3
    asks_for_human_handoff_from_depth: Depth = Depth.D2
    negative_sentiment_handoff_from_depth: Depth = Depth.D2
    repeated_question_handoff_from_depth: Depth = Depth.D2
    answer_rejected_handoff_from_depth: Depth = Depth.D2
    repeat_question_threshold: int = Field(default=2, ge=2)
    """The same question asked this many times counts as "repeated" (from the context facts)."""

    # the lowest autonomy level an intent may be handled at; ``None``: never without a person
    intent_min_level: dict[str, int | None] = Field(default_factory=_default_intent_levels)

    urgent_from_depth: Depth = Depth.D4
    skill_by_intent: dict[str, str] = Field(default_factory=_default_skill_by_intent)
    skill_by_depth: dict[str, str] = Field(default_factory=_default_skill_by_depth)

    # return to AUTO: there is NO time-based return unless the clinic turns this on (PLAN-M section 5)
    allow_auto_release: bool = False

    holding_message: str = HOLDING_MESSAGE
    holding_message_urgent: str = HOLDING_MESSAGE_URGENT


def config_from_row(raw: dict[str, Any] | None) -> HandoffConfig:
    """The config of a ``classifier_config`` jsonb; a field that is missing keeps its default."""
    return HandoffConfig.model_validate(raw or {})

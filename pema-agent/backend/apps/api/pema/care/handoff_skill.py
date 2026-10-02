"""The skill ``handoff``: the agent senses by itself when a person is needed (PLAN-AI01-M sections 5 and 6).

New module (not a port). Zalo-agent's per-thread ``bot_enabled`` is the on/off switch of the channel; this
skill is the part that decides to move a conversation to a person (there is no "talk to a human" button,
PLAN-M section 15, decision 4). It runs before EVERY reply: ``HandoffSkill`` is the
``HandoffDecider`` the turn loop asks (``pema.care.loop``), and its verdict carries the full
``HandoffDecision``.

Signals weighed (PLAN-M section 6), all through ``HandoffConfig`` (``agent.skills.classifier_config``; every
default is TEMPORARY and ``pending_doctor_approval``):

* depth of the question (``pema.care.depth``): D5 is a red flag, decided before anything else and without a
  model (the early return below);
* the classifier's own confidence under ``confidence_threshold``;
* the patient: VIP, complex history, past complaint, work waiting for a doctor, identity not
  verified (D1 only);
* mood and course: the patient asks for a person (a SIGNAL that lowers the depth that goes to a
  person, never a command), is upset, repeats the question, rejected the last answer;
* context: outside clinic hours, within ``post_procedure_window_hours`` of a procedure;
* limit of rights: an intent the agent's autonomy level does not cover (``intent_min_level``).

Each signal gives "hand off from depth X"; the LOWEST applicable X wins, so the more careful signal rules. The
patient facts come from ``PatientContext.facts`` (loaded through ``actions/``, PII-masked): ``vip``,
``complex_history``, ``past_complaint``, ``pending_doctor_work`` (bool), ``last_procedure_at`` (ISO time),
``repeat_count`` (int), ``identity_verified`` (bool; without it, a patient with a verified channel counts as
verified, one without does not). A missing fact is "no" except identity, which is "not verified".

``ensure_handoff_skill`` seeds the row ``agent.skills`` ``handoff``; ``SqlHandoffConfigSource`` reads it
on every turn. A row whose ``classifier_config`` does not validate falls back to the defaults (and says
so in the log).
The column ``enabled_for_profiles`` is NOT used to switch the skill off: it always runs for a care agent.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.depth import EVENT_DEPTH, DepthClassifier, DepthResult, DepthSource
from pema.care.events import CareEvent, EventKind
from pema.care.handoff_types import (
    Depth,
    HandoffAction,
    HandoffConfig,
    HandoffDecision,
    Urgency,
    config_from_row,
    level_number,
)
from pema.care.models import PATIENT_CHANNEL_PROFILE, Skill
from pema.care.ports import (
    CareAgentSnapshot,
    HandoffConfigSource,
    HandoffSettings,
    HandoffVerdict,
    MessageTextSource,
    PatientContext,
    SendWindowProvider,
)
from pema.core.db import ClinicDatabase

logger = logging.getLogger(__name__)

HANDOFF_SKILL_NAME = "handoff"

HANDOFF_INSTRUCTION = (
    "Bạn là bộ phân loại độ sâu của trợ lý chăm sóc khách phòng khám da liễu. Đọc tin nhắn của khách và xếp "
    "vào D1 (hành chính: lịch hẹn, giờ làm việc, địa chỉ, thanh toán), D2 (hướng dẫn chăm sóc chuẩn), "
    "D3 (triệu chứng nhẹ trong dự kiến sau thủ thuật), D4 (cần phán đoán y khoa: đổi thuốc, triệu chứng "
    "bất thường, câu hỏi chẩn đoán). Không bao giờ trả lời câu hỏi của khách, không chẩn đoán, "
    "không gợi ý thuốc. "
    "Nếu không chắc, chọn độ sâu cao hơn và ghi độ tin cậy thấp."
)
"""Instruction of the classifier call (the ``instruction`` column). Wording awaits the doctor."""

# signal codes (reason / signals of the decision; never patient text)
RED_FLAG = "red_flag"
LOW_CONFIDENCE = "low_confidence"
NO_TEXT = "no_text"
UNVERIFIED = "unverified_patient"
VIP = "vip"
COMPLEX_HISTORY = "complex_history"
PAST_COMPLAINT = "past_complaint"
PENDING_DOCTOR_WORK = "pending_doctor_work"
POST_PROCEDURE = "within_post_procedure_window"
OUT_OF_HOURS = "out_of_hours"
ASKS_FOR_HUMAN = "patient_asks_for_human"
NEGATIVE_SENTIMENT = "negative_sentiment"
REPEATED_QUESTION = "repeated_question"
ANSWER_REJECTED = "answer_rejected"
EXCEEDS_AUTONOMY = "exceeds_autonomy"
DEPTH_THRESHOLD = "depth_at_or_above_threshold"
WITHIN_AUTONOMY = "within_autonomy"
NOT_A_PATIENT_MESSAGE = "not_a_patient_message"
CLASSIFIER_FALLBACK = "classifier_unavailable"

type Clock = Callable[[], datetime]


@dataclass(frozen=True)
class PatientSignals:
    """The patient-state signals, read from ``PatientContext.facts`` (see the module docstring)."""

    vip: bool = False
    complex_history: bool = False
    past_complaint: bool = False
    pending_doctor_work: bool = False
    verified: bool = False
    last_procedure_at: datetime | None = None
    repeat_count: int = 0

    @classmethod
    def from_context(cls, context: PatientContext) -> PatientSignals:
        facts = context.facts
        return cls(
            vip=facts.get("vip") is True,
            complex_history=facts.get("complex_history") is True,
            past_complaint=facts.get("past_complaint") is True,
            pending_doctor_work=facts.get("pending_doctor_work") is True,
            verified=_bool(facts.get("identity_verified"), default=context.channel is not None),
            last_procedure_at=_parse_time(facts.get("last_procedure_at")),
            repeat_count=_int(facts.get("repeat_count")),
        )


def _bool(value: object, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _parse_time(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def effective_level(agent: CareAgentSnapshot, intent: str, now: datetime) -> int:
    """The autonomy level of the agent for ``intent`` (a number 0..2; the tables store ``"L0"``..``"L2"``,
    ``level_number`` reads both). M3 owns the meaning of the levels; this
    only reads them: ``autonomy_levels[intent]``, else ``autonomy_levels['default']``, else 0 (L0), lowered by
    a time-boxed ``autonomy_override`` that has not expired."""
    levels = agent.autonomy_levels
    base = _level(levels.get(intent), _level(levels.get("default"), 0))
    override = agent.autonomy_override
    if override is None:
        return base
    until = _parse_time(override.get("until"))
    if until is not None and until <= now:
        return base
    return min(base, _level(override.get("level"), base))


def _level(value: object, default: int) -> int:
    parsed = level_number(value)
    return default if parsed is None else parsed


class HandoffSkill:
    """``HandoffDecider`` of the care loop."""

    def __init__(
        self,
        *,
        classifier: DepthClassifier,
        config_source: HandoffConfigSource,
        texts: MessageTextSource,
        clock: Clock,
        window: SendWindowProvider | None = None,
    ) -> None:
        self._classifier = classifier
        self._config = config_source
        self._texts = texts
        self._clock = clock
        self._window = window

    async def decide(
        self, agent: CareAgentSnapshot, event: CareEvent, context: PatientContext
    ) -> HandoffVerdict:
        decision = await self.evaluate(agent, event, context)
        return HandoffVerdict(decision.action, decision.reason, decision)

    async def evaluate(
        self, agent: CareAgentSnapshot, event: CareEvent, context: PatientContext
    ) -> HandoffDecision:
        if event.kind is not EventKind.PATIENT_MESSAGE:
            # the patient asked nothing: what the agent writes because of a system event is standard care (a
            # draft for staff when the patient has no verified channel), not a question that needs a person.
            return HandoffDecision(
                action=HandoffAction.ANSWER,
                reason=NOT_A_PATIENT_MESSAGE,
                depth=EVENT_DEPTH.get(event.kind, Depth.D1),
                confidence=1.0,
                required_skill="general",
            )
        now = self._clock()
        settings = await self._config.get(agent.clinic_id)
        config = settings.config
        texts = await self._texts.patient_texts(agent, event)
        result = await self._classifier.classify(event, texts, instruction=settings.instruction)

        if result.depth is Depth.D5:  # a red flag: a doctor at once; nothing below may soften it
            return _red_flag_decision(result, config)

        signals = PatientSignals.from_context(context)
        in_hours = await self._in_hours(agent, now)
        return _weigh(agent, result, signals, config, now, in_hours=in_hours)

    async def _in_hours(self, agent: CareAgentSnapshot, now: datetime) -> bool:
        if self._window is None:
            return True
        window = await self._window.get(agent.clinic_id)
        return window.is_open(now)


def _skill_for(result: DepthResult, config: HandoffConfig) -> str:
    if result.required_skill:
        return result.required_skill
    if result.intent is not None and result.intent in config.skill_by_intent:
        return config.skill_by_intent[result.intent]
    return config.skill_by_depth.get(result.depth.value, "general")


def _red_flag_decision(result: DepthResult, config: HandoffConfig) -> HandoffDecision:
    codes = tuple(f"{RED_FLAG}:{category}" for category in result.red_flags) or (RED_FLAG,)
    return HandoffDecision(
        action=HandoffAction.HANDOFF,
        reason=RED_FLAG,
        depth=Depth.D5,
        confidence=1.0,
        required_skill=config.skill_by_depth.get("D5", "medical"),
        urgency=Urgency.CRITICAL,
        signals=(RED_FLAG, *codes),
    )


def _thresholds(
    result: DepthResult,
    patient: PatientSignals,
    config: HandoffConfig,
    now: datetime,
    *,
    in_hours: bool,
) -> list[tuple[str, int]]:
    """Every applicable "hand off from depth" as ``(signal, rank)``, in the order the plan lists them."""
    found: list[tuple[str, int]] = []
    if not patient.verified:
        found.append((UNVERIFIED, config.unverified_max_depth.rank + 1))
    if patient.vip:
        found.append((VIP, config.vip_handoff_from_depth.rank))
    if patient.complex_history:
        found.append((COMPLEX_HISTORY, config.complex_history_handoff_from_depth.rank))
    if patient.past_complaint:
        found.append((PAST_COMPLAINT, config.past_complaint_handoff_from_depth.rank))
    if patient.pending_doctor_work:
        found.append((PENDING_DOCTOR_WORK, config.pending_doctor_work_handoff_from_depth.rank))
    if result.signals.asks_for_human:
        found.append((ASKS_FOR_HUMAN, config.asks_for_human_handoff_from_depth.rank))
    if result.signals.negative_sentiment:
        found.append((NEGATIVE_SENTIMENT, config.negative_sentiment_handoff_from_depth.rank))
    if result.signals.repeated_question or patient.repeat_count >= config.repeat_question_threshold:
        found.append((REPEATED_QUESTION, config.repeated_question_handoff_from_depth.rank))
    if result.signals.answer_rejected:
        found.append((ANSWER_REJECTED, config.answer_rejected_handoff_from_depth.rank))
    if _within_post_procedure(patient, config, now):
        found.append((POST_PROCEDURE, config.post_procedure_handoff_from_depth.rank))
    if not in_hours:
        found.append((OUT_OF_HOURS, config.out_of_hours_handoff_from_depth.rank))
    return found


def _within_post_procedure(patient: PatientSignals, config: HandoffConfig, now: datetime) -> bool:
    done = patient.last_procedure_at
    if done is None or done > now:
        return False
    return (now - done).total_seconds() <= config.post_procedure_window_hours * 3600


def _exceeds_autonomy(
    agent: CareAgentSnapshot, result: DepthResult, config: HandoffConfig, now: datetime
) -> bool:
    intent = result.intent
    if intent is None or intent not in config.intent_min_level:
        return False
    needed = config.intent_min_level[intent]
    return needed is None or effective_level(agent, intent, now) < needed


def _urgency(depth: Depth, post_procedure: bool, config: HandoffConfig) -> Urgency:
    if depth is Depth.D5:
        return Urgency.CRITICAL
    if depth.rank >= config.urgent_from_depth.rank or (post_procedure and depth.rank >= Depth.D3.rank):
        return Urgency.URGENT
    return Urgency.NORMAL


def _weigh(
    agent: CareAgentSnapshot,
    result: DepthResult,
    patient: PatientSignals,
    config: HandoffConfig,
    now: datetime,
    *,
    in_hours: bool,
) -> HandoffDecision:
    fired: list[str] = []
    if result.source is DepthSource.FALLBACK:
        fired.append(CLASSIFIER_FALLBACK)
    if result.source is DepthSource.NO_TEXT:
        fired.append(NO_TEXT)
    if result.confidence < config.confidence_threshold:
        fired.append(LOW_CONFIDENCE)

    thresholds = _thresholds(result, patient, config, now, in_hours=in_hours)
    if result.depth.rank >= config.default_handoff_from_depth.rank:
        fired.append(DEPTH_THRESHOLD)
    fired.extend(signal for signal, rank in thresholds if result.depth.rank >= rank)
    if _exceeds_autonomy(agent, result, config, now):
        fired.append(EXCEEDS_AUTONOMY)

    handoff = bool(fired)
    post_procedure = any(signal == POST_PROCEDURE for signal, _ in thresholds)
    return HandoffDecision(
        action=HandoffAction.HANDOFF if handoff else HandoffAction.ANSWER,
        reason=fired[0] if fired else WITHIN_AUTONOMY,
        depth=result.depth,
        confidence=result.confidence,
        required_skill=_skill_for(result, config),
        urgency=_urgency(result.depth, post_procedure, config) if handoff else Urgency.NORMAL,
        signals=tuple(fired),
    )


# ------------------------------------------------------------------------------------ the skill row
async def ensure_handoff_skill(session: AsyncSession, clinic_id: UUID) -> None:
    """Seed ``agent.skills`` ``handoff`` with the temporary defaults (``pending_doctor_approval = true``).

    Idempotent: an existing row (maybe edited by the doctor on the dashboard) is left alone."""
    await session.execute(
        pg_insert(Skill)
        .values(
            clinic_id=clinic_id,
            name=HANDOFF_SKILL_NAME,
            instruction=HANDOFF_INSTRUCTION,
            classifier_config=HandoffConfig().model_dump(mode="json"),
            enabled_for_profiles=[PATIENT_CHANNEL_PROFILE],
        )
        .on_conflict_do_nothing(index_elements=[Skill.clinic_id, Skill.name])
    )


class SqlHandoffConfigSource:
    """``HandoffConfigSource`` over ``agent.skills``; read on every turn, defaults when there is no row."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get(self, clinic_id: UUID) -> HandoffSettings:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(Skill.instruction, Skill.classifier_config).where(
                        Skill.clinic_id == clinic_id, Skill.name == HANDOFF_SKILL_NAME
                    )
                )
            ).first()
        if row is None:
            return HandoffSettings(HANDOFF_INSTRUCTION, HandoffConfig())
        raw: Mapping[str, Any] = row.classifier_config
        try:
            config = config_from_row(dict(raw))
        except ValidationError:
            logger.error("handoff classifier_config is invalid; defaults are used")
            config = HandoffConfig()
        return HandoffSettings(row.instruction or HANDOFF_INSTRUCTION, config)

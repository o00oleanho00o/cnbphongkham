"""Autonomy levels L0-L2 per action type, override, pause and kill switches (package M, step M3).

New module (not a port of zalo-agent). Source: ``docs/PLAN-AI01-M.md`` sections 4 and 15 (decisions 1 and 3)
and ``recipes/M/05-M3-autonomy.md``. Single tenant: no row level security; ``clinic_id`` is the
installation id.

What a care agent may do without a person
-----------------------------------------
============  ==========================================================================================
level         the agent may send, without review
============  ==========================================================================================
L0            nothing: everything is a draft (default for a new patient and after a demotion)
L1            a message FROM a doctor-approved template (``settings.templates_l1``); the confirmation of
              an appointment slot the patient picked
L2            L1 plus ``faq_kb_answer`` with >= 1 knowledge-base citation, ``confidence >= threshold``,
              no red flag and depth <= D2 (D3 only for the types the doctor enabled)
============  ==========================================================================================

Always a person, whatever the configuration says (hard rules, tested, not configurable):
``medical_judgement``, any D4 or D5 depth, any red flag, ``birthday_greeting`` (clinic rule: a birthday is a
staff task) and any marketing text for a patient with ``marketingOptOut``. The ``patient_channel`` profile
(``pema_contracts.policy``) is a hard CEILING: ``evaluate_auto_send`` also refuses what the profile refuses
(unverified identity, a scheduled text that is not from a template) and nothing here edits a profile.

Where the numbers live
----------------------
* Per agent: ``agent.care_agents.autonomy_levels`` ({action_type: "L0"|"L1"|"L2"}, an EXPLICIT entry wins over
  the clinic floor below), ``autonomy_override`` ({level, until, note?, set_by?}), ``paused``.
* Per installation: ``AutonomySettings`` (key ``care.autonomy`` of the runtime settings KV, the table
  ``agent.runtime_settings``; there is no ``clinic.settings`` table) and ``KillSwitchState`` (key
  ``care.kill_switch``). Both are read synchronously from the in-memory snapshot, so ``effective_level`` and
  ``may_auto_send`` stay plain functions. Every default value is TEMPORARY and flagged
  ``pending_doctor_approval=True``: the doctor decides the final N, threshold and serious-edit rule.

Decisions of this step (the recipe leaves them open)
----------------------------------------------------
* The clinic floor: when the clinic enables a template (``templates_l1`` not empty) the template types are L1
  for every agent without an explicit entry; ``appointment_confirm`` is L1 only after
  ``appointment_confirm_l1`` is switched on. A new patient with nothing enabled is L0 everywhere. A demotion
  writes explicit ``L0`` entries, so it also beats the floor.
* The override LOWERS, never raises: ``effective = min(base, override.level)``. An expired override is ignored
  by ``effective_level`` at once and removed (with a log row) by ``resolve_level``.
* ``paused`` and ANY kill switch (system, or any specialist agent) give L0: a switched-off Reviewer agent
  means drafts are not checked, so nothing may leave without a person. An unreadable kill switch value fails
  closed (treated as "system on").
* Levels only go UP through the trust score (``pema.care.trust``); ``demote`` and ``demote_all_to_l0`` are the
  only manual level writes, and they refuse to raise a level.
* Audit: every level change writes ``agent.actions_log`` with ``action_type='autonomy_change'`` and the
  initiator inside ``reviewer_edit_diff``. The table has no ``kind``/``initiator`` column (M1 final) and its
  ``disposition`` CHECK allows only auto_sent/reviewed/paused, so the row uses ``disposition='reviewed'``;
  ``log_autonomy_change`` is the single place to change when M1 adds the columns. The log never carries the
  staff note or any patient text.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import null, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.models import ActionDisposition, ActionLog, CareAgent
from pema.config.runtime_settings_kv import RuntimeSettingsKv, get_runtime_settings_kv
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    PATIENT_CHANNEL_PROFILE,
    PolicyProfile,
    PolicyProfileKey,
    ScheduledJobPolicy,
)

logger = logging.getLogger(__name__)

SETTINGS_KEY = "care.autonomy"
KILL_SWITCH_KEY = "care.kill_switch"
AUTONOMY_CHANGE = "autonomy_change"
SYSTEM_SCOPE = "system"


class Level(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"

    @property
    def rank(self) -> int:
        return _RANK[self]


_RANK = {Level.L0: 0, Level.L1: 1, Level.L2: 2}


def min_level(a: Level, b: Level) -> Level:
    return a if a.rank <= b.rank else b


class ActionType(StrEnum):
    REMINDER_TEMPLATE = "reminder_template"
    CARE_GUIDE_TEMPLATE = "care_guide_template"
    APPOINTMENT_CONFIRM = "appointment_confirm"
    FAQ_KB_ANSWER = "faq_kb_answer"
    SYMPTOM_REPLY = "symptom_reply"
    MEDICAL_JUDGEMENT = "medical_judgement"
    BIRTHDAY_GREETING = "birthday_greeting"


ACTION_TYPES: tuple[str, ...] = tuple(t.value for t in ActionType)

TEMPLATE_TYPES: frozenset[str] = frozenset(
    {ActionType.REMINDER_TEMPLATE.value, ActionType.CARE_GUIDE_TEMPLATE.value}
)
ALWAYS_HUMAN_TYPES: frozenset[str] = frozenset({ActionType.MEDICAL_JUDGEMENT.value})
"""A medical judgement, a medicine change, an abnormal symptom: never automatic, not configurable."""
NEVER_AUTO_SENT_TYPES: frozenset[str] = frozenset({ActionType.BIRTHDAY_GREETING.value})
"""Clinic rule: a birthday greeting is a staff task, never auto-sent, not configurable."""
HARD_HUMAN_TYPES: frozenset[str] = ALWAYS_HUMAN_TYPES | NEVER_AUTO_SENT_TYPES

DEPTH_ORDER: tuple[str, ...] = ("D1", "D2", "D3", "D4", "D5")
HUMAN_DEPTHS: frozenset[str] = frozenset({"D4", "D5"})
"""D4: always call a person. D5: call the doctor at once, no LLM call."""
L1_MAX_DEPTH = "D1"
L2_MAX_DEPTH = "D2"
TEMPLATE_DEFAULT_DEPTH = "D1"
"""A template message has no classified depth; it counts as D1."""


class Initiator(StrEnum):
    SYSTEM = "system"
    STAFF = "staff"
    DOCTOR = "doctor"
    MANAGER = "manager"


# ================================================================================================ settings
class SeriousEditRule(BaseModel):
    """What counts as a SERIOUS edit of a draft (TEMPORARY: the doctor decides the final rule).

    A deterministic text comparison between the draft and the text the reviewer approved
    (``pema.care.trust.classify_edit``). Each check can be switched off. Lists are lower case; matching is
    case-insensitive on NFC text.
    """

    model_config = ConfigDict(frozen=True)

    changed_clinical_meaning: bool = True
    """A dose, duration, count or percentage differs, or a prohibition appears or disappears."""
    removed_warning: bool = True
    """A warning phrase of the draft is no longer in the final text."""
    added_drug: bool = True
    """A drug name or a new dose of a medicine appears that the draft did not have."""
    warning_markers: tuple[str, ...] = (
        "lưu ý",
        "cảnh báo",
        "khẩn cấp",
        "đi khám ngay",
        "liên hệ ngay",
        "gọi ngay",
        "tuyệt đối không",
        "không được",
        "chống chỉ định",
        "tác dụng phụ",
        "dị ứng",
        "nếu sưng",
        "nếu chảy máu",
        "nếu sốt",
    )
    drug_terms: tuple[str, ...] = (
        "paracetamol",
        "ibuprofen",
        "aspirin",
        "diclofenac",
        "amoxicillin",
        "augmentin",
        "metronidazole",
        "clindamycin",
        "prednisolone",
        "corticoid",
        "kháng sinh",
        "giảm đau",
    )
    negation_phrases: tuple[str, ...] = (
        "không được",
        "không nên",
        "không cần",
        "đừng",
        "tránh",
        "cấm",
        "kiêng",
        "ngưng",
        "ngừng",
        "dừng",
    )
    quantity_units: tuple[str, ...] = (
        "mg",
        "mcg",
        "ml",
        "g",
        "viên",
        "ống",
        "gói",
        "lần",
        "ngày",
        "giờ",
        "phút",
        "tuần",
        "tháng",
        "%",
        "°c",
    )


class AutonomySettings(BaseModel):
    """Installation-wide autonomy configuration. EVERY default is temporary (doctor decides, section 15.1)."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    n_to_l2: dict[str, int] = Field(default_factory=lambda: {ActionType.FAQ_KB_ANSWER.value: 10})
    """Approved-unchanged drafts of one type needed to promote that type to L2 (TEMPORARY N = 10)."""
    templates_l1: tuple[str, ...] = ()
    """Ids of the templates the doctor approved for sending without review (empty = none)."""
    appointment_confirm_l1: bool = False
    """The clinic let ``appointment_confirm`` of a slot the patient picked run at L1 for every agent."""
    confidence_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
    """L2 ``faq_kb_answer`` needs ``confidence >= threshold`` (TEMPORARY 0.85)."""
    d3_enabled_types: tuple[str, ...] = ()
    """Types for which the doctor opened depth D3 at L2 (default none: D3 is draft + review)."""
    serious_edit_rule: SeriousEditRule = Field(default_factory=SeriousEditRule)
    pending_doctor_approval: bool = True

    @field_validator("n_to_l2")
    @classmethod
    def _n_to_l2(cls, value: dict[str, int]) -> dict[str, int]:
        kept: dict[str, int] = {}
        for action_type, n in value.items():
            if action_type in HARD_HUMAN_TYPES:
                logger.warning(
                    "autonomy settings: hard rule type ignored in n_to_l2", extra={"type": action_type}
                )
                continue
            if n >= 1:
                kept[action_type] = n
        return kept

    @field_validator("d3_enabled_types")
    @classmethod
    def _d3_types(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(t for t in value if t not in HARD_HUMAN_TYPES)

    def l1_floor(self, action_type: str) -> Level:
        """The level every agent without an explicit entry has for ``action_type``."""
        if action_type in TEMPLATE_TYPES and self.templates_l1:
            return Level.L1
        if action_type == ActionType.APPOINTMENT_CONFIRM.value and self.appointment_confirm_l1:
            return Level.L1
        return Level.L0


@dataclass(frozen=True)
class KillSwitchState:
    """System-wide switch and one switch per specialist agent (Scheduler, Knowledge, Reviewer)."""

    system: bool = False
    agents: frozenset[str] = field(default_factory=frozenset[str])

    @property
    def any_on(self) -> bool:
        return self.system or bool(self.agents)

    def blocks(self, specialist_agent_id: str) -> bool:
        """M4 asks this before it runs a specialist agent."""
        return self.system or specialist_agent_id in self.agents

    def to_json(self) -> str:
        return json.dumps({"system": self.system, "agents": sorted(self.agents)}, separators=(",", ":"))


FAIL_CLOSED_KILL_SWITCH = KillSwitchState(system=True)


def load_settings(kv: RuntimeSettingsKv | None = None) -> AutonomySettings:
    """The stored settings, or the temporary defaults (flagged pending). An unreadable value gives the
    defaults, which allow nothing beyond L0 (no template enabled)."""
    raw = (kv or get_runtime_settings_kv()).get(SETTINGS_KEY)
    if raw is None:
        return AutonomySettings()
    try:
        return AutonomySettings.model_validate_json(raw)
    except ValidationError:
        logger.error("autonomy settings unreadable, using the temporary defaults")
        return AutonomySettings()


async def save_settings(settings: AutonomySettings, kv: RuntimeSettingsKv | None = None) -> None:
    await (kv or get_runtime_settings_kv()).aset(SETTINGS_KEY, settings.model_dump_json())


class _KillSwitchValue(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    system: bool = False
    agents: list[str] = Field(default_factory=list[str])


def load_kill_switch(kv: RuntimeSettingsKv | None = None) -> KillSwitchState:
    raw = (kv or get_runtime_settings_kv()).get(KILL_SWITCH_KEY)
    if raw is None:
        return KillSwitchState()
    try:
        value = _KillSwitchValue.model_validate_json(raw)
    except ValidationError:
        logger.error("kill switch value unreadable, failing closed (system switch on)")
        return FAIL_CLOSED_KILL_SWITCH
    return KillSwitchState(system=value.system, agents=frozenset(value.agents))


async def set_kill_switch(
    scope: str,
    on: bool,
    *,
    initiator: Initiator,
    kv: RuntimeSettingsKv | None = None,
) -> KillSwitchState:
    """Manager API: switch the whole system (``scope='system'``) or one specialist agent on or off.

    Effect: ``effective_level`` is L0 for every care agent while any switch is on, so nothing auto-sends.
    There is no care agent to attach an ``actions_log`` row to; the change is logged here (no PII) and the
    HTTP layer records it in the clinic audit log.
    """
    store = kv or get_runtime_settings_kv()
    current = load_kill_switch(store)
    if scope == SYSTEM_SCOPE:
        new = KillSwitchState(system=on, agents=current.agents)
    else:
        agents = set(current.agents)
        if on:
            agents.add(scope)
        else:
            agents.discard(scope)
        new = KillSwitchState(system=current.system, agents=frozenset(agents))
    await store.aset(KILL_SWITCH_KEY, new.to_json())
    logger.warning("kill switch changed", extra={"scope": scope, "on": on, "initiator": initiator.value})
    return new


# ============================================================================================ level reading
def _level_or_none(value: object) -> Level | None:
    try:
        return Level(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _parse_until(override: Mapping[str, Any]) -> datetime | None:
    raw: Any = override.get("until")
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def active_override(care_agent: CareAgent, now: datetime) -> Level | None:
    """The level of a running override (``until > now``), else ``None`` (none, expired or unreadable)."""
    override = care_agent.autonomy_override
    if not override:
        return None
    until = _parse_until(override)
    level = _level_or_none(override.get("level"))
    if until is None or level is None or until <= now:
        return None
    return level


def override_expired(care_agent: CareAgent, now: datetime) -> bool:
    """An override is stored but no longer applies."""
    return bool(care_agent.autonomy_override) and active_override(care_agent, now) is None


def base_level(care_agent: CareAgent, action_type: str, settings: AutonomySettings) -> Level:
    """Explicit entry of the agent, else the clinic floor (before override, pause and kill switches)."""
    explicit = _level_or_none((care_agent.autonomy_levels or {}).get(action_type))
    return explicit if explicit is not None else settings.l1_floor(action_type)


def effective_level(
    care_agent: CareAgent,
    action_type: str,
    now: datetime,
    *,
    settings: AutonomySettings | None = None,
    kill_switch: KillSwitchState | None = None,
) -> Level:
    """The level that applies to ``action_type`` of ``care_agent`` right now.

    Order: unknown type or hard-human type -> L0; paused or any kill switch -> L0; a running override can only
    lower the agent's own level; an expired override is ignored (``resolve_level`` removes it).
    """
    if action_type not in ACTION_TYPES or action_type in HARD_HUMAN_TYPES:
        return Level.L0
    cfg = settings if settings is not None else load_settings()
    switches = kill_switch if kill_switch is not None else load_kill_switch()
    if care_agent.paused or switches.any_on:
        return Level.L0
    level = base_level(care_agent, action_type, cfg)
    override = active_override(care_agent, now)
    return min_level(level, override) if override is not None else level


def levels_snapshot(
    care_agent: CareAgent,
    now: datetime,
    *,
    settings: AutonomySettings | None = None,
    kill_switch: KillSwitchState | None = None,
) -> dict[str, Level]:
    """``effective_level`` of every action type (supervision screen)."""
    cfg = settings if settings is not None else load_settings()
    switches = kill_switch if kill_switch is not None else load_kill_switch()
    return {t: effective_level(care_agent, t, now, settings=cfg, kill_switch=switches) for t in ACTION_TYPES}


# ============================================================================================ auto-send gate
@dataclass(frozen=True)
class AutoSendDecision:
    """What the care agent wants to send, as the facts ``may_auto_send`` needs (no text, no PII)."""

    action_type: str
    depth: str | None = None
    template_id: str | None = None
    slot_picked_by_patient: bool = False
    kb_citations: int = 0
    confidence: float | None = None
    red_flags: tuple[str, ...] = ()
    is_marketing: bool = False
    marketing_opt_out: bool = False
    identity_verified: bool = False
    scheduled: bool = False


@dataclass(frozen=True)
class AutoSendVerdict:
    allowed: bool
    reason: str
    """Short code for the audit log: ``ok`` or why a person must handle it."""


def _depth_rank(depth: str) -> int | None:
    return DEPTH_ORDER.index(depth) if depth in DEPTH_ORDER else None


def _within(depth: str | None, limit: str, *, none_means: str | None) -> bool:
    effective = depth if depth is not None else none_means
    if effective is None:
        return False
    rank = _depth_rank(effective)
    return rank is not None and rank <= DEPTH_ORDER.index(limit)


def _resolve_profile(profile: PolicyProfile | PolicyProfileKey | str | None) -> PolicyProfile:
    if profile is None:
        return PATIENT_CHANNEL_PROFILE
    if isinstance(profile, PolicyProfile):
        return profile
    try:
        return DEFAULT_PROFILES[PolicyProfileKey(profile)]
    except ValueError:
        return PATIENT_CHANNEL_PROFILE


def evaluate_auto_send(
    decision: AutoSendDecision,
    level: Level,
    *,
    settings: AutonomySettings | None = None,
    profile: PolicyProfile | PolicyProfileKey | str | None = None,
) -> AutoSendVerdict:
    """``may_auto_send`` with the reason. ``level`` is the ``effective_level`` of ``decision.action_type``."""
    cfg = settings if settings is not None else load_settings()
    prof = _resolve_profile(profile)
    kind = decision.action_type

    # hard rules and the profile ceiling come first: no level can lift them
    if kind not in ACTION_TYPES:
        return AutoSendVerdict(False, "unknown_action_type")
    if kind in ALWAYS_HUMAN_TYPES:
        return AutoSendVerdict(False, "always_human")
    if kind in NEVER_AUTO_SENT_TYPES:
        return AutoSendVerdict(False, "never_auto_sent")
    if decision.depth is not None and (decision.depth in HUMAN_DEPTHS or _depth_rank(decision.depth) is None):
        return AutoSendVerdict(False, "depth_requires_human")
    if decision.red_flags:
        return AutoSendVerdict(False, "red_flag")
    if decision.is_marketing and decision.marketing_opt_out:
        return AutoSendVerdict(False, "marketing_opt_out")
    if prof.require_identity_verification and not decision.identity_verified:
        return AutoSendVerdict(False, "identity_not_verified")
    if (
        decision.scheduled
        and prof.scheduled_jobs is ScheduledJobPolicy.MESSAGE_FROM_TEMPLATE_ONLY
        and kind not in TEMPLATE_TYPES
    ):
        return AutoSendVerdict(False, "scheduled_not_from_template")
    if level is Level.L0:
        return AutoSendVerdict(False, "level_l0")

    # abilities of L1
    if kind in TEMPLATE_TYPES:
        if not _within(decision.depth, L1_MAX_DEPTH, none_means=TEMPLATE_DEFAULT_DEPTH):
            return AutoSendVerdict(False, "depth_too_deep")
        if decision.template_id is None or decision.template_id not in cfg.templates_l1:
            return AutoSendVerdict(False, "template_not_approved")
        return AutoSendVerdict(True, "ok")
    if kind == ActionType.APPOINTMENT_CONFIRM.value:
        if not _within(decision.depth, L1_MAX_DEPTH, none_means=TEMPLATE_DEFAULT_DEPTH):
            return AutoSendVerdict(False, "depth_too_deep")
        if not decision.slot_picked_by_patient:
            return AutoSendVerdict(False, "slot_not_picked_by_patient")
        return AutoSendVerdict(True, "ok")

    # abilities added by L2
    if kind == ActionType.FAQ_KB_ANSWER.value:
        if level.rank < Level.L2.rank:
            return AutoSendVerdict(False, "needs_l2")
        if decision.kb_citations < 1:
            return AutoSendVerdict(False, "no_kb_citation")
        if decision.confidence is None or decision.confidence < cfg.confidence_threshold:
            return AutoSendVerdict(False, "confidence_below_threshold")
        limit = "D3" if kind in cfg.d3_enabled_types else L2_MAX_DEPTH
        if not _within(decision.depth, limit, none_means=None):
            return AutoSendVerdict(False, "depth_too_deep")
        return AutoSendVerdict(True, "ok")

    return AutoSendVerdict(False, "no_auto_ability")


def may_auto_send(
    decision: AutoSendDecision,
    level: Level,
    *,
    settings: AutonomySettings | None = None,
    profile: PolicyProfile | PolicyProfileKey | str | None = None,
) -> bool:
    """True only when the care agent may send ``decision`` without a person (see the module docstring)."""
    return evaluate_auto_send(decision, level, settings=settings, profile=profile).allowed


# ============================================================================================ audit log
async def log_autonomy_change(
    session: AsyncSession,
    care_agent: CareAgent,
    *,
    scope: str,
    from_value: str | None,
    to_value: str | None,
    initiator: Initiator,
    reason: str,
    actor_user_id: UUID | None = None,
    extra: Mapping[str, Any] | None = None,
) -> None:
    """One ``actions_log`` row of kind ``autonomy_change`` (see the module docstring for the columns used).

    ``scope`` is an action type, ``all``, ``override`` or ``paused``; ``reason`` is a short code. Never put
    free text or patient data in ``extra``.
    """
    detail: dict[str, Any] = {
        "kind": AUTONOMY_CHANGE,
        "initiator": initiator.value,
        "scope": scope,
        "from": from_value,
        "to": to_value,
        "reason": reason,
    }
    if actor_user_id is not None:
        detail["actor_user_id"] = str(actor_user_id)
    if extra:
        detail.update(extra)
    session.add(
        ActionLog(
            clinic_id=care_agent.clinic_id,
            care_agent_id=care_agent.id,
            action_type=AUTONOMY_CHANGE,
            disposition=ActionDisposition.REVIEWED.value,
            reviewer_edit_diff=detail,
        )
    )
    await session.flush()
    logger.info(
        "autonomy change",
        extra={
            "care_agent_id": str(care_agent.id),
            "scope": scope,
            "from": from_value,
            "to": to_value,
            "initiator": initiator.value,
            "reason": reason,
        },
    )


async def lock_care_agent(session: AsyncSession, care_agent_id: UUID) -> CareAgent:
    """Re-read the row with ``FOR UPDATE`` so two writers (trust update, override, pause) serialise."""
    row = await session.scalar(
        select(CareAgent)
        .where(CareAgent.id == care_agent_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise LookupError("care agent not found")
    return row


# ======================================================================================== level writes
def _agent_levels(care_agent: CareAgent) -> dict[str, Any]:
    return dict(care_agent.autonomy_levels or {})


async def demote(
    session: AsyncSession,
    care_agent_id: UUID,
    action_type: str,
    level: Level,
    *,
    initiator: Initiator,
    reason: str,
    actor_user_id: UUID | None = None,
    settings: AutonomySettings | None = None,
) -> Level:
    """Lower the explicit level of one action type (doctor or manager, any time). Raising is refused: levels
    go up only through the trust score. Returns the level now stored. Same level: no write, no log."""
    if action_type not in ACTION_TYPES:
        raise ValueError(f"unknown action type: {action_type}")
    cfg = settings if settings is not None else load_settings()
    agent = await lock_care_agent(session, care_agent_id)
    current = base_level(agent, action_type, cfg)
    if level.rank > current.rank:
        raise ValueError("a level can only be lowered here; promotion goes through the trust score")
    if level is current and _level_or_none(_agent_levels(agent).get(action_type)) is level:
        return level
    levels = _agent_levels(agent)
    levels[action_type] = level.value
    agent.autonomy_levels = levels
    scores = trust_scores_of(agent)
    scores.pop(action_type, None)
    set_trust_scores(agent, scores)
    await session.flush()
    await log_autonomy_change(
        session,
        agent,
        scope=action_type,
        from_value=current.value,
        to_value=level.value,
        initiator=initiator,
        reason=reason,
        actor_user_id=actor_user_id,
    )
    return level


async def demote_all_to_l0(
    session: AsyncSession,
    care_agent_id: UUID,
    *,
    initiator: Initiator,
    reason: str,
    actor_user_id: UUID | None = None,
    extra: Mapping[str, Any] | None = None,
    settings: AutonomySettings | None = None,
) -> list[str]:
    """Whole care agent to L0 (explicit entries for every type, so the clinic floor does not lift it) and
    the trust scores back to zero. Returns the types whose level dropped. One log row."""
    agent = await lock_care_agent(session, care_agent_id)
    cfg = settings if settings is not None else load_settings()
    dropped = [t for t in ACTION_TYPES if base_level(agent, t, cfg) is not Level.L0]
    agent.autonomy_levels = dict.fromkeys(ACTION_TYPES, Level.L0.value)
    agent.trust_scores = {"scores": {}, "processed_reviews": processed_reviews_of(agent)}
    await session.flush()
    await log_autonomy_change(
        session,
        agent,
        scope="all",
        from_value=",".join(dropped) if dropped else "L0",
        to_value=Level.L0.value,
        initiator=initiator,
        reason=reason,
        actor_user_id=actor_user_id,
        extra=extra,
    )
    return dropped


async def promote_to_l2(
    session: AsyncSession,
    agent: CareAgent,
    action_type: str,
    *,
    initiator: Initiator = Initiator.SYSTEM,
    reason: str = "trust_threshold",
) -> None:
    """Only ``pema.care.trust`` calls this: the one way a level goes up. ``agent`` is locked by the caller."""
    cfg = load_settings()
    current = base_level(agent, action_type, cfg)
    levels = _agent_levels(agent)
    levels[action_type] = Level.L2.value
    agent.autonomy_levels = levels
    await session.flush()
    await log_autonomy_change(
        session,
        agent,
        scope=action_type,
        from_value=current.value,
        to_value=Level.L2.value,
        initiator=initiator,
        reason=reason,
    )


# ---------------------------------------------------------------------------------------- trust helpers
def trust_scores_of(care_agent: CareAgent) -> dict[str, int]:
    raw = cast("object", (care_agent.trust_scores or {}).get("scores", {}))
    if not isinstance(raw, dict):
        return {}
    items = cast("dict[object, object]", raw)
    return {str(k): v for k, v in items.items() if isinstance(v, int)}


def processed_reviews_of(care_agent: CareAgent) -> list[str]:
    raw = cast("object", (care_agent.trust_scores or {}).get("processed_reviews", []))
    if not isinstance(raw, list):
        return []
    return [str(x) for x in cast("list[object]", raw)]


def set_trust_scores(care_agent: CareAgent, scores: dict[str, int]) -> None:
    care_agent.trust_scores = {"scores": scores, "processed_reviews": processed_reviews_of(care_agent)}


# ============================================================================== override, pause, resume
async def set_override(
    session: AsyncSession,
    care_agent_id: UUID,
    level: Level,
    until: datetime,
    note: str | None = None,
    *,
    initiator: Initiator = Initiator.STAFF,
    actor_user_id: UUID | None = None,
    now: datetime,
) -> None:
    """Staff API (also used by M2b ``release_to_auto``): lower the agent to ``level`` until ``until``. After
    that the agent is back at its own level. The override never raises a level above the agent's own."""
    if until.tzinfo is None:
        raise ValueError("until must be timezone-aware")
    if until <= now:
        raise ValueError("until must be in the future")
    agent = await lock_care_agent(session, care_agent_id)
    previous = agent.autonomy_override
    override: dict[str, Any] = {"level": level.value, "until": until.isoformat()}
    if note:
        override["note"] = note
    if actor_user_id is not None:
        override["set_by"] = str(actor_user_id)
    agent.autonomy_override = override
    await session.flush()
    await log_autonomy_change(
        session,
        agent,
        scope="override",
        from_value=(str(previous.get("level")) if previous else None),
        to_value=level.value,
        initiator=initiator,
        reason="override_set",
        actor_user_id=actor_user_id,
        extra={"until": until.isoformat(), "has_note": bool(note)},
    )


async def clear_override(
    session: AsyncSession,
    care_agent_id: UUID,
    *,
    initiator: Initiator,
    reason: str = "override_cleared",
    actor_user_id: UUID | None = None,
) -> bool:
    """Remove the override (staff, or the system when it expired). False when there was none."""
    agent = await lock_care_agent(session, care_agent_id)
    previous = agent.autonomy_override
    if not previous:
        return False
    # SQL NULL, not JSON null: the column has no ``none_as_null`` and its CHECK refuses a JSON null
    agent.autonomy_override = cast("Any", null())
    await session.flush()
    await log_autonomy_change(
        session,
        agent,
        scope="override",
        from_value=str(previous.get("level")),
        to_value=None,
        initiator=initiator,
        reason=reason,
        actor_user_id=actor_user_id,
    )
    return True


async def resolve_level(
    session: AsyncSession,
    care_agent: CareAgent,
    action_type: str,
    now: datetime,
    *,
    settings: AutonomySettings | None = None,
    kill_switch: KillSwitchState | None = None,
) -> Level:
    """``effective_level`` that also CLEARS an expired override (and logs it) before answering."""
    if override_expired(care_agent, now):
        await clear_override(session, care_agent.id, initiator=Initiator.SYSTEM, reason="override_expired")
        await session.refresh(care_agent)
    return effective_level(care_agent, action_type, now, settings=settings, kill_switch=kill_switch)


async def _set_paused(
    session: AsyncSession,
    patient_id: UUID,
    paused: bool,
    initiator: Initiator,
    actor_user_id: UUID | None,
) -> bool:
    found = await session.scalar(select(CareAgent.id).where(CareAgent.patient_id == patient_id))
    if found is None:
        raise LookupError("care agent not found")
    agent = await lock_care_agent(session, found)
    if agent.paused is paused:
        return False
    agent.paused = paused
    await session.flush()
    await log_autonomy_change(
        session,
        agent,
        scope="paused",
        from_value=str(not paused).lower(),
        to_value=str(paused).lower(),
        initiator=initiator,
        reason="pause" if paused else "resume",
        actor_user_id=actor_user_id,
    )
    return True


async def pause(
    session: AsyncSession,
    patient_id: UUID,
    *,
    initiator: Initiator = Initiator.STAFF,
    actor_user_id: UUID | None = None,
) -> bool:
    """Per-patient kill switch: the care agent of ``patient_id`` is L0 for every type until ``resume``."""
    return await _set_paused(session, patient_id, True, initiator, actor_user_id)


async def resume(
    session: AsyncSession,
    patient_id: UUID,
    *,
    initiator: Initiator = Initiator.STAFF,
    actor_user_id: UUID | None = None,
) -> bool:
    return await _set_paused(session, patient_id, False, initiator, actor_user_id)

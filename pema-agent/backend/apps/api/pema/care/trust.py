"""Trust scores of a care agent from review outcomes (package M, step M3).

New module (not a port of zalo-agent). Source: ``docs/PLAN-AI01-M.md`` section 4 and
``recipes/M/05-M3-autonomy.md`` step 5.

Events come from B1's review queue (``pema_contracts.review``): a reviewer approves a draft as it is, approves
it after editing (``final_text``), or rejects it. B1 stores ``draft_text`` and ``final_text`` on the item,
which is enough to compare, so no diff is needed from B1 (``ReviewOutcome.from_review_item`` builds the
outcome from a ``ReviewItemOut``). B1's approve action has no extension point yet: its caller invokes
``ReviewDecidedHook.on_review_decided`` (implemented by ``TrustReviewHook``) in the SAME session after the
decision is stored, exactly like ``pema.care.ports.PatientCreatedHook`` for the pairing.

Rules
-----
* approved UNCHANGED -> +1 for ``(care_agent, action_type)``; reaching ``settings.n_to_l2[type]`` promotes
  that type to L2 (the only way a level goes up) and logs it;
* approved after a MINOR edit -> no change;
* approved after a SERIOUS edit (``SeriousEditRule``: changed clinical meaning, removed a warning, added a
  drug) -> the WHOLE care agent to L0, trust scores back to zero, logged, and the manager is alerted;
* rejected, escalated, expired -> no change (open item: should a rejection demote? the doctor decides);
* a hard-human type (``medical_judgement``, ``birthday_greeting``) never earns score, but a serious edit of
  its draft still demotes the agent;
* the same review item is counted once (the last 50 ids are kept in ``trust_scores.processed_reviews``).

``trust_scores`` layout: ``{"scores": {action_type: int}, "processed_reviews": [review_item_id, ...]}``.

``classify_edit`` is a deterministic text comparison with TEMPORARY lists (``SeriousEditRule``, awaiting the
doctor). It errs on the side of "serious": a false alarm costs a demotion, a miss costs a wrong message sent
without review.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.autonomy import (
    ACTION_TYPES,
    HARD_HUMAN_TYPES,
    AutonomySettings,
    Initiator,
    Level,
    SeriousEditRule,
    base_level,
    demote_all_to_l0,
    load_settings,
    lock_care_agent,
    processed_reviews_of,
    promote_to_l2,
    trust_scores_of,
)
from pema.care.models import CareAgent
from pema_contracts.review import ReviewItemOut, ReviewStatus

logger = logging.getLogger(__name__)

PROCESSED_REVIEWS_KEPT = 50
MEDICINE_UNITS: frozenset[str] = frozenset({"mg", "mcg", "ml", "g", "viên", "ống", "gói"})


class EditKind(StrEnum):
    UNCHANGED = "unchanged"
    MINOR = "minor"
    SERIOUS = "serious"


@dataclass(frozen=True)
class EditClassification:
    kind: EditKind
    reasons: tuple[str, ...] = ()
    """Codes only: ``changed_clinical_meaning``, ``removed_warning``, ``added_drug``."""


def _normalise(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).casefold().split()).replace(",", ".")


def _quantity_pattern(units: tuple[str, ...]) -> re.Pattern[str]:
    alternation = "|".join(re.escape(u) for u in sorted(units, key=len, reverse=True))
    return re.compile(rf"(\d+(?:\.\d+)?)\s*({alternation})(?!\w)")


def _quantities(text: str, units: tuple[str, ...]) -> Counter[tuple[str, str]]:
    return Counter((m.group(1), m.group(2)) for m in _quantity_pattern(units).finditer(text))


def _negations(text: str, phrases: tuple[str, ...]) -> Counter[str]:
    return Counter({p: text.count(p) for p in phrases if p in text})


def classify_edit(draft: str | None, final: str | None, rule: SeriousEditRule) -> EditClassification:
    """Compare the draft with the text a reviewer approved. ``final=None`` means "sent as drafted"."""
    if final is None or draft is None:
        # nothing to compare: no final text is "approved as it is"; no draft means no baseline
        return EditClassification(EditKind.UNCHANGED if final is None else EditKind.MINOR)
    before, after = _normalise(draft), _normalise(final)
    if before == after:
        return EditClassification(EditKind.UNCHANGED)

    reasons: list[str] = []
    if rule.removed_warning and any(m in before and m not in after for m in rule.warning_markers):
        reasons.append("removed_warning")
    if rule.added_drug:
        new_term = any(t in after and t not in before for t in rule.drug_terms)
        medicine_units = tuple(u for u in rule.quantity_units if u in MEDICINE_UNITS)
        new_dose = bool(_quantities(after, medicine_units)) and not _quantities(before, medicine_units)
        if new_term or new_dose:
            reasons.append("added_drug")
    if rule.changed_clinical_meaning and (
        _quantities(before, rule.quantity_units) != _quantities(after, rule.quantity_units)
        or _negations(before, rule.negation_phrases) != _negations(after, rule.negation_phrases)
    ):
        reasons.append("changed_clinical_meaning")
    if reasons:
        return EditClassification(EditKind.SERIOUS, tuple(reasons))
    return EditClassification(EditKind.MINOR)


# ============================================================================================== outcome
@dataclass(frozen=True)
class ReviewOutcome:
    """A reviewer's decision about one draft of a care agent (a ``ReviewItemOut`` boiled down)."""

    review_item_id: UUID
    care_agent_id: UUID
    action_type: str
    decision: ReviewStatus
    draft_text: str | None = None
    final_text: str | None = None
    """The edited text; ``None`` = approved as drafted."""

    @classmethod
    def from_review_item(cls, item: ReviewItemOut, *, care_agent_id: UUID, action_type: str) -> ReviewOutcome:
        return cls(
            review_item_id=item.id,
            care_agent_id=care_agent_id,
            action_type=action_type,
            decision=item.status,
            draft_text=item.draft_text,
            final_text=item.final_text,
        )


@dataclass(frozen=True)
class TrustUpdate:
    edit: EditKind | None = None
    score: int | None = None
    promoted: bool = False
    demoted: bool = False
    duplicate: bool = False
    ignored: str | None = None


@runtime_checkable
class ManagerAlerter(Protocol):
    """Tells the manager that an agent was demoted (the notification channel belongs to another package)."""

    async def alert_manager(self, *, code: str, care_agent_id: UUID, detail: Mapping[str, str]) -> None: ...


class LoggingManagerAlerter:
    """Default alerter: a warning in the log (ids and codes only, never text)."""

    async def alert_manager(self, *, code: str, care_agent_id: UUID, detail: Mapping[str, str]) -> None:
        logger.warning("manager alert", extra={"code": code, "care_agent_id": str(care_agent_id), **detail})


@runtime_checkable
class ReviewDecidedHook(Protocol):
    """Called once per decided review item of a care agent, in the unit of work that stored the decision."""

    async def on_review_decided(self, session: AsyncSession, outcome: ReviewOutcome) -> None: ...


def _remember(agent: CareAgent, review_item_id: UUID, scores: dict[str, int]) -> None:
    processed = [*processed_reviews_of(agent), str(review_item_id)][-PROCESSED_REVIEWS_KEPT:]
    agent.trust_scores = {"scores": scores, "processed_reviews": processed}


async def record_review_outcome(
    session: AsyncSession,
    outcome: ReviewOutcome,
    *,
    settings: AutonomySettings | None = None,
    alerter: ManagerAlerter | None = None,
) -> TrustUpdate:
    """Apply the rules of the module docstring. Idempotent per ``review_item_id``."""
    if outcome.decision is not ReviewStatus.APPROVED:
        return TrustUpdate(ignored="not_approved")
    cfg = settings if settings is not None else load_settings()
    agent = await lock_care_agent(session, outcome.care_agent_id)
    if str(outcome.review_item_id) in processed_reviews_of(agent):
        return TrustUpdate(duplicate=True)

    edit = classify_edit(outcome.draft_text, outcome.final_text, cfg.serious_edit_rule)
    scores = trust_scores_of(agent)

    if edit.kind is EditKind.SERIOUS:
        _remember(agent, outcome.review_item_id, scores)
        await session.flush()
        await demote_all_to_l0(
            session,
            agent.id,
            initiator=Initiator.SYSTEM,
            reason="serious_edit",
            settings=cfg,
            extra={"action_type": outcome.action_type, "edit_reasons": list(edit.reasons)},
        )
        await (alerter or LoggingManagerAlerter()).alert_manager(
            code="serious_edit",
            care_agent_id=agent.id,
            detail={"action_type": outcome.action_type, "reasons": ",".join(edit.reasons)},
        )
        return TrustUpdate(edit=edit.kind, demoted=True)

    if (
        edit.kind is EditKind.MINOR
        or outcome.action_type not in ACTION_TYPES
        or (outcome.action_type in HARD_HUMAN_TYPES)
    ):
        _remember(agent, outcome.review_item_id, scores)
        await session.flush()
        return TrustUpdate(edit=edit.kind, score=scores.get(outcome.action_type))

    score = scores.get(outcome.action_type, 0) + 1
    scores[outcome.action_type] = score
    _remember(agent, outcome.review_item_id, scores)
    await session.flush()
    promoted = False
    needed = cfg.n_to_l2.get(outcome.action_type)
    if needed is not None and score >= needed and base_level(agent, outcome.action_type, cfg) is not Level.L2:
        await promote_to_l2(session, agent, outcome.action_type)
        promoted = True
    return TrustUpdate(edit=edit.kind, score=score, promoted=promoted)


class TrustReviewHook:
    """``ReviewDecidedHook`` that feeds the decision into the trust score."""

    def __init__(self, *, alerter: ManagerAlerter | None = None) -> None:
        self._alerter = alerter

    async def on_review_decided(self, session: AsyncSession, outcome: ReviewOutcome) -> None:
        await record_review_outcome(session, outcome, alerter=self._alerter)

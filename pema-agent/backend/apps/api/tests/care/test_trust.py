"""Trust scores from review outcomes (package M, step M3). New tests (no zalo-agent original).

``classify_edit`` tests are pure; the outcome tests need ``PEMA_TEST_DATABASE_URL`` (skipped otherwise).
All texts are synthetic.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from pema.care.autonomy import (
    ACTION_TYPES,
    ActionType,
    AutonomySettings,
    Level,
    SeriousEditRule,
    effective_level,
    levels_snapshot,
)
from pema.care.models import ActionLog, CareAgent
from pema.care.pairing import ensure_care_agent
from pema.care.trust import (
    EditKind,
    LoggingManagerAlerter,
    ManagerAlerter,
    ReviewDecidedHook,
    ReviewOutcome,
    TrustReviewHook,
    classify_edit,
    record_review_outcome,
)
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.runtime_settings_kv import (
    InMemoryRuntimeSettingsKv,
    install_runtime_settings_kv,
    reset_runtime_settings_kv,
)
from pema.core.db import ClinicDatabase
from pema_contracts.common import VN_TZ
from pema_contracts.review import ReviewItemOut, ReviewKind, ReviewOrigin, ReviewStatus, RiskLevel

NOW = datetime(2026, 10, 3, 9, 0, tzinfo=VN_TZ)
RULE = SeriousEditRule()
FAQ = ActionType.FAQ_KB_ANSWER.value

DRAFT = (
    "Dạ sau khi nhổ răng mình cắn gạc 30 phút, uống paracetamol 500mg khi đau, "
    "tối đa 3 lần mỗi ngày. Lưu ý: nếu chảy máu nhiều hãy gọi phòng khám ngay ạ."
)


@pytest.fixture(autouse=True)
def kv() -> Iterator[InMemoryRuntimeSettingsKv]:
    store = InMemoryRuntimeSettingsKv()
    install_runtime_settings_kv(store)
    yield store
    reset_runtime_settings_kv()


# ============================================================================================ edits
def test_identical_or_missing_final_text_is_unchanged() -> None:
    assert classify_edit(DRAFT, None, RULE).kind is EditKind.UNCHANGED
    assert classify_edit(DRAFT, DRAFT, RULE).kind is EditKind.UNCHANGED
    assert classify_edit(DRAFT, "  " + DRAFT.replace(" ", "  ") + "\n", RULE).kind is EditKind.UNCHANGED


def test_a_change_of_tone_is_a_minor_edit() -> None:
    final = DRAFT.replace("Dạ ", "Chào bạn, ").replace("ạ.", "nhé.")
    result = classify_edit(DRAFT, final, RULE)
    assert (result.kind, result.reasons) == (EditKind.MINOR, ())


def test_a_changed_case_only_is_not_an_edit() -> None:
    assert classify_edit("Hẹn gặp mình lúc 9 giờ", "hẹn gặp mình lúc 9 giờ", RULE).kind is EditKind.UNCHANGED


def test_removing_a_warning_is_serious() -> None:
    final = (
        "Dạ sau khi nhổ răng mình cắn gạc 30 phút, uống paracetamol 500mg khi đau, tối đa 3 lần mỗi ngày ạ."
    )
    result = classify_edit(DRAFT, final, RULE)
    assert result.kind is EditKind.SERIOUS
    assert "removed_warning" in result.reasons


def test_adding_a_drug_is_serious() -> None:
    draft = "Dạ mình nhớ giữ vệ sinh răng miệng ạ."
    final = "Dạ mình nhớ giữ vệ sinh răng miệng và uống amoxicillin ạ."
    result = classify_edit(draft, final, RULE)
    assert (result.kind, result.reasons) == (EditKind.SERIOUS, ("added_drug",))


def test_adding_a_dose_where_the_draft_had_none_is_a_new_drug() -> None:
    result = classify_edit("Dạ mình nhớ nghỉ ngơi ạ.", "Dạ mình nhớ nghỉ ngơi, uống 2 viên khi đau ạ.", RULE)
    assert result.kind is EditKind.SERIOUS
    assert "added_drug" in result.reasons


def test_changing_a_dose_or_a_duration_changes_the_clinical_meaning() -> None:
    result = classify_edit(DRAFT, DRAFT.replace("500mg", "1000mg"), RULE)
    assert (result.kind, result.reasons) == (EditKind.SERIOUS, ("changed_clinical_meaning",))
    assert classify_edit(DRAFT, DRAFT.replace("30 phút", "10 phút"), RULE).kind is EditKind.SERIOUS
    assert classify_edit("Uống 0,5 viên", "Uống 0.5 viên", RULE).kind is EditKind.UNCHANGED


def test_a_prohibition_that_appears_or_disappears_changes_the_clinical_meaning() -> None:
    assert classify_edit("Mình nên ăn đồ nóng.", "Mình tránh ăn đồ nóng.", RULE).kind is EditKind.SERIOUS
    assert classify_edit("Mình đừng súc miệng mạnh.", "Mình súc miệng mạnh.", RULE).kind is EditKind.SERIOUS


def test_the_units_are_matched_whole_words() -> None:
    # "3 giờ" must not read as "3 g" (grams): only the hour count changes the meaning here
    result = classify_edit("Hẹn mình lúc 3 giờ chiều ạ.", "Hẹn mình lúc 3 giờ chiều nhé.", RULE)
    assert result.kind is EditKind.MINOR


def test_each_check_can_be_switched_off() -> None:
    lenient = SeriousEditRule(changed_clinical_meaning=False, removed_warning=False, added_drug=False)
    assert classify_edit(DRAFT, "Dạ mình nghỉ ngơi ạ.", lenient).kind is EditKind.MINOR


def test_a_final_text_without_a_draft_is_minor() -> None:
    assert classify_edit(None, "Dạ ạ", RULE).kind is EditKind.MINOR


# ======================================================================================= protocols
def test_the_hook_and_the_alerter_implement_their_protocols() -> None:
    assert isinstance(TrustReviewHook(), ReviewDecidedHook)
    assert isinstance(LoggingManagerAlerter(), ManagerAlerter)


def test_an_outcome_is_built_from_a_review_item() -> None:
    item = ReviewItemOut(
        id=uuid4(), kind=ReviewKind.REPLY_DRAFT, origin=ReviewOrigin.AGENT_TURN, status=ReviewStatus.APPROVED,
        conversation_id=None, patient_id=None, patient_code=None, draft_text="a", final_text="b",
        risk_level=RiskLevel.NORMAL, requires_doctor=False, created_at=NOW, version=2,
    )  # fmt: skip
    outcome = ReviewOutcome.from_review_item(item, care_agent_id=uuid4(), action_type=FAQ)
    assert (outcome.review_item_id, outcome.decision) == (item.id, ReviewStatus.APPROVED)
    assert (outcome.draft_text, outcome.final_text, outcome.action_type) == ("a", "b", FAQ)


# ============================================================================================== db
class _Alerts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, UUID, dict[str, str]]] = []

    async def alert_manager(self, *, code: str, care_agent_id: UUID, detail: Mapping[str, str]) -> None:
        self.calls.append((code, care_agent_id, dict(detail)))


async def _agent_id(db: ClinicDatabase, world: SeedResult, code: str = "P025") -> UUID:
    async with db.session() as session:
        return (await ensure_care_agent(session, world.patients[code])).id


def _outcome(
    care_agent_id: UUID,
    *,
    action_type: str = FAQ,
    final_text: str | None = None,
    decision: ReviewStatus = ReviewStatus.APPROVED,
    draft: str = DRAFT,
    review_item_id: UUID | None = None,
) -> ReviewOutcome:
    return ReviewOutcome(
        review_item_id=review_item_id or uuid4(),
        care_agent_id=care_agent_id,
        action_type=action_type,
        decision=decision,
        draft_text=draft,
        final_text=final_text,
    )


async def _agent(db: ClinicDatabase, care_agent_id: UUID) -> CareAgent:
    async with db.session() as session:
        row = await session.scalar(select(CareAgent).where(CareAgent.id == care_agent_id))
        assert row is not None
        session.expunge(row)
        return row


async def _log(db: ClinicDatabase, care_agent_id: UUID) -> list[dict[str, Any]]:
    async with db.session() as session:
        rows = await session.scalars(
            select(ActionLog)
            .where(ActionLog.care_agent_id == care_agent_id, ActionLog.action_type == "autonomy_change")
            .order_by(ActionLog.id)
        )
        return [r.reviewer_edit_diff or {} for r in rows]


@pytest.mark.db
async def test_ten_approved_unchanged_promote_faq_kb_answer_to_l2(
    db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = AutonomySettings(n_to_l2={FAQ: 10})
    for done in range(1, 10):
        async with db.session() as session:
            update = await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
        assert (update.score, update.promoted) == (done, False)
        assert effective_level(await _agent(db, care_agent_id), FAQ, NOW, settings=settings) is Level.L0
    async with db.session() as session:
        update = await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
    assert (update.edit, update.score, update.promoted) == (EditKind.UNCHANGED, 10, True)
    agent = await _agent(db, care_agent_id)
    assert effective_level(agent, FAQ, NOW, settings=settings) is Level.L2
    assert effective_level(agent, ActionType.SYMPTOM_REPLY.value, NOW, settings=settings) is Level.L0
    (row,) = await _log(db, care_agent_id)
    assert (row["initiator"], row["scope"], row["from"], row["to"]) == ("system", FAQ, "L0", "L2")


@pytest.mark.db
async def test_a_minor_edit_changes_nothing(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = AutonomySettings(n_to_l2={FAQ: 2})
    minor = DRAFT.replace("Dạ ", "Chào bạn, ")
    async with db.session() as session:
        await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
        update = await record_review_outcome(
            session, _outcome(care_agent_id, final_text=minor), settings=settings
        )
    assert (update.edit, update.score, update.promoted, update.demoted) == (EditKind.MINOR, 1, False, False)
    agent = await _agent(db, care_agent_id)
    assert agent.trust_scores["scores"] == {FAQ: 1}
    assert await _log(db, care_agent_id) == []


@pytest.mark.db
async def test_one_serious_edit_sends_the_whole_agent_to_l0_and_alerts_the_manager(
    db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = AutonomySettings(n_to_l2={FAQ: 2}, templates_l1=("tpl-1",), appointment_confirm_l1=True)
    alerts = _Alerts()
    async with db.session() as session:
        await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
        await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
    agent = await _agent(db, care_agent_id)
    levels = levels_snapshot(agent, NOW, settings=settings)
    assert levels[FAQ] is Level.L2
    assert levels[ActionType.REMINDER_TEMPLATE.value] is Level.L1
    assert levels[ActionType.APPOINTMENT_CONFIRM.value] is Level.L1

    serious = DRAFT.replace("500mg", "2000mg")
    async with db.session() as session:
        update = await record_review_outcome(
            session, _outcome(care_agent_id, final_text=serious), settings=settings, alerter=alerts
        )
    assert (update.edit, update.demoted) == (EditKind.SERIOUS, True)
    agent = await _agent(db, care_agent_id)
    assert set(levels_snapshot(agent, NOW, settings=settings).values()) == {Level.L0}
    assert set(ACTION_TYPES) <= set(agent.autonomy_levels)
    assert agent.trust_scores["scores"] == {}
    assert [(c[0], c[1]) for c in alerts.calls] == [("serious_edit", care_agent_id)]
    assert alerts.calls[0][2]["action_type"] == FAQ
    last = (await _log(db, care_agent_id))[-1]
    assert (last["initiator"], last["scope"], last["to"], last["reason"]) == (
        "system",
        "all",
        "L0",
        "serious_edit",
    )
    assert last["edit_reasons"] == ["changed_clinical_meaning"]
    assert DRAFT not in str(last)  # no patient or draft text in the log
    assert serious not in str(last)


@pytest.mark.db
async def test_after_a_demotion_the_scores_start_again_from_zero(
    db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = AutonomySettings(n_to_l2={FAQ: 2})
    serious = DRAFT.replace("500mg", "2000mg")
    async with db.session() as session:
        await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
        await record_review_outcome(session, _outcome(care_agent_id, final_text=serious), settings=settings)
        first = await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
    assert (first.score, first.promoted) == (1, False)


@pytest.mark.db
async def test_the_same_review_item_is_counted_once(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = AutonomySettings(n_to_l2={FAQ: 5})
    outcome = _outcome(care_agent_id)
    async with db.session() as session:
        first = await record_review_outcome(session, outcome, settings=settings)
        again = await record_review_outcome(session, outcome, settings=settings)
    assert (first.score, again.duplicate) == (1, True)
    agent = await _agent(db, care_agent_id)
    assert agent.trust_scores["scores"] == {FAQ: 1}
    assert agent.trust_scores["processed_reviews"] == [str(outcome.review_item_id)]


@pytest.mark.db
async def test_rejected_and_escalated_drafts_change_nothing(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    async with db.session() as session:
        for decision in (
            ReviewStatus.REJECTED,
            ReviewStatus.ESCALATED,
            ReviewStatus.EXPIRED,
            ReviewStatus.PENDING,
        ):
            update = await record_review_outcome(session, _outcome(care_agent_id, decision=decision))
            assert update.ignored == "not_approved"
    agent = await _agent(db, care_agent_id)
    assert agent.trust_scores == {}


@pytest.mark.db
async def test_medical_judgement_never_earns_score_but_a_serious_edit_of_it_demotes(
    db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = AutonomySettings(n_to_l2={FAQ: 1})
    kind = ActionType.MEDICAL_JUDGEMENT.value
    async with db.session() as session:
        update = await record_review_outcome(
            session, _outcome(care_agent_id, action_type=kind), settings=settings
        )
        assert (update.score, update.promoted) == (None, False)
        await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
    assert effective_level(await _agent(db, care_agent_id), FAQ, NOW, settings=settings) is Level.L2
    async with db.session() as session:
        demoted = await record_review_outcome(
            session,
            _outcome(care_agent_id, action_type=kind, final_text="Dạ mình nghỉ ngơi ạ."),
            settings=settings,
        )
    assert demoted.demoted is True
    assert effective_level(await _agent(db, care_agent_id), FAQ, NOW, settings=settings) is Level.L0


@pytest.mark.db
async def test_the_hook_feeds_the_trust_score_with_the_stored_settings(
    db: ClinicDatabase, world: SeedResult
) -> None:
    care_agent_id = await _agent_id(db, world)
    hook = TrustReviewHook()
    async with db.session() as session:
        await hook.on_review_decided(session, _outcome(care_agent_id))
    agent = await _agent(db, care_agent_id)
    assert agent.trust_scores["scores"] == {FAQ: 1}


@pytest.mark.db
async def test_the_list_of_processed_reviews_is_bounded(db: ClinicDatabase, world: SeedResult) -> None:
    care_agent_id = await _agent_id(db, world)
    settings = AutonomySettings(n_to_l2={})
    async with db.session() as session:
        for _ in range(55):
            await record_review_outcome(session, _outcome(care_agent_id), settings=settings)
    agent = await _agent(db, care_agent_id)
    assert len(agent.trust_scores["processed_reviews"]) == 50
    assert agent.trust_scores["scores"] == {FAQ: 55}

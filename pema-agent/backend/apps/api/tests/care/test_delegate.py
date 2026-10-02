"""``delegate``, budgets, depth 1 and the three specialists end to end with a fake model (package M, step M4).

New tests (no zalo-agent original). The "LLM" is ``ScriptedModel``; nothing sleeps except the one deadline test,
which waits a few tens of milliseconds.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from pema.agent.streaming_model_test_helper import ScriptedModel, goi_tool, tool_keys, tra_loi
from pema.agent.tools.testing import make_tool_context, make_tool_deps
from pema.agent.tools.tool_registry import DefaultToolRegistry, scope_of_context
from pema.care.autonomy import KillSwitchState
from pema.care.models import TaskStatus
from pema.care.ports import DepthError, FreeSlot, SpecialistRunner
from pema.care.specialists.delegate import (
    BLOCKED_KILL_SWITCH,
    BUDGET_EXHAUSTED,
    DelegationService,
    UnknownSpecialistError,
    build_delegate_spec,
)
from pema.care.specialists.scope import CARE_TURN_EXTRA
from pema.care.specialists.spec import (
    DELEGATE_TOOL,
    KNOWLEDGE_ID,
    REVIEWER_ID,
    SCHEDULER_ID,
    SpecialistCall,
    SpecialistRun,
)
from pema.care.task_result import TaskResult
from pema.care.testing import make_rig
from pema_contracts.knowledge import KbHit
from pema_contracts.policy import PolicyProfileKey

SLOT_A = FreeSlot(starts_at=datetime(2026, 10, 7, 9, 0, tzinfo=UTC), duration_min=30)
SLOT_B = FreeSlot(starts_at=datetime(2026, 10, 7, 10, 0, tzinfo=UTC), duration_min=30)
HIT = KbHit(
    source_id="kb-aftercare-1",
    source_name="Hướng dẫn sau điều trị",
    title="Chăm sóc da",
    content="Tránh nắng 48 giờ.",
    score=0.9,
)

_ids = iter(range(1, 10_000))


def call(tool: str, **args: Any) -> Any:
    """One scripted model step that calls ``tool`` (a fresh call id each time)."""
    call_id = f"call-{next(_ids)}"
    return lambda: goi_tool(tool, args, call_id=call_id)


def submit(**result: Any) -> Any:
    return call("submit_result", **result)


def model(*steps: Any) -> ScriptedModel:
    return ScriptedModel(list(steps))


def tool_error_texts(m: ScriptedModel) -> str:
    return str(m.calls[-1].messages)


# ================================================================================================ depth 1
async def test_a_specialist_calling_delegate_never_reaches_a_delegation() -> None:
    scripted = model(call(DELEGATE_TOOL, agent_name=KNOWLEDGE_ID, task="loop"), submit(summary="done"))
    rig = make_rig(models={SCHEDULER_ID: scripted}, slots=[SLOT_A])
    result = await rig.service.delegate(rig.scope, SCHEDULER_ID, "tim slot", None)
    assert DELEGATE_TOOL not in tool_keys(scripted.calls[0])  # not offered to the model
    assert "tool" in tool_error_texts(scripted).lower()  # the call came back as an error
    assert len(rig.tasks.children()) == 1  # nothing was delegated from the specialist
    assert result.needs_human is True  # it never produced a slot


def test_the_delegate_tool_exists_for_the_care_agent_and_not_for_a_specialist() -> None:
    rig = make_rig()
    registry = DefaultToolRegistry(make_tool_deps(), definitions=[build_delegate_spec(rig.service)])
    care_ctx = make_tool_context(profile=PolicyProfileKey.PATIENT_CHANNEL, agent_patch={"id": "care-agent"})
    assert [s.key for s in registry.list_available(scope_of_context(care_ctx))] == [DELEGATE_TOOL]
    for specialist_id in (SCHEDULER_ID, KNOWLEDGE_ID, REVIEWER_ID):
        ctx = make_tool_context(profile=PolicyProfileKey.PATIENT_CHANNEL, agent_patch={"id": specialist_id})
        assert registry.list_available(scope_of_context(ctx)) == []


async def test_delegate_is_refused_outside_a_care_turn() -> None:
    rig = make_rig()
    spec = build_delegate_spec(rig.service)
    tool = spec.build(make_tool_context())  # no CareTurnScope in extras
    out = await tool.execute({"agent_name": SCHEDULER_ID, "task": "x"})
    assert out == {"ok": False, "loi": out["loi"]}  # type: ignore[index]
    assert rig.tasks.rows == {}


async def test_the_delegate_tool_returns_the_fields_of_the_task_result() -> None:
    rig = make_rig(contexts={"turn-ctx": {"action_type": "reminder_template"}})
    ctx = make_tool_context(profile=PolicyProfileKey.PATIENT_CHANNEL)
    ctx.extras[CARE_TURN_EXTRA] = rig.scope
    tool = build_delegate_spec(rig.service).build(ctx)
    out: Any = await tool.execute(
        {"agent_name": "reviewer", "task": "Nhắc lịch hẹn mai 9h ạ.", "context_ref": "turn-ctx"}
    )
    assert set(out) == {"summary", "artifacts", "citations", "needs_human", "confidence"}
    assert out["needs_human"] is False
    bad: Any = await tool.execute({"agent_name": "nobody", "task": "x"})
    assert bad["ok"] is False


async def test_the_tasks_tree_is_never_deeper_than_one() -> None:
    rig = make_rig(models={KNOWLEDGE_ID: model(submit(summary="x"))})
    for name in ("reviewer", "reviewer", "reviewer"):
        await rig.service.delegate(rig.scope, name, "Nháp mẫu", None)
    assert len(rig.tasks.children()) == 3
    assert {rig.tasks.depth(row.id) for row in rig.tasks.rows.values()} == {0, 1}
    child = rig.tasks.children()[0]
    with pytest.raises(DepthError):
        await rig.tasks.create_child(
            child.id, agent_id="x", input={}, started_at=rig.clock.now, deadline_at=rig.clock.now
        )


async def test_every_delegation_is_recorded_with_parent_tokens_cost_and_timing() -> None:
    rig = make_rig(
        models={
            KNOWLEDGE_ID: model(
                call("kb_search", question="sau laser"), submit(summary="Tránh nắng", confidence=0.8)
            )
        },
        hits={"sau laser": [HIT]},
    )
    rig.clock.advance(timedelta(seconds=2))
    await rig.service.delegate(rig.scope, "knowledge", "sau laser", None)
    (row,) = rig.tasks.children()
    root = rig.tasks.rows[row.parent_id]  # type: ignore[index]
    assert (root.parent_id, root.care_agent_id) == (None, rig.scope.care_agent.id)
    assert row.agent_id == KNOWLEDGE_ID
    assert row.status == TaskStatus.DONE.value
    assert row.tokens == 300  # two scripted steps of 150 tokens
    assert row.started_at is not None
    assert row.finished_at is not None
    assert row.deadline_at is not None
    assert row.result is not None
    assert row.result.citations[0].source_id == HIT.source_id
    assert rig.scope.budget.tokens_used == 300


# ============================================================================================== budgets
async def test_the_fourth_delegation_of_a_turn_is_needs_human_with_an_audit_row() -> None:
    rig = make_rig()
    results = [await rig.service.delegate(rig.scope, "reviewer", "Nháp mẫu", None) for _ in range(4)]
    assert [r.needs_human for r in results] == [False, False, False, True]
    kinds = [a.action_type for a in rig.store.actions]
    assert kinds == [f"{BUDGET_EXHAUSTED}:max_specialists"]
    assert rig.store.actions[0].disposition == "paused"
    assert rig.tasks.children()[-1].error == f"{BUDGET_EXHAUSTED}:max_specialists"


async def test_the_token_ceiling_cuts_a_specialist_and_gives_needs_human() -> None:
    forever = model(call("kb_search", question="a"))  # the last step repeats: a model that never stops
    rig = make_rig(models={KNOWLEDGE_ID: forever}, token_ceiling=200, hits={"a": [HIT]})
    result = await rig.service.delegate(rig.scope, "knowledge", "x", None)
    assert result.needs_human is True
    assert forever.count == 2  # 150 then 300 tokens: stopped after the step that crossed the ceiling
    assert [a.action_type for a in rig.store.actions] == [f"{BUDGET_EXHAUSTED}:token_ceiling"]
    assert rig.scope.budget.tokens_used == 300


async def test_the_step_cap_cuts_a_specialist_and_gives_needs_human() -> None:
    forever = model(call("kb_search", question="a"))
    rig = make_rig(models={KNOWLEDGE_ID: forever}, max_tool_steps=3, hits={"a": [HIT]})
    result = await rig.service.delegate(rig.scope, "knowledge", "x", None)
    assert (result.needs_human, forever.count) == (True, 3)
    assert [a.action_type for a in rig.store.actions] == [f"{BUDGET_EXHAUSTED}:max_tool_steps"]


async def test_an_expired_deadline_refuses_before_any_model_call() -> None:
    scripted = model(submit(summary="x"))
    rig = make_rig(models={KNOWLEDGE_ID: scripted})
    rig.clock.advance(timedelta(minutes=4))
    result = await rig.service.delegate(rig.scope, "knowledge", "x", None)
    assert (result.needs_human, scripted.count) == (True, 0)
    assert [a.action_type for a in rig.store.actions] == [f"{BUDGET_EXHAUSTED}:deadline"]


class _SlowRunner:
    async def run(self, call: SpecialistCall) -> SpecialistRun:
        await asyncio.sleep(5)
        return SpecialistRun(result=TaskResult(summary="late"))


async def test_a_run_that_outlives_the_deadline_is_cut_with_needs_human() -> None:
    rig = make_rig(deadline=timedelta(milliseconds=60))
    slow: SpecialistRunner = _SlowRunner()
    service = DelegationService(
        specs={KNOWLEDGE_ID: next(s for s in _all() if s.agent_id == KNOWLEDGE_ID)},
        runners={KNOWLEDGE_ID: slow},
        toolkit=rig.toolkit,
        tasks=rig.tasks,
        store=rig.store,
        kill_switch=KillSwitchState,
    )
    started = time.monotonic()
    result = await service.delegate(rig.scope, "knowledge", "x", None)
    assert result.needs_human is True
    assert time.monotonic() - started < 2
    assert [a.action_type for a in rig.store.actions] == [f"{BUDGET_EXHAUSTED}:deadline"]


def _all() -> Any:
    from pema.care.specialists.store import all_specs

    return all_specs()


async def test_a_failing_model_is_a_failed_task_and_needs_human_not_an_exception() -> None:
    broken = ScriptedModel([lambda: RuntimeError("model unavailable")])
    rig = make_rig(models={KNOWLEDGE_ID: broken})
    result = await rig.service.delegate(rig.scope, "knowledge", "x", None)
    assert result.needs_human is True
    (row,) = rig.tasks.children()
    assert (row.status, row.error) == (TaskStatus.FAILED.value, "RuntimeError")


async def test_a_specialist_that_never_submits_a_structured_answer_is_needs_human() -> None:
    chatty = model(lambda: tra_loi("Em nghĩ là chị nên nghỉ ngơi."))
    rig = make_rig(models={KNOWLEDGE_ID: chatty})
    result = await rig.service.delegate(rig.scope, "knowledge", "x", None)
    assert result.needs_human is True
    assert rig.tasks.children()[0].error == "no_result"


async def test_a_text_answer_that_is_a_valid_task_result_json_is_accepted() -> None:
    json_text = '{"summary": "ok", "confidence": 0.6, "needs_human": false, "artifacts": [], "citations": []}'
    fenced = "```json\n" + json_text + "\n```"
    scripted = model(call("kb_search", question="sau laser"), lambda: tra_loi(fenced))
    rig = make_rig(models={KNOWLEDGE_ID: scripted}, hits={"sau laser": [HIT]})
    result = await rig.service.delegate(rig.scope, "knowledge", "sau laser", None)
    assert (result.summary, result.confidence, result.needs_human) == ("ok", 0.6, False)
    assert [c.source_id for c in result.citations] == [HIT.source_id]


async def test_the_kill_switch_of_a_specialist_blocks_only_that_specialist() -> None:
    scripted = model(submit(summary="x"))
    rig = make_rig(
        models={KNOWLEDGE_ID: scripted}, kill_switch=KillSwitchState(agents=frozenset({KNOWLEDGE_ID}))
    )
    blocked = await rig.service.delegate(rig.scope, "knowledge", "x", None)
    assert (blocked.needs_human, scripted.count) == (True, 0)
    assert [a.action_type for a in rig.store.actions] == [BLOCKED_KILL_SWITCH]
    assert rig.tasks.rows == {}
    reviewed = await rig.service.delegate(rig.scope, "reviewer", "Nháp mẫu", None)
    assert reviewed.needs_human is False


async def test_an_unknown_specialist_is_an_error_for_the_tool_to_report() -> None:
    rig = make_rig()
    with pytest.raises(UnknownSpecialistError):
        await rig.service.delegate(rig.scope, "coordinator", "x", None)


# ========================================================================================= knowledge agent
async def test_knowledge_with_no_citations_is_needs_human() -> None:
    scripted = model(
        call("kb_search", question="điều gì đó không có"), submit(summary="Chắc là vậy", confidence=0.9)
    )
    rig = make_rig(models={KNOWLEDGE_ID: scripted})
    result = await rig.service.delegate(rig.scope, "knowledge", "điều gì đó không có", None)
    assert (result.needs_human, result.citations, result.confidence) == (True, [], 0.0)


async def test_knowledge_citations_are_the_sources_it_really_received_not_what_it_wrote() -> None:
    scripted = model(
        call("kb_search", question="sau laser"),
        submit(
            summary="Tránh nắng 48 giờ",
            confidence=0.9,
            citations=[{"source_id": "kb-aftercare-1"}, {"source_id": "kb-invented-9"}],
        ),
    )
    rig = make_rig(models={KNOWLEDGE_ID: scripted}, hits={"sau laser": [HIT]})
    result = await rig.service.delegate(rig.scope, "knowledge", "sau laser", None)
    assert result.needs_human is False
    assert [c.source_id for c in result.citations] == ["kb-aftercare-1"]
    assert rig.knowledge.searches == [("sau laser", True)]  # toward a patient: approved sources only


async def test_knowledge_cannot_cite_a_source_it_never_searched() -> None:
    scripted = model(
        submit(summary="Theo tài liệu thì ổn", confidence=0.9, citations=[{"source_id": "kb-invented-9"}])
    )
    rig = make_rig(models={KNOWLEDGE_ID: scripted})
    result = await rig.service.delegate(rig.scope, "knowledge", "x", None)
    assert (result.needs_human, result.citations) == (True, [])


async def test_kb_ingest_creates_an_unapproved_unbound_source_and_the_search_tool_stays_available() -> None:
    scripted = model(
        call("kb_ingest", name="Hướng dẫn mới", text="Nội dung"), call("kb_list"), submit(summary="đã nạp")
    )
    rig = make_rig(models={KNOWLEDGE_ID: scripted})
    await rig.service.delegate(rig.scope, "knowledge", "nạp tài liệu", None)
    assert rig.knowledge.ingested == ["Hướng dẫn mới"]
    assert sorted(tool_keys(scripted.calls[0])) == ["kb_ingest", "kb_list", "kb_search", "submit_result"]
    assert "CHƯA" in str(scripted.calls[1].messages)  # the model is told it is neither bound nor approved


# ========================================================================================= scheduler agent
def _search() -> Any:
    return call("appointment.search_slots", from_date="2026-10-07", to_date="2026-10-14")


async def test_search_slots_is_free_and_only_real_slots_are_offered() -> None:
    scripted = model(
        _search(),
        submit(
            summary="Có 2 khung",
            confidence=0.9,
            artifacts=[
                {"kind": "slot", "starts_at": SLOT_A.starts_at.isoformat(), "duration_min": 30},
                {"kind": "slot", "starts_at": "2026-10-07T23:00:00+00:00", "duration_min": 30},
            ],
        ),
    )
    rig = make_rig(models={SCHEDULER_ID: scripted}, slots=[SLOT_A, SLOT_B])
    result = await rig.service.delegate(rig.scope, "scheduler", "tìm slot tuần sau", None)
    assert [a["starts_at"] for a in result.artifacts] == [SLOT_A.starts_at.isoformat()]
    assert result.needs_human is False
    assert rig.actions.proposals == []  # searching never proposes anything
    assert len(rig.slots.queries) == 1


async def test_book_creates_a_draft_proposal_only_for_a_slot_the_search_returned() -> None:
    scripted = model(
        call("appointment.book", starts_at="2026-10-07T09:00:00+00:00"),  # before any search: refused
        _search(),
        call("appointment.book", starts_at=SLOT_A.starts_at.isoformat(), patient_chosen=True),
        submit(summary="Đã tạo nháp", confidence=0.9),
    )
    rig = make_rig(models={SCHEDULER_ID: scripted}, slots=[SLOT_A])
    result = await rig.service.delegate(rig.scope, "scheduler", "đặt lịch", None)
    assert len(rig.actions.proposals) == 1
    assert rig.actions.proposals[0].patient_ref == "P900"
    (draft,) = result.artifacts
    assert (draft["kind"], draft["confirm_eligible"]) == ("appointment_draft", False)
    assert result.needs_human is False


async def test_a_patient_chosen_slot_is_confirm_eligible_only_when_m3_says_l1() -> None:
    def script() -> ScriptedModel:
        return model(
            _search(),
            call("appointment.book", starts_at=SLOT_A.starts_at.isoformat(), patient_chosen=True),
            submit(summary="Đã tạo nháp", confidence=0.9),
        )

    eligible = make_rig(models={SCHEDULER_ID: script()}, slots=[SLOT_A], l1_confirm=True)
    result = await eligible.service.delegate(eligible.scope, "scheduler", "đặt lịch", None)
    assert result.artifacts[0]["confirm_eligible"] is True
    not_chosen = model(
        _search(),
        call("appointment.book", starts_at=SLOT_A.starts_at.isoformat()),
        submit(summary="Đã tạo nháp", confidence=0.9),
    )
    other = make_rig(models={SCHEDULER_ID: not_chosen}, slots=[SLOT_A], l1_confirm=True)
    assert (await other.service.delegate(other.scope, "scheduler", "x", None)).artifacts[0][
        "confirm_eligible"
    ] is False


async def test_no_free_slot_means_a_person_decides() -> None:
    scripted = model(_search(), submit(summary="Không còn chỗ", confidence=0.9))
    rig = make_rig(models={SCHEDULER_ID: scripted}, slots=[])
    assert (await rig.service.delegate(rig.scope, "scheduler", "x", None)).needs_human is True


# ========================================================================================= reviewer agent
async def test_the_reviewer_flags_a_draft_with_a_fake_phone_number_and_is_read_only() -> None:
    rig = make_rig()
    result = await rig.service.delegate(
        rig.scope, "reviewer", "Chị gọi 0901 234 567 để được hỗ trợ nhé.", None
    )
    assert result.needs_human is True
    assert result.artifacts[0]["flags"] == ["no_pii"]
    assert rig.actions.proposals == []
    assert rig.knowledge.ingested == []
    (row,) = rig.tasks.children()
    assert (row.agent_id, row.tokens, row.status) == (REVIEWER_ID, 0, TaskStatus.NEEDS_HUMAN.value)


async def test_the_reviewer_reads_the_context_the_care_loop_prepared() -> None:
    rig = make_rig(contexts={"draft-ctx": {"action_type": "faq_kb_answer", "citations": []}})
    flagged = await rig.service.delegate(rig.scope, "reviewer", "Sau laser nên tránh nắng.", "draft-ctx")
    assert flagged.artifacts[0]["flags"] == ["has_sources"]
    unknown_ref = await rig.service.delegate(
        rig.scope, "reviewer", "Sau laser nên tránh nắng.", "no-such-ref"
    )
    assert (
        unknown_ref.needs_human is False
    )  # an unknown reference is an empty context, never another patient's


# ============================================================================================ sample flow
async def test_the_sample_flow_find_a_slot_next_week_and_aftercare_guidance_with_a_review() -> None:
    """The flow of the recipe with a fake model: a slot, cited guidance, a review of the combined draft."""
    rig = make_rig(
        models={
            SCHEDULER_ID: model(
                _search(),
                submit(
                    summary="1 khung phù hợp",
                    confidence=0.9,
                    artifacts=[
                        {"kind": "slot", "starts_at": SLOT_A.starts_at.isoformat(), "duration_min": 30}
                    ],
                ),
            ),
            KNOWLEDGE_ID: model(
                call("kb_search", question="chăm sóc sau laser"),
                submit(summary="Tránh nắng 48 giờ, dùng kem dưỡng ẩm", confidence=0.85),
            ),
        },
        slots=[SLOT_A],
        hits={"chăm sóc sau laser": [HIT]},
        contexts={
            "draft": {"action_type": "faq_kb_answer", "citations": ["kb-aftercare-1"], "claimed_depth": "D2"}
        },
    )
    started = time.perf_counter()
    slot = await rig.service.delegate(rig.scope, "scheduler", "tìm một khung giờ tuần sau", None)
    guidance = await rig.service.delegate(rig.scope, "knowledge", "chăm sóc sau laser", None)
    draft = f"Em có khung {SLOT_A.starts_at:%d/%m %H:%M}. Sau laser chị nên tránh nắng 48 giờ."
    review = await rig.service.delegate(rig.scope, "reviewer", draft, "draft")
    elapsed = time.perf_counter() - started
    assert [r.needs_human for r in (slot, guidance, review)] == [False, False, False]
    assert slot.artifacts[0]["starts_at"] == SLOT_A.starts_at.isoformat()
    assert [c.source_id for c in guidance.citations] == ["kb-aftercare-1"]
    assert review.confidence == 1.0
    assert rig.scope.budget.specialists_started == 3
    assert elapsed < 5  # with a fake model the flow is plumbing only; the real latency is measured on Ollama
    assert len(rig.tasks.children()) == 3
    assert {rig.tasks.depth(r.id) for r in rig.tasks.children()} == {1}

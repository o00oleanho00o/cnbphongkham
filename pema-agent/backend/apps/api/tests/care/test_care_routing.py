"""Staff routing, SLA, the chain that always ends at the on-call contact, the patient notice (package M, M2c).

New tests (no zalo-agent original). Fakes, fake clock, no database (the SQL side is
``test_care_routing_store``). The "LLM" is counted everywhere: ``FakeHarness`` (answers) and ``FakeDepthLlm``
(classifies); routing itself has no model, so a test that is about routing asserts neither was needed.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from pema.care.handoff_types import Depth, Urgency
from pema.care.loop import TurnStatus
from pema.care.models import ControlState
from pema.care.patient_notices import format_eta
from pema.care.routing import is_on_shift, next_shift_start
from pema.care.routing_types import CandidateKind, CandidateStatus, RankReason, RoutingConfig
from pema.care.testing import vn
from pema.care.testing_routing import (
    MONDAY_10,
    MONDAY_22,
    RED_FLAG_TEXT,
    RoutingRig,
    make_routing_rig,
    staff_context,
)
from pema_contracts.roles import ActorType

ZONE = "Asia/Ho_Chi_Minh"


def users(rig: RoutingRig) -> list[UUID | None]:
    return [c.user_id for c in rig.chain()]


def kinds(rig: RoutingRig) -> list[CandidateKind]:
    return [c.kind for c in rig.chain()]


async def decline(rig: RoutingRig, user: UUID, reason: str = "đang bận", suggest: UUID | None = None) -> None:
    await rig.control.decline(staff_context(user), rig.agent.patient_id, reason, suggest)


# ---------------------------------------------------------------------------------------- shifts
def test_on_shift_follows_the_weekday_and_the_hours() -> None:
    shift = {"mon": [["08:00", "17:00"]], "tue": [["08:00", "12:00"], ["14:00", "18:00"]]}
    assert is_on_shift(shift, vn(2026, 10, 5, 8, 0), ZONE)
    assert is_on_shift(shift, vn(2026, 10, 5, 16, 59), ZONE)
    assert not is_on_shift(shift, vn(2026, 10, 5, 17, 0), ZONE)
    assert not is_on_shift(shift, vn(2026, 10, 6, 13, 0), ZONE)
    assert is_on_shift(shift, vn(2026, 10, 6, 15, 0), ZONE)
    assert not is_on_shift(shift, vn(2026, 10, 10, 10, 0), ZONE)  # Saturday


def test_an_empty_shift_is_never_on_shift_and_has_no_next_start() -> None:
    assert not is_on_shift({}, MONDAY_10, ZONE)
    assert next_shift_start({}, MONDAY_10, ZONE) is None


def test_garbage_in_a_shift_is_ignored() -> None:
    shift: dict[str, object] = {"mon": [["8am", "5pm"], "x", ["09:00"], ["09:00", "09:00"]], "tue": "all day"}
    assert not is_on_shift(shift, MONDAY_10, ZONE)
    assert next_shift_start(shift, MONDAY_10, ZONE) is None


def test_next_shift_start_is_strictly_after_now() -> None:
    shift = {"mon": [["08:00", "17:00"]], "tue": [["08:00", "17:00"]]}
    assert next_shift_start(shift, MONDAY_10, ZONE) == vn(2026, 10, 6, 8, 0)
    assert next_shift_start(shift, vn(2026, 10, 5, 7, 0), ZONE) == vn(2026, 10, 5, 8, 0)
    assert next_shift_start(shift, vn(2026, 10, 6, 9, 0), ZONE) == vn(2026, 10, 12, 8, 0)


def test_a_night_shift_runs_into_the_next_morning() -> None:
    shift = {"mon": [["22:00", "06:00"]]}
    assert is_on_shift(shift, vn(2026, 10, 5, 23, 0), ZONE)
    assert is_on_shift(shift, vn(2026, 10, 6, 3, 0), ZONE)
    assert not is_on_shift(shift, vn(2026, 10, 6, 6, 0), ZONE)


# ------------------------------------------------------------------------- the chain: who is asked
async def test_the_chain_always_ends_with_the_on_call_contact() -> None:
    for staff_count in (0, 1, 3, 9):
        rig = make_routing_rig()
        for _ in range(staff_count):
            rig.directory.add_staff("cs_staff")
        await rig.open_round(Depth.D2, Urgency.NORMAL)
        chain = rig.chain()
        assert chain[-1].kind is CandidateKind.ON_CALL
        assert chain[-1].user_id is None
        assert [c.kind for c in chain].count(CandidateKind.ON_CALL) == 1
        assert 1 <= len(chain) <= 5
        assert rig.harness.calls == 0
        assert rig.llm.calls == []


async def test_owners_come_first_then_the_least_loaded_on_shift() -> None:
    rig = make_routing_rig()
    busy = rig.directory.add_staff("cs_staff", load=4)
    free = rig.directory.add_staff("cs_staff", load=0)
    middle = rig.directory.add_staff("cs_staff", load=2)
    owner = rig.directory.add_staff("cs_staff", load=5, shift={})  # full and off shift: still the owner
    doctor = rig.directory.add_staff("doctor", shift={})
    rig.directory.own(rig.agent.patient_id, cs_owner=owner, doctor=doctor)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    chain = rig.chain()
    assert users(rig) == [owner, doctor, free, middle, None]
    assert [c.rank_reason for c in chain] == [
        RankReason.CS_OWNER,
        RankReason.TREATING_DOCTOR,
        RankReason.ON_SHIFT,
        RankReason.ON_SHIFT,
        RankReason.ON_CALL,
    ]
    assert busy not in users(rig)  # the fifth place went to the on-call contact


async def test_d5_goes_to_doctors_only_the_treating_one_even_off_shift() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    on_shift = rig.directory.add_staff("doctor")
    rig.directory.add_staff("doctor", shift={})  # not the treating doctor and off shift
    treating = rig.directory.add_staff("doctor", shift={})
    cs_owner = rig.directory.add_staff("cs_staff")
    rig.directory.own(rig.agent.patient_id, cs_owner=cs_owner, doctor=treating)
    await rig.open_round(Depth.D5, Urgency.CRITICAL)
    assert users(rig) == [treating, on_shift, None]


async def test_d4_goes_to_the_treating_doctor_or_a_doctor_on_shift() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    rig.directory.add_staff("manager")
    on_shift = rig.directory.add_staff("doctor")
    await rig.open_round(Depth.D4, Urgency.URGENT)
    assert users(rig) == [on_shift, None]


async def test_a_full_non_owner_is_skipped_and_an_off_shift_one_too() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff", capacity=2, load=2)
    rig.directory.add_staff("cs_staff", shift={})
    ok = rig.directory.add_staff("cs_staff", capacity=2, load=1)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert users(rig) == [ok, None]


async def test_the_skill_of_the_request_filters_the_people() -> None:
    rig = make_routing_rig()
    laser = rig.directory.add_staff("cs_staff", skills=["laser"])
    rig.directory.add_staff("cs_staff", skills=["mun"])
    await rig.open_round(Depth.D2, Urgency.NORMAL, required_skill="laser")
    assert users(rig) == [laser, None]


async def test_when_nobody_has_the_skill_the_skill_filter_is_dropped() -> None:
    rig = make_routing_rig()
    first = rig.directory.add_staff("cs_staff", skills=["mun"], load=0)
    second = rig.directory.add_staff("cs_staff", skills=["nam"], load=1)
    await rig.open_round(Depth.D2, Urgency.NORMAL, required_skill="khieu_nai")
    assert users(rig) == [first, second, None]


async def test_an_owner_is_not_filtered_by_skill_but_a_wrong_role_still_is() -> None:
    rig = make_routing_rig()
    owner = rig.directory.add_staff("cs_staff", skills=[])
    rig.directory.own(rig.agent.patient_id, cs_owner=owner)
    await rig.open_round(Depth.D2, Urgency.NORMAL, required_skill="laser")
    assert users(rig)[0] == owner
    other = make_routing_rig()
    cs = other.directory.add_staff("cs_staff")
    other.directory.own(other.agent.patient_id, cs_owner=cs)
    await other.open_round(Depth.D4, Urgency.URGENT)  # D4: doctors only, even for the owner
    assert users(other) == [None]


async def test_at_most_five_candidates_and_the_on_call_contact_is_the_fifth_or_earlier() -> None:
    rig = make_routing_rig()
    ids = [rig.directory.add_staff("cs_staff", load=i % 5) for i in range(9)]
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    chain = rig.chain()
    assert len(chain) == 5
    assert chain[-1].kind is CandidateKind.ON_CALL
    assert set(users(rig)[:4]) <= set(ids)
    assert len({u for u in users(rig) if u is not None}) == 4  # no duplicates


async def test_max_candidates_is_configuration() -> None:
    rig = make_routing_rig(routing_config=RoutingConfig(max_candidates=3))
    for _ in range(6):
        rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert len(rig.chain()) == 3


async def test_the_same_request_gives_the_same_chain() -> None:
    rig = make_routing_rig()
    for load in (3, 1, 2, 1, 0):
        rig.directory.add_staff("cs_staff", load=load)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    first = await rig.service.build_candidates(rig.request, rig.clock.now)
    second = await rig.service.build_candidates(rig.request, rig.clock.now)
    assert first == second


async def test_no_clinic_id_on_a_request_is_refused() -> None:
    rig = make_routing_rig()
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    from dataclasses import replace

    with pytest.raises(ValueError, match="clinic id"):
        await rig.service.build_candidates(replace(rig.request, clinic_id=None))


# --------------------------------------------------------------------------- asking and the SLA
async def test_the_first_candidate_is_notified_with_the_summary_and_an_sla_check_is_scheduled() -> None:
    rig = make_routing_rig()
    first = rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D4, Urgency.URGENT)  # no doctor: only on-call
    assert rig.notifier.staff == []
    rig2 = make_routing_rig()
    doctor = rig2.directory.add_staff("doctor")
    await rig2.open_round(Depth.D4, Urgency.URGENT)
    ((who, notice),) = rig2.notifier.staff
    assert who == doctor
    assert notice.request_id == rig2.request.id
    assert notice.position == 0
    assert "P900" in notice.summary
    assert first != doctor


async def test_sla_defaults_are_5_minutes_urgent_and_30_normal() -> None:
    urgent = make_routing_rig()
    urgent.directory.add_staff("doctor")
    await urgent.open_round(Depth.D4, Urgency.URGENT)
    assert urgent.chain()[0].sla_due_at == MONDAY_10 + timedelta(minutes=5)
    assert urgent.sla.last.due_at == MONDAY_10 + timedelta(minutes=5)
    assert urgent.sla.last.idx == 0

    critical = make_routing_rig()
    critical.directory.add_staff("doctor")
    await critical.open_round(Depth.D5, Urgency.CRITICAL)
    assert critical.chain()[0].sla_due_at == MONDAY_10 + timedelta(minutes=5)

    normal = make_routing_rig()
    normal.directory.add_staff("cs_staff")
    await normal.open_round(Depth.D2, Urgency.NORMAL)
    assert normal.chain()[0].sla_due_at == MONDAY_10 + timedelta(minutes=30)


async def test_the_sla_minutes_are_configuration() -> None:
    rig = make_routing_rig(routing_config=RoutingConfig(sla_normal_minutes=45, sla_urgent_minutes=2))
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert rig.chain()[0].sla_due_at == MONDAY_10 + timedelta(minutes=45)


async def test_out_of_hours_the_deadline_is_the_start_of_the_next_shift() -> None:
    rig = make_routing_rig(now=MONDAY_22)
    owner = rig.directory.add_staff("cs_staff")
    rig.directory.own(rig.agent.patient_id, cs_owner=owner)
    await rig.open_round(Depth.D2, Urgency.NORMAL)  # shallower than D3: waits for the morning
    assert users(rig) == [owner, None]
    assert rig.chain()[0].sla_due_at == vn(2026, 10, 6, 8, 0)
    assert rig.sla.last.due_at == vn(2026, 10, 6, 8, 0)


async def test_an_sla_check_that_fires_early_looks_again_at_the_deadline() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    before = len(rig.sla.checks)
    rig.clock.advance(timedelta(minutes=10))
    assert await rig.service.on_sla_expired(rig.request.id, 0) is None
    assert len(rig.sla.checks) == before + 1
    assert rig.request.current_idx == 0


async def test_a_notification_that_fails_is_logged_and_the_sla_still_moves_the_request_on() -> None:
    from pema.care.testing_routing import FakeStaffNotify

    rig = make_routing_rig(notifier=FakeStaffNotify(fail=True))
    first = rig.directory.add_staff("cs_staff", load=0)
    second = rig.directory.add_staff("cs_staff", load=1)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert "routing:notify_failed:0" in rig.actions()
    assert rig.sla.last.idx == 0
    rig.clock.advance(timedelta(minutes=31))
    await rig.service.on_sla_expired(rig.request.id, 0)
    assert [u for u, _ in rig.notifier.staff] == [first, second]


# ------------------------------------------------------------------ declines, SLA, reaching on-call
async def test_two_declines_and_one_sla_expiry_reach_the_on_call_contact() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    c = rig.directory.add_staff("cs_staff", load=2)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert users(rig) == [a, b, c, None]
    assert rig.request.outcome is None

    await decline(rig, a)
    assert rig.request.current_idx == 1
    await decline(rig, b)
    assert rig.request.current_idx == 2
    assert rig.request.outcome is None
    assert [u for u, _ in rig.notifier.staff] == [a, b, c]

    rig.clock.advance(timedelta(minutes=31))
    await rig.service.on_sla_expired(rig.request.id, 2)
    assert rig.request.outcome == "exhausted_to_oncall"
    assert rig.request.current_idx == 3
    assert rig.state is ControlState.HANDOFF_ROUTING  # still waits for a staff member to accept
    ((contact, notice),) = rig.notifier.on_call
    assert contact.zalo_number == "0000000001"
    assert contact.is_fixture
    assert notice.is_on_call
    assert [x.status for x in rig.chain()] == [
        CandidateStatus.DECLINED,
        CandidateStatus.DECLINED,
        CandidateStatus.EXPIRED,
        CandidateStatus.NOTIFIED,
    ]
    assert "oncall_used:chain" in rig.actions()
    assert "oncall_used:notify" in rig.actions()
    assert rig.harness.calls == 0
    assert rig.llm.calls == []


async def test_nobody_is_asked_after_the_on_call_contact() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    rig.clock.advance(timedelta(minutes=31))
    await rig.service.on_sla_expired(rig.request.id, 0)
    assert rig.request.outcome == "exhausted_to_oncall"
    notified = len(rig.notifier.on_call)
    assert await rig.service.advance(rig.request) is None
    rig.clock.advance(timedelta(hours=3))
    assert await rig.service.sweep_overdue() == 0
    assert len(rig.notifier.on_call) == notified


async def test_a_staff_member_can_still_accept_after_the_chain_reached_the_on_call_contact() -> None:
    rig = make_routing_rig()
    await rig.open_round(Depth.D2, Urgency.NORMAL)  # nobody on the roster: straight to on-call
    assert rig.request.outcome == "exhausted_to_oncall"
    me = uuid4()
    await rig.control.accept(staff_context(me), rig.agent.patient_id)
    assert rig.state is ControlState.STAFF
    assert rig.request.outcome == "accepted"
    assert rig.request.accepted_by == me


async def test_an_sla_check_after_the_request_was_accepted_does_nothing() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff")
    rig.directory.add_staff("cs_staff", load=1)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    await rig.control.accept(staff_context(a), rig.agent.patient_id)
    rig.clock.advance(timedelta(minutes=31))
    assert await rig.service.on_sla_expired(rig.request.id, 0) is None
    assert len(rig.notifier.staff) == 1
    assert rig.state is ControlState.STAFF


async def test_a_duplicated_sla_check_advances_only_once() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    rig.directory.add_staff("cs_staff", load=2)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    rig.clock.advance(timedelta(minutes=31))
    assert await rig.service.on_sla_expired(rig.request.id, 0) is not None
    assert await rig.service.on_sla_expired(rig.request.id, 0) is None
    assert rig.request.current_idx == 1
    assert [u for u, _ in rig.notifier.staff] == [a, b]


async def test_a_decline_and_an_sla_expiry_of_the_same_candidate_move_the_request_once() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    rig.directory.add_staff("cs_staff", load=2)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    rig.clock.advance(timedelta(minutes=31))
    await rig.service.on_sla_expired(rig.request.id, 0)  # the check won the race
    await decline(rig, a, "xin lỗi, bận")  # the decline arrives late
    assert rig.request.current_idx == 1
    assert [u for u, _ in rig.notifier.staff] == [a, b]
    assert rig.chain()[0].status is CandidateStatus.DECLINED
    assert rig.chain()[0].decline_reason == "xin lỗi, bận"


async def test_a_decline_of_a_later_candidate_is_skipped_without_moving_the_request() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    c = rig.directory.add_staff("cs_staff", load=2)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    await decline(rig, b)
    assert rig.request.current_idx == 0
    assert [u for u, _ in rig.notifier.staff] == [a]
    rig.clock.advance(timedelta(minutes=31))
    await rig.service.on_sla_expired(rig.request.id, 0)
    assert rig.request.current_idx == 2  # b is skipped
    assert [u for u, _ in rig.notifier.staff] == [a, c]


async def test_a_decline_from_somebody_outside_the_chain_changes_nothing() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    before = rig.request
    await decline(rig, uuid4())
    assert rig.request == before
    assert "routing:declined_outside_chain" in rig.actions()


# ---------------------------------------------------------------------------------- suggestions
async def test_a_suggested_person_is_placed_next() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    c = rig.directory.add_staff("cs_staff", load=2)
    outsider = rig.directory.add_staff("cs_staff", load=5, capacity=5)  # full: not in the chain
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert outsider not in users(rig)
    await decline(rig, a, "không đúng chuyên môn", suggest=outsider)
    assert users(rig) == [a, outsider, b, c, None]
    assert rig.chain()[1].rank_reason is RankReason.SUGGESTED
    assert rig.request.current_idx == 1
    assert [u for u, _ in rig.notifier.staff] == [a, outsider]


async def test_a_person_already_in_the_chain_who_is_suggested_moves_up() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    c = rig.directory.add_staff("cs_staff", load=2)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    await decline(rig, a, suggest=c)
    assert users(rig) == [a, c, b, None]
    assert rig.request.current_idx == 1


async def test_a_suggestion_is_ignored_when_the_person_may_not_take_this_request() -> None:
    rig = make_routing_rig()
    doctor = rig.directory.add_staff("doctor", load=0)
    second = rig.directory.add_staff("doctor", load=1)
    cs = rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D5, Urgency.CRITICAL)
    await decline(rig, doctor, suggest=cs)  # D5: doctors only
    assert users(rig) == [doctor, second, None]
    await decline(rig, second, suggest=uuid4())  # not a staff member at all
    assert users(rig) == [doctor, second, None]
    assert rig.request.current_idx == 2


async def test_a_suggestion_of_somebody_already_asked_is_ignored() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    await decline(rig, a)
    await decline(rig, b, suggest=a)  # a was already asked and declined
    assert users(rig) == [a, b, None]
    assert rig.request.current_idx == 2
    assert [u for u, _ in rig.notifier.staff].count(a) == 1


# ------------------------------------------------------------------- decline reasons and export
async def test_the_decline_reason_is_masked_stored_on_the_candidate_and_exportable() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    rig.directory.add_staff("cs_staff", load=1)
    await rig.open_round(Depth.D2, Urgency.NORMAL, required_skill="laser")
    await decline(rig, a, "không rành laser, gọi 0912345678 hỏi chị Lan")
    stored = rig.chain()[0]
    assert stored.status is CandidateStatus.DECLINED
    assert stored.decline_reason is not None
    assert "0912345678" not in stored.decline_reason
    assert stored.declined_at == MONDAY_10
    exported = await rig.service.export_declines(MONDAY_10 - timedelta(days=1))
    assert [(r.user_id, r.required_skill, r.depth) for r in exported] == [(a, "laser", "D2")]
    assert exported[0].reason == stored.decline_reason
    assert await rig.service.export_declines(MONDAY_10 + timedelta(days=1)) == []


async def test_nothing_changes_a_staff_profile() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", skills=["mun"])
    before = rig.directory.staff[a]
    await rig.open_round(Depth.D2, Urgency.NORMAL, required_skill="laser")
    await decline(rig, a, "không rành laser")
    assert rig.directory.staff[a] == before


async def test_declining_needs_a_staff_member() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    from pema_contracts.actions import ActionContext

    agent = ActionContext(clinic_id=UUID(int=1), actor_type=ActorType.AGENT, actor_user_id=uuid4())
    with pytest.raises(PermissionError):
        await rig.control.decline(agent, rig.agent.patient_id, "x")
    assert rig.request.current_idx == 0


# ---------------------------------------------------------------------------------- the backstop
async def test_the_sweeper_moves_on_a_request_whose_sla_check_never_ran() -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff", load=0)
    b = rig.directory.add_staff("cs_staff", load=1)
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert await rig.service.sweep_overdue() == 0  # not due yet
    rig.clock.advance(timedelta(minutes=31))
    assert await rig.service.sweep_overdue() == 1
    assert [u for u, _ in rig.notifier.staff] == [a, b]


async def test_a_round_whose_routing_failed_to_start_is_picked_up_by_the_sweeper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rig = make_routing_rig()
    a = rig.directory.add_staff("cs_staff")

    async def boom(clinic_id: UUID) -> list[object]:
        raise RuntimeError("database down")

    with monkeypatch.context() as patched:
        patched.setattr(rig.directory, "list_staff", boom)
        await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert rig.state is ControlState.HANDOFF_ROUTING  # the round is open, the patient was told
    assert rig.request.candidates == ()
    assert len(rig.channel.sent) == 1
    assert await rig.service.sweep_overdue() == 1
    assert users(rig) == [a, None]
    assert [u for u, _ in rig.notifier.staff] == [a]


async def test_without_a_configured_on_call_contact_the_chain_still_ends_with_an_on_call_entry() -> None:
    rig = make_routing_rig(with_on_call=False)
    a = rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert users(rig) == [a, None]
    assert rig.chain()[-1].oncall_id is None
    assert "routing:oncall_missing" in rig.actions()
    rig.clock.advance(timedelta(minutes=31))
    await rig.service.on_sla_expired(rig.request.id, 0)
    assert rig.request.outcome == "exhausted_to_oncall"
    assert rig.notifier.on_call == []  # nobody to tell: logged, audited
    assert "routing:oncall_notify_failed" in rig.actions()


async def test_a_failing_on_call_message_is_audited() -> None:
    from pema.care.testing_routing import FakeStaffNotify

    rig = make_routing_rig(notifier=FakeStaffNotify(fail_on_call=True))
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    assert rig.request.outcome == "exhausted_to_oncall"
    assert "routing:oncall_notify_failed" in rig.actions()


# --------------------------------------------------------------- out of hours and the patient notice
async def test_d5_out_of_hours_goes_to_on_call_and_the_patient_gets_exactly_one_template() -> None:
    rig = make_routing_rig(now=MONDAY_22)
    rig.directory.add_staff("doctor")
    outcome = await rig.message(RED_FLAG_TEXT)
    assert outcome.status is TurnStatus.HANDOFF
    assert rig.state is ControlState.HANDOFF_ROUTING
    assert kinds(rig) == [CandidateKind.ON_CALL]
    assert rig.request.outcome == "exhausted_to_oncall"
    assert len(rig.notifier.on_call) == 1
    assert rig.notifier.staff == []

    assert len(rig.channel.sent) == 1
    _, text, proactive = rig.channel.sent[0]
    assert not proactive
    assert "0000000001" in text
    assert "115" in text  # generic emergency guidance
    assert "oncall_used:patient_notice" in rig.actions()
    assert rig.harness.calls == 0  # nothing written by a model
    assert rig.llm.calls == []  # a red flag is decided by rules

    await rig.message(RED_FLAG_TEXT)  # a second message of the same round: no second template
    assert len(rig.channel.sent) == 1


async def test_d3_to_d4_out_of_hours_get_a_holding_message_with_a_response_time() -> None:
    rig = make_routing_rig(now=MONDAY_22, depth=Depth.D4)
    rig.directory.add_staff("doctor")
    outcome = await rig.message()
    assert outcome.status is TurnStatus.HANDOFF
    assert kinds(rig) == [CandidateKind.ON_CALL]
    assert len(rig.channel.sent) == 1
    text = rig.channel.sent[0][1]
    assert "08:00 ngày 06/10" in text
    assert "0000000001" not in text  # only a D5 gets the number
    assert rig.harness.calls == 0


async def test_inside_clinic_hours_the_default_holding_message_stays() -> None:
    rig = make_routing_rig(now=MONDAY_10, depth=Depth.D4)
    rig.directory.add_staff("doctor")
    await rig.message()
    assert len(rig.channel.sent) == 1
    text = rig.channel.sent[0][1]
    assert "0000000001" not in text
    assert "ngày" not in text
    assert kinds(rig) == [CandidateKind.STAFF, CandidateKind.ON_CALL]


async def test_d5_out_of_hours_without_an_on_call_contact_falls_back_to_the_urgent_holding_message() -> None:
    rig = make_routing_rig(now=MONDAY_22, with_on_call=False)
    await rig.message(RED_FLAG_TEXT)
    assert len(rig.channel.sent) == 1
    assert "115" not in rig.channel.sent[0][1]


async def test_the_out_of_hours_depth_is_configuration() -> None:
    rig = make_routing_rig(now=MONDAY_22, routing_config=RoutingConfig(oncall_direct_from_depth=Depth.D5))
    owner = rig.directory.add_staff("doctor")
    rig.directory.own(rig.agent.patient_id, doctor=owner)
    await rig.open_round(Depth.D4, Urgency.URGENT)
    assert users(rig) == [owner, None]  # D4 no longer jumps the staff


async def test_the_eta_names_the_day_only_when_it_is_not_today() -> None:
    assert format_eta(vn(2026, 10, 5, 8, 0), vn(2026, 10, 5, 6, 0), ZONE) == "08:00"
    assert format_eta(vn(2026, 10, 6, 8, 0), vn(2026, 10, 5, 22, 0), ZONE) == "08:00 ngày 06/10"
    assert format_eta(vn(2026, 10, 6, 8, 0), vn(2026, 10, 5, 22, 0), "No/Such_Zone") == "01:00 ngày 06/10"


# ------------------------------------------------------------------------- the on-call number
async def test_changing_the_on_call_number_applies_to_the_next_turn() -> None:
    rig = make_routing_rig(now=MONDAY_22)
    await rig.message(RED_FLAG_TEXT)
    assert "0000000001" in rig.channel.sent[0][1]
    me = uuid4()
    await rig.control.accept(staff_context(me), rig.agent.patient_id)
    await rig.control.release_to_auto(staff_context(me), rig.agent.patient_id, "xong")

    rig.oncall_source.set_number("0000000002")  # the dashboard edit
    await rig.message(RED_FLAG_TEXT)
    assert "0000000002" in rig.channel.sent[1][1]
    assert "0000000001" not in rig.channel.sent[1][1]
    assert rig.notifier.on_call[-1][0].zalo_number == "0000000002"


async def test_the_chain_uses_the_number_that_is_current_when_it_is_notified() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D2, Urgency.NORMAL)
    rig.oncall_source.set_number("0000000003")  # changed while the first candidate was thinking
    rig.clock.advance(timedelta(minutes=31))
    await rig.service.on_sla_expired(rig.request.id, 0)
    assert rig.notifier.on_call[-1][0].zalo_number == "0000000003"


async def test_the_routing_never_needs_the_models_to_pick_people() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("doctor")
    rig.directory.add_staff("cs_staff")
    await rig.open_round(Depth.D4, Urgency.URGENT)
    await rig.open_round(Depth.D5, Urgency.CRITICAL)  # a second call is the same round: nothing changes
    assert rig.harness.calls == 0
    assert rig.llm.calls == []
    assert len(rig.controls.requests) == 1

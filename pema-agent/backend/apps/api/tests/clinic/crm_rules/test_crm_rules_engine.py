# ported from: prototype/crm-test.cjs (the rule-level checks)
"""Test names are the snake_case form of the title of the original check; the Vietnamese title is the docstring.

The original ``crm-test.cjs`` also covers resolving a task, booking from a task, rollback and metrics: those
belong to the CRM actions of package B1 and are not part of the rule engine. What is ported here is every check
about WHICH tasks the rules create and keep. The same behaviours are also proven against the real JavaScript
engine in ``test_crm_equivalence.py``; these tests keep them readable and cover what the fixed clock cannot
(year boundary, 29 February, non-default protocol).
"""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, datetime, timedelta
from uuid import uuid4

from pema.clinic.crm_rules.dates import add_days, birthday_in_year, days_between, next_birthday
from pema.clinic.crm_rules.engine import SUPERSEDED_RESOLUTION, run_rules, task_key
from pema.clinic.crm_rules.profile import compute_profile, refresh_patient, to_profile_dto
from pema.clinic.crm_rules.records import (
    AppointmentStatus,
    ExistingTask,
    LifecycleStage,
    PatientSnapshot,
    RiskLevel,
    RulesOutcome,
    TaskCandidate,
)
from pema.clinic.crm_rules.rules import DEFAULT_RULES, RuleConfig
from pema.clinic.crm_rules.store import MemoryCrmRuleStore, StoreChanges
from pema.clinic.crm_rules.testing import NOW, appointment, make_patient, session
from pema_contracts.common import VN_TZ
from pema_contracts.crm import RuleKey, TaskStatus

TODAY = date(2026, 9, 20)
LASER = "laser-co2"


def _run(
    patients: list[PatientSnapshot],
    existing: list[ExistingTask] | None = None,
    rules: tuple[RuleConfig, ...] = DEFAULT_RULES,
    now: datetime = NOW,
) -> RulesOutcome:
    return run_rules(patients, rules, existing or [], now)


def _by_rule(outcome: RulesOutcome, rule: RuleKey) -> list[TaskCandidate]:
    return [t for t in outcome.candidates if t.rule_key is rule]


def _laser_yesterday(code: str = "P025") -> PatientSnapshot:
    return make_patient(
        code,
        last_visit=TODAY - timedelta(days=1),
        sessions=(session("s-laser", TODAY - timedelta(days=1), LASER),),
        total_sessions=5,
        completed_sessions=1,
    )


def test_automation_rerun_and_reload_never_duplicate_tasks() -> None:
    """Chạy lại và tải lại không bao giờ tạo trùng việc."""
    patients = [
        _laser_yesterday("P025"),
        make_patient(
            "P030",
            last_visit=TODAY - timedelta(days=180),
            sessions=(session("a", TODAY - timedelta(days=180)),),
        ),
    ]
    store = MemoryCrmRuleStore(patients=patients)

    async def go() -> tuple[int, int, int]:
        first = _run(list((await store.load(uuid4(), NOW)).patients))
        await store.apply(
            uuid4(), StoreChanges(first.new_tasks, first.superseded_keys, first.patient_updates, NOW)
        )
        data = await store.load(uuid4(), NOW)
        second = run_rules(data.patients, data.rules, data.existing_tasks, NOW)
        third = run_rules(data.patients, data.rules, data.existing_tasks, NOW)
        return len(first.new_tasks), len(second.new_tasks), len(third.new_tasks)

    first, second, third = asyncio.run(go())
    assert first > 0
    assert (second, third) == (0, 0)


def test_d1_d3_d7_from_completed_protocol_sessions_only() -> None:
    """D+1/D+3/D+7 chỉ sinh từ buổi có protocol Laser CO2 đã hoàn tất."""
    plain = make_patient(
        "P001", last_visit=TODAY, sessions=(session("plain", TODAY),), total_sessions=1, completed_sessions=1
    )
    outcome = _run([_laser_yesterday(), plain])
    chain = {
        t.rule_key: t
        for t in outcome.candidates
        if t.patient_code == "P025" and t.source_event_id == "s-laser"
    }
    assert set(chain) == {RuleKey.D1, RuleKey.D3, RuleKey.D7}
    assert [chain[k].due_at.date() for k in (RuleKey.D1, RuleKey.D3, RuleKey.D7)] == [
        TODAY,
        TODAY + timedelta(days=2),
        TODAY + timedelta(days=6),
    ]
    assert not [t for t in outcome.candidates if t.patient_code == "P001" and t.rule_key is RuleKey.D1]


def test_d7_goes_to_the_doctor_and_the_rest_to_the_cs_owner() -> None:
    """D+7 giao cho bác sĩ, các việc còn lại giao cho người phụ trách CSKH."""
    doctor, cs = uuid4(), uuid4()
    patient = replace(_laser_yesterday(), doctor_id=doctor, cs_owner_id=cs)
    outcome = _run([patient])
    owners = {
        t.rule_key: t.owner_user_id for t in outcome.candidates if t.rule_key in (RuleKey.D1, RuleKey.D7)
    }
    assert owners == {RuleKey.D1: cs, RuleKey.D7: doctor}


def test_a_session_older_than_45_days_starts_no_chain() -> None:
    """Buổi Laser quá 45 ngày không còn sinh chuỗi D+1/3/7."""
    old = TODAY - timedelta(days=46)
    patient = make_patient("P001", last_visit=old, sessions=(session("old", old, LASER),))
    inside = replace(patient, sessions=(session("old", TODAY - timedelta(days=45), LASER),))
    assert not [t for t in _run([patient]).candidates if t.rule_key is RuleKey.D1]
    assert [t for t in _run([inside]).candidates if t.rule_key is RuleKey.D1]


def test_expected_visit_overdue_is_14_days_with_doctor_source() -> None:
    """Quá hạn tái khám 14 ngày, nguồn là khuyến nghị của bác sĩ."""
    patient = make_patient(
        "P027",
        last_visit=TODAY - timedelta(days=30),
        sessions=(session("s", TODAY - timedelta(days=30)),),
        recommendation_at=TODAY - timedelta(days=14),
        expected_visit_source="doctor_recommendation",
    )
    view = compute_profile(patient, TODAY)
    assert view.overdue_days == 14
    assert view.expected_visit_source == "doctor_recommendation"
    overdue = _by_rule(_run([patient]), RuleKey.OVERDUE)
    assert [t.task_key for t in overdue] == [
        task_key(RuleKey.OVERDUE, "P027", (TODAY - timedelta(days=14)).isoformat())
    ]
    assert overdue[0].due_at.date() == TODAY - timedelta(days=14)


def test_unfinished_six_session_plan_and_sixty_day_gap() -> None:
    """Liệu trình 6 buổi còn dở và 60 ngày không quay lại sinh việc bỏ liệu trình."""
    last = TODAY - timedelta(days=60)
    patient = make_patient(
        "P029",
        last_visit=last,
        sessions=(session("c0", last - timedelta(days=60)), session("c2", last)),
        total_sessions=6,
        completed_sessions=3,
        first_plan_id=str(uuid4()),
    )
    assert compute_profile(patient, TODAY).remaining == 3
    abandoned = _by_rule(_run([patient]), RuleKey.ABANDONED)
    assert len(abandoned) == 1
    assert abandoned[0].source_event_id == "c2"
    assert abandoned[0].due_at.date() == add_days(last, 45)
    assert abandoned[0].related_plan_id == patient.first_plan_id


def test_abandoned_needs_more_than_45_days_and_no_booking() -> None:
    """Chỉ nguy cơ bỏ liệu trình khi quá 45 ngày và chưa đặt lại."""
    base = make_patient(
        "P029",
        last_visit=TODAY - timedelta(days=45),
        sessions=(session("c", TODAY - timedelta(days=45)),),
        total_sessions=6,
        completed_sessions=3,
    )
    assert not _by_rule(_run([base]), RuleKey.ABANDONED)
    later = replace(base, last_visit=TODAY - timedelta(days=46))
    assert _by_rule(_run([later]), RuleKey.ABANDONED)
    booked = replace(later, appointments=(appointment("a", TODAY + timedelta(days=3)),))
    assert not _by_rule(_run([booked]), RuleKey.ABANDONED)


def test_no_show_and_cancellation_older_than_24h_without_future_booking() -> None:
    """Vắng/hủy cách đây từ 24 giờ và chưa có lịch mới thì gọi lại."""
    missed = appointment(
        "A-missed", TODAY - timedelta(days=2), status=AppointmentStatus.MISSED,
        missed_at=datetime(2026, 9, 18, 10, 0, tzinfo=VN_TZ),
    )  # fmt: skip
    patient = make_patient("P028", appointments=(missed,))
    recall = _by_rule(_run([patient]), RuleKey.NO_SHOW)
    assert [t.related_appointment_id for t in recall] == ["A-missed"]
    assert recall[0].due_at.date() == TODAY - timedelta(days=1)
    assert not _by_rule(_run([make_patient("P001")]), RuleKey.NO_SHOW)
    booked = replace(patient, appointments=(missed, appointment("A-new", TODAY + timedelta(days=5))))
    assert not _by_rule(_run([booked]), RuleKey.NO_SHOW)


def test_recall_respects_actual_24_hour_boundary_not_calendar_day_alone() -> None:
    """Gọi lại tôn trọng đúng mốc 24 giờ thực, không chỉ ngày dương lịch."""
    day_before = TODAY - timedelta(days=1)
    recent = appointment(
        "recent", day_before, hour=17, status=AppointmentStatus.CANCELLED,
        cancelled_at=datetime(2026, 9, 19, 17, 0, tzinfo=VN_TZ),
    )  # fmt: skip
    older = replace(recent, cancelled_at=datetime(2026, 9, 19, 8, 0, tzinfo=VN_TZ))
    exactly_24h = replace(recent, cancelled_at=NOW - timedelta(hours=24))
    assert not _by_rule(_run([make_patient("P036", appointments=(recent,))]), RuleKey.NO_SHOW)
    assert _by_rule(_run([make_patient("P036", appointments=(older,))]), RuleKey.NO_SHOW)
    assert _by_rule(_run([make_patient("P036", appointments=(exactly_24h,))]), RuleKey.NO_SHOW)


def test_dormant90_180_are_exclusive_per_customer() -> None:
    """dormant90 và dormant180 loại trừ nhau theo từng khách."""

    def patient(age: int) -> PatientSnapshot:
        day = TODAY - timedelta(days=age)
        return make_patient(f"P{age}", last_visit=day, sessions=(session(f"s{age}", day),))

    outcome = _run([patient(95), patient(180), patient(89), patient(90), patient(179)])
    dormant90 = {t.patient_code for t in _by_rule(outcome, RuleKey.DORMANT90)}
    dormant180 = {t.patient_code for t in _by_rule(outcome, RuleKey.DORMANT180)}
    assert dormant180 == {"P180"}
    assert dormant90 == {"P95", "P90", "P179"}
    assert not dormant90 & dormant180


def test_birthday_window_handles_year_boundary_and_excludes_past_birthdays() -> None:
    """Cửa sổ sinh nhật qua giao năm và loại các sinh nhật đã qua."""
    late_december = datetime(2026, 12, 28, 9, 0, tzinfo=VN_TZ)
    january = make_patient("P1", birth_date=date(1990, 1, 2))
    just_passed = make_patient("P2", birth_date=date(1990, 12, 20))
    outcome = _run([january, just_passed], now=late_december)
    birthdays = _by_rule(outcome, RuleKey.BIRTHDAY)
    assert [(t.patient_code, t.source_event_id) for t in birthdays] == [("P1", "2027-01-02")]
    assert birthdays[0].due_at.date() == date(2027, 1, 2)
    assert not _by_rule(_run([make_patient("P3", birth_date=date(1990, 9, 19))]), RuleKey.BIRTHDAY)
    assert _by_rule(_run([make_patient("P4", birth_date=date(1990, 9, 27))]), RuleKey.BIRTHDAY)
    assert not _by_rule(_run([make_patient("P5", birth_date=date(1990, 9, 28))]), RuleKey.BIRTHDAY)


def test_birthday_on_29_february_is_observed_on_the_28th_in_a_common_year() -> None:
    """Sinh nhật 29/2 được tính vào 28/2 ở năm thường (bản JavaScript sinh ngày không hợp lệ)."""
    leap_day = date(1992, 2, 29)
    assert birthday_in_year(leap_day, 2027) == date(2027, 2, 28)
    assert birthday_in_year(leap_day, 2028) == date(2028, 2, 29)
    assert next_birthday(leap_day, date(2027, 2, 20)) == date(2027, 2, 28)
    assert next_birthday(leap_day, date(2027, 3, 1)) == date(2028, 2, 29)
    assert days_between(date(2027, 2, 20), next_birthday(leap_day, date(2027, 2, 20))) == 8


def test_opt_out_suppresses_marketing_retains_clinical_tasks_and_trace() -> None:
    """Từ chối nhận tin chặn việc marketing nhưng giữ việc lâm sàng và dấu vết."""
    last = TODAY - timedelta(days=180)
    patient = make_patient(
        "P030",
        last_visit=last,
        sessions=(session("c", last),),
        total_sessions=6,
        completed_sessions=3,
        birth_date=date(1990, 9, 22),
    )
    before = _run([patient])
    assert {RuleKey.DORMANT180, RuleKey.ABANDONED, RuleKey.BIRTHDAY} <= {
        t.rule_key for t in before.candidates
    }
    stored = [ExistingTask(t.task_key, t.rule_key, TaskStatus.OPEN) for t in before.new_tasks]

    after = _run([replace(patient, marketing_opt_out=True)], existing=stored)
    kept = {t.rule_key for t in after.candidates}
    assert RuleKey.DORMANT180 not in kept
    assert RuleKey.BIRTHDAY not in kept
    assert RuleKey.ABANDONED in kept
    superseded = {k.split(":")[1] for k in after.superseded_keys}
    assert superseded == {"dormant180", "birthday"}


def test_new_protocol_completion_schedules_future_d1_3_7_without_adding_them_to_due_queue() -> None:
    """Hoàn tất buổi protocol mới hẹn sẵn D+1/3/7 ở tương lai, chưa vào hàng đợi đến hạn."""
    patient = make_patient(
        "P001",
        last_visit=TODAY,
        sessions=(session("new-session", TODAY, LASER),),
        total_sessions=3,
        completed_sessions=1,
    )
    outcome = _run([patient])
    new = [t for t in outcome.new_tasks if t.source_event_id == "new-session"]
    assert len(new) == 3
    assert sorted(t.due_at.date() for t in new) == [
        TODAY + timedelta(days=1),
        TODAY + timedelta(days=3),
        TODAY + timedelta(days=7),
    ]
    assert all(t.due_at.date() > TODAY for t in new)


def test_cancel_booked_appointment_returns_expected_visit_to_saved_recommendation() -> None:
    """Hủy lịch đã đặt thì ngày dự kiến quay về khuyến nghị đã lưu."""
    patient = make_patient(
        "P027",
        last_visit=TODAY - timedelta(days=30),
        sessions=(session("s", TODAY - timedelta(days=30)),),
        recommendation_at=TODAY - timedelta(days=14),
        expected_visit_source="doctor_recommendation",
    )
    booked = replace(patient, appointments=(appointment("A", TODAY + timedelta(days=7)),))
    view = compute_profile(booked, TODAY)
    assert (view.overdue_days, view.expected_visit_source) == (0, "appointment")
    assert view.expected_next_visit_at == TODAY + timedelta(days=7)
    cancelled_at = NOW - timedelta(hours=1)
    cancelled = replace(
        patient,
        appointments=(
            appointment(
                "A", TODAY + timedelta(days=7), status=AppointmentStatus.CANCELLED, cancelled_at=cancelled_at
            ),
        ),
    )
    assert compute_profile(cancelled, TODAY).overdue_days == 14


def test_a_booking_supersedes_the_overdue_task_and_a_cancelled_booking_never_revives_it() -> None:
    """Đặt lịch thay thế việc quá hạn; hủy lịch sau đó không mở lại việc đã đóng."""
    patient = make_patient(
        "P027", last_visit=TODAY - timedelta(days=30), sessions=(session("s", TODAY - timedelta(days=30)),),
        recommendation_at=TODAY - timedelta(days=14),
    )  # fmt: skip
    first = _run([patient])
    overdue_key = _by_rule(first, RuleKey.OVERDUE)[0].task_key
    stored = [ExistingTask(t.task_key, t.rule_key, TaskStatus.OPEN) for t in first.new_tasks]

    booked = replace(patient, appointments=(appointment("A", TODAY + timedelta(days=7)),))
    second = _run([booked], existing=stored)
    assert overdue_key in second.superseded_keys

    after_cancel = [
        replace(t, status=TaskStatus.SUPERSEDED) if t.task_key in second.superseded_keys else t
        for t in stored
    ]
    third = _run([patient], existing=after_cancel)
    assert overdue_key not in {t.task_key for t in third.new_tasks}
    assert overdue_key not in third.superseded_keys


def test_manual_tasks_and_closed_tasks_are_never_superseded() -> None:
    """Việc thủ công và việc đã đóng không bao giờ bị thay thế."""
    stored = [
        ExistingTask("CRM:manual:P001:x", RuleKey.MANUAL, TaskStatus.OPEN),
        ExistingTask("CRM:d1:P001:old", RuleKey.D1, TaskStatus.RESOLVED),
        ExistingTask("CRM:d3:P001:old", RuleKey.D3, TaskStatus.SUPERSEDED),
        ExistingTask("CRM:d7:P001:old", RuleKey.D7, TaskStatus.RESCHEDULED),
    ]
    outcome = _run([make_patient("P001")], existing=stored)
    assert outcome.superseded_keys == ("CRM:d7:P001:old",)


def test_an_inactive_rule_creates_nothing_and_supersedes_its_open_tasks() -> None:
    """Quy tắc tắt không tạo việc và thay thế các việc đang mở của nó."""
    patient = _laser_yesterday()
    off = tuple(replace(r, active=False) if r.key is RuleKey.D1 else r for r in DEFAULT_RULES)
    first = _run([patient])
    d1 = _by_rule(first, RuleKey.D1)[0]
    stored = [ExistingTask(d1.task_key, RuleKey.D1, TaskStatus.OPEN)]
    outcome = _run([patient], existing=stored, rules=off)
    assert not _by_rule(outcome, RuleKey.D1)
    assert outcome.superseded_keys == (d1.task_key,)
    assert SUPERSEDED_RESOLUTION.startswith("Nguồn đã đổi")


def test_the_task_key_is_rule_patient_and_source_event() -> None:
    """Khoá chống trùng là quy tắc + hồ sơ + sự kiện nguồn."""
    assert task_key(RuleKey.D1, "P025", "s24-0") == "CRM:d1:P025:s24-0"
    candidate = _by_rule(_run([_laser_yesterday("P025")]), RuleKey.D1)[0]
    assert candidate.task_key == "CRM:d1:P025:s-laser"
    assert candidate.reason == "Sau thủ thuật D+1"
    assert candidate.suggested_action == "Hỏi tình trạng sau thủ thuật"


def test_a_rule_can_name_another_protocol() -> None:
    """Quy tắc đọc protocol từ cấu hình; mặc định vẫn là Laser CO2."""
    other = make_patient("P001", last_visit=TODAY, sessions=(session("x", TODAY, "peel"),))
    assert not _by_rule(_run([other]), RuleKey.D1)
    rules = tuple(replace(r, protocol="peel") if r.key is RuleKey.D1 else r for r in DEFAULT_RULES)
    assert _by_rule(_run([other], rules=rules), RuleKey.D1)


def test_due_today_unless_the_patient_already_arrived() -> None:
    """Đến hạn hôm nay, trừ khi bệnh nhân đã đến."""
    base = make_patient("P001", recommendation_at=TODAY, expected_visit_source="doctor_recommendation")
    assert [t.due_at.date() for t in _by_rule(_run([base]), RuleKey.DUE)] == [TODAY]
    arrived = replace(base, appointments=(appointment("A", TODAY, status=AppointmentStatus.ARRIVED),))
    assert not _by_rule(_run([arrived]), RuleKey.DUE)
    booked_today = replace(base, appointments=(appointment("A", TODAY, status=AppointmentStatus.BOOKED),))
    assert _by_rule(_run([booked_today]), RuleKey.DUE)


def test_lifecycle_stage_and_risk() -> None:
    """Giai đoạn vòng đời và mức rủi ro: một lịch đã đặt vẫn chưa là đã quay lại."""

    def stage(**fields: object) -> LifecycleStage:
        return compute_profile(make_patient("P1", **fields), TODAY).lifecycle_stage

    old = TODAY - timedelta(days=100)
    assert stage() is LifecycleStage.NEW
    assert stage(sessions=(session("s", TODAY),), last_visit=TODAY) is LifecycleStage.RETURNING
    assert (
        stage(sessions=(session("s", TODAY),), last_visit=TODAY, total_sessions=4) is LifecycleStage.TREATING
    )
    assert stage(sessions=(session("s", old),), last_visit=old) is LifecycleStage.DORMANT
    assert (
        stage(sessions=(session("s", old),), last_visit=old, reactivated_at=NOW) is LifecycleStage.REACTIVATED
    )
    booked = make_patient("P1", sessions=(session("s", old),), last_visit=old,
                          appointments=(appointment("A", TODAY + timedelta(days=2)),))  # fmt: skip
    assert compute_profile(booked, TODAY).lifecycle_stage is LifecycleStage.DORMANT

    def risk(patient: PatientSnapshot) -> RiskLevel:
        return compute_profile(patient, TODAY).risk_level

    seven = make_patient("P2", recommendation_at=TODAY - timedelta(days=7))
    eight = make_patient("P2", recommendation_at=TODAY - timedelta(days=8))
    assert (risk(seven), risk(eight)) == (RiskLevel.NORMAL, RiskLevel.HIGH)
    unfinished = make_patient(
        "P3", last_visit=TODAY - timedelta(days=46), total_sessions=5, completed_sessions=2
    )
    assert risk(unfinished) is RiskLevel.HIGH
    assert (
        risk(replace(unfinished, appointments=(appointment("A", TODAY + timedelta(days=1)),)))
        is RiskLevel.NORMAL
    )


def test_the_profile_dto_matches_the_contract_shape() -> None:
    """DTO hồ sơ CRM đúng hình dạng hợp đồng cho Patient 360."""
    patient = make_patient("P1", recommendation_at=TODAY - timedelta(days=3), marketing_opt_out=True)
    dto = to_profile_dto(compute_profile(patient, TODAY))
    assert (dto.overdue_days, dto.marketing_opt_out, dto.risk_level) == (3, True, "normal")


def test_a_laser_session_sets_the_d30_recommendation_once_so_a_doctor_edit_survives() -> None:
    """Buổi Laser đặt khuyến nghị D+30 đúng một lần, nên chỉnh sửa của bác sĩ được giữ."""
    patient = _laser_yesterday()
    refreshed, update = refresh_patient(patient)
    assert update is not None
    assert update.recommendation_at == TODAY - timedelta(days=1) + timedelta(days=30)
    assert (update.expected_visit_source, update.last_protocol_session_id) == ("service_protocol", "s-laser")
    assert refreshed.recommendation_at == update.recommendation_at

    edited = replace(refreshed, recommendation_at=date(2026, 12, 1))
    again, nothing = refresh_patient(edited)
    assert nothing is None
    assert again.recommendation_at == date(2026, 12, 1)

    plain = make_patient("P1", sessions=(session("s", TODAY),))
    assert refresh_patient(plain)[1] is None

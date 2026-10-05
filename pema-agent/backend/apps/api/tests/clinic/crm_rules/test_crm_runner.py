# new tests (orchestration of the ported engine; no JavaScript original)
"""One run of the rules over a clinic with the in-memory store and the fake scheduler.

What these pin: a run is idempotent (tasks AND jobs), jobs are only ever created through ``SchedulerPort`` (the
CRM has no channel and cannot send), a pending job is disabled when its task stops being valid, and a refusal of
the scheduler leaves the staff task in place.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta
from uuid import UUID, uuid4

from pema.clinic.crm_rules.records import ChannelTarget, ExistingTask, PatientSnapshot, TemplateRef
from pema.clinic.crm_rules.rules import DEFAULT_RULES, RuleConfig
from pema.clinic.crm_rules.runner import CrmRulesRunner
from pema.clinic.crm_rules.store import MemoryCrmRuleStore
from pema.clinic.crm_rules.testing import NOW, FakeScheduler, appointment, make_patient, session
from pema_contracts.crm import RuleKey, RuleSendMode, TaskStatus
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind, JobOrigin, ScheduledJob, ScheduleKind

CLINIC: UUID = uuid4()
TODAY = date(2026, 9, 20)
TARGET = ChannelTarget(account_id="acc-1", thread_id="thread-1")


def _rules(**modes: RuleSendMode) -> tuple[RuleConfig, ...]:
    return tuple(replace(r, send_mode=modes.get(r.key.value, r.send_mode)) for r in DEFAULT_RULES)


def _laser_patient(code: str = "P025", **fields: object) -> PatientSnapshot:
    base: dict[str, object] = {
        "last_visit": TODAY - timedelta(days=1),
        "sessions": (session("s-laser", TODAY - timedelta(days=1), "laser-co2"),),
        "total_sessions": 5,
        "completed_sessions": 1,
        "channel_target": TARGET,
        "messaging_consent": True,
    }
    return make_patient(code, **{**base, **fields})


def _runner(
    store: MemoryCrmRuleStore, scheduler: FakeScheduler, *, cap: int = 10, lateness: int = 1
) -> CrmRulesRunner:
    return CrmRulesRunner(store, scheduler, daily_cap=cap, max_lateness_days=lateness)


async def test_a_run_creates_the_tasks_and_a_rerun_creates_nothing() -> None:
    """Chạy một lần tạo đủ việc; chạy lại không tạo thêm việc hay job nào."""
    store = MemoryCrmRuleStore(
        rules=_rules(d1=RuleSendMode.AUTO_REMINDER),
        patients=[_laser_patient()],
        templates=[TemplateRef("crm.d1")],
    )
    scheduler = FakeScheduler()
    runner = _runner(store, scheduler)

    first = await runner.run_clinic(CLINIC, NOW)
    assert first.tasks_created == 3  # d1, d3, d7
    assert first.jobs_created == 1
    assert len(scheduler.jobs) == 1
    job = next(iter(scheduler.jobs.values()))
    assert (job.kind, job.payload, job.origin) == (JobKind.MESSAGE, "crm.d1", JobOrigin.CRM_RULE)
    assert job.patient_id is not None

    second = await runner.run_clinic(CLINIC, NOW)
    assert (second.tasks_created, second.tasks_superseded, second.patients_updated) == (0, 0, 0)
    assert second.jobs_created == 0
    assert second.jobs_already_scheduled == 1
    assert scheduler.create_calls == 1
    assert len(scheduler.jobs) == 1


async def test_the_first_run_applies_the_d30_recommendation_to_the_patient() -> None:
    """Lần chạy đầu ghi khuyến nghị D+30 cho hồ sơ và lần sau không ghi lại."""
    patient = _laser_patient()
    store = MemoryCrmRuleStore(patients=[patient])
    runner = _runner(store, FakeScheduler())
    first = await runner.run_clinic(CLINIC, NOW)
    stored = store.patients[patient.id]
    assert first.patients_updated == 1
    assert stored.recommendation_at == TODAY - timedelta(days=1) + timedelta(days=30)
    assert stored.last_protocol_session_id == "s-laser"
    assert (await runner.run_clinic(CLINIC, NOW)).patients_updated == 0


async def test_with_default_rules_the_run_only_creates_staff_tasks() -> None:
    """Với cấu hình mặc định, lần chạy chỉ tạo việc cho nhân viên và không đụng tới bộ lập lịch."""
    store = MemoryCrmRuleStore(patients=[_laser_patient()], templates=[TemplateRef("crm.d1")])
    scheduler = FakeScheduler()
    report = await _runner(store, scheduler).run_clinic(CLINIC, NOW)
    assert report.tasks_created > 0
    assert scheduler.create_calls == 0
    assert report.jobs_created == 0
    assert report.jobs_skipped == {}


async def test_a_booking_supersedes_the_task_and_disables_its_pending_job() -> None:
    """Đặt lịch làm việc cũ bị thay thế và tắt job đang chờ của nó."""
    old = TODAY - timedelta(days=95)
    patient = make_patient(
        "P031",
        last_visit=old,
        sessions=(session("c", old),),
        channel_target=TARGET,
        messaging_consent=True,
    )
    store = MemoryCrmRuleStore(
        rules=_rules(dormant90=RuleSendMode.AUTO_REMINDER),
        patients=[patient],
        templates=[TemplateRef("crm.dormant90", marketing=True)],
    )
    scheduler = FakeScheduler()
    runner = _runner(store, scheduler, lateness=30)
    assert (await runner.run_clinic(CLINIC, NOW)).jobs_created == 1
    assert len(scheduler.enabled()) == 1

    store.patients[patient.id] = replace(patient, appointments=(appointment("A", TODAY + timedelta(days=7)),))
    report = await runner.run_clinic(CLINIC, NOW)
    assert report.tasks_superseded == 1
    assert report.jobs_disabled == 1
    assert scheduler.enabled() == []


async def test_opting_out_disables_the_pending_marketing_job_and_keeps_the_clinical_task() -> None:
    """Từ chối nhận tin tắt job marketing đang chờ nhưng giữ việc lâm sàng."""
    old = TODAY - timedelta(days=95)
    patient = make_patient(
        "P031",
        last_visit=old,
        sessions=(session("c", old),),
        total_sessions=5,
        completed_sessions=2,
        channel_target=TARGET,
        messaging_consent=True,
    )
    store = MemoryCrmRuleStore(
        rules=_rules(dormant90=RuleSendMode.AUTO_REMINDER),
        patients=[patient],
        templates=[TemplateRef("crm.dormant90", marketing=True)],
    )
    scheduler = FakeScheduler()
    runner = _runner(store, scheduler, lateness=30)
    await runner.run_clinic(CLINIC, NOW)
    assert len(scheduler.enabled()) == 1

    store.patients[patient.id] = replace(patient, marketing_opt_out=True)
    report = await runner.run_clinic(CLINIC, NOW)
    assert report.jobs_disabled == 1
    assert scheduler.enabled() == []
    open_rules = {t.rule_key for t in store.tasks.values() if t.status is TaskStatus.OPEN}
    assert RuleKey.ABANDONED in open_rules
    assert RuleKey.DORMANT90 not in open_rules


async def test_a_task_staff_resolved_loses_its_pending_job() -> None:
    """Nhân viên xử lý xong việc thì job đang chờ của việc đó bị tắt."""
    store = MemoryCrmRuleStore(
        rules=_rules(d3=RuleSendMode.AUTO_REMINDER),
        patients=[_laser_patient()],
        templates=[TemplateRef("crm.d3")],
    )
    scheduler = FakeScheduler()
    runner = _runner(store, scheduler)
    await runner.run_clinic(CLINIC, NOW)
    assert len(scheduler.enabled()) == 1
    key = next(k for k in store.tasks if k.startswith("CRM:d3:"))
    store.tasks[key] = ExistingTask(key, RuleKey.D3, TaskStatus.RESOLVED)
    report = await runner.run_clinic(CLINIC, NOW)
    assert report.jobs_disabled == 1
    assert scheduler.enabled() == []


async def test_a_job_that_already_ran_is_never_touched() -> None:
    """Job đã chạy xong không bao giờ bị đụng tới."""
    store = MemoryCrmRuleStore(
        rules=_rules(d1=RuleSendMode.AUTO_REMINDER),
        patients=[_laser_patient()],
        templates=[TemplateRef("crm.d1")],
    )
    scheduler = FakeScheduler()
    runner = _runner(store, scheduler)
    await runner.run_clinic(CLINIC, NOW)
    job = next(iter(scheduler.jobs.values()))
    scheduler.seed(job.model_copy(update={"run_count": 1}))
    store.tasks[job.dedupe_key or ""] = ExistingTask(job.dedupe_key or "", RuleKey.D1, TaskStatus.RESOLVED)
    report = await runner.run_clinic(CLINIC, NOW)
    assert report.jobs_disabled == 0
    assert scheduler.jobs[job.id].enabled


async def test_a_scheduler_refusal_is_counted_and_the_staff_task_stays() -> None:
    """Bộ lập lịch từ chối thì chỉ đếm lại; việc nhân viên vẫn còn."""

    def refuse(job: CreateScheduledJobInput) -> DomainError | None:
        return DomainError(ErrorCode.POLICY_DENIED, "Chính sách không cho phép.")

    store = MemoryCrmRuleStore(
        rules=_rules(d1=RuleSendMode.AUTO_REMINDER),
        patients=[_laser_patient()],
        templates=[TemplateRef("crm.d1")],
    )
    scheduler = FakeScheduler(refuse=refuse)
    report = await _runner(store, scheduler).run_clinic(CLINIC, NOW)
    assert report.jobs_failed == {"policy_denied": 1}
    assert report.jobs_created == 0
    assert any(k.startswith("CRM:d1:") for k in store.tasks)


async def test_jobs_of_other_origins_count_against_the_patients_daily_cap() -> None:
    """Job do nguồn khác (công cụ agent, nhân viên) cũng tính vào trần ngày của bệnh nhân."""
    patient = _laser_patient()
    store = MemoryCrmRuleStore(
        rules=_rules(d1=RuleSendMode.AUTO_REMINDER),
        patients=[patient],
        templates=[TemplateRef("crm.d1")],
    )
    scheduler = FakeScheduler()
    scheduler.seed(
        ScheduledJob(
            id="manual-1",
            clinic_id=CLINIC,
            account_id="acc-1",
            thread_id="thread-1",
            thread_type=0,
            name="by staff",
            kind=JobKind.MESSAGE,
            payload="crm.other",
            schedule_kind=ScheduleKind.ONCE,
            next_run_at="2026-09-20T05:00:00.000Z",
            max_runs=1,
            patient_id=patient.id,
            origin=JobOrigin.STAFF,
        )
    )
    report = await _runner(store, scheduler, cap=1).run_clinic(CLINIC, NOW)
    assert report.jobs_created == 0
    assert report.jobs_skipped == {"daily_cap": 1}


async def test_the_birthday_task_is_created_but_never_a_job() -> None:
    """Sinh nhật chỉ tạo việc thủ công, không bao giờ tạo job gửi tin."""
    patient = make_patient(
        "P032",
        birth_date=date(1996, 9, 23),
        channel_target=TARGET,
        messaging_consent=True,
        marketing_opt_out=False,
    )
    store = MemoryCrmRuleStore(
        rules=_rules(birthday=RuleSendMode.AUTO_REMINDER),
        patients=[patient],
        templates=[TemplateRef("crm.birthday", marketing=True)],
    )
    scheduler = FakeScheduler()
    report = await _runner(store, scheduler).run_clinic(CLINIC, NOW)
    assert any(k.startswith("CRM:birthday:") for k in store.tasks)
    assert scheduler.create_calls == 0
    assert report.jobs_skipped == {"birthday_never_auto": 1}

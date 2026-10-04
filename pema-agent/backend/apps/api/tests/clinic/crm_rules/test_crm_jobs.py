# new tests (no JavaScript original: crm-automation.js never sent anything)
"""Policy that turns CRM tasks into scheduler jobs: which task MAY also become an automatic message.

Pure tests of ``pema.clinic.crm_rules.jobs.plan_jobs``. The safety rules of AGENT.md and PLAN-AI01 section 5 are
each pinned by one test: birthday never automatic, ``marketing_opt_out`` blocks marketing, a message job carries
an approved template key (never free text), an agent job only drafts and only under a review profile.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from pema.clinic.crm_rules.engine import run_rules
from pema.clinic.crm_rules.jobs import (
    JobPlan,
    JobSkipReason,
    PendingJob,
    plan_jobs,
    scope_key_for,
)
from pema.clinic.crm_rules.records import ChannelTarget, PatientSnapshot, TaskCandidate, TemplateRef
from pema.clinic.crm_rules.rules import DEFAULT_RULES, RuleConfig
from pema.clinic.crm_rules.testing import NOW, make_patient, session
from pema_contracts.common import VN_TZ
from pema_contracts.crm import RuleKey, RuleSendMode, TaskPriority
from pema_contracts.policy import PolicyProfileKey, ProactiveCapScope
from pema_contracts.scheduler import JobKind, JobOrigin, OnceSchedule

CLINIC = uuid4()
TODAY = date(2026, 9, 20)
TARGET = ChannelTarget(account_id="acc-1", thread_id="thread-1", thread_type=0)


def _patient(code: str = "P025", **fields: object) -> PatientSnapshot:
    """A patient with a Laser CO2 session yesterday, a verified channel and a messaging consent."""
    base: dict[str, object] = {
        "last_visit": TODAY - timedelta(days=1),
        "sessions": (session("s-laser", TODAY - timedelta(days=1), "laser-co2"),),
        "total_sessions": 5,
        "completed_sessions": 1,
        "channel_target": TARGET,
        "messaging_consent": True,
    }
    return make_patient(code, **{**base, **fields})


def _rules(**modes: RuleSendMode) -> dict[RuleKey, RuleConfig]:
    return {r.key: replace(r, send_mode=modes.get(r.key.value, r.send_mode)) for r in DEFAULT_RULES}


def _candidates(patients: list[PatientSnapshot], rules: dict[RuleKey, RuleConfig]) -> list[TaskCandidate]:
    return list(run_rules(patients, list(rules.values()), [], NOW).candidates)


def _plan(
    patients: list[PatientSnapshot],
    rules: dict[RuleKey, RuleConfig],
    *,
    templates: dict[str, TemplateRef] | None = None,
    pending: list[PendingJob] | None = None,
    settled: set[str] | None = None,
    cap: int = 10,
    lateness: int = 1,
    candidates: list[TaskCandidate] | None = None,
) -> JobPlan:
    return plan_jobs(
        candidates if candidates is not None else _candidates(patients, rules),
        clinic_id=CLINIC,
        rules=rules,
        patients={p.id: p for p in patients},
        templates=templates if templates is not None else {"crm.d1": TemplateRef("crm.d1")},
        pending=pending or [],
        settled_task_keys=settled or set(),
        now=NOW,
        daily_cap=cap,
        max_lateness_days=lateness,
    )


def _candidate(
    patient: PatientSnapshot, key: str, priority: TaskPriority, rule: RuleKey = RuleKey.D1
) -> TaskCandidate:
    return TaskCandidate(
        task_key=f"CRM:{rule.value}:{patient.code}:{key}",
        patient_id=patient.id,
        patient_code=patient.code,
        rule_key=rule,
        reason="r",
        priority=priority,
        created_at=NOW,
        due_at=datetime(2026, 9, 20, 9, 0, tzinfo=VN_TZ),
        owner_user_id=None,
        suggested_action="a",
        source_event_id=key,
    )


def test_a_staff_task_rule_never_creates_a_job() -> None:
    """Quy tắc ở chế độ việc nhân viên (mặc định) không bao giờ tạo job."""
    plan = _plan([_patient()], _rules())
    assert plan.planned == ()
    assert plan.skipped == ()
    assert plan.already_scheduled == ()


def test_auto_reminder_creates_a_message_job_whose_payload_is_the_approved_template_key() -> None:
    """Nhắc tự động tạo job tin nhắn, nội dung là khoá mẫu đã duyệt chứ không phải văn bản tự do."""
    patient = _patient()
    plan = _plan([patient], _rules(d1=RuleSendMode.AUTO_REMINDER))
    assert len(plan.planned) == 1
    job = plan.planned[0].job
    assert job.kind is JobKind.MESSAGE
    assert job.payload == "crm.d1"
    assert (job.account_id, job.thread_id, job.thread_type) == ("acc-1", "thread-1", 0)
    assert job.origin is JobOrigin.CRM_RULE
    assert job.dedupe_key == plan.planned[0].task_key == f"CRM:d1:{patient.code}:s-laser"
    assert job.patient_id == patient.id
    assert job.max_runs == 1
    assert isinstance(job.schedule, OnceSchedule)
    assert job.schedule.run_at_utc == "2026-09-20T02:00:00.000Z"
    assert "Hỏi tình trạng" not in job.payload


def test_a_job_never_runs_before_now_and_waits_for_a_future_due_date() -> None:
    """Job không chạy trước hiện tại và chờ đến ngày hẹn nếu việc chưa đến hạn."""
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER, d3=RuleSendMode.AUTO_REMINDER)
    templates = {"crm.d1": TemplateRef("crm.d1"), "crm.d3": TemplateRef("crm.d3")}
    plan = _plan([_patient()], rules, templates=templates)
    runs = {p.job.payload: p.job.schedule for p in plan.planned if isinstance(p.job.schedule, OnceSchedule)}
    assert runs["crm.d1"].run_at_utc == "2026-09-20T02:00:00.000Z"
    assert runs["crm.d3"].run_at_utc == "2026-09-22T02:00:00.000Z"


def test_draft_for_review_creates_an_agent_job_only_under_a_review_profile() -> None:
    """Soạn nháp chỉ tạo job agent khi hồ sơ chính sách bắt duyệt trước khi gửi."""
    rules = _rules(d1=RuleSendMode.DRAFT_FOR_REVIEW)
    review = _plan([_patient()], rules)
    assert [p.job.kind for p in review.planned] == [JobKind.AGENT]
    instruction = review.planned[0].job.payload
    assert "NHÁP" in instruction
    assert "chẩn đoán" in instruction
    assert "P025" not in instruction

    direct = replace(TARGET, policy_profile=PolicyProfileKey.STAFF_ASSISTANT)
    plan = _plan([_patient(channel_target=direct)], rules)
    assert plan.planned == ()
    assert [s.reason for s in plan.skipped] == [JobSkipReason.REVIEW_NOT_AVAILABLE]


def test_birthday_is_never_automatic_even_when_a_rule_is_forced_to_auto() -> None:
    """Sinh nhật không bao giờ tự gửi, kể cả khi cấu hình bị ép sang chế độ tự động."""
    rules = _rules(birthday=RuleSendMode.AUTO_REMINDER)
    patient = _patient(birth_date=date(1990, 9, 22))
    plan = _plan([patient], rules, templates={"crm.birthday": TemplateRef("crm.birthday")})
    assert [p for p in plan.planned if p.job.payload == "crm.birthday"] == []
    assert [s.reason for s in plan.skipped] == [JobSkipReason.BIRTHDAY_NEVER_AUTO]
    candidates = _candidates([patient], rules)
    assert [c.rule_key for c in candidates if c.rule_key is RuleKey.BIRTHDAY] == [RuleKey.BIRTHDAY]


def test_marketing_opt_out_stops_the_marketing_rule_but_keeps_the_safety_task() -> None:
    """Từ chối nhận tin chặn quy tắc marketing; việc chăm sóc an toàn vẫn còn."""
    old = TODAY - timedelta(days=95)
    patient = _patient(
        last_visit=old,
        sessions=(session("c", old),),
        total_sessions=5,
        completed_sessions=2,
        marketing_opt_out=True,
    )
    rules = _rules(dormant90=RuleSendMode.AUTO_REMINDER)
    templates = {"crm.dormant90": TemplateRef("crm.dormant90", marketing=True)}
    assert {c.rule_key for c in _candidates([patient], rules)} == {RuleKey.ABANDONED}
    assert _plan([patient], rules, templates=templates, lateness=30).planned == ()

    opted_in = replace(patient, marketing_opt_out=False)
    plan = _plan([opted_in], rules, templates=templates, lateness=30)
    assert [p.job.payload for p in plan.planned] == ["crm.dormant90"]


def test_a_marketing_template_on_a_clinical_rule_is_blocked_by_opt_out() -> None:
    """Mẫu marketing gắn vào quy tắc lâm sàng vẫn bị chặn khi bệnh nhân từ chối nhận tin."""
    patient = _patient(marketing_opt_out=True)
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER)
    templates = {"crm.d1": TemplateRef("crm.d1", marketing=True)}
    plan = _plan([patient], rules, templates=templates)
    assert plan.planned == ()
    assert [s.reason for s in plan.skipped] == [JobSkipReason.MARKETING_OPT_OUT]
    assert [c.rule_key for c in _candidates([patient], rules) if c.rule_key is RuleKey.D1] == [RuleKey.D1]


def test_no_verified_channel_no_consent_or_no_approved_template_means_staff_task_only() -> None:
    """Thiếu kênh đã xác minh, đồng ý nhận tin hoặc mẫu đã duyệt thì chỉ còn việc cho nhân viên."""
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER)
    no_channel = _plan([_patient(channel_target=None)], rules)
    no_consent = _plan([_patient(messaging_consent=False)], rules)
    no_template = _plan([_patient()], rules, templates={})
    assert [s.reason for s in no_channel.skipped] == [JobSkipReason.NO_CHANNEL]
    assert [s.reason for s in no_consent.skipped] == [JobSkipReason.NO_CONSENT]
    assert [s.reason for s in no_template.skipped] == [JobSkipReason.NO_TEMPLATE]
    assert no_channel.planned == no_consent.planned == no_template.planned == ()


def test_a_task_due_long_ago_is_left_to_staff() -> None:
    """Việc đến hạn đã lâu để nhân viên xử lý, không phát lại hàng loạt nhắc trễ."""
    patient = _patient()
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER)
    stale = _candidate(patient, "old", TaskPriority.HIGH)
    stale = replace(stale, due_at=datetime(2026, 9, 17, 9, 0, tzinfo=VN_TZ))
    yesterday = replace(
        _candidate(patient, "y", TaskPriority.HIGH), due_at=datetime(2026, 9, 19, 9, 0, tzinfo=VN_TZ)
    )
    plan = _plan([patient], rules, candidates=[stale, yesterday])
    assert [p.task_key for p in plan.planned] == [yesterday.task_key]
    assert [s.reason for s in plan.skipped] == [JobSkipReason.STALE]
    late = plan.planned[0].job.schedule
    assert isinstance(late, OnceSchedule)
    assert late.run_at_utc == "2026-09-20T02:00:00.000Z"


def test_the_daily_cap_is_per_patient_and_account_and_keeps_the_most_urgent_first() -> None:
    """Trần trong ngày tính theo bệnh nhân + tài khoản; việc khẩn đi trước."""
    patient = _patient()
    other = _patient("P026", sessions=(session("s2", TODAY - timedelta(days=1), "laser-co2"),))
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER)
    candidates = [
        _candidate(patient, "low", TaskPriority.LOW),
        _candidate(patient, "high", TaskPriority.HIGH),
        _candidate(patient, "normal", TaskPriority.NORMAL),
        _candidate(other, "only", TaskPriority.LOW),
    ]
    plan = _plan([patient, other], rules, cap=2, candidates=candidates)
    assert [p.task_key for p in plan.planned] == [
        f"CRM:d1:{patient.code}:high",
        f"CRM:d1:{patient.code}:normal",
        f"CRM:d1:{other.code}:only",
    ]
    assert [(s.task_key, s.reason) for s in plan.skipped] == [
        (f"CRM:d1:{patient.code}:low", JobSkipReason.DAILY_CAP)
    ]


def test_jobs_already_pending_count_against_the_cap_and_are_never_planned_twice() -> None:
    """Job đang chờ tính vào trần ngày và không bao giờ được lên lịch lần hai."""
    patient = _patient()
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER)
    scope = scope_key_for(ProactiveCapScope.PATIENT_ACCOUNT, patient.id, "acc-1", "thread-1")
    other_origin = PendingJob(dedupe_key=None, scope_key=scope, run_day=TODAY)
    existing = PendingJob(dedupe_key=f"CRM:d1:{patient.code}:there", scope_key=scope, run_day=TODAY)
    here = _candidate(patient, "there", TaskPriority.HIGH)
    new = _candidate(patient, "new", TaskPriority.NORMAL)
    plan = _plan([patient], rules, pending=[other_origin, existing], cap=3, candidates=[here, new])
    assert plan.already_scheduled == (here.task_key,)
    assert [p.task_key for p in plan.planned] == [new.task_key]
    full = _plan([patient], rules, pending=[other_origin, existing], cap=2, candidates=[here, new])
    assert full.already_scheduled == (here.task_key,)
    assert [s.reason for s in full.skipped] == [JobSkipReason.DAILY_CAP]


def test_settled_tasks_get_no_job_and_are_not_desired() -> None:
    """Việc đã xử lý hoặc đã bị thay thế không có job, nên job đang chờ của nó sẽ bị tắt."""
    patient = _patient()
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER)
    candidate = _candidate(patient, "done", TaskPriority.HIGH)
    plan = _plan([patient], rules, settled={candidate.task_key}, candidates=[candidate])
    assert plan.planned == ()
    assert candidate.task_key not in plan.desired_keys
    live = _plan([patient], rules, candidates=[candidate])
    assert live.desired_keys == {candidate.task_key}


def test_the_cap_key_follows_the_policy_profile() -> None:
    """Khoá trần theo hồ sơ chính sách: theo bệnh nhân + tài khoản hoặc theo tài khoản + cuộc trò chuyện."""
    patient_id = UUID(int=7)
    assert scope_key_for(ProactiveCapScope.PATIENT_ACCOUNT, patient_id, "acc", "thr") == f"{patient_id}:acc"
    assert scope_key_for(ProactiveCapScope.ACCOUNT_THREAD, patient_id, "acc", "thr") == "acc:thr"
    assert scope_key_for(ProactiveCapScope.PATIENT_ACCOUNT, None, "acc", "thr") == "acc:thr"


def test_an_unapproved_template_is_not_in_the_catalogue_so_no_job_is_planned() -> None:
    """Mẫu chưa được bác sĩ duyệt không có trong danh mục, nên không có job nào được lên lịch."""
    rules = _rules(d1=RuleSendMode.AUTO_REMINDER)
    plan = _plan([_patient()], rules, templates={"crm.other": TemplateRef("crm.other")})
    assert plan.planned == ()
    assert [s.reason for s in plan.skipped] == [JobSkipReason.NO_TEMPLATE]

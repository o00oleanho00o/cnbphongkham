"""Policy behaviour of the scheduler (new tests, no zalo-agent source): the ``patient_channel`` profile and the
``PolicyHooks`` of package P (PLAN-AI01 section 5, CONTRACTS section 3).

What is proved here:

* under ``patient_channel`` NOTHING proactive leaves the system without a human decision: an ``agent`` job only
  DRAFTS, a ``message`` job sends the doctor-approved TEMPLATE body, and both end in a ``review_item`` - even when
  the injected hooks are the permissive default (clinic safety does not wait for package P to be wired);
* a held draft consumes neither a cap slot nor the notice, and the same occurrence never creates two items;
* ``check_job`` ``deny`` / ``downgrade_to_draft`` and ``on_outbound`` ``drop`` / ``hold_for_review`` are obeyed
  under ``staff_assistant`` too (P can tighten a profile that is otherwise direct);
* marketing templates respect ``marketingOptOut`` at send time, not only at creation.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import pytest

from pema.scheduler.run_scheduled_job import RunScheduledJobOptions, run_scheduled_job
from pema.scheduler.store import PgSchedulerStore
from pema.scheduler.testing_env import ACC, Env
from pema_contracts.channel import InboundMessage
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import (
    JobAction,
    JobDecision,
    OutboundAction,
    OutboundDecision,
    OutboundOrigin,
    PermissivePolicyHooks,
    PolicyContext,
    PolicyProfileKey,
)
from pema_contracts.review import ReviewKind, ReviewOrigin
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    EverySchedule,
    JobKind,
    JobOrigin,
    JobRunStatus,
    OnceSchedule,
    ScheduledJob,
)

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
PATIENT = PolicyProfileKey.PATIENT_CHANNEL
THREAD = "t-patient"


async def run(env: Env, job: ScheduledJob) -> None:
    await run_scheduled_job(
        env.deps,
        job,
        RunScheduledJobOptions(late=False, scheduled_for=job.next_run_at or "", now=datetime.now(UTC)),
    )


async def last_run(env: Env, job_id: str):
    return (await env.deps.runs.list_runs(env.clinic_id, job_id, 1))[0]


# ============================================================================== patient_channel


async def test_patient_channel_agent_job_only_drafts_it_never_sends_and_takes_no_cap_slot(
    make_env: EnvMaker,
) -> None:
    """patient_channel: kind agent chỉ soạn nháp -> review_item followup_draft, không gửi, không tốn suất trần"""
    env = make_env(PATIENT)
    env.engine.script = ["Chị nhớ tái khám sau 1 tuần nhé ạ."]
    patient_id = env.add_patient("P025")
    job = await env.make_job(
        thread_id=THREAD, kind=JobKind.AGENT, payload="Nhắc tái khám", patient_id=patient_id
    )

    await run(env, job)

    assert env.channel.sent == [], "patient_channel không bao giờ tự gửi"
    assert env.history.messages == [], "tin chưa gửi thì không được ghi vào history"
    assert len(env.actions.items) == 1
    item = next(iter(env.actions.items.values()))
    assert item.kind is ReviewKind.FOLLOWUP_DRAFT
    assert item.origin is ReviewOrigin.SCHEDULED_AGENT
    assert item.draft_text == "Chị nhớ tái khám sau 1 tuần nhé ạ."
    assert item.patient_ref == "P025", "chỉ mã bệnh nhân, không tên/SĐT"
    assert item.payload is not None
    assert item.payload["job_id"] == job.id
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.OK
    assert "chờ duyệt" in run_row.detail
    assert env.row("SELECT count(*) FROM agent.proactive_send_counters WHERE clinic_id = :c") == (0,)
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.run_count == 1, "bản nháp đã giao cho người duyệt: lượt này đã chạy xong"


async def test_patient_channel_message_job_sends_the_approved_template_body_as_a_draft(
    make_env: EnvMaker,
) -> None:
    """patient_channel: kind message lấy THÂN MẪU đã duyệt (payload là khoá mẫu) và cũng chỉ thành bản nháp"""
    env = make_env(PATIENT)
    env.add_template("followup-d1", "Chào chị, hôm qua chị đã làm thủ thuật, chị thấy thế nào ạ?")
    job = await env.make_job(thread_id=THREAD, payload="followup-d1", origin=JobOrigin.CRM_RULE)

    await run(env, job)

    assert env.channel.sent == []
    item = next(iter(env.actions.items.values()))
    assert item.draft_text == "Chào chị, hôm qua chị đã làm thủ thuật, chị thấy thế nào ạ?"
    assert item.origin is ReviewOrigin.CRM_RULE
    assert item.payload is not None
    assert item.payload["template_key"] == "followup-d1"
    assert (await last_run(env, job.id)).status is JobRunStatus.OK


async def test_patient_channel_message_job_with_an_unapproved_or_unknown_template_is_blocked_and_keeps_the_slot(
    make_env: EnvMaker,
) -> None:
    """patient_channel: mẫu chưa được bác sĩ duyệt/không tồn tại -> chặn, giữ suất chạy (chưa gửi thì chưa chạy)"""
    env = make_env(PATIENT)
    env.add_template("chua-duyet", "Nội dung chờ bác sĩ ký", approved=False)
    unapproved = await env.make_job(thread_id=THREAD, payload="chua-duyet")
    unknown = await env.make_job(thread_id=THREAD, payload="khong-co-mau-nay")

    for job in (unapproved, unknown):
        await run(env, job)
        run_row = await last_run(env, job.id)
        assert run_row.status is JobRunStatus.SKIPPED
        assert "bác sĩ duyệt" in run_row.detail
        after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
        assert after is not None
        assert after.run_count == 0
        assert after.enabled is True
        assert after.next_run_at == job.next_run_at

    assert env.actions.items == {}
    assert env.channel.sent == []


async def test_patient_channel_marketing_template_is_skipped_for_a_patient_who_opted_out(
    make_env: EnvMaker,
) -> None:
    """patient_channel: mẫu tiếp thị + bệnh nhân marketingOptOut -> bỏ lượt (đã tiêu suất), không tạo nháp"""
    env = make_env(PATIENT)
    env.add_template("khuyen-mai-thang-9", "Ưu đãi tháng 9 dành cho chị", marketing=True)
    patient_id = env.add_patient("P026", marketing_opt_out=True)
    job = await env.make_job(thread_id=THREAD, payload="khuyen-mai-thang-9", patient_id=patient_id)

    await run(env, job)

    assert env.actions.items == {}
    assert env.channel.sent == []
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert "từ chối tin tiếp thị" in run_row.detail
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.run_count == 1, "quyết định chính sách đã được áp dụng: lượt này không lặp lại mỗi tick"
    assert after.enabled is False


async def test_patient_channel_marketing_template_for_a_patient_who_did_not_opt_out_becomes_a_draft(
    make_env: EnvMaker,
) -> None:
    """patient_channel: mẫu tiếp thị + bệnh nhân KHÔNG từ chối -> vẫn chỉ thành bản nháp chờ duyệt"""
    env = make_env(PATIENT)
    env.add_template("khuyen-mai-thang-9", "Ưu đãi tháng 9 dành cho chị", marketing=True)
    patient_id = env.add_patient("P027")
    job = await env.make_job(thread_id=THREAD, payload="khuyen-mai-thang-9", patient_id=patient_id)

    await run(env, job)

    assert len(env.actions.items) == 1
    assert env.channel.sent == []


async def test_patient_channel_the_same_occurrence_never_creates_two_review_items(make_env: EnvMaker) -> None:
    """patient_channel: chạy lại CÙNG một lượt (retry) trả về cùng mục duyệt - khoá idempotency theo job@mốc"""
    env = make_env(PATIENT)
    env.add_template("followup-d3", "Chào chị, chị thấy vùng điều trị thế nào rồi ạ?")
    job = await env.make_job(thread_id=THREAD, payload="followup-d3")

    await run(env, job)
    await run(env, job)

    assert len(env.actions.items) == 1
    assert next(iter(env.actions.items)) == f"{job.id}@{job.next_run_at}"


async def test_patient_channel_a_failing_review_service_counts_as_not_handled_and_retries(
    make_env: EnvMaker,
) -> None:
    """patient_channel: không tạo được mục duyệt = chưa xử lý: đếm delivery_attempts, KHÔNG mark_run"""
    env = make_env(PATIENT)
    env.add_template("followup-d7", "Chào chị, chị cần hỗ trợ gì thêm không ạ?")
    env.actions.fail = True
    job = await env.make_job(thread_id=THREAD, payload="followup-d7")

    await run(env, job)

    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.run_count == 0
    assert after.delivery_attempts == 1
    assert after.next_run_at == job.next_run_at, "once được phục hồi mốc để tick sau thử lại"
    assert "Không tạo được mục chờ duyệt" in (await last_run(env, job.id)).detail


async def test_patient_channel_does_not_send_the_daily_cap_notice_to_a_patient(make_env: EnvMaker) -> None:
    """patient_channel: không bao giờ tự nhắn 'đã đủ trần' cho bệnh nhân (mọi tin chủ động đều qua người duyệt)"""
    env = make_env(PATIENT, tuning={"SCHEDULER_MAX_PROACTIVE_PER_DAY": 1})
    env.add_template("followup-d1", "Chào chị")
    job = await env.make_job(thread_id=THREAD, payload="followup-d1", schedule=EverySchedule(minutes=30))
    await env.deps.guard.record_proactive_send(
        env.clinic_id, f"{ACC}:{THREAD}", "Asia/Ho_Chi_Minh", 1, datetime.now(UTC)
    )

    await run(env, job)

    assert env.channel.sent == []
    assert len(env.actions.items) == 1


# ============================================================================== hooks under staff_assistant


class DenyHooks(PermissivePolicyHooks):
    async def check_job(self, ctx: PolicyContext, job: CreateScheduledJobInput) -> JobDecision:
        return JobDecision(action=JobAction.DENY, reason="Không được phép tạo lịch này.")


class DowngradeHooks(PermissivePolicyHooks):
    async def check_job(self, ctx: PolicyContext, job: CreateScheduledJobInput) -> JobDecision:
        return JobDecision(action=JobAction.DOWNGRADE_TO_DRAFT, reason="policy:draft")


class OutboundHooks(PermissivePolicyHooks):
    def __init__(self, action: OutboundAction, reason: str | None = None) -> None:
        self.action = action
        self.reason = reason
        self.seen: list[tuple[OutboundOrigin, bool]] = []

    async def on_outbound(
        self, ctx: PolicyContext, text: str, *, proactive: bool, origin: OutboundOrigin
    ) -> OutboundDecision:
        self.seen.append((origin, proactive))
        return OutboundDecision(action=self.action, reason=self.reason)

    async def before_llm(self, ctx: PolicyContext, batch: Sequence[InboundMessage]):
        return await super().before_llm(ctx, batch)


async def test_staff_assistant_check_job_deny_at_run_time_skips_and_spends_the_slot(
    make_env: EnvMaker,
) -> None:
    """check_job = deny lúc chạy: bỏ lượt, tiêu suất (quyết định chính sách không lặp lại mỗi tick), không gửi"""
    env = make_env(hooks=DenyHooks())
    job = await env.make_job(thread_id=THREAD, payload="Nhắc")

    await run(env, job)

    assert env.channel.sent == []
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert run_row.detail == "Không được phép tạo lịch này."
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.run_count == 1


async def test_staff_assistant_check_job_downgrade_to_draft_turns_the_output_into_a_review_item(
    make_env: EnvMaker,
) -> None:
    """check_job = downgrade_to_draft: lượt vẫn chạy nhưng đầu ra thành review item, không gửi (kể cả staff_assistant)"""
    env = make_env(hooks=DowngradeHooks())
    env.engine.script = ["Nội dung nháp"]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Báo cáo")

    await run(env, job)

    assert env.channel.sent == []
    item = next(iter(env.actions.items.values()))
    assert item.draft_text == "Nội dung nháp"
    assert item.payload is not None
    assert item.payload["policy_reason"] == "policy:draft"


@pytest.mark.parametrize("origin_kind", [JobKind.MESSAGE, JobKind.AGENT])
async def test_staff_assistant_on_outbound_drop_concludes_skipped_and_sends_nothing(
    make_env: EnvMaker, origin_kind: JobKind
) -> None:
    """on_outbound = drop: không gửi, run 'skipped' kèm lý do, đã tiêu suất"""
    hooks = OutboundHooks(OutboundAction.DROP, "marketing_opt_out")
    env = make_env(hooks=hooks)
    env.engine.script = ["Nội dung"]
    job = await env.make_job(thread_id=THREAD, kind=origin_kind, payload="Nhắc")

    await run(env, job)

    assert env.channel.sent == []
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert run_row.detail == "marketing_opt_out"
    expected = (
        OutboundOrigin.SCHEDULED_AGENT if origin_kind is JobKind.AGENT else OutboundOrigin.SCHEDULED_MESSAGE
    )
    assert hooks.seen == [(expected, True)], "on_outbound được gọi với proactive=True và đúng nguồn"


async def test_staff_assistant_on_outbound_hold_for_review_creates_a_review_item(make_env: EnvMaker) -> None:
    """on_outbound = hold_for_review: thành review item, không gửi"""
    env = make_env(hooks=OutboundHooks(OutboundAction.HOLD_FOR_REVIEW))
    job = await env.make_job(thread_id=THREAD, payload="Nhắc uống thuốc")

    await run(env, job)

    assert env.channel.sent == []
    assert len(env.actions.items) == 1
    assert env.row("SELECT count(*) FROM agent.proactive_send_counters WHERE clinic_id = :c") == (0,)


async def test_staff_assistant_default_permissive_hooks_still_send_directly_like_the_original(
    make_env: EnvMaker,
) -> None:
    """staff_assistant + hook mặc định: gửi thẳng như zalo-agent gốc (không có gì bị giữ lại)"""
    env = make_env()
    job = await env.make_job(thread_id=THREAD, payload="Nhắc uống thuốc")

    await run(env, job)

    assert [p.text for p in env.channel.sent] == ["Nhắc uống thuốc"]
    assert env.actions.items == {}


# ================================================================================ SchedulerPort.create_job


async def test_scheduler_port_create_job_is_denied_by_the_policy_hook_with_policy_denied(
    make_env: EnvMaker,
) -> None:
    """SchedulerPort.create_job: check_job = deny -> DomainError(policy_denied), không ghi gì"""
    env = make_env(hooks=DenyHooks())
    port = PgSchedulerStore(env.deps)

    with pytest.raises(DomainError) as caught:
        await port.create_job(_create_input(env))

    assert caught.value.code is ErrorCode.POLICY_DENIED
    assert env.row("SELECT count(*) FROM agent.jobs WHERE clinic_id = :c") == (0,)


async def test_scheduler_port_create_job_dedupe_key_makes_the_crm_rule_idempotent(make_env: EnvMaker) -> None:
    """SchedulerPort.create_job: B2 gọi lại với cùng dedupe_key (rule + bệnh nhân + sự kiện nguồn) -> cùng một job"""
    env = make_env(PATIENT)
    env.make_thread(THREAD)
    port = PgSchedulerStore(env.deps)

    first = await port.create_job(_create_input(env, dedupe_key="d1:P025:visit-9"))
    second = await port.create_job(_create_input(env, dedupe_key="d1:P025:visit-9"))

    assert second.id == first.id
    assert len(await port.list_jobs(env.clinic_id)) == 1
    assert len(await port.list_jobs(env.clinic_id, ACC)) == 1
    assert await port.list_jobs(env.clinic_id, "acc-khac") == []
    assert (await port.get_job(env.clinic_id, ACC, THREAD, first.id)) is not None
    assert (await port.get_job(env.clinic_id, ACC, "t-khac", first.id)) is None
    assert (await port.list_jobs_for_thread(env.clinic_id, ACC, THREAD))[0].id == first.id


async def test_scheduler_port_create_job_for_an_unknown_account_is_not_found(make_env: EnvMaker) -> None:
    """SchedulerPort.create_job: account không tồn tại -> not_found"""
    env = make_env()
    port = PgSchedulerStore(env.deps)
    with pytest.raises(DomainError) as caught:
        await port.create_job(_create_input(env, account_id="acc-khong-co"))
    assert caught.value.code is ErrorCode.NOT_FOUND


async def test_scheduler_port_run_trial_under_patient_channel_ends_in_a_review_draft_not_a_send(
    make_env: EnvMaker,
) -> None:
    """SchedulerPort.run_trial: dưới patient_channel chạy thử chỉ có thể ra bản nháp, không bao giờ gửi thật"""
    env = make_env(PATIENT)
    env.add_template("followup-d1", "Chào chị")
    job = await env.make_job(
        thread_id=THREAD, payload="followup-d1", schedule=OnceSchedule(run_at_utc="2099-01-01T00:00:00.000Z")
    )
    port = PgSchedulerStore(env.deps)

    record = await port.run_trial(env.clinic_id, job.id)

    assert record.status is JobRunStatus.OK
    assert env.channel.sent == []
    assert len(env.actions.items) == 1
    assert next(iter(env.actions.items)).endswith(f"#trial{record.id}"), (
        "bản nháp của lần chạy thử không chiếm khoá của lượt thật"
    )
    assert uuid.UUID(str(env.clinic_id))


def _create_input(
    env: Env, *, dedupe_key: str | None = None, account_id: str = ACC
) -> CreateScheduledJobInput:
    return CreateScheduledJobInput(
        clinic_id=env.clinic_id,
        account_id=account_id,
        thread_id=THREAD,
        thread_type=0,
        name="Nhắc tái khám",
        kind=JobKind.MESSAGE,
        payload="followup-d1",
        schedule=OnceSchedule(run_at_utc="2099-01-01T00:00:00.000Z"),
        created_by="rule-d1",
        dedupe_key=dedupe_key,
        origin=JobOrigin.CRM_RULE,
    )


async def test_scheduler_port_b2_can_find_and_switch_off_a_job_by_its_dedupe_key(make_env: EnvMaker) -> None:
    """SchedulerPort: B2 tìm/tắt job theo dedupe_key (việc xong, bị thay thế, opt-out, template bị thu hồi)"""
    env = make_env(PATIENT)
    env.make_thread(THREAD)
    port = PgSchedulerStore(env.deps)
    job = await port.create_job(_create_input(env, dedupe_key="d3:P025:visit-9"))

    found = await port.get_job_by_dedupe_key(env.clinic_id, "d3:P025:visit-9")
    assert found is not None
    assert found.id == job.id
    assert await port.get_job_by_dedupe_key(env.clinic_id, "khong-co") is None

    assert await port.set_enabled_by_dedupe_key(env.clinic_id, "d3:P025:visit-9", False) is True
    off = await port.get_job_by_dedupe_key(env.clinic_id, "d3:P025:visit-9")
    assert off is not None
    assert off.enabled is False
    assert [
        j.id for j in await env.deps.jobs.list_due_jobs(env.clinic_id, datetime(2100, 1, 1, tzinfo=UTC))
    ] == []
    assert await port.set_enabled_by_dedupe_key(env.clinic_id, "khong-co", False) is False

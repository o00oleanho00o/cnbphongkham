# ported from: src/scheduler/run-scheduled-job-trial.test.ts
"""The race fixed in review round 2: "Run now" must CLAIM the job (next_run_at=NULL) before dispatching, the same
clear-before-dispatch as the tick - otherwise a REAL tick in between (a ``kind='agent'`` job calling an LLM easily
runs longer than ``SCHEDULER_TICK_MS``) would dispatch for real once more, then the restore of the trial would wipe
its progress and the next tick would send a DUPLICATE real message.

SAFETY: the channel is ALWAYS a fake - it never touches a real network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from pema.scheduler.run_scheduled_job_trial import run_scheduled_job_trial
from pema.scheduler.scheduler_loop import SchedulerLoop
from pema.scheduler.testing_env import ACC, Env
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_so_luong
from pema_contracts.channel import QuoteRef, SendResult, TextStyle, ThreadKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.scheduler import JobRunStatus, OnceSchedule

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]


class GatedChannel:
    """Wraps the ``FakeChannel`` of the env: ``send_text`` records the part and then HANGS until ``release()``."""

    def __init__(self, inner: object) -> None:
        self._inner = inner
        self.gate = asyncio.Event()

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    async def send_text(
        self,
        thread_id: str,
        text: str,
        *,
        thread_kind: ThreadKind = ThreadKind.USER,
        styles: Sequence[TextStyle] = (),
        quote: QuoteRef | None = None,
        proactive: bool = False,
    ) -> SendResult:
        result = await self._inner.send_text(  # type: ignore[attr-defined]
            thread_id, text, thread_kind=thread_kind, styles=styles, quote=quote, proactive=proactive
        )
        await self.gate.wait()
        return result  # type: ignore[no-any-return]


async def test_run_scheduled_job_trial_an_overdue_job_is_not_picked_by_a_real_tick_while_the_trial_hangs_and_the_state_is_restored(
    make_env: EnvMaker,
) -> None:
    """job đang quá hạn: tick thật KHÔNG nhặt được job trong lúc trial còn treo, và trạng thái phục hồi đúng sau khi thử xong"""
    env = make_env()
    gated = GatedChannel(env.channel)
    env.registry.register(env.clinic_id, gated)  # type: ignore[arg-type]
    overdue = (datetime.now(UTC) - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    job = await env.make_job(
        thread_id="t-trial-race",
        payload="Tin quá hạn, đang chờ tick thật",
        schedule=OnceSchedule(run_at_utc=overdue),
        now=datetime.now(UTC) - timedelta(minutes=30),
    )
    assert job.next_run_at is not None
    assert datetime.fromisoformat(job.next_run_at.replace("Z", "+00:00")) < datetime.now(UTC), (
        "job phải đang quá hạn"
    )

    trial = asyncio.create_task(run_scheduled_job_trial(env.deps, job))

    # Wait for the EXACT point needed: the trial reached the send (now hanging on the gate). The claim happens
    # BEFORE the send call, so seeing the first message proves the claim is done (waiting by condition, not by a
    # sleep that only measures the wall clock).
    await doi_cho_so_luong(lambda: len(env.channel.sent), 1, WaitOptions(mo_ta="trial đi tới send_text"))

    during = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert during is not None
    assert during.next_run_at is None, "job phải bị GIÀNH (next_run_at=NULL) trong lúc trial còn chạy"

    # A REAL tick while the trial is "hanging" - exactly the race scenario
    loop = SchedulerLoop(env.deps)
    await loop.run_tick(env.clinic_id, datetime.now(UTC))
    await loop.wait_idle()
    assert len(env.channel.sent) == 1, "tick KHÔNG được dispatch job này lần nữa - next_run_at đang NULL"

    gated.gate.set()
    record = await trial

    assert record is not None
    assert record.status is JobRunStatus.OK
    assert len(env.channel.sent) == 1, "chỉ ĐÚNG 1 tin được gửi - không nhân đôi vì tick chen vào giữa"
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.next_run_at == job.next_run_at, (
        "next_run_at phải quay về ĐÚNG mốc quá hạn ban đầu để tick THẬT còn nhặt lại"
    )
    assert after.enabled is True
    assert after.run_count == 0, "chạy thử không được tính là 1 lần chạy thật"
    assert after.delivery_attempts == 0
    assert after.last_status is None


async def test_run_scheduled_job_trial_does_not_use_up_the_only_slot_of_a_once_job_even_when_run_twice(
    make_env: EnvMaker,
) -> None:
    """gửi thật NHƯNG next_run_at/enabled/run_count của job KHÔNG đổi, kể cả chạy thử 2 lần liên tiếp"""
    env = make_env()
    job = await env.make_job(
        thread_id="t-trial-twice",
        payload="Tin chạy thử nghiệm",
        schedule=OnceSchedule(run_at_utc="2099-01-01T00:00:00.000Z"),
    )

    first = await run_scheduled_job_trial(env.deps, job)
    second = await run_scheduled_job_trial(env.deps, job)

    assert first is not None
    assert second is not None
    assert first.status is JobRunStatus.OK
    assert second.status is JobRunStatus.OK
    assert [p.text for p in env.channel.sent] == ["Tin chạy thử nghiệm", "Tin chạy thử nghiệm"]
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.next_run_at == job.next_run_at
    assert after.enabled is True, (
        "job 'once' KHÔNG được tự tắt sau khi chạy thử (bug: maxRuns=1 dùng hết suất)"
    )
    assert after.run_count == 0


async def test_run_scheduled_job_trial_refuses_when_another_worker_took_the_occurrence_in_between(
    make_env: EnvMaker,
) -> None:
    """(nhiều worker) bản job của người gọi nói 'đã lên lịch' nhưng hàng đã bị worker khác giành (next_run_at=NULL): từ chối, không đua"""
    env = make_env()
    job = await env.make_job(
        thread_id="t-trial-claimed", schedule=OnceSchedule(run_at_utc="2099-01-01T00:00:00.000Z")
    )
    await env.deps.jobs.set_next_run(env.clinic_id, job.id, None)  # another worker's claim

    with pytest.raises(DomainError) as caught:
        await run_scheduled_job_trial(env.deps, job)

    assert caught.value.code is ErrorCode.INVALID_STATE
    assert env.channel.sent == []
    assert await env.deps.runs.list_runs(env.clinic_id, job.id) == [], (
        "giao dịch bị huỷ: không để lại dòng running"
    )


async def test_run_scheduled_job_trial_a_job_deleted_before_the_snapshot_runs_through_and_returns_no_run(
    make_env: EnvMaker,
) -> None:
    """job bị xoá ngay trước lúc snapshot (cực hiếm): chạy thẳng, không có gì để giành/phục hồi, trả về run rỗng"""
    env = make_env()
    job = await env.make_job(thread_id="t-trial-deleted")
    await env.deps.jobs.delete_job(env.clinic_id, ACC, "t-trial-deleted", job.id)

    assert await run_scheduled_job_trial(env.deps, job) is None

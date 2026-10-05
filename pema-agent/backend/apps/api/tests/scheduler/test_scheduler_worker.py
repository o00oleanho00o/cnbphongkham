"""The scheduler worker entry point and the liveness heartbeat (new tests, no zalo-agent source)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta

import pytest

from pema.scheduler.redis_locks import InMemoryLockBackend
from pema.scheduler.run_scheduled_job import RunScheduledJobOptions, run_scheduled_job
from pema.scheduler.testing_env import Env
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_so_luong
from pema.shared.zone_time import to_iso_z
from pema.workers.scheduler_worker import build_send_gate, recover_installation, run_scheduler_worker
from pema_contracts.channel import QuoteRef, SendResult, TextStyle, ThreadKind
from pema_contracts.scheduler import JobRunStatus, OnceSchedule

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
BASE: dict[str, str | int | float | bool] = {"SCHEDULER_SEND_GAP_MS": 0, "SCHEDULER_ONCE_GRACE_MINUTES": 1}


async def test_run_scheduler_worker_processes_due_jobs_of_the_clinic_and_stops_cleanly(
    make_env: EnvMaker,
) -> None:
    """worker: chạy vòng tick cho phòng khám của bản cài đặt, dừng sạch khi nhận tín hiệu (đợi các lượt đang chạy chốt sổ)"""
    env = make_env(tuning=BASE)
    due = OnceSchedule(run_at_utc=to_iso_z(datetime.now(UTC) - timedelta(seconds=5)))
    job = await env.make_job(thread_id="t-worker", payload="tin của worker", schedule=due)
    stop = asyncio.Event()

    worker = asyncio.create_task(
        run_scheduler_worker(env.deps, lock_backend=InMemoryLockBackend(), stop=stop)
    )
    await doi_cho_so_luong(
        lambda: len(env.channel.sent), 1, WaitOptions(tran_ms=3000, mo_ta="tin của worker")
    )
    stop.set()
    await asyncio.wait_for(worker, timeout=5)

    assert [p.text for p in env.channel.sent] == ["tin của worker"]
    runs = await env.deps.runs.list_runs(env.clinic_id, job.id)
    assert [r.status for r in runs] == [JobRunStatus.OK], "lượt phải được chốt sổ trước khi worker dừng"


async def test_recover_installation_interrupts_dead_runs_and_revives_their_claimed_once_jobs(
    make_env: EnvMaker,
) -> None:
    """recover_installation (CLI vận hành): lượt của worker đã chết -> interrupted, job 'once' nó giành dở -> phục hồi"""
    env = make_env(tuning=BASE, stale_run_seconds=0)
    run_at = to_iso_z(datetime.now(UTC) + timedelta(hours=1))
    job = await env.make_job(thread_id="t-recover", schedule=OnceSchedule(run_at_utc=run_at))
    await env.deps.jobs.set_next_run(env.clinic_id, job.id, None)
    await env.deps.runs.open_run(env.clinic_id, job.id, worker_id="worker-dead")
    await asyncio.sleep(0.05)  # the stale window of this env is 0 s: any heartbeat in the past is stale

    await recover_installation(env.deps)

    runs = await env.deps.runs.list_runs(env.clinic_id, job.id)
    assert runs[0].status is JobRunStatus.INTERRUPTED
    revived = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert revived is not None
    assert revived.next_run_at == run_at


class SlowChannel:
    def __init__(self, inner: object, delay: float) -> None:
        self._inner = inner
        self._delay = delay

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
        await asyncio.sleep(self._delay)
        return await self._inner.send_text(  # type: ignore[attr-defined,no-any-return]
            thread_id, text, thread_kind=thread_kind, styles=styles, quote=quote, proactive=proactive
        )


async def test_a_long_run_keeps_refreshing_its_heartbeat_so_another_worker_does_not_take_it_for_dead(
    make_env: EnvMaker,
) -> None:
    """lượt chạy dài tự làm mới nhịp tim: worker khác không coi nó là đã chết"""
    env = make_env(tuning=BASE, heartbeat_seconds=0.05, stale_run_seconds=1.0)
    env.registry.register(env.clinic_id, SlowChannel(env.channel, 1.5))  # type: ignore[arg-type]
    job = await env.make_job(thread_id="t-heartbeat", payload="lượt dài")
    task = asyncio.create_task(
        run_scheduled_job(
            env.deps,
            job,
            RunScheduledJobOptions(late=False, scheduled_for=job.next_run_at or "", now=datetime.now(UTC)),
        )
    )
    await asyncio.sleep(1.2)  # longer than the stale window: only the heartbeat keeps the row alive

    interrupted = await env.deps.runs.interrupt_stale_runs(env.clinic_id, 1.0)
    await task

    assert interrupted == 0, "lượt còn sống bị coi là chết dù đang gửi"
    run_row = (await env.deps.runs.list_runs(env.clinic_id, job.id))[0]
    assert run_row.status is JobRunStatus.OK


def test_build_send_gate_returns_the_cross_process_spacing_gate_for_the_deps() -> None:
    """build_send_gate: cổng giãn cách gửi giữa các tiến trình, dùng cho SchedulerDeps(send_gate=...)"""
    assert build_send_gate(InMemoryLockBackend()) is not None

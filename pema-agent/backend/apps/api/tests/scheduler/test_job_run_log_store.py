# ported from: src/scheduler/job-run-log-store.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Difference forced by Postgres: ``agent.job_runs`` has a real foreign key to ``agent.jobs`` (the SQLite table had a
plain TEXT ``job_id``), so each test creates the job first. The last group is new: the heartbeat that lets
several workers tell a long run from a dead worker.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pema.scheduler.job_run_log_store import FinishRunParams
from pema.scheduler.testing_env import Env
from pema_contracts.scheduler import JobRunStatus

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]


async def test_open_run_opens_a_running_run_ids_increase(make_env: EnvMaker) -> None:
    """mở lượt mới ở trạng thái running, id tăng dần"""
    env = make_env()
    job = await env.make_job(thread_id="t-a")
    id1 = await env.deps.runs.open_run(env.clinic_id, job.id)
    id2 = await env.deps.runs.open_run(env.clinic_id, job.id)
    assert id2 > id1

    newest = (await env.deps.runs.list_runs(env.clinic_id, job.id, 1))[0]
    assert newest.id == id2
    assert newest.status is JobRunStatus.RUNNING
    assert newest.finished_at is None


async def test_finish_run_records_status_detail_delivered_chars_turn_id_finished_at(
    make_env: EnvMaker,
) -> None:
    """chốt lượt ghi đủ status/detail/deliveredChars/turnId/finishedAt"""
    env = make_env()
    job = await env.make_job(thread_id="t-b")
    run_id = await env.deps.runs.open_run(env.clinic_id, job.id)
    await env.deps.runs.finish_run(
        env.clinic_id,
        run_id,
        FinishRunParams(status=JobRunStatus.OK, detail="gửi xong", delivered_chars=42, turn_id=999),
    )
    run = (await env.deps.runs.list_runs(env.clinic_id, job.id, 1))[0]
    assert run.status is JobRunStatus.OK
    assert run.detail == "gửi xong"
    assert run.delivered_chars == 42
    assert run.turn_id == 999
    assert run.finished_at is not None


async def test_finish_run_with_nothing_passed_still_has_reasonable_defaults(make_env: EnvMaker) -> None:
    """chốt lượt không truyền gì vẫn có giá trị mặc định hợp lý"""
    env = make_env()
    job = await env.make_job(thread_id="t-c")
    run_id = await env.deps.runs.open_run(env.clinic_id, job.id)
    await env.deps.runs.finish_run(env.clinic_id, run_id, FinishRunParams(status=JobRunStatus.SKIPPED))
    run = (await env.deps.runs.list_runs(env.clinic_id, job.id, 1))[0]
    assert run.status is JobRunStatus.SKIPPED
    assert run.detail == ""
    assert run.delivered_chars == 0
    assert run.turn_id is None


async def test_list_runs_newest_first_only_that_job_respects_the_limit(make_env: EnvMaker) -> None:
    """mới nhất đứng trước, chỉ của đúng job, tôn trọng limit"""
    env = make_env()
    job = await env.make_job(thread_id="t-list")
    other = await env.make_job(thread_id="t-khac")
    for _ in range(5):
        await env.deps.runs.open_run(env.clinic_id, job.id)
    await env.deps.runs.open_run(env.clinic_id, other.id)

    top2 = await env.deps.runs.list_runs(env.clinic_id, job.id, 2)
    assert len(top2) == 2
    assert top2[0].id > top2[1].id, "mới nhất (id lớn nhất) phải đứng đầu"
    assert all(r.job_id == job.id for r in top2)


async def test_list_runs_a_job_with_no_runs_returns_an_empty_list(make_env: EnvMaker) -> None:
    """job chưa có lượt nào trả mảng rỗng"""
    env = make_env()
    job = await env.make_job(thread_id="t-trong")
    assert await env.deps.runs.list_runs(env.clinic_id, job.id) == []


async def test_keep_pruning_keeps_only_the_most_recent_runs_per_job_without_touching_other_jobs(
    make_env: EnvMaker,
) -> None:
    """chỉ giữ KEEP lượt gần nhất mỗi job, không đụng job khác"""
    env = make_env()
    job_a = await env.make_job(thread_id="t-keep-a")
    job_b = await env.make_job(thread_id="t-keep-b")
    ids_of_a = [await env.deps.runs.open_run(env.clinic_id, job_a.id, 3) for _ in range(7)]
    await env.deps.runs.open_run(env.clinic_id, job_b.id, 3)  # another job, its own threshold

    kept = await env.deps.runs.list_runs(env.clinic_id, job_a.id, 100)
    assert len(kept) == 3, "chỉ còn 3 lượt gần nhất"
    assert sorted(r.id for r in kept) == sorted(ids_of_a[-3:])
    assert len(await env.deps.runs.list_runs(env.clinic_id, job_b.id, 100)) == 1


async def test_has_running_run_true_only_while_a_run_is_not_closed(make_env: EnvMaker) -> None:
    """(hasRunningRun) chỉ true khi còn lượt CHƯA chốt sổ"""
    env = make_env()
    job = await env.make_job(thread_id="t-has-running")
    assert await env.deps.runs.has_running_run(env.clinic_id, job.id) is False
    run_id = await env.deps.runs.open_run(env.clinic_id, job.id)
    assert await env.deps.runs.has_running_run(env.clinic_id, job.id) is True
    await env.deps.runs.finish_run(env.clinic_id, run_id, FinishRunParams(status=JobRunStatus.OK))
    assert await env.deps.runs.has_running_run(env.clinic_id, job.id) is False


async def test_interrupt_stale_runs_only_interrupts_rows_whose_heartbeat_is_stale(make_env: EnvMaker) -> None:
    """(nhiều worker) lượt running còn nhịp tim gần đây KHÔNG bị đánh dấu interrupted, lượt mất nhịp thì có"""
    env = make_env()
    job = await env.make_job(thread_id="t-stale")
    alive = await env.deps.runs.open_run(env.clinic_id, job.id, worker_id="worker-live")
    dead = await env.deps.runs.open_run(env.clinic_id, job.id, worker_id="worker-dead")
    env.execute(
        "UPDATE agent.job_runs SET heartbeat_at = now() - interval '10 minutes' WHERE clinic_id = :c AND id = :i",
        i=dead,
    )

    changed = await env.deps.runs.interrupt_stale_runs(env.clinic_id, 120)

    assert changed == 1
    runs = {r.id: r for r in await env.deps.runs.list_runs(env.clinic_id, job.id)}
    assert runs[dead].status is JobRunStatus.INTERRUPTED
    assert runs[dead].finished_at is not None
    assert runs[alive].status is JobRunStatus.RUNNING

    await env.deps.runs.heartbeat(env.clinic_id, alive)  # a beat of a live run is harmless
    after = {r.id: r for r in await env.deps.runs.list_runs(env.clinic_id, job.id)}
    assert after[alive].status is JobRunStatus.RUNNING

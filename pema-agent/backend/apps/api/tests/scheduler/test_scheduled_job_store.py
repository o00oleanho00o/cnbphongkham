# ported from: src/scheduler/scheduled-job-store.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Runs on a real Postgres as the ``agent_worker`` role (see ``conftest``); every test gets a fresh clinic. The
original tests used the clinic-less SQLite store; here the clinic is part of every call, and a job of ANOTHER
clinic is invisible (RLS), which the last group adds.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from pema.scheduler.job_run_log_store import FinishRunParams
from pema.scheduler.scheduled_job_store import UpdateScheduledJobInput, schedule_of
from pema.scheduler.testing_env import ACC, Env
from pema_contracts.scheduler import CronSchedule, EverySchedule, JobRunStatus, OnceSchedule, ParsedSchedule

pytestmark = pytest.mark.db

ONCE: ParsedSchedule = OnceSchedule(run_at_utc="2026-08-01T08:00:00.000Z")
EVERY_30: ParsedSchedule = EverySchedule(minutes=30)
T0 = datetime(2026, 8, 1, 0, 0, tzinfo=UTC)

EnvMaker = Callable[..., Env]


# ------------------------------------------------------------------------------------------ createJob


async def test_create_job_once_next_run_at_is_run_at_utc_max_runs_defaults_to_1(make_env: EnvMaker) -> None:
    """once: next_run_at = runAtUtc, max_runs mặc định 1"""
    env = make_env()
    job = await env.make_job(thread_id="t-once", schedule=ONCE)
    assert job.next_run_at == "2026-08-01T08:00:00.000Z"
    assert job.max_runs == 1
    assert job.schedule_kind.value == "once"
    assert job.run_at == "2026-08-01T08:00:00.000Z"
    assert job.every_minutes is None
    assert job.enabled is True
    assert job.run_count == 0


async def test_create_job_every_next_run_at_is_now_plus_interval_max_runs_defaults_to_unlimited(
    make_env: EnvMaker,
) -> None:
    """every: next_run_at = now + interval, max_runs mặc định vô hạn (NULL)"""
    env = make_env()
    job = await env.make_job(thread_id="t-every", schedule=EVERY_30)
    assert job.next_run_at == "2026-08-01T00:30:00.000Z"
    assert job.max_runs is None
    assert job.every_minutes == 30
    assert job.cron_expr is None


async def test_create_job_once_explicit_max_runs_above_1_is_forced_to_1(make_env: EnvMaker) -> None:
    """once: maxRuns tường minh > 1 bị ép về 1 - 'once' theo định nghĩa chỉ chạy đúng 1 lần

    The hole found in review: compute_next_run('once') always returns run_at_utc whatever ``now`` is, so if
    max_runs=5 got through, after the first run (run_count=1 < 5) next_run_at stays at the past instant and the
    next tick picks it up AT ONCE, firing again every tick until 5 runs."""
    env = make_env()
    job = await env.make_job(thread_id="t-once-clamp", schedule=ONCE, max_runs=5)
    assert job.max_runs == 1


async def test_create_job_id_is_12_hex_characters(make_env: EnvMaker) -> None:
    """id là hex 12 ký tự"""
    env = make_env()
    job = await env.make_job(thread_id="t-id")
    assert len(job.id) == 12
    assert all(c in "0123456789abcdef" for c in job.id)


async def test_create_job_dedupe_key_returns_the_first_job_on_a_second_create(make_env: EnvMaker) -> None:
    """(clinic) cùng dedupe_key trong cùng phòng khám trả về job đầu, không tạo job thứ hai"""
    env = make_env()
    first = await env.make_job(thread_id="t-dedupe", dedupe_key="rule-d1:P025:visit-9")
    second = await env.make_job(thread_id="t-dedupe", dedupe_key="rule-d1:P025:visit-9", name="khác tên")
    assert second.id == first.id
    assert second.name == first.name
    assert len(await env.deps.jobs.list_jobs_for_thread(env.clinic_id, ACC, "t-dedupe")) == 1


# ------------------------------------------------------------- getJob / getJobUnscoped / listJobsForThread


async def test_get_job_unknown_id_returns_none(make_env: EnvMaker) -> None:
    """getJob: id không tồn tại trả undefined"""
    env = make_env()
    assert await env.deps.jobs.get_job(env.clinic_id, ACC, "t-khong-ton-tai", "khong-ton-tai") is None


async def test_get_job_scope_right_account_and_thread_reads_wrong_one_is_none_blocks_idor(
    make_env: EnvMaker,
) -> None:
    """getJob: đúng phạm vi thì đọc được, sai accountId hoặc threadId đều trả undefined dù id đúng - chặn IDOR"""
    env = make_env()
    job = await env.make_job(thread_id="t-scope-get")
    found = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-scope-get", job.id)
    assert found is not None
    assert found.id == job.id
    assert await env.deps.jobs.get_job(env.clinic_id, "acc-khac", "t-scope-get", job.id) is None
    assert await env.deps.jobs.get_job(env.clinic_id, ACC, "t-thread-khac", job.id) is None


async def test_get_job_unscoped_reads_regardless_of_scope_internal_use_only(make_env: EnvMaker) -> None:
    """getJobUnscoped: đọc được bất kể phạm vi - chỉ dùng nội bộ (vòng tick/markRun), không phơi cho tool/API"""
    env = make_env()
    job = await env.make_job(thread_id="t-scope-unscoped")
    found = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert found is not None
    assert found.id == job.id


async def test_get_job_unscoped_a_job_of_another_clinic_is_invisible(make_env: EnvMaker) -> None:
    """(clinic) job của phòng khám khác không đọc được dù biết đúng id - RLS + clinic_id"""
    env_a = make_env()
    env_b = make_env()
    job = await env_a.make_job(thread_id="t-clinic-a")
    assert await env_b.deps.jobs.get_job_unscoped(env_b.clinic_id, job.id) is None


async def test_list_jobs_for_thread_lists_only_that_account_and_thread(make_env: EnvMaker) -> None:
    """chỉ liệt kê job của đúng account+thread, không lẫn thread khác"""
    env = make_env()
    await env.make_job(thread_id="t-list-a", name="job A1")
    await env.make_job(thread_id="t-list-a", name="job A2")
    await env.make_job(thread_id="t-list-b", name="job B1")
    listed = await env.deps.jobs.list_jobs_for_thread(env.clinic_id, ACC, "t-list-a")
    assert len(listed) == 2
    assert all(j.thread_id == "t-list-a" for j in listed)


# ------------------------------------------------------------------------------------------ updateJob


async def test_update_job_unknown_id_returns_false(make_env: EnvMaker) -> None:
    """id không tồn tại trả false"""
    env = make_env()
    assert (
        await env.deps.jobs.update_job(
            env.clinic_id, ACC, "t-nope", "khong-ton-tai", UpdateScheduledJobInput(name="x")
        )
        is False
    )


async def test_update_job_wrong_scope_returns_false_and_changes_nothing_blocks_idor(
    make_env: EnvMaker,
) -> None:
    """sai accountId hoặc threadId thì trả false và KHÔNG sửa gì - chặn IDOR"""
    env = make_env()
    job = await env.make_job(thread_id="t-scope-update")
    patch = UpdateScheduledJobInput(name="bị đổi trái phép")
    assert await env.deps.jobs.update_job(env.clinic_id, "acc-khac", "t-scope-update", job.id, patch) is False
    assert await env.deps.jobs.update_job(env.clinic_id, ACC, "t-thread-khac", job.id, patch) is False
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.name == job.name


async def test_update_job_only_name_and_payload_keeps_next_run_at(make_env: EnvMaker) -> None:
    """chỉ đổi name/payload thì next_run_at GIỮ NGUYÊN"""
    env = make_env()
    job = await env.make_job(thread_id="t-update-1", schedule=EVERY_30)
    ok = await env.deps.jobs.update_job(
        env.clinic_id,
        ACC,
        "t-update-1",
        job.id,
        UpdateScheduledJobInput(name="tên mới", payload="nội dung mới"),
    )
    assert ok is True
    after = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-update-1", job.id)
    assert after is not None
    assert after.name == "tên mới"
    assert after.payload == "nội dung mới"
    assert after.next_run_at == job.next_run_at, "đổi tên/payload không được nhảy mốc lịch"
    assert after.max_runs == job.max_runs, "không đổi schedule thì maxRuns cũng giữ nguyên"


async def test_update_job_changed_every_frequency_recomputes_next_run_at_max_runs_stays_null(
    make_env: EnvMaker,
) -> None:
    """đổi schedule (giữ nguyên kind every) thì next_run_at được TÍNH LẠI, maxRuns giữ null"""
    env = make_env()
    job = await env.make_job(thread_id="t-update-2", schedule=EVERY_30)
    await env.deps.jobs.update_job(
        env.clinic_id,
        ACC,
        "t-update-2",
        job.id,
        UpdateScheduledJobInput(schedule=EverySchedule(minutes=45), now=T0),
    )
    after = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-update-2", job.id)
    assert after is not None
    assert after.every_minutes == 45
    assert after.next_run_at == "2026-08-01T00:45:00.000Z"
    assert after.max_runs is None


async def test_update_job_kind_every_to_once_without_max_runs_recomputes_max_runs_to_1_and_mark_run_switches_off(
    make_env: EnvMaker,
) -> None:
    """đổi kind every -> once KHÔNG kèm maxRuns: tự tính lại maxRuns=1 theo kind mới, markRun tự tắt sau đúng 1 lần (chặn spam vô hạn)"""
    env = make_env()
    job = await env.make_job(thread_id="t-update-kind-change", schedule=EVERY_30)
    assert job.max_runs is None

    ok = await env.deps.jobs.update_job(
        env.clinic_id, ACC, "t-update-kind-change", job.id, UpdateScheduledJobInput(schedule=ONCE, now=T0)
    )
    assert ok is True
    after = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-update-kind-change", job.id)
    assert after is not None
    assert after.schedule_kind.value == "once"
    assert after.max_runs == 1, "phải tính lại theo kind mới, không giữ null của kind cũ"

    await env.deps.jobs.mark_run(env.clinic_id, job.id, JobRunStatus.OK)
    done = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-update-kind-change", job.id)
    assert done is not None
    assert done.enabled is False, "phải tự tắt sau đúng 1 lần chạy, không lặp lại mỗi tick"
    assert done.next_run_at is None


async def test_update_job_kind_every_to_cron_with_explicit_max_runs_uses_that_value(
    make_env: EnvMaker,
) -> None:
    """đổi kind every -> cron CÓ truyền maxRuns tường minh thì dùng đúng giá trị đó, không bị tính lại đè lên"""
    env = make_env()
    job = await env.make_job(thread_id="t-update-explicit-maxruns", schedule=EVERY_30)
    await env.deps.jobs.update_job(
        env.clinic_id,
        ACC,
        "t-update-explicit-maxruns",
        job.id,
        UpdateScheduledJobInput(
            schedule=CronSchedule(expr="0 8 * * *", time_zone="Asia/Ho_Chi_Minh"), max_runs=5, now=T0
        ),
    )
    after = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-update-explicit-maxruns", job.id)
    assert after is not None
    assert after.max_runs == 5


async def test_update_job_to_once_with_explicit_max_runs_above_1_is_still_forced_to_1(
    make_env: EnvMaker,
) -> None:
    """đổi sang once CÓ truyền maxRuns tường minh > 1 vẫn bị ép về 1 - bất biến 'once' thắng cả override tường minh"""
    env = make_env()
    job = await env.make_job(thread_id="t-update-once-clamp", schedule=EVERY_30)
    await env.deps.jobs.update_job(
        env.clinic_id,
        ACC,
        "t-update-once-clamp",
        job.id,
        UpdateScheduledJobInput(schedule=ONCE, max_runs=5, now=T0),
    )
    after = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-update-once-clamp", job.id)
    assert after is not None
    assert after.max_runs == 1


async def test_update_job_same_kind_change_of_frequency_keeps_an_explicit_max_runs(
    make_env: EnvMaker,
) -> None:
    """cùng kind (every -> every, chỉ đổi tần suất), maxRuns đặt tường minh KHÁC NULL từ lúc tạo: KHÔNG bị trigger tính lại xoá mất

    A job "remind 5 times then stop", only the frequency changes (kind still every): the cap must not vanish
    into unlimited."""
    env = make_env()
    job = await env.make_job(thread_id="t-update-keep-maxruns", schedule=EVERY_30, max_runs=5)
    assert job.max_runs == 5
    await env.deps.jobs.update_job(
        env.clinic_id,
        ACC,
        "t-update-keep-maxruns",
        job.id,
        UpdateScheduledJobInput(schedule=EverySchedule(minutes=45), now=T0),
    )
    after = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-update-keep-maxruns", job.id)
    assert after is not None
    assert after.every_minutes == 45, "tần suất vẫn phải đổi đúng yêu cầu"
    assert after.max_runs == 5, "maxRuns phải còn nguyên vì kind KHÔNG đổi"


# --------------------------------------------------------------------------- setEnabled / deleteJob


async def test_set_enabled_changes_the_flag_and_returns_false_for_unknown_id(make_env: EnvMaker) -> None:
    """setEnabled đổi cờ, trả false khi id lạ"""
    env = make_env()
    job = await env.make_job(thread_id="t-enable")
    assert await env.deps.jobs.set_enabled(env.clinic_id, ACC, "t-enable", job.id, False) is True
    after = await env.deps.jobs.get_job(env.clinic_id, ACC, "t-enable", job.id)
    assert after is not None
    assert after.enabled is False
    assert await env.deps.jobs.set_enabled(env.clinic_id, ACC, "t-enable", "khong-ton-tai", True) is False


async def test_set_enabled_wrong_scope_returns_false_and_does_not_disable_blocks_idor(
    make_env: EnvMaker,
) -> None:
    """setEnabled: sai phạm vi thì trả false và KHÔNG tắt job - chặn IDOR"""
    env = make_env()
    job = await env.make_job(thread_id="t-scope-setenabled")
    assert await env.deps.jobs.set_enabled(env.clinic_id, ACC, "t-thread-khac", job.id, False) is False
    still = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert still is not None
    assert still.enabled is True


async def test_delete_job_removes_the_row_second_call_returns_false(make_env: EnvMaker) -> None:
    """deleteJob xoá hẳn row, gọi lần 2 trả false"""
    env = make_env()
    job = await env.make_job(thread_id="t-delete")
    assert await env.deps.jobs.delete_job(env.clinic_id, ACC, "t-delete", job.id) is True
    assert await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id) is None
    assert await env.deps.jobs.delete_job(env.clinic_id, ACC, "t-delete", job.id) is False


async def test_delete_job_wrong_scope_returns_false_and_job_stays_blocks_idor(make_env: EnvMaker) -> None:
    """deleteJob: sai phạm vi thì trả false và job vẫn còn nguyên - chặn IDOR"""
    env = make_env()
    job = await env.make_job(thread_id="t-scope-delete")
    assert await env.deps.jobs.delete_job(env.clinic_id, "acc-khac", "t-scope-delete", job.id) is False
    assert await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id) is not None


async def test_delete_job_also_deletes_the_run_history_no_orphans(make_env: EnvMaker) -> None:
    """deleteJob xoá LUÔN scheduled_job_runs của job đó - không để lại lịch sử mồ côi (Mục M2)"""
    env = make_env()
    job = await env.make_job(thread_id="t-delete-runs")
    run_id = await env.deps.runs.open_run(env.clinic_id, job.id)
    await env.deps.runs.finish_run(env.clinic_id, run_id, _finish("ok", "gửi xong"))
    assert len(await env.deps.runs.list_runs(env.clinic_id, job.id)) == 1

    assert await env.deps.jobs.delete_job(env.clinic_id, ACC, "t-delete-runs", job.id) is True

    assert env.row("SELECT count(*) FROM agent.job_runs WHERE clinic_id = :c AND job_id = :j", j=job.id) == (
        0,
    )


async def test_delete_job_wrong_scope_does_not_touch_the_run_history(make_env: EnvMaker) -> None:
    """deleteJob sai phạm vi (bị chặn IDOR) thì KHÔNG được đụng vào scheduled_job_runs của job đó"""
    env = make_env()
    job = await env.make_job(thread_id="t-delete-runs-idor")
    run_id = await env.deps.runs.open_run(env.clinic_id, job.id)
    await env.deps.runs.finish_run(env.clinic_id, run_id, _finish("ok"))

    assert await env.deps.jobs.delete_job(env.clinic_id, "acc-khac", "t-delete-runs-idor", job.id) is False

    assert len(await env.deps.runs.list_runs(env.clinic_id, job.id)) == 1


# ------------------------------------------------------------------------------------------- listDueJobs


async def test_list_due_jobs_only_enabled_and_next_run_at_before_the_instant_sorted_ascending(
    make_env: EnvMaker,
) -> None:
    """chỉ trả job enabled=1 và next_run_at <= mốc truyền vào, sắp tăng dần"""
    env = make_env()
    early = await env.make_job(thread_id="t-due", name="due-som", schedule=ONCE)  # 08:00
    late = await env.make_job(
        thread_id="t-due", name="due-muon", schedule=OnceSchedule(run_at_utc="2026-08-01T09:00:00.000Z")
    )
    not_yet = await env.make_job(
        thread_id="t-due", name="chua-toi-han", schedule=OnceSchedule(run_at_utc="2026-08-01T23:00:00.000Z")
    )
    off = await env.make_job(thread_id="t-due", name="da-tat", schedule=ONCE)
    await env.deps.jobs.set_enabled(env.clinic_id, ACC, "t-due", off.id, False)

    due = await env.deps.jobs.list_due_jobs(env.clinic_id, datetime(2026, 8, 1, 9, 30, tzinfo=UTC))
    ids = [j.id for j in due]
    assert ids == [early.id, late.id], "sắp theo next_run_at tăng dần, bỏ job chưa tới hạn và job đã tắt"
    assert not_yet.id not in ids
    assert off.id not in ids


# ------------------------------------------------------------------------------------------- setNextRun


async def test_set_next_run_writes_the_new_instant_and_can_write_null(make_env: EnvMaker) -> None:
    """ghi mốc mới, và ghi NULL được (job hết lượt)"""
    env = make_env()
    job = await env.make_job(thread_id="t-setnext", schedule=EVERY_30)
    await env.deps.jobs.set_next_run(env.clinic_id, job.id, "2026-09-01T00:00:00.000Z")
    got = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert got is not None
    assert got.next_run_at == "2026-09-01T00:00:00.000Z"

    await env.deps.jobs.set_next_run(env.clinic_id, job.id, None)
    got = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert got is not None
    assert got.next_run_at is None


# --------------------------------------------------------------------------------------------- markRun


async def test_mark_run_unlimited_job_increments_run_count_records_status_and_never_switches_off(
    make_env: EnvMaker,
) -> None:
    """job vô hạn (every): tăng run_count, ghi last_status/last_error, KHÔNG tự tắt"""
    env = make_env()
    job = await env.make_job(thread_id="t-mark-every", schedule=EVERY_30)
    await env.deps.jobs.mark_run(env.clinic_id, job.id, JobRunStatus.OK)
    await env.deps.jobs.mark_run(env.clinic_id, job.id, JobRunStatus.ERROR, "router chết")

    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.run_count == 2
    assert after.last_status == "error"
    assert after.last_error == "router chết"
    assert after.enabled is True
    assert after.last_run_at is not None


async def test_mark_run_once_reaching_the_cap_switches_off_and_nulls_next_run_but_keeps_the_row(
    make_env: EnvMaker,
) -> None:
    """job once (max_runs=1): chạm trần thì tự tắt + next_run_at=NULL nhưng GIỮ NGUYÊN row"""
    env = make_env()
    job = await env.make_job(thread_id="t-mark-once", schedule=ONCE)
    await env.deps.jobs.mark_run(env.clinic_id, job.id, JobRunStatus.OK)

    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.run_count == 1
    assert after.enabled is False, "chạm max_runs phải tự tắt"
    assert after.next_run_at is None, "không còn lượt kế tiếp"
    assert after.last_status == "ok"


async def test_mark_run_unknown_id_is_a_no_op_without_raising(make_env: EnvMaker) -> None:
    """id không tồn tại: no-op, không throw"""
    env = make_env()
    await env.deps.jobs.mark_run(env.clinic_id, "khong-ton-tai", JobRunStatus.OK)


async def test_mark_run_concurrent_finishes_never_lose_an_increment(make_env: EnvMaker) -> None:
    """(Postgres) 20 lần markRun đồng thời đều được đếm - tăng + so trần nằm trong MỘT câu UPDATE"""
    env = make_env()
    job = await env.make_job(thread_id="t-mark-concurrent", schedule=EVERY_30)
    await asyncio.gather(*(env.deps.jobs.mark_run(env.clinic_id, job.id, JobRunStatus.OK) for _ in range(20)))
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.run_count == 20


# ------------------------------------------------------------------------------------------ scheduleOf


async def test_schedule_of_rebuilds_the_right_parsed_schedule_for_each_kind(make_env: EnvMaker) -> None:
    """dựng lại đúng ParsedSchedule cho từng kind"""
    env = make_env()
    once_job = await env.make_job(thread_id="t-schedule-once", schedule=ONCE)
    every_job = await env.make_job(thread_id="t-schedule-every", schedule=EVERY_30)
    assert schedule_of(once_job, "UTC") == ONCE
    assert schedule_of(every_job, "UTC") == EVERY_30


async def test_schedule_of_cron_empty_timezone_falls_back_to_the_default_passed_by_the_caller(
    make_env: EnvMaker,
) -> None:
    """cron: timezone rỗng trên row rơi về defaultTimeZone do caller truyền vào"""
    env = make_env()
    job = await env.make_job(
        thread_id="t-schedule-cron",
        schedule=CronSchedule(expr="0 7 * * *", time_zone="Asia/Ho_Chi_Minh"),
        timezone="",  # the job "floats" with the current configuration instead of being pinned
    )
    assert schedule_of(job, "Europe/Paris") == CronSchedule(expr="0 7 * * *", time_zone="Europe/Paris")


async def test_schedule_of_cron_pinned_timezone_is_kept_not_replaced_by_the_default(
    make_env: EnvMaker,
) -> None:
    """cron: timezone đã pin trên row thì giữ nguyên, không rơi về default"""
    env = make_env()
    job = await env.make_job(
        thread_id="t-schedule-cron-pinned",
        schedule=CronSchedule(expr="0 7 * * *", time_zone="Asia/Ho_Chi_Minh"),
        timezone="Asia/Ho_Chi_Minh",
    )
    assert schedule_of(job, "Europe/Paris") == CronSchedule(expr="0 7 * * *", time_zone="Asia/Ho_Chi_Minh")


# ----------------------------------------------------------------------------------------------- helpers


def _finish(status: str, detail: str = "") -> FinishRunParams:
    return FinishRunParams(status=JobRunStatus(status), detail=detail)

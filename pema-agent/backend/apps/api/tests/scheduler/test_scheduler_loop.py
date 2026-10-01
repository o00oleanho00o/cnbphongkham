# ported from: src/scheduler/scheduler-loop.test.ts
"""Integration tests of the tick loop: the REAL database and stores, the REAL guard; only the channel (a fake with an
optional delay), the LLM and package C2's pipeline are fakes. Not re-testing "send / guard / silent" (that is
``test_run_scheduled_job``): the focus is the RIGHT RHYTHM - clear-before-dispatch, no await in the tick,
skip-forward, recovery at boot - plus the part the original got for free from one synchronous process: SEVERAL
workers ticking the same clinic never run a job twice.

Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.
``SCHEDULER_TICK_MS`` has a hard floor of 5000 ms, so a repeated tick is driven by calling ``run_tick`` directly
instead of waiting for the real timer (the timer itself is covered by ``start`` tests that only need the FIRST tick).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.scheduler.deps import SchedulerDeps
from pema.scheduler.redis_locks import InMemoryLockBackend, TickLease
from pema.scheduler.scheduler_loop import SchedulerLoop
from pema.scheduler.testing import FakeOutbound
from pema.scheduler.testing_env import ACC, Env
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi, doi_cho_so_luong
from pema.shared.zone_time import deferred_run_at_utc, to_iso_z, today_key
from pema_contracts.channel import QuoteRef, SendResult, TextStyle, ThreadKind
from pema_contracts.scheduler import EverySchedule, JobKind, JobRunStatus, OnceSchedule, ScheduledJob
from pema_contracts.testing import InMemoryThreadLock

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
TZ = "Asia/Ho_Chi_Minh"
BASE: dict[str, str | int | float | bool] = {
    "SCHEDULER_TICK_MS": 5000,
    "SCHEDULER_SEND_GAP_MS": 0,
    "SCHEDULER_ONCE_GRACE_MINUTES": 1,
    "BOT_TIMEZONE": TZ,
}


def once_due(seconds_ago: int = 5) -> OnceSchedule:
    return OnceSchedule(run_at_utc=to_iso_z(datetime.now(UTC) - timedelta(seconds=seconds_ago)))


def loop_of(env: Env, **kwargs: object) -> SchedulerLoop:
    async def ids() -> list[UUID]:
        return [env.clinic_id]

    return SchedulerLoop(env.deps, clinic_ids=ids, **kwargs)  # type: ignore[arg-type]


async def last_run(env: Env, job_id: str):
    runs = await env.deps.runs.list_runs(env.clinic_id, job_id, 1)
    return runs[0] if runs else None


async def job_now(env: Env, job_id: str) -> ScheduledJob:
    job = await env.deps.jobs.get_job_unscoped(env.clinic_id, job_id)
    assert job is not None
    return job


def sent_count(env: Env) -> Callable[[], int]:
    return lambda: len(env.channel.sent)


class SlowChannel:
    """Wraps the env channel: ``send_text`` sleeps ``delay`` seconds after recording the part."""

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
        result = await self._inner.send_text(  # type: ignore[attr-defined]
            thread_id, text, thread_kind=thread_kind, styles=styles, quote=quote, proactive=proactive
        )
        await asyncio.sleep(self._delay)
        return result  # type: ignore[no-any-return]


# ====================================================================== startScheduler - SCHEDULER_ENABLED


async def test_start_scheduler_enabled_false_registers_nothing_a_due_job_is_never_processed(
    make_env: EnvMaker,
) -> None:
    """=false thì không đăng ký gì - job đã đến hạn không bao giờ được xử lý"""
    env = make_env(tuning={**BASE, "SCHEDULER_ENABLED": False})
    job = await env.make_job(thread_id="t-tat-scheduler", schedule=once_due())
    loop = loop_of(env)

    await loop.start()
    await asyncio.sleep(0.2)  # a negative: there is no event to wait for

    assert env.channel.sent == []
    assert await env.deps.runs.list_runs(env.clinic_id, job.id) == [], (
        "không được có run nào - tick chưa từng chạy"
    )
    await loop.stop()


async def test_start_scheduler_disabled_midway_takes_effect_at_once_read_again_every_tick(
    make_env: EnvMaker,
) -> None:
    """tắt GIỮA CHỪNG (sau khi đã startScheduler) vẫn có tác dụng ngay - đọc lại mỗi tick, không chỉ lúc start

    SCHEDULER_ENABLED is hot-tunable: a safety switch that cannot really switch off is meaningless."""
    env = make_env(tuning=BASE)
    loop = loop_of(env)
    await loop.start()
    await loop.stop()  # the first boot tick may already have run: only the explicit tick below is measured

    install_tuning_provider(StaticTuningProvider({**BASE, "SCHEDULER_ENABLED": False}))  # switched off midway
    job = await env.make_job(thread_id="t-tat-giua-chung", schedule=once_due())

    await loop.run_tick(env.clinic_id, datetime.now(UTC))
    await loop.wait_idle()

    assert env.channel.sent == [], "tick phải tự bỏ qua khi cờ đã tắt, dù interval vẫn đang đăng ký"
    assert await env.deps.runs.list_runs(env.clinic_id, job.id) == []


# ============================================================================== recovery at boot


async def test_start_scheduler_boot_run_still_running_from_a_killed_worker_is_marked_interrupted(
    make_env: EnvMaker,
) -> None:
    """run còn status='running' (process cũ bị giết giữa chừng) được đánh dấu 'interrupted'

    With several workers only a run whose HEARTBEAT is stale belongs to a dead worker: the test sets it stale (the
    deps use a 120 s window)."""
    env = make_env(tuning=BASE)
    job = await env.make_job(
        thread_id="t-boot-interrupt", schedule=OnceSchedule(run_at_utc="2099-01-01T00:00:00.000Z")
    )
    run_id = await env.deps.runs.open_run(env.clinic_id, job.id)  # opened and NEVER finished: a killed worker
    env.execute(
        "UPDATE agent.job_runs SET heartbeat_at = now() - interval '5 minutes' WHERE clinic_id = :c AND id = :i",
        i=run_id,
    )
    loop = loop_of(env)

    await loop.start()
    await loop.stop()

    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.INTERRUPTED


async def test_start_scheduler_boot_a_claimed_once_reminder_whose_worker_died_is_revived_to_run_at(
    make_env: EnvMaker,
) -> None:
    """lời nhắc 'once' bị GIÀNH (next_run_at=NULL bởi clear-before-dispatch) nhưng worker bị giết trước khi markRun: next_run_at được phục hồi về run_at (I2)"""
    env = make_env(tuning=BASE)
    run_at = to_iso_z(datetime.now(UTC) + timedelta(hours=1))
    job = await env.make_job(thread_id="t-boot-revive-claimed-once", schedule=OnceSchedule(run_at_utc=run_at))
    await env.deps.jobs.set_next_run(
        env.clinic_id, job.id, None
    )  # the claim; the worker died before mark_run
    loop = loop_of(env)

    await loop.start()
    await loop.stop()

    after = await job_now(env, job.id)
    assert after.next_run_at == run_at, (
        "next_run_at phải được phục hồi về run_at - không thì lời nhắc mất vĩnh viễn"
    )
    assert after.run_count == 0, "job chưa hề chạy - phục hồi không được đụng run_count"


async def test_start_scheduler_boot_a_once_job_that_already_ran_is_not_revived_even_with_next_run_at_null(
    make_env: EnvMaker,
) -> None:
    """job 'once' ĐÃ chạy xong (hitMax -> enabled=0) thì KHÔNG bị hồi sinh dù next_run_at đang NULL (I2)"""
    env = make_env(tuning=BASE)
    run_at = to_iso_z(datetime.now(UTC) + timedelta(hours=1))
    job = await env.make_job(thread_id="t-boot-no-revive-done", schedule=OnceSchedule(run_at_utc=run_at))
    await env.deps.jobs.mark_run(env.clinic_id, job.id, JobRunStatus.OK)
    loop = loop_of(env)

    await loop.start()
    await loop.stop()

    after = await job_now(env, job.id)
    assert after.next_run_at is None, "job đã chạy xong thì next_run_at phải VẪN là null"
    assert after.enabled is False


async def test_recovery_a_live_worker_with_a_fresh_heartbeat_is_neither_interrupted_nor_has_its_job_revived(
    make_env: EnvMaker,
) -> None:
    """(nhiều worker) lượt đang chạy của worker khác còn nhịp tim mới: KHÔNG bị interrupted, job của nó KHÔNG bị hồi sinh (tránh gửi trùng)"""
    env = make_env(tuning=BASE)
    run_at = to_iso_z(datetime.now(UTC) + timedelta(hours=1))
    job = await env.make_job(thread_id="t-live-worker", schedule=OnceSchedule(run_at_utc=run_at))
    await env.deps.jobs.set_next_run(env.clinic_id, job.id, None)  # claimed by a live worker...
    await env.deps.runs.open_run(env.clinic_id, job.id, worker_id="worker-live")  # ...with a fresh heartbeat
    loop = loop_of(env)

    await loop.recover_clinic(env.clinic_id)

    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.RUNNING
    assert (await job_now(env, job.id)).next_run_at is None, (
        "job đang chạy ở worker khác, không được hồi sinh"
    )


# ================================================================================== tick rhythm


async def test_start_scheduler_processes_a_due_job_at_boot_without_waiting_for_the_first_tick_interval(
    make_env: EnvMaker,
) -> None:
    """xử lý NGAY job đã đến hạn lúc boot, không đợi hết SCHEDULER_TICK_MS đầu tiên"""
    env = make_env(tuning=BASE)
    await env.make_job(thread_id="t-boot-ngay", schedule=once_due())
    loop = loop_of(env)

    await loop.start()
    # 2000 ms is still MUCH shorter than SCHEDULER_TICK_MS=5000, so a send inside it can only come from the boot tick
    await doi_cho_so_luong(sent_count(env), 1, WaitOptions(tran_ms=2000, mo_ta="tin gửi bởi tick lúc boot"))
    await loop.stop()
    await loop.wait_idle()

    assert len(env.channel.sent) == 1, "phải gửi ngay, không chờ chu kỳ tick đầu tiên"


async def test_stop_scheduler_resets_the_state_so_start_works_again_not_locked_by_the_already_running_guard(
    make_env: EnvMaker,
) -> None:
    """reset trạng thái để startScheduler() sau đó khởi động lại được - không bị khoá bởi guard 'đã chạy rồi'"""
    env = make_env(tuning=BASE)
    loop = loop_of(env)
    await loop.start()
    await loop.stop()

    await env.make_job(thread_id="t-restart-sau-stop", schedule=once_due())  # created AFTER the stop

    await loop.start()
    await doi_cho_so_luong(
        sent_count(env), 1, WaitOptions(tran_ms=2000, mo_ta="tin của tick lúc boot lần start thứ hai")
    )
    await loop.stop()
    await loop.wait_idle()

    assert len(env.channel.sent) == 1, "start lại sau khi stop phải chạy tick ngay như một lần boot mới"


async def test_run_scheduler_tick_is_not_blocked_by_a_slow_job_and_the_next_tick_is_not_stuck_either(
    make_env: EnvMaker,
) -> None:
    """tick tự trả về nhanh dù vừa dispatch job chậm, và tick GỌI NGAY SAU đó cũng không bị 'dính' theo"""
    env = make_env(tuning=BASE)
    env.registry.register(env.clinic_id, SlowChannel(env.channel, 0.25))  # type: ignore[arg-type]
    job = await env.make_job(thread_id="t-cham", payload="việc chậm", schedule=once_due())
    loop = loop_of(env)

    t0 = time.monotonic()
    await loop.run_tick(env.clinic_id, datetime.now(UTC))
    first_ms = (time.monotonic() - t0) * 1000
    assert first_ms < 150, f"tick lần 1 phải trả về nhanh dù vừa dispatch 1 job chậm ({first_ms:.0f}ms)"

    t1 = time.monotonic()
    await loop.run_tick(env.clinic_id, datetime.now(UTC))
    second_ms = (time.monotonic() - t1) * 1000
    assert second_ms < 150, f"tick lần 2 (gọi ngay sau tick 1) cũng phải trả về nhanh ({second_ms:.0f}ms)"

    current = await last_run(env, job.id)
    assert current is not None
    assert current.status is not JobRunStatus.OK, "job chậm phải CHƯA xong ngay sau 2 lần gọi tick liên tiếp"

    async def finished() -> bool:
        run_row = await last_run(env, job.id)
        return run_row is not None and run_row.status is JobRunStatus.OK

    await doi_cho_den_khi(finished, WaitOptions(mo_ta="job chậm chạy xong"))


async def test_clear_before_dispatch_a_once_job_is_cleared_to_null_at_dispatch_a_second_tick_does_not_pick_it(
    make_env: EnvMaker,
) -> None:
    """job 'once' được clear next_run_at về NULL ngay khi dispatch - gọi tick() lần 2 ngay sau đó không nhặt lại"""
    env = make_env(tuning=BASE)
    env.registry.register(env.clinic_id, SlowChannel(env.channel, 0.2))  # type: ignore[arg-type]
    job = await env.make_job(thread_id="t-clear-once", schedule=once_due())
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, datetime.now(UTC))
    assert (await job_now(env, job.id)).next_run_at is None, "next_run_at đã phải là NULL NGAY"

    await loop.run_tick(env.clinic_id, datetime.now(UTC))
    await loop.wait_idle()

    assert len(await env.deps.runs.list_runs(env.clinic_id, job.id)) == 1, (
        "chỉ đúng 1 lần chạy dù gọi tick() 2 lần liên tiếp"
    )


# ==================================================================== preflight - Finding 1


async def test_preflight_account_not_running_job_stays_alive_and_is_sent_by_the_next_tick_once_online(
    make_env: EnvMaker,
) -> None:
    """account KHÔNG chạy: job VẪN CÒN SỐNG sau tick (enabled=1, next_run_at KHÔNG bị xoá, KHÔNG có run log) - tick sau account online lại thì gửi được

    A perfectly normal case of zca-js: the account drops its session exactly when the job becomes due."""
    env = make_env(tuning=BASE, online=False)
    job = await env.make_job(thread_id="t-account-offline", payload="nhớ họp trực tuyến", schedule=once_due())
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, datetime.now(UTC))

    offline = await job_now(env, job.id)
    assert offline.enabled is True, "job KHÔNG được tự tắt"
    assert offline.next_run_at == job.next_run_at, "next_run_at KHÔNG được đụng vào"
    assert offline.run_count == 0, "run_count KHÔNG được tăng - job chưa từng chạy thật sự"
    assert await env.deps.runs.list_runs(env.clinic_id, job.id) == [], "không ghi run nào - chưa hề dispatch"
    assert offline.last_status == "blocked", "phải thấy được trên dashboard dù chưa có run log nào"
    assert "không chạy" in (offline.last_error or "")

    env.go_online()
    await loop.run_tick(env.clinic_id, datetime.now(UTC))
    await doi_cho_so_luong(sent_count(env), 1, WaitOptions(mo_ta="tin gửi ở tick sau khi account online lại"))
    await loop.wait_idle()

    assert len(env.channel.sent) == 1, "job phải gửi được ở tick kế tiếp sau khi account online lại"
    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.OK
    assert (await job_now(env, job.id)).last_status == "ok", "dấu 'blocked' tự lành khi job chạy thật lần kế"


async def test_preflight_thread_with_the_bot_disabled_job_stays_alive_without_mark_run(
    make_env: EnvMaker,
) -> None:
    """thread bot_enabled=0: job VẪN CÒN SỐNG sau tick, không markRun - đúng bất biến như ca account offline"""
    env = make_env(tuning=BASE)
    job = await env.make_job(thread_id="t-bot-tat-tick", schedule=once_due())
    env.set_bot_enabled("t-bot-tat-tick", False)
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, datetime.now(UTC))

    after = await job_now(env, job.id)
    assert after.enabled is True
    assert after.next_run_at == job.next_run_at
    assert after.run_count == 0
    assert await env.deps.runs.list_runs(env.clinic_id, job.id) == []


async def test_preflight_a_job_blocked_right_at_the_tick_resets_delivery_attempts(make_env: EnvMaker) -> None:
    """job bị chặn NGAY Ở TICK (account offline) phải RESET delivery_attempts - đây là đường PHỔ BIẾN nhất trong sản xuất (Mục 1, vòng 4)

    Without it: one failed send, the account offline for days, then a failed send 2 and 3 WEEKS apart still add up
    to 3 and a 'once' job is switched off - a reminder lost although it never failed 3 times CONSECUTIVELY."""
    env = make_env(tuning=BASE, online=False)
    job = await env.make_job(thread_id="t-tick-block-reset-delivery-attempts", schedule=once_due())
    await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id)
    await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id)

    await loop_of(env).run_tick(env.clinic_id, datetime.now(UTC))

    assert await env.deps.attempts.get_delivery_attempts(env.clinic_id, job.id) == 0


# ==================================================== the daily cap blocked AT THE TICK (Item 1)


async def reserve_all(env: Env, thread: str, now: datetime) -> None:
    await env.deps.guard.reserve_proactive_slot(env.clinic_id, f"{ACC}:{thread}", TZ, now, 1)


async def test_cap_at_tick_a_once_job_is_pushed_to_the_configured_hour_of_tomorrow_one_notice_no_mark_run(
    make_env: EnvMaker,
) -> None:
    """job 'once' bị trần chặn: next_run_at đẩy sang GIỜ CẤU HÌNH (mặc định 8h) của NGÀY MAI (không phải 00:00, không phải mốc cũ, không phải NULL), đúng 1 tin thông báo, KHÔNG markRun"""
    env = make_env(tuning={**BASE, "SCHEDULER_MAX_PROACTIVE_PER_DAY": 1})
    thread = "t-tick-tran-once"
    now = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)  # 10:00 Vietnam on 01/08
    env.make_thread(thread)
    await reserve_all(env, thread, now)  # take every slot BEFORE the tick runs
    job = await env.make_job(thread_id=thread, schedule=OnceSchedule(run_at_utc=to_iso_z(now)))
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, now)
    await doi_cho_so_luong(sent_count(env), 1, WaitOptions(mo_ta="tin thông báo chạm trần"))
    await loop.wait_idle()

    assert len(env.channel.sent) == 1, "chỉ có ĐÚNG 1 tin - câu thông báo chạm trần, không phải payload gốc"
    assert env.channel.sent[0].text != job.payload
    after = await job_now(env, job.id)
    assert after.run_count == 0, "chưa markRun - job chưa 'chạy' thật sự"
    assert after.enabled is True
    assert after.next_run_at == deferred_run_at_utc(TZ, 8, now)
    # 8:00 Vietnam on 02/08 = 01:00Z 02/08 - NOT 17:00Z 01/08 (00:00 Vietnam, the midnight of the earlier version)
    assert after.next_run_at == "2026-08-02T01:00:00.000Z", (
        "phải là 8h sáng giờ VN ngày mai, KHÔNG dồn về nửa đêm"
    )
    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.SKIPPED
    assert "chạm trần" in run_row.detail


async def test_cap_at_tick_the_right_to_announce_uses_the_day_key_of_the_simulated_now_not_the_real_day(
    make_env: EnvMaker,
) -> None:
    """giành quyền báo trần dùng ĐÚNG day-key của `now` giả lập, không lệch sang ngày THẬT lúc chạy test (Mục 3, vòng 4)"""
    env = make_env(tuning={**BASE, "SCHEDULER_MAX_PROACTIVE_PER_DAY": 1})
    thread = "t-tick-tran-day-key-dung"
    now = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)  # far from the real day of the test run
    env.make_thread(thread)
    await reserve_all(env, thread, now)
    await env.make_job(thread_id=thread, schedule=OnceSchedule(run_at_utc=to_iso_z(now)))
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, now)
    await loop.wait_idle()

    counter = await env.deps.counters.get_proactive_counter(
        env.clinic_id, f"{ACC}:{thread}", today_key(TZ, now)
    )
    assert counter.notice_sent is True, "quyền báo phải ghi ĐÚNG day-key của `now` giả lập đang xử lý"


async def test_cap_at_tick_an_every_job_keeps_its_natural_next_slot_not_pushed_to_tomorrow_like_once(
    make_env: EnvMaker,
) -> None:
    """job 'every' bị trần chặn: next_run_at GIỮ mốc kế TỰ NHIÊN (đã tính sẵn bởi clear-before-dispatch) - KHÔNG bị đẩy qua ngày mai như 'once'"""
    env = make_env(tuning={**BASE, "SCHEDULER_MAX_PROACTIVE_PER_DAY": 1})
    thread = "t-tick-tran-every"
    now = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)
    env.make_thread(thread)
    await reserve_all(env, thread, now)
    job = await env.make_job(thread_id=thread, schedule=EverySchedule(minutes=30), now=now)
    await env.deps.jobs.set_next_run(env.clinic_id, job.id, to_iso_z(now))  # force it due exactly at ``now``
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, now)
    await loop.wait_idle()

    after = await job_now(env, job.id)
    assert after.next_run_at == to_iso_z(now + timedelta(minutes=30)), "mốc kế every 30 phút TỰ NHIÊN"
    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.SKIPPED


async def test_cap_at_tick_a_kind_agent_job_creates_no_agent_turn_the_llm_never_ran(
    make_env: EnvMaker,
) -> None:
    """job kind='agent' bị trần chặn: KHÔNG tạo agent_turns nào - lượt LLM chưa từng chạy, tránh đốt token cho job chắc chắn không gửi được"""
    env = make_env(tuning={**BASE, "SCHEDULER_MAX_PROACTIVE_PER_DAY": 1})
    thread = "t-tick-tran-agent"
    now = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)
    env.make_thread(thread)
    await reserve_all(env, thread, now)
    job = await env.make_job(
        thread_id=thread, kind=JobKind.AGENT, schedule=EverySchedule(minutes=30), now=now
    )
    await env.deps.jobs.set_next_run(env.clinic_id, job.id, to_iso_z(now))
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, now)
    await loop.wait_idle()

    assert env.usage.opened == [], "không được tạo agent_turns nào - lượt LLM chưa từng chạy"
    assert env.engine.requests == []
    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.SKIPPED


async def test_cap_at_tick_a_deferred_once_job_resent_keeps_the_label_with_the_original_time_not_the_deferred_one(
    make_env: EnvMaker,
) -> None:
    """job 'once' bị trần chặn rồi được gửi lại: nhãn '(nhắc trễ, lịch gốc HH:MM)' phải giữ ĐÚNG GIỜ GỐC, không phải giờ hoãn (Mục 3, vòng 3)"""
    env = make_env(tuning={**BASE, "SCHEDULER_MAX_PROACTIVE_PER_DAY": 1})
    thread = "t-tick-tran-once-nhac-tre"
    run_at = datetime(2026, 8, 1, 16, 50, tzinfo=UTC)  # 23:50 Vietnam on 01/08
    env.make_thread(thread)
    await reserve_all(env, thread, run_at)  # same Vietnam day as run_at
    job = await env.make_job(
        thread_id=thread, payload="Nhớ họp", schedule=OnceSchedule(run_at_utc=to_iso_z(run_at))
    )
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, run_at)  # blocked by the cap, pushed to 8:00 tomorrow
    await doi_cho_so_luong(sent_count(env), 1, WaitOptions(mo_ta="tin thông báo chạm trần"))
    await loop.wait_idle()
    assert len(env.channel.sent) == 1, "chỉ có tin thông báo chạm trần ở lượt này"

    deferred = await job_now(env, job.id)
    assert deferred.run_at == to_iso_z(run_at), (
        "run_at (mốc GỐC) KHÔNG được đụng vào dù next_run_at đã bị đẩy"
    )
    assert deferred.next_run_at is not None

    # The notice of tick 1 consumed a slot of the day of ``run_at``; the new tick is on the NEXT day, but reset to
    # isolate exactly what this test guards (the label), as the original did.
    await env.deps.guard.reset_proactive_send_counters(env.clinic_id)

    next_tick = datetime.fromisoformat(deferred.next_run_at.replace("Z", "+00:00"))
    await loop.run_tick(env.clinic_id, next_tick)
    await doi_cho_so_luong(sent_count(env), 2, WaitOptions(mo_ta="tin nhắc trễ"))
    await loop.wait_idle()

    assert [p.text for p in env.channel.sent][1] == "(nhắc trễ, lịch gốc 23:50) Nhớ họp", (
        "nhãn nhắc trễ phải giữ ĐÚNG giờ gốc 23:50 (run_at) - dùng next_run_at đã bị đẩy sẽ MẤT nhãn"
    )


async def test_cap_at_tick_n_jobs_of_the_same_thread_blocked_in_one_tick_send_exactly_one_notice(
    make_env: EnvMaker,
) -> None:
    """N job CÙNG thread cùng bị chặn trong 1 tick (gap khác 0): chỉ ĐÚNG 1 tin thông báo, KHÔNG nhân bản theo số job (Mục 1, vòng 3)

    The gap must be NON-ZERO - exactly the case that produced the bug: the send path (the notice too) waits the gap
    before committing "announced", which opened a window long enough for N other jobs to think they were first."""
    env = make_env(tuning={**BASE, "SCHEDULER_MAX_PROACTIVE_PER_DAY": 1, "SCHEDULER_SEND_GAP_MS": 50})
    thread = "t-tick-nhieu-job-cham-tran"
    now = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)
    env.make_thread(thread)
    await reserve_all(env, thread, now)
    for n in (1, 2, 3):
        await env.make_job(thread_id=thread, name=f"job-{n}", schedule=OnceSchedule(run_at_utc=to_iso_z(now)))
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, now)
    await loop.wait_idle()

    sent_here = [p for p in env.channel.sent if p.thread_id == thread]
    assert len(sent_here) == 1, f"chỉ được ĐÚNG 1 tin thông báo dù có 3 job cùng bị chặn ({len(sent_here)})"


# ================================================================================== skip-forward / run-late


async def test_skip_forward_every_later_than_the_grace_skips_the_slot_without_sending_next_run_jumps_to_the_future(
    make_env: EnvMaker,
) -> None:
    """every trễ quá cửa sổ grace: bỏ lượt (không gửi gì), ghi run 'skipped', next_run_at nhảy tới TƯƠNG LAI"""
    env = make_env(tuning=BASE)
    now = datetime.now(UTC)
    job = await env.make_job(
        thread_id="t-skip-forward", schedule=EverySchedule(minutes=30), now=now - timedelta(seconds=2000)
    )
    # every 30 minutes -> grace = half a period = 900 s = 15 minutes; set next_run_at 2000 s late (> 900 s)
    await env.deps.jobs.set_next_run(env.clinic_id, job.id, to_iso_z(now - timedelta(seconds=2000)))

    await loop_of(env).run_tick(env.clinic_id, now)

    assert env.channel.sent == [], "skip-forward không được gửi gì"
    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.SKIPPED
    assert "grace" in run_row.detail
    updated = await job_now(env, job.id)
    assert updated.next_run_at is not None
    assert datetime.fromisoformat(updated.next_run_at.replace("Z", "+00:00")) > now, (
        "next_run_at phải nhảy tới tương lai"
    )


async def test_run_late_once_later_than_the_grace_still_dispatches_with_the_late_reminder_label(
    make_env: EnvMaker,
) -> None:
    """once trễ quá grace: vẫn dispatch (không phải skip-forward), text gửi đi có tiền tố '(nhắc trễ, lịch gốc HH:MM)'"""
    env = make_env(tuning=BASE)
    # 08:00Z = 15:00 Vietnam; 5 minutes late against "now" 08:05Z, beyond the 1 minute grace of the test
    job = await env.make_job(
        thread_id="t-run-late",
        payload="Nhớ họp",
        schedule=OnceSchedule(run_at_utc="2026-08-01T08:00:00.000Z"),
    )
    now = datetime(2026, 8, 1, 8, 5, tzinfo=UTC)
    loop = loop_of(env)

    await loop.run_tick(env.clinic_id, now)
    await doi_cho_so_luong(sent_count(env), 1, WaitOptions(mo_ta="tin nhắc trễ"))
    await loop.wait_idle()

    assert len(env.channel.sent) == 1
    assert env.channel.sent[0].text == "(nhắc trễ, lịch gốc 15:00) Nhớ họp"
    run_row = await last_run(env, job.id)
    assert run_row is not None
    assert run_row.status is JobRunStatus.OK


# ======================================================================= several workers (new)


def second_worker(env: Env, name: str) -> SchedulerDeps:
    """Another worker process over the SAME database: its own locks, queue and worker id, the same channel."""
    return SchedulerDeps(
        db=env.db,
        channels=env.registry,
        accounts=env.accounts,
        agents=env.agents,
        history=env.history,  # type: ignore[arg-type]
        usage=env.usage,  # type: ignore[arg-type]
        engine=env.engine,
        outbound=FakeOutbound(),
        thread_lock=InMemoryThreadLock(),
        clinic_actions=env.actions,  # type: ignore[arg-type]
        wrap_untrusted=env.deps.wrap_untrusted,
        worker_id=name,
    )


async def test_several_workers_ticking_the_same_clinic_at_once_run_every_due_job_exactly_once(
    make_env: EnvMaker,
) -> None:
    """(nhiều worker) 3 worker quét CÙNG lúc 30 job đến hạn: mỗi job chạy ĐÚNG 1 lần - claim nguyên tử, không chạy đôi

    No lock is shared between the workers (each has its own in-process lock), so the only thing that can stop a
    double run is the compare-and-swap of ``claim_due_job`` in Postgres."""
    env = make_env(tuning=BASE)
    jobs = [
        await env.make_job(thread_id=f"t-multi-{n}", payload=f"tin {n}", schedule=once_due())
        for n in range(30)
    ]
    loops = [
        SchedulerLoop(env.deps),
        SchedulerLoop(second_worker(env, "worker-b")),
        SchedulerLoop(second_worker(env, "worker-c")),
    ]
    now = datetime.now(UTC)

    await asyncio.gather(*(lp.run_tick(env.clinic_id, now) for lp in loops))
    for lp in loops:
        await lp.wait_idle()

    texts = sorted(p.text for p in env.channel.sent)
    assert texts == sorted(f"tin {n}" for n in range(30)), "mỗi tin phải ra đúng 1 lần"
    for job in jobs:
        runs = await env.deps.runs.list_runs(env.clinic_id, job.id)
        assert len(runs) == 1, f"job {job.id} có {len(runs)} lượt chạy"
        assert runs[0].status is JobRunStatus.OK
        assert (await job_now(env, job.id)).run_count == 1


async def test_several_workers_never_exceed_the_daily_cap_when_racing_for_the_same_thread(
    make_env: EnvMaker,
) -> None:
    """(nhiều worker) 3 worker tranh nhau 12 job CÙNG thread, trần 5: đúng 5 tin job + tối đa 1 thông báo trần"""
    env = make_env(tuning={**BASE, "SCHEDULER_MAX_PROACTIVE_PER_DAY": 5})
    now = datetime.now(UTC)
    for n in range(12):
        await env.make_job(thread_id="t-multi-cap", payload=f"nhắc {n}", schedule=once_due())
    loops = [
        SchedulerLoop(env.deps),
        SchedulerLoop(second_worker(env, "worker-b")),
        SchedulerLoop(second_worker(env, "worker-c")),
    ]

    await asyncio.gather(*(lp.run_tick(env.clinic_id, now) for lp in loops))
    for lp in loops:
        await lp.wait_idle()

    job_messages = [p for p in env.channel.sent if p.text.startswith("nhắc ")]
    notices = [p for p in env.channel.sent if p.text.startswith("Hôm nay cuộc trò chuyện này")]
    assert len(job_messages) == 5, f"trần 5 bị vượt: {len(job_messages)}"
    assert len(notices) <= 1, "câu thông báo chạm trần không được nhân bản qua các worker"


async def test_tick_lease_only_one_worker_scans_a_clinic_per_tick_without_losing_or_duplicating_a_job(
    make_env: EnvMaker,
) -> None:
    """(Redis) hợp đồng cho thuê tick: chỉ 1 worker quét 1 phòng khám mỗi tick; job vẫn chạy đúng 1 lần"""
    env = make_env(tuning=BASE)
    job = await env.make_job(thread_id="t-lease", payload="tin lease", schedule=once_due())
    backend = InMemoryLockBackend()
    lease_a = TickLease(backend, lambda: 5000)
    lease_b = TickLease(backend, lambda: 5000)
    loop_a = loop_of(env, tick_lease=lease_a)
    loop_b = loop_of(env, tick_lease=lease_b)
    now = datetime.now(UTC)

    await loop_b.run_tick_all(now)  # B holds the lease for this tick
    await loop_a.run_tick_all(now)  # A is told to skip the clinic
    await loop_a.wait_idle()
    await loop_b.wait_idle()

    assert [p.text for p in env.channel.sent] == ["tin lease"]
    assert len(await env.deps.runs.list_runs(env.clinic_id, job.id)) == 1


async def test_tick_lease_fails_open_when_the_lock_backend_is_down_the_atomic_claim_still_protects_the_job(
    make_env: EnvMaker,
) -> None:
    """(Redis) backend khoá hỏng: lease mở (fail open) - tính đúng đắn nằm ở claim SQL, job vẫn chạy đúng 1 lần"""

    class BrokenBackend:
        async def acquire(self, key: str, ttl_ms: int) -> str | None:
            raise ConnectionError("redis down")

        async def release(self, key: str, token: str) -> None:
            raise ConnectionError("redis down")

        async def remaining_ms(self, key: str) -> int:
            raise ConnectionError("redis down")

    env = make_env(tuning=BASE)
    await env.make_job(thread_id="t-lease-open", payload="tin fail-open", schedule=once_due())
    lease = TickLease(BrokenBackend(), lambda: 5000)
    loops = [loop_of(env, tick_lease=lease), loop_of(env, tick_lease=lease)]
    now = datetime.now(UTC)

    await asyncio.gather(*(lp.run_tick_all(now) for lp in loops))
    for lp in loops:
        await lp.wait_idle()

    assert [p.text for p in env.channel.sent] == ["tin fail-open"]

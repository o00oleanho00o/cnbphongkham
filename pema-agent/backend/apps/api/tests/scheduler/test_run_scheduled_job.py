# ported from: src/scheduler/run-scheduled-job.test.ts (+ scheduled-job-send.test.ts)
"""Integration tests for ``run_scheduled_job``: the REAL database (jobs, run log, counters) as the ``agent_worker``
role, the REAL guard and stores; only the network (a ``FakeChannel``), the LLM (``FakeEngine``) and the outbound
pipeline of package C2 (``FakeOutbound``) are fakes. This checks the real wiring between the modules, not
isolated mocks.

Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Differences forced by the port, all in the fakes: the model is scripted through ``FakeEngine`` (no
``MockLanguageModel``); ``FakeOutbound`` strips bold markers into style spans but has no inline-code style, so the
"`9h`" span of the original is not asserted; the "tools in a scheduled turn" test belongs to D4/D1 (this module
only passes ``isolated=True``).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from pema.scheduler.run_scheduled_job import RunScheduledJobOptions, run_scheduled_job
from pema.scheduler.testing_env import ACC, Env
from pema.shared.zone_time import today_key
from pema_contracts.agent_turn import TurnSource
from pema_contracts.channel import SendResult, SendStatus, ThreadKind
from pema_contracts.errors import ErrorCode
from pema_contracts.scheduler import EverySchedule, JobKind, JobRunStatus, ScheduledJob
from pema_contracts.turn_errors import AgentTurnError, ProviderErrorKind

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
THREAD = "t-run-job"
TZ = "Asia/Ho_Chi_Minh"


async def run(
    env: Env,
    job: ScheduledJob,
    *,
    late: bool = False,
    scheduled_for: str | None = None,
    now: datetime | None = None,
) -> None:
    await run_scheduled_job(
        env.deps,
        job,
        RunScheduledJobOptions(
            late=late,
            scheduled_for=scheduled_for or job.next_run_at or "2026-08-01T08:00:00.000Z",
            now=now or datetime.now(UTC),
        ),
    )


async def last_run(env: Env, job_id: str):
    return (await env.deps.runs.list_runs(env.clinic_id, job_id, 1))[0]


async def job_now(env: Env, job_id: str) -> ScheduledJob:
    job = await env.deps.jobs.get_job_unscoped(env.clinic_id, job_id)
    assert job is not None
    return job


def reject(detail: str) -> SendResult:
    return SendResult(status=SendStatus.REJECTED, error_code=ErrorCode.CHANNEL_UNAVAILABLE, detail=detail)


def sent_texts(env: Env) -> list[str]:
    return [p.text for p in env.channel.sent]


# ============================================================================== kind=message


async def test_run_scheduled_job_kind_message_sends_0_agent_turns_writes_history_run_ok(
    make_env: EnvMaker,
) -> None:
    """gửi được, 0 lượt agent, ghi history + run 'ok'"""
    env = make_env()
    job = await env.make_job(thread_id=THREAD, payload="Nhắc họp lúc 3h chiều nay")

    await run(env, job)

    assert sent_texts(env) == ["Nhắc họp lúc 3h chiều nay"]
    assert env.channel.sent[0].thread_id == THREAD
    assert env.usage.opened == [], "job kind=message không được tạo agent_turns nào"
    assert env.history.contents(ACC, THREAD)[-1] == "Nhắc họp lúc 3h chiều nay"
    assert (await last_run(env, job.id)).status is JobRunStatus.OK
    updated = await job_now(env, job.id)
    assert updated.last_status == "ok"
    assert updated.run_count == 1


async def test_run_scheduled_job_account_not_running_skips_at_once_sends_nothing_run_skipped_with_reason(
    make_env: EnvMaker,
) -> None:
    """account không chạy (chưa attach) thì skip ngay, không gửi gì, run 'skipped' kèm lý do"""
    env = make_env(online=False)
    job = await env.make_job(thread_id="t-bat-ky")

    await run(env, job)

    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert "không chạy" in run_row.detail
    assert env.channel.sent == []


async def test_run_scheduled_job_blocked_because_the_account_is_not_running_resets_delivery_attempts(
    make_env: EnvMaker,
) -> None:
    """bị chặn vì account không chạy phải RESET delivery_attempts - lượt này kết thúc KHÔNG PHẢI vì gửi hỏng (Mục 4, vòng 3)"""
    env = make_env(online=False)
    job = await env.make_job(thread_id="t-bat-ky-2")
    await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id)
    await env.deps.attempts.increment_delivery_attempts(
        env.clinic_id, job.id
    )  # 2 failed sends scattered earlier

    await run(env, job)

    assert await env.deps.attempts.get_delivery_attempts(env.clinic_id, job.id) == 0


async def test_run_scheduled_job_failed_send_retries_at_most_3_times_before_a_real_error_never_writes_history(
    make_env: EnvMaker,
) -> None:
    """gửi hỏng (zca-js ném lỗi) thì thử lại tối đa 3 lần trước khi ghi 'error' thật (Mục 2) - KHÔNG ghi history bất kỳ lần nào"""
    env = make_env()
    env.channel.reject_with = reject("mạng rớt giữa chừng")
    job = await env.make_job(thread_id=THREAD, payload="Tin sẽ không bao giờ tới nơi")
    history_before = len(env.history.messages)

    # Attempts 1 and 2: the send failed but the 3 are not reached - the job must LIVE (no mark_run)
    for attempt in (1, 2):
        await run(env, job)
        alive = await job_now(env, job.id)
        assert alive.run_count == 0, (
            f"lần thử {attempt}: run_count KHÔNG được tăng - job chưa 'chạy xong' thật sự"
        )
        assert alive.last_error is None, (
            f"lần thử {attempt}: last_error KHÔNG được ghi - job còn cơ hội thử lại"
        )
        assert alive.enabled is True, f"lần thử {attempt}: job KHÔNG được tự tắt"
        assert "thử lại lần" in (await last_run(env, job.id)).detail

    # Attempt 3: the maximum is reached - NOW the run slot is spent and the real error written
    await run(env, job)
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.ERROR
    assert "mạng rớt giữa chừng" in run_row.detail
    dead = await job_now(env, job.id)
    assert dead.run_count == 1, "lần thứ 3 mới thật sự tính là 1 lần chạy"
    assert "mạng rớt giữa chừng" in (dead.last_error or "")
    assert len(env.history.messages) == history_before, "gửi hỏng thì KHÔNG được ghi thêm gì vào history"


async def test_run_scheduled_job_fails_once_then_succeeds_delivery_attempts_reset_not_accumulated_across_runs(
    make_env: EnvMaker,
) -> None:
    """gửi hỏng lần đầu rồi THÀNH CÔNG lần sau: delivery_attempts phải reset - không cộng dồn qua các lượt chạy KHÁC NHAU"""
    env = make_env()
    env.channel.reject_with = reject("lỗi mạng thoáng qua")
    job = await env.make_job(thread_id=THREAD, payload="Sẽ gửi được ở lần thứ 2")

    await run(env, job)
    assert await env.deps.attempts.get_delivery_attempts(env.clinic_id, job.id) == 1, (
        "lần 1 hỏng phải tăng delivery_attempts lên 1"
    )

    env.channel.reject_with = None
    await run(env, job)

    assert (await last_run(env, job.id)).status is JobRunStatus.OK
    assert env.history.contents(ACC, THREAD)[-1] == "Sẽ gửi được ở lần thứ 2", (
        "lần 2 phải THẬT SỰ tới nơi (có ghi history)"
    )
    assert await env.deps.attempts.get_delivery_attempts(env.clinic_id, job.id) == 0, (
        "gửi được rồi thì bộ đếm phải reset về 0"
    )


async def test_run_scheduled_job_late_true_prefixes_the_payload_with_the_late_reminder_label(
    make_env: EnvMaker,
) -> None:
    """late=true: nguyên văn payload được thêm tiền tố '(nhắc trễ, lịch gốc HH:MM)'"""
    env = make_env(tuning={"BOT_TIMEZONE": TZ})
    job = await env.make_job(thread_id=THREAD, payload="Nhớ họp")

    # 08:00Z = 15:00 Vietnam time (the job pins no time zone of its own)
    await run(env, job, late=True, scheduled_for="2026-08-01T08:00:00.000Z")

    assert sent_texts(env)[0] == "(nhắc trễ, lịch gốc 15:00) Nhớ họp"


async def test_run_scheduled_job_daily_cap_message_11_is_blocked_with_exactly_1_notice_message_12_is_silent(
    make_env: EnvMaker,
) -> None:
    """trần ngày (mặc định 10/ngày): tin thứ 11 bị chặn kèm ĐÚNG 1 câu thông báo, tin thứ 12 im lặng"""
    env = make_env()
    thread = "t-cham-tran-runjob"
    job = await env.make_job(thread_id=thread, payload="nhắc lặp lại", schedule=EverySchedule(minutes=30))
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)

    for i in range(10):
        await run(env, job, now=now)
        assert (await last_run(env, job.id)).status is JobRunStatus.OK, (
            f"tin thứ {i + 1} (trong trần 10) phải gửi được"
        )
    assert len(env.channel.sent) == 10

    # Message 11: cap reached -> blocked + 1 extra NOTICE message (not the payload)
    await run(env, job, now=now)
    assert (await last_run(env, job.id)).status is JobRunStatus.SKIPPED, "tin thứ 11 phải bị chặn"
    assert len(env.channel.sent) == 11, "phải có thêm đúng 1 tin - câu thông báo chạm trần"
    assert sent_texts(env)[-1] != "nhắc lặp lại", "tin thêm phải là câu THÔNG BÁO, không phải payload gốc"
    assert await env.deps.attempts.get_delivery_attempts(env.clinic_id, job.id) == 0, (
        "bị chặn vì trần ngày phải reset delivery_attempts"
    )

    # Message 12 the same day: still blocked but the notice is NOT repeated
    await run(env, job, now=now)
    assert (await last_run(env, job.id)).status is JobRunStatus.SKIPPED
    assert len(env.channel.sent) == 11, "câu thông báo không được lặp lại trong cùng ngày"


async def test_run_scheduled_job_personal_channel_still_sends_styles_guard_against_fixing_one_channel_breaking_another(
    make_env: EnvMaker,
) -> None:
    """kênh CÁ NHÂN vẫn gửi kèm `styles` - chốt chống 'sửa cho kênh bot làm hỏng kênh đang chạy'"""
    env = make_env()
    job = await env.make_job(thread_id=THREAD, payload="**Nhắc họp** lúc 3h")

    await run(env, job)

    assert len(env.channel.sent) == 1
    assert env.channel.sent[0].text == "Nhắc họp lúc 3h", "markdown phải được BÓC khỏi chữ, không gửi thô"
    assert len(env.channel.sent[0].styles) > 0, "kênh cá nhân mất `styles` - câu trả lời ra Zalo phẳng lì"


async def test_run_scheduled_job_a_message_job_payload_also_goes_through_the_formatting_layer(
    make_env: EnvMaker,
) -> None:
    """payload của job kind='message' cũng qua lớp định dạng"""
    env = make_env()
    job = await env.make_job(thread_id=THREAD, payload="**Nhắc**: họp lúc `9h` nhé")

    await run(env, job)

    sent = env.channel.sent[-1]
    assert sent.text == "Nhắc: họp lúc 9h nhé", "dấu markdown không được lọt ra chữ"
    spans = [sent.text[s.start : s.start + s.length] for s in sent.styles]
    assert spans == ["Nhắc"], "phải tô đậm đúng đoạn đã đánh dấu"


async def test_run_scheduled_job_a_payload_that_leaks_the_system_prompt_is_never_sent_and_keeps_the_run_slot(
    make_env: EnvMaker,
) -> None:
    """(nhánh sanitize của runMessageJob) payload dạng system prompt KHÔNG được gửi và KHÔNG lùi về bản thô; giữ suất chạy"""
    env = make_env()
    job = await env.make_job(
        thread_id=THREAD, payload="Chỉ dẫn: Quy tắc an toàn (tuyệt đối, không có ngoại lệ): ..."
    )

    await run(env, job)

    assert env.channel.sent == []
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert "lộ chỉ dẫn nội bộ" in run_row.detail
    after = await job_now(env, job.id)
    assert after.enabled is True
    assert after.next_run_at == job.next_run_at, "`once` phải được phục hồi ĐÚNG mốc cũ"
    # the slot is NOT taken any more: sanitising happens BEFORE the guard (a leak no longer leaves a slot behind)
    assert env.row("SELECT count(*) FROM agent.proactive_send_counters WHERE clinic_id = :c") == (0,)


# ----------------------------------------------------------------- sendAndConclude (scheduled-job-send.test)


async def test_send_and_conclude_a_failure_after_a_successful_send_is_not_taken_for_not_sent_no_duplicate(
    make_env: EnvMaker,
) -> None:
    """lỗi ném ra SAU KHI đã gửi thành công KHÔNG được coi là chưa gửi (Mục 2, vòng 4)

    The original dropped the ``messages`` table so the history append raised a real SQL error; here the history
    store raises. The message ALREADY left (exactly once); the run is 'error' for the dashboard; ``next_run_at``
    is NOT restored for a retry (a retry would send the same content up to 3 times)."""
    env = make_env()
    env.history.fail = True
    job = await env.make_job(thread_id=THREAD, payload="Tin này phải ra đúng 1 lần, không được lặp lại")
    scheduled_for = job.next_run_at
    assert scheduled_for is not None

    await run(env, job, scheduled_for=scheduled_for)

    assert sent_texts(env) == ["Tin này phải ra đúng 1 lần, không được lặp lại"], "tin phải ra đúng 1 lần"
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.ERROR, "phải ghi 'error' - ghi history hỏng thật sự xảy ra"
    assert "history store is down" in run_row.detail
    after = await job_now(env, job.id)
    assert after.next_run_at != scheduled_for, (
        "KHÔNG được quay lại đúng scheduledFor - đó là dấu hiệu đã rơi vào đường retry"
    )
    assert after.next_run_at is None, "once đã mark_run (maxRuns=1, hitMax) nên next_run_at phải là NULL"
    assert after.run_count == 1, "phải mark_run - job ĐÃ chạy thật"
    assert after.enabled is False


async def test_send_and_conclude_a_failed_send_refunds_the_slot_to_the_day_of_the_run_not_the_real_day(
    make_env: EnvMaker,
) -> None:
    """gửi hỏng ở lượt có `now` giả lập: suất hoàn về ngày của LƯỢT, không phải ngày thật lúc chạy"""
    env = make_env()
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)  # deliberately far from the real day
    day_of_run = today_key(TZ, now)
    real_day = today_key(TZ, datetime.now(UTC))
    assert day_of_run != real_day, "mốc giả lập phải khác ngày thật thì ca này mới có nghĩa"
    env.channel.reject_with = reject("Zalo từ chối")
    job = await env.make_job(thread_id=THREAD, payload="tin này sẽ gửi hỏng")
    scope = f"{ACC}:{THREAD}"

    await run(env, job, now=now)

    counters = env.deps.counters
    assert (await counters.get_proactive_counter(env.clinic_id, scope, day_of_run)).count == 0, (
        "gửi hỏng thì suất của NGÀY LƯỢT phải được hoàn"
    )
    assert (await counters.get_proactive_counter(env.clinic_id, scope, real_day)).count == 0, (
        "lượt này KHÔNG được đụng vào bộ đếm của ngày THẬT"
    )


# ====================================================================== thread lock and cap counting


async def test_run_scheduled_job_does_not_hold_the_thread_lock_while_waiting_in_the_global_queue(
    make_env: EnvMaker,
) -> None:
    """tin THẬT trên CÙNG thread chạy được ngay dù job đang xếp hàng ở hàng đợi toàn cục (Finding 3)"""
    env = make_env()
    job = await env.make_job(thread_id=THREAD, payload="chậm vì hàng đợi toàn cục")

    # Occupy the global queue with a "slow" job of 200 ms - the job dispatched right after must QUEUE behind it
    occupier = asyncio.create_task(env.deps.queue.enqueue_proactive_send(lambda: asyncio.sleep(0.2)))
    job_run = asyncio.create_task(run(env, job))
    await asyncio.sleep(
        0.05
    )  # enough for the job to reach the queue, much shorter than the 200 ms of the queue

    # While the job is STILL waiting in the global queue, a REAL message of the SAME thread must run AT ONCE: the
    # InMemoryThreadLock raises when the key is already held, so the job cannot be holding it
    t0 = time.monotonic()
    async with env.deps.thread_lock.hold(ACC, THREAD):
        entered = True
    elapsed = (time.monotonic() - t0) * 1000

    assert entered is True
    assert elapsed < 100, (
        f"tin thật phải chạy gần như ngay, không đợi job xong hàng đợi toàn cục ({elapsed:.0f}ms)"
    )
    await asyncio.gather(occupier, job_run)


async def test_run_scheduled_job_cap_counts_per_message_one_long_run_cut_into_parts_counts_all_parts(
    make_env: EnvMaker,
) -> None:
    """1 lượt bị cắt thành nhiều tin thì trần cộng đúng SỐ TIN thật sự gửi, không phải cố định 1 (Finding 4)"""
    env = make_env()
    long_text = "Nội dung báo cáo hôm nay khá dài, cần trình bày đầy đủ từng mục. " * 60
    job = await env.make_job(thread_id="t-dai-tin", payload=long_text)
    now = datetime.now(UTC)
    day_key = today_key(TZ, now)

    await run(env, job, now=now)

    assert (await last_run(env, job.id)).status is JobRunStatus.OK
    counter = await env.deps.counters.get_proactive_counter(env.clinic_id, f"{ACC}:t-dai-tin", day_key)
    assert counter.count >= 2, (
        f"payload dài phải cắt thành >= 2 tin, bộ đếm phải tăng đúng bằng đó ({counter.count})"
    )
    assert counter.count == len(env.channel.sent)


# ================================================================================= kind=agent


async def test_run_scheduled_job_kind_agent_sends_agent_turn_source_schedule_trace_run_ok(
    make_env: EnvMaker,
) -> None:
    """chạy được (có nội dung) -> gửi + agent_turns.source='schedule' + có trace + run 'ok'"""
    env = make_env()
    env.engine.script = ["Hôm nay có 3 tin đáng chú ý về AI."]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Tóm tắt tin công nghệ hôm nay")

    await run(env, job)

    assert sent_texts(env)[-1] == "Hôm nay có 3 tin đáng chú ý về AI."
    assert len(env.usage.opened) == 1, "phải có đúng 1 dòng agent_turns mới"
    turn_id, source = env.usage.opened[0]
    assert source is TurnSource.SCHEDULE
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.OK
    assert run_row.turn_id == turn_id, "run phải nối được sang agent_turns qua turn_id"
    assert len(env.usage.traces[turn_id]) == 1, "phải có trace cho lượt vừa chạy (đúng 1 lần)"
    assert len(env.usage.finished[turn_id]) == 1
    assert env.history.contents(ACC, THREAD)[-1] == "Hôm nay có 3 tin đáng chú ý về AI."


async def test_run_scheduled_job_kind_agent_runs_an_isolated_turn_with_source_schedule(
    make_env: EnvMaker,
) -> None:
    """isolated:true xuyên suốt tới engine (lọc add_reaction/save_memory là việc của D4/D1)"""
    env = make_env()
    env.engine.script = ["ok"]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Báo cáo gì đó")

    await run(env, job)

    request = env.engine.requests[0]
    assert request.isolated is True
    assert request.source is TurnSource.SCHEDULE
    assert request.scheduled_job_id == job.id
    assert request.batch[0].msg_id == "", "không có tin thật nào kích hoạt lượt này"
    assert "CHẠY THEO LỊCH" in request.batch[0].text


async def test_run_scheduled_job_kind_agent_silent_sends_nothing_run_silent_but_the_turn_still_exists(
    make_env: EnvMaker,
) -> None:
    """trả [SILENT] thì KHÔNG gửi gì, run ghi 'silent' - nhưng agent_turns vẫn có (đã chạy, chỉ chọn im)"""
    env = make_env()
    env.engine.script = ["[SILENT]"]
    job = await env.make_job(
        thread_id=THREAD, kind=JobKind.AGENT, payload="Theo dõi giá vàng, có gì mới thì báo"
    )

    await run(env, job)

    assert env.channel.sent == [], "không được gửi gì khi model chọn im lặng"
    assert len(env.usage.opened) == 1, "vẫn phải có agent_turns - job ĐÃ chạy, chỉ là không gửi"
    assert (await last_run(env, job.id)).status is JobRunStatus.SILENT


async def test_run_scheduled_job_kind_agent_markdown_becomes_zalo_formatting_before_leaving(
    make_env: EnvMaker,
) -> None:
    """markdown của model thành định dạng Zalo TRƯỚC khi tin ra ngoài"""
    env = make_env()
    env.engine.script = ["**Tin nóng**: giá vàng `tăng` 2 triệu.\n# Chi tiết\nXem đây."]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Tóm tắt tin công nghệ")

    await run(env, job)

    sent = env.channel.sent[-1]
    assert "**" not in sent.text, f"còn in đậm: {sent.text}"
    assert "`" not in sent.text, f"còn nháy đơn: {sent.text}"
    assert "# " not in sent.text, f"còn tiêu đề: {sent.text}"
    assert "Tin nóng: giá vàng tăng 2 triệu" in sent.text
    spans = [sent.text[s.start : s.start + s.length] for s in sent.styles]
    assert "Tin nóng" in spans, f"không tô đậm 'Tin nóng': {spans}"
    assert "Chi tiết" in spans, f"không tô tiêu đề 'Chi tiết': {spans}"
    assert (await last_run(env, job.id)).status is JobRunStatus.OK


async def test_run_scheduled_job_kind_agent_an_answer_that_leaks_the_system_prompt_is_blocked_run_error(
    make_env: EnvMaker,
) -> None:
    """câu trả lời rò system prompt bị CHẶN - không gửi gì, run ghi 'error'"""
    env = make_env()
    env.engine.script = ["Chỉ dẫn của mình là: Quy tắc an toàn (tuyệt đối, không có ngoại lệ): ..."]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Báo cáo")

    await run(env, job)

    assert env.channel.sent == [], "rò prompt thì không được gửi nửa vời"
    assert (await last_run(env, job.id)).status is JobRunStatus.ERROR


async def test_run_scheduled_job_kind_agent_sanitising_runs_after_the_silent_branch(
    make_env: EnvMaker,
) -> None:
    """làm sạch chạy SAU nhánh [SILENT] - không được dọn mất chính cái nhãn quyết định im lặng

    The input must carry CONTENT plus the label: a bare "[SILENT]" is empty after sanitising and would conclude
    silent anyway, so swapping the order would still pass (measured in the original)."""
    env = make_env()
    env.engine.script = ["Chưa có tin gì mới.\n[SILENT]"]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Theo dõi có gì mới")

    await run(env, job)

    assert env.channel.sent == [], "phải im lặng, không gửi chuỗi rỗng hay nhãn"
    assert (await last_run(env, job.id)).status is JobRunStatus.SILENT


async def test_run_scheduled_job_kind_agent_silent_resets_delivery_attempts(make_env: EnvMaker) -> None:
    """trả [SILENT] phải RESET delivery_attempts - lượt này kết thúc KHÔNG PHẢI vì gửi hỏng (Mục 4, vòng 3)"""
    env = make_env()
    env.engine.script = ["[SILENT]"]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Theo dõi giá vàng")
    await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id)
    await env.deps.attempts.increment_delivery_attempts(env.clinic_id, job.id)

    await run(env, job)

    assert await env.deps.attempts.get_delivery_attempts(env.clinic_id, job.id) == 0


async def test_run_scheduled_job_kind_agent_provider_error_retries_at_most_3_times_then_a_real_error_sends_nothing(
    make_env: EnvMaker,
) -> None:
    """provider ném lỗi (lượt agent chết giữa chừng) thì thử lại tối đa 3 lần trước khi ghi 'error' thật (Mục 2), KHÔNG gửi gì"""
    env = make_env()
    env.engine.script = [AgentTurnError(ProviderErrorKind.TRANSIENT, "500 từ router")]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Việc sẽ không bao giờ xong")

    for attempt in (1, 2):
        await run(env, job)
        alive = await job_now(env, job.id)
        assert alive.run_count == 0, f"lần thử {attempt}: job chưa 'chạy xong' thật sự"
        assert alive.last_error is None, f"lần thử {attempt}: chưa được ghi last_error"

    await run(env, job)
    assert env.channel.sent == [], "không bao giờ gửi gì - lượt agent chết trước cả khi tính ra text"
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.ERROR
    assert "500 từ router" in run_row.detail
    dead = await job_now(env, job.id)
    assert dead.run_count == 1, "lần thứ 3 mới thật sự tính là 1 lần chạy"
    assert "500 từ router" in (dead.last_error or "")
    # every failed turn closed its usage ONCE with the zero usage (never twice, never lost)
    assert all(len(v) == 1 for v in env.usage.finished.values())


async def test_run_scheduled_job_kind_agent_late_true_prefixes_the_agent_answer(make_env: EnvMaker) -> None:
    """late=true: câu trả lời của agent được thêm tiền tố '(nhắc trễ, lịch gốc HH:MM)' trước khi gửi"""
    env = make_env(tuning={"BOT_TIMEZONE": TZ})
    env.engine.script = ["Báo cáo xong rồi đấy."]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Báo cáo định kỳ")

    await run(env, job, late=True, scheduled_for="2026-08-01T08:00:00.000Z")

    assert sent_texts(env)[-1] == "(nhắc trễ, lịch gốc 15:00) Báo cáo xong rồi đấy."


async def test_run_scheduled_job_kind_agent_config_error_keeps_the_run_slot_and_is_not_counted_as_a_failed_send(
    make_env: EnvMaker,
) -> None:
    """(sửa lỗi nhánh cau_hinh) bot chưa cấu hình LLM: giữ suất, phục hồi next_run_at, KHÔNG đếm delivery_attempts

    In the original the inner catch swallowed this error, so the branch that was written for it never ran and a
    ``once`` reminder lost its slot after 3 ticks just because nobody had typed the API key yet."""
    env = make_env()
    env.engine.script = [AgentTurnError(ProviderErrorKind.CONFIG, "chưa có API key")]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Báo cáo")

    for _ in range(4):
        await run(env, job)

    after = await job_now(env, job.id)
    assert after.run_count == 0
    assert after.enabled is True
    assert after.next_run_at == job.next_run_at
    assert after.delivery_attempts == 0
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert "chưa cấu hình xong LLM" in run_row.detail
    assert env.channel.sent == []


# ================================================================ two gates that nobody used to guard


async def test_run_scheduled_job_the_thread_type_of_the_job_arrives_a_group_reminder_is_not_sent_as_a_private_chat(
    make_env: EnvMaker,
) -> None:
    """`threadType` của job đi TỚI NƠI - lời nhắc của NHÓM không đi qua endpoint chat riêng"""
    env = make_env()
    job = await env.make_job(thread_id=THREAD, thread_type=1, payload="Nhắc cả nhóm họp 3h")

    await run(env, job)

    assert len(env.channel.sent) == 1
    assert env.channel.sent[0].thread_kind is ThreadKind.GROUP, "threadType của job không tới được channel"


async def test_run_scheduled_job_account_stopped_during_the_agent_turn_does_not_send_keeps_slot_restores_the_instant(
    make_env: EnvMaker,
) -> None:
    """account bị TẮT giữa lượt agent: không gửi, giữ suất, phục hồi mốc

    The only gate against a stale channel is the fresh ``check_account_and_thread_ready`` in ``blocked_by_guard``,
    called right at the send. It looks redundant (the tick already checked) so it is easy to "clean up", and the
    consequence is silent: a job sent through the client of an account that was just switched off."""
    env = make_env()
    env.engine.script = ["Báo cáo đây."]
    env.engine.on_run = env.go_offline
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Tra cứu rồi báo cáo")

    await run(env, job)

    assert env.channel.sent == [], "gửi qua client của account đã tắt"
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert "không chạy" in run_row.detail
    after = await job_now(env, job.id)
    assert after.enabled is True, "job bị tắt vì account tạm dừng - lời nhắc mất vĩnh viễn"
    assert after.next_run_at == job.next_run_at, "`once` phải được phục hồi ĐÚNG mốc cũ để tick sau thử lại"


async def test_run_scheduled_job_never_raises_even_when_the_job_was_deleted_under_it(
    make_env: EnvMaker,
) -> None:
    """(hợp đồng 'KHÔNG BAO GIỜ ném lỗi ra ngoài') job bị xoá giữa chừng thì không có exception thoát ra"""
    env = make_env()
    job = await env.make_job(thread_id=THREAD)
    await env.deps.jobs.delete_job(env.clinic_id, ACC, THREAD, job.id)

    await run(env, job)  # must not raise: it is called not awaited from the tick

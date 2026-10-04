# ported from: src/scheduler/lich-hen-kenh-bot.test.ts
"""Schedules that run FOR REAL on a Zalo Bot account.

The seam nobody guarded in the original: ``test_run_scheduled_job`` always uses a fully capable personal channel,
and the bot-channel tests measured loose pieces. This proves the scheduler sends through a ``ChannelPort`` of kind
``zalo_bot`` that cannot carry style spans and caps one message at 2000 characters. SAFETY: the channel is a
``FakeChannel``; nothing here touches the Bot API.

Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring. Left out on
purpose, they belong to other packages: "scheduled turn on the bot channel still has exactly 4 lookup tools" is
the tool registry of D4, and the ``ZALO_MAX_MESSAGE_CHARS`` tuning of the shared splitter is C2's pipeline; here
the channel limit comes from ``capabilities().max_text_length`` and the fake splitter obeys it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from pema.scheduler.run_context import resolve_policy_context
from pema.scheduler.run_scheduled_job import RunScheduledJobOptions, run_scheduled_job
from pema.scheduler.scheduled_job_cap_guard import conclude_cap_blocked_at_tick
from pema.scheduler.testing_env import ACC, Env
from pema_contracts.channel import ChannelKind
from pema_contracts.scheduler import EverySchedule, JobKind, JobRunStatus, ScheduledJob

pytestmark = pytest.mark.db

EnvMaker = Callable[..., Env]
THREAD = "chat-lich-bot"


def bot_env(make_env: EnvMaker, **kwargs: object) -> Env:
    return make_env(
        channel_kind=ChannelKind.ZALO_BOT, supports_formatting=False, max_text_length=2000, **kwargs
    )  # type: ignore[arg-type]


async def run(env: Env, job: ScheduledJob, now: datetime | None = None) -> None:
    await run_scheduled_job(
        env.deps,
        job,
        RunScheduledJobOptions(late=False, scheduled_for=job.next_run_at or "", now=now or datetime.now(UTC)),
    )


async def last_run(env: Env, job_id: str):
    return (await env.deps.runs.list_runs(env.clinic_id, job_id, 1))[0]


async def test_bot_a_message_job_really_sends_through_the_bot_channel_writes_history_run_ok(
    make_env: EnvMaker,
) -> None:
    """job kind=message gửi THẬT qua Bot API, ghi history, run 'ok'"""
    env = bot_env(make_env)
    job = await env.make_job(thread_id=THREAD, payload="Nhắc uống nước lúc 3h")

    await run(env, job)

    assert [(p.thread_id, p.text) for p in env.channel.sent] == [(THREAD, "Nhắc uống nước lúc 3h")]
    assert (await last_run(env, job.id)).status is JobRunStatus.OK
    assert env.history.contents(ACC, THREAD)[-1] == "Nhắc uống nước lúc 3h"


async def test_bot_the_channel_character_limit_wins_over_the_general_one(make_env: EnvMaker) -> None:
    """trần ký tự của KÊNH thắng trần chung - Bot API ép cứng 2000 phía server

    One shared number would let anyone who raises it for the personal channel make the bot channel LOSE the whole
    answer (the server refuses the entire message instead of cutting). The test text is between 2000 and 4000."""
    env = bot_env(make_env)
    long_text = " ".join(f"cau{i}" for i in range(500))
    assert 2000 < len(long_text) < 4000
    job = await env.make_job(thread_id=THREAD, payload=long_text)

    await run(env, job)

    assert len(env.channel.sent) == 2, "trần 2000 của kênh bot bị bỏ qua"
    assert len(env.channel.sent[0].text) <= 2000, (
        f"tin đầu {len(env.channel.sent[0].text)} ký tự, vượt trần nền tảng"
    )


async def test_bot_markdown_is_stripped_from_the_text_but_no_styles_travel_on_the_bot_channel(
    make_env: EnvMaker,
) -> None:
    """chuỗi THẬT của LỊCH HẸN: lời nhắc có markdown ra kênh bot KHÔNG mang styles

    The scheduler formats EVERY scheduled send and rich text is on by default: if the channel flag that says "no
    spans" is lost on the way, the byte budget counts the styles too, splits too many messages, and the daily cap
    (counted per message) burns faster - silently. The text must still be STRIPPED of markdown: dropping the flag
    is not dropping the formatting."""
    env = bot_env(make_env)
    job = await env.make_job(thread_id=THREAD, payload="**Nhắc họp** lúc 3h")

    await run(env, job)

    assert [(p.thread_id, p.text) for p in env.channel.sent] == [(THREAD, "Nhắc họp lúc 3h")]
    assert env.channel.sent[0].styles == ()


async def test_bot_a_kind_agent_job_runs_with_no_personal_channel_api(make_env: EnvMaker) -> None:
    """job kind=agent chạy được với `api: null` - lượt cô lập không cần zca-js"""
    env = bot_env(make_env)
    env.engine.script = ["Hôm nay có 3 tin đáng chú ý."]
    job = await env.make_job(thread_id=THREAD, kind=JobKind.AGENT, payload="Tóm tắt tin công nghệ hôm nay")

    await run(env, job)

    assert env.channel.sent[-1].text == "Hôm nay có 3 tin đáng chú ý."
    assert (await last_run(env, job.id)).status is JobRunStatus.OK
    assert len(env.usage.opened) == 1, "lượt agent theo lịch phải để lại đúng 1 dòng usage"


async def test_bot_a_stopped_bot_account_skips_and_keeps_the_run_slot_does_not_switch_the_job_off(
    make_env: EnvMaker,
) -> None:
    """account bot ĐANG TẮT: skip và GIỮ suất chạy, không tắt job

    "A bot account" and "an account that is not running" are now two different things; the old code merged them
    and switched a bot's jobs OFF even while the bot ran fine."""
    env = bot_env(make_env, online=False)
    job = await env.make_job(thread_id=THREAD, payload="gửi khi bot tắt")

    await run(env, job)

    assert env.channel.sent == []
    run_row = await last_run(env, job.id)
    assert run_row.status is JobRunStatus.SKIPPED
    assert "không chạy" in run_row.detail
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.enabled is True, "job bị TẮT vì account tạm dừng - lời nhắc mất vĩnh viễn"
    assert after.next_run_at == job.next_run_at, "`once` phải được phục hồi ĐÚNG mốc cũ để tick sau thử lại"


async def test_bot_an_every_job_that_finished_a_run_stays_enabled_and_has_a_next_slot(
    make_env: EnvMaker,
) -> None:
    """job `every` trên bot chạy xong vẫn BẬT và có mốc kế - không bị tắt như bản cũ"""
    env = bot_env(make_env)
    job = await env.make_job(thread_id=THREAD, payload="nhắc định kỳ", schedule=EverySchedule(minutes=30))

    await run(env, job)

    assert len(env.channel.sent) == 1
    after = await env.deps.jobs.get_job_unscoped(env.clinic_id, job.id)
    assert after is not None
    assert after.enabled is True
    assert after.next_run_at is not None, "job `every` mất mốc kế là chết lặng, không tick nào nhặt lại được"


async def test_bot_the_daily_proactive_cap_still_counts_on_the_bot_channel(make_env: EnvMaker) -> None:
    """trần tin chủ động mỗi ngày vẫn đếm trên kênh bot

    Counted by the CONTENT of the jobs, not by the number of sent messages: a blocked run also sends the cap
    notice, so the total is 3 (the first version of the original test asserted 2 and was red for counting the
    notice as a job message)."""
    env = bot_env(make_env, tuning={"SCHEDULER_MAX_PROACTIVE_PER_DAY": 2, "SCHEDULER_SEND_GAP_MS": 0})
    now = datetime(2026, 8, 1, 8, 0, tzinfo=UTC)
    for i in range(3):
        job = await env.make_job(thread_id=THREAD, payload=f"tin {i}")
        await run(env, job, now)

    job_messages = [p.text for p in env.channel.sent if p.text.startswith("tin ")]
    assert job_messages == ["tin 0", "tin 1"], "trần 2/ngày phải áp cho kênh bot"
    assert any("tạm dừng để tránh làm phiền" in p.text for p in env.channel.sent), (
        "chạm trần mà người nhắn không được báo gì"
    )


async def test_bot_the_daily_cap_notice_is_sent_on_the_bot_channel_the_silent_hole_of_the_cap_guard(
    make_env: EnvMaker,
) -> None:
    """thông báo CHẠM TRẦN NGÀY gửi được trên kênh bot (lỗ câm của cap-guard)

    ``conclude_cap_blocked_at_tick`` builds its own target. The original built it with the personal API, so for a
    bot account the target was undefined and NOBODY WAS TOLD. It goes through the shared factory now."""
    env = bot_env(make_env)
    job = await env.make_job(thread_id=THREAD, payload="nội dung không quan trọng")
    run_id = await env.deps.runs.open_run(env.clinic_id, job.id)
    account = await env.accounts.get_account(env.clinic_id, ACC)
    assert account is not None
    ctx = await resolve_policy_context(env.deps, job, account, isolated=False)
    cap = await env.deps.guard.effective_cap(ctx, env.deps.hooks)

    await conclude_cap_blocked_at_tick(
        env.deps,
        job,
        run_id,
        "Đã đạt trần tin nhắn chủ động hôm nay.",
        True,
        "Asia/Ho_Chi_Minh",
        datetime(2026, 8, 1, 8, 0, tzinfo=UTC),
        cap=cap,
        ctx=ctx,
    )

    assert len(env.channel.sent) == 1, "chạm trần ngày mà không ai được báo trên kênh bot"
    assert env.channel.sent[0].thread_id == THREAD
    assert (await last_run(env, job.id)).status is JobRunStatus.SKIPPED

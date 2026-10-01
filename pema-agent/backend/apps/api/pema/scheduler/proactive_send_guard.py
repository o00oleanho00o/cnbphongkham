# ported from: src/scheduler/proactive-send-guard.ts
"""Guardrail before EVERY PROACTIVE send of the scheduler (not an answer to an incoming message): the account
is running -> the thread is still valid (exists in ``agent.threads`` AND ``bot_enabled``) -> the daily cap is
not reached (counted PER MESSAGE, durable across restarts - see ``proactive_send_counter_store``). Failing any
of them returns a reason as text to write into ``job_runs.detail``.

The daily cap has 2 DIFFERENT checkpoints: ``check_proactive_daily_cap`` (PURE READ, an EARLY filter at the
tick before running the agent - avoids burning the LLM, but reserves nothing so it cannot block the race) and
``reserve_proactive_slot`` (ATOMIC, used right at the real send in ``scheduled_job_send`` - takes 1 slot with
one conditional upsert, which blocks exactly that race).

Together with the global spaced queue (``SCHEDULER_SEND_GAP_MS``, see ``proactive_send_queue``).

Forced deviations / additions for the clinic:

* the counters are keyed by ``scope_key`` (not ``(account, thread)``): the policy profile chooses it through
  ``PolicyHooks.proactive_cap`` (``account:thread`` for ``staff_assistant``, ``patient:account`` for
  ``patient_channel``); ``effective_cap`` combines the hook with the clinic-wide ``channel_setting.daily_cap``
  (the smaller wins) and never leaves a send uncapped;
* ``check_account_and_thread_ready`` also honours the clinic-wide switchboard of the channel kind
  (``clinic_agent.channel_policy``: disabled, KILL SWITCH, send window). A clinic with NO row for the channel
  has no clinic-wide restriction (the original behaviour);
* ``PgProactiveSendGuard`` implements the contract ``ProactiveSendGuard`` over the same store (one instance
  per clinic), so any package that sends an already-approved message (B1/C2, review item approval) takes its
  slot from the SAME counter as the scheduler."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pema.config.runtime_tuning_settings import bot_time_zone, get_tuning_int
from pema.scheduler.ports import ChannelPolicyReader, ThreadStatusReader
from pema.scheduler.proactive_send_counter_store import ProactiveSendCounterStore
from pema.shared.zone_time import today_key
from pema_contracts.channel import ChannelRegistry
from pema_contracts.policy import PolicyContext, PolicyHooks
from pema_contracts.scheduler import ProactiveSlotResult

ACCOUNT_NOT_RUNNING_REASON = "Account hiện không chạy (chưa đăng nhập hoặc bị dừng)."
"""Wording shared with the pre-flight of ``scheduler_loop`` / ``run_scheduled_job``: same condition, same
sentence."""

COUNTER_RETENTION_DAYS = 3
"""How many days of counters are kept: the cap only needs to know EXACTLY TODAY, so no need to keep long."""


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    reason: str = ""


@dataclass(frozen=True)
class GuardResult:
    ok: bool
    reason: str = ""
    notify_cap_hit_once: bool = False
    """True means the cap was NOT announced today yet - the caller must win the right to announce it itself
    (``reserve_cap_notice``) and only then send. The cap-check functions of this file are PURE READ or only
    RESERVE, they send nothing."""


@dataclass(frozen=True)
class EffectiveCap:
    scope_key: str
    max_per_day: int


def default_scope_key(account_id: str, thread_id: str) -> str:
    """The ``staff_assistant`` key: per (account, thread). ``PermissivePolicyHooks.proactive_cap`` returns the
    same string."""
    return f"{account_id}:{thread_id}"


def _keep_since_day_key(time_zone: str, now: datetime) -> str:
    cutoff = now - timedelta(days=COUNTER_RETENTION_DAYS)
    return today_key(time_zone, cutoff)


def _cap_reason(max_per_day: int, time_zone: str) -> str:
    return (
        f"Đã chạm trần {max_per_day} tin chủ động/ngày cho cuộc trò chuyện này (tính theo ngày {time_zone})."
    )


def _parse_hhmm(value: str) -> tuple[int, int]:
    hours, minutes = value.split(":")[:2]
    return int(hours), int(minutes)


def _inside_window(start: str, end: str, now: datetime) -> bool:
    """``start <= local time < end`` in ``bot_time_zone()``; a window that crosses midnight (22:00-06:00) is
    supported."""
    try:
        zone = ZoneInfo(bot_time_zone())
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = ZoneInfo("UTC")
    local = now.astimezone(zone)
    minutes_now = local.hour * 60 + local.minute
    start_h, start_m = _parse_hhmm(start)
    end_h, end_m = _parse_hhmm(end)
    start_min, end_min = start_h * 60 + start_m, end_h * 60 + end_m
    if start_min == end_min:
        return True
    if start_min < end_min:
        return start_min <= minutes_now < end_min
    return minutes_now >= start_min or minutes_now < end_min


class ProactiveSendGuardService:
    """``now`` is a MANDATORY PARAMETER of every cap function in this class - the ``= new Date()`` defaults
    were deleted on purpose.

    This is a mistake that was paid for: ``recordProactiveSend`` once had a default ``new Date()``, and
    ``sendCapNotice`` forgot to pass ``now``. A double consequence, both silent:

    1. the counter was added to the day-key of the REAL time instead of the day of the run being handled;
    2. ``keep_since_day_key`` pruned the table with the cutoff of the real time, DELETING the very row just
       written (3-day retention).

    The worst is the midnight case: ``reserve_proactive_slot`` takes a slot of day D, the send takes 20
    seconds (``SCHEDULER_SEND_GAP_MS``) then fails, ``refund_proactive_slot`` returns the slot to day D+1 -
    day D keeps the slot forever and nobody can claim it back, and this is the shield against getting an
    account locked.

    INVARIANT: one run of a job = ONE instant, fixed at the start of the tick and threaded through everywhere.
    Leaving a default would reopen exactly that trap for whoever edits this later."""

    def __init__(
        self,
        counters: ProactiveSendCounterStore,
        channels: ChannelRegistry,
        threads: ThreadStatusReader,
        channel_policy: ChannelPolicyReader,
    ) -> None:
        self._counters = counters
        self._channels = channels
        self._threads = threads
        self._channel_policy = channel_policy

    # ------------------------------------------------------------------------------------ pre-flight

    async def check_account_and_thread_ready(
        self, clinic_id: UUID, account_id: str, thread_id: str, now: datetime
    ) -> PreflightResult:
        """The part that does NOT depend on the content of the guard - account running + valid thread (+ the
        clinic-wide switchboard of the channel). Split out so ``scheduler_loop`` can check it RIGHT IN THE
        TICK, BEFORE clear-before-dispatch: a job blocked here leaves ``next_run_at``/``run_count`` untouched
        and the next tick retries by itself - the job does not "die" just because the account dropped its
        session exactly when it became due (a perfectly normal case with zca-js)."""
        channel = self._channels.get_running(clinic_id, account_id)
        if channel is None:
            return PreflightResult(False, ACCOUNT_NOT_RUNNING_REASON)
        thread = await self._threads.find_thread_status(clinic_id, account_id, thread_id)
        if thread is None:
            return PreflightResult(
                False, "Cuộc trò chuyện chưa từng ghi nhận trong hệ thống - không nhắn chủ động được."
            )
        if not thread.bot_enabled:
            return PreflightResult(False, "Bot đang tắt cho cuộc trò chuyện này.")

        policy = await self._channel_policy.get_channel_policy(clinic_id, channel.kind.value)
        if policy is not None:
            if policy.kill_switch_on:
                return PreflightResult(False, "Kênh đang bật công tắc dừng khẩn cấp - không nhắn chủ động.")
            if not policy.enabled:
                return PreflightResult(False, "Kênh chưa được bật cho phòng khám - không nhắn chủ động.")
            if (
                policy.send_window_start is not None
                and policy.send_window_end is not None
                and not _inside_window(policy.send_window_start, policy.send_window_end, now)
            ):
                return PreflightResult(
                    False,
                    f"Ngoài khung giờ gửi chủ động ({policy.send_window_start}-{policy.send_window_end}).",
                )
        return PreflightResult(True)

    async def effective_cap(self, ctx: PolicyContext, hooks: PolicyHooks) -> EffectiveCap:
        """Scope key and daily maximum for this job: the policy hook picks the key (and may lower the cap),
        the clinic-wide ``channel_setting.daily_cap`` can only LOWER it further. A hook that answers ``None``
        ("no cap beyond the channel's") still gets the ``SCHEDULER_MAX_PROACTIVE_PER_DAY`` default: the cap is
        the shield against an account lock, so it is never switched off silently."""
        default_max = get_tuning_int("SCHEDULER_MAX_PROACTIVE_PER_DAY")
        cap = await hooks.proactive_cap(ctx, default_max)
        max_per_day = default_max if cap.max_per_day is None else cap.max_per_day
        channel = self._channels.get_running(ctx.clinic_id, ctx.account_id)
        if channel is not None:
            policy = await self._channel_policy.get_channel_policy(ctx.clinic_id, channel.kind.value)
            if policy is not None and policy.daily_cap is not None:
                max_per_day = min(max_per_day, policy.daily_cap)
        return EffectiveCap(scope_key=cap.scope_key, max_per_day=max_per_day)

    # ---------------------------------------------------------------------------------------- caps

    async def check_proactive_daily_cap(
        self, clinic_id: UUID, scope_key: str, time_zone: str, now: datetime, max_per_day: int
    ) -> GuardResult:
        """PURE READ, does NOT reserve - used for the EARLY filter at the tick (``scheduler_loop``), BEFORE
        running the agent: avoids burning the LLM for a job that surely cannot send. NOT atomic so it is NOT
        used to decide "may I send or not" right at the real send - see ``reserve_proactive_slot``."""
        day_key = today_key(time_zone, now)
        counter = await self._counters.get_proactive_counter(clinic_id, scope_key, day_key)
        if counter.count >= max_per_day:
            return GuardResult(
                False, _cap_reason(max_per_day, time_zone), notify_cap_hit_once=not counter.notice_sent
            )
        return GuardResult(True)

    async def reserve_proactive_slot(
        self, clinic_id: UUID, scope_key: str, time_zone: str, now: datetime, max_per_day: int
    ) -> GuardResult:
        """ATOMIC - takes EXACTLY 1 slot if there is room (one conditional upsert, see
        ``try_reserve_proactive_slot``). Used RIGHT AT the real send - the point that BLOCKS THE RACE between
        several jobs of the same scope that become due together (``check_proactive_daily_cap`` above only
        filters early, it reserves nothing). Call ``record_proactive_send`` afterwards to add the REST when
        ``sent_parts`` > 1, or ``refund_proactive_slot`` if in the end nothing could be sent."""
        day_key = today_key(time_zone, now)
        if not await self._counters.try_reserve_proactive_slot(clinic_id, scope_key, day_key, max_per_day):
            counter = await self._counters.get_proactive_counter(clinic_id, scope_key, day_key)
            return GuardResult(
                False, _cap_reason(max_per_day, time_zone), notify_cap_hit_once=not counter.notice_sent
            )
        return GuardResult(True)

    async def refund_proactive_slot(
        self, clinic_id: UUID, scope_key: str, time_zone: str, now: datetime
    ) -> None:
        """Give back EXACTLY 1 slot that ``reserve_proactive_slot`` took but in the end nothing was sent."""
        await self._counters.refund_proactive_slot(clinic_id, scope_key, today_key(time_zone, now))

    async def check_proactive_send_guard(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        scope_key: str,
        time_zone: str,
        now: datetime,
        max_per_day: int,
    ) -> GuardResult:
        """All the conditions together, PURE READ - handy where you only need to know "is it blocked" without
        reserving (for example a preview page)."""
        preflight = await self.check_account_and_thread_ready(clinic_id, account_id, thread_id, now)
        if not preflight.ok:
            return GuardResult(False, preflight.reason, notify_cap_hit_once=False)
        return await self.check_proactive_daily_cap(clinic_id, scope_key, time_zone, now, max_per_day)

    async def mark_proactive_cap_notified(
        self, clinic_id: UUID, scope_key: str, time_zone: str, now: datetime
    ) -> None:
        """Mark the cap as announced today - an UNCONDITIONAL overwrite, kept for places that are already sure
        (for example the "Run now" page, where there is no race between jobs). The REAL send path of the
        scheduler uses the ATOMIC ``reserve_cap_notice`` / ``revert_cap_notice`` below instead."""
        await self._counters.mark_proactive_cap_notice_sent(clinic_id, scope_key, today_key(time_zone, now))

    async def reserve_cap_notice(
        self, clinic_id: UUID, scope_key: str, time_zone: str, now: datetime
    ) -> bool:
        """ATOMIC - takes the RIGHT to send the cap notice (see ``try_reserve_cap_notice``). Call RIGHT BEFORE
        really sending - the point that BLOCKS THE RACE when N jobs of the same scope are blocked in 1 tick,
        unlike ``mark_proactive_cap_notified`` (written AFTER the send, too late to block the race)."""
        return await self._counters.try_reserve_cap_notice(clinic_id, scope_key, today_key(time_zone, now))

    async def revert_cap_notice(self, clinic_id: UUID, scope_key: str, time_zone: str, now: datetime) -> None:
        """Hand back the right taken in ``reserve_cap_notice`` but the send failed - a later job/tick has a
        chance to retry."""
        await self._counters.revert_cap_notice(clinic_id, scope_key, today_key(time_zone, now))

    async def record_proactive_send(
        self, clinic_id: UUID, scope_key: str, time_zone: str, count: int, now: datetime
    ) -> None:
        """Record ``count`` MORE proactive messages SENT SUCCESSFULLY - call AFTER sending, with the REST of
        the number of messages that REALLY went out (``reply.sent_parts - 1``, since 1 slot was already taken
        by ``reserve_proactive_slot``) - 1 long answer can be cut by ``send_reply_in_parts`` into several."""
        await self._counters.add_proactive_send_count(
            clinic_id, scope_key, today_key(time_zone, now), count, _keep_since_day_key(time_zone, now)
        )

    async def reset_proactive_send_counters(self, clinic_id: UUID) -> None:
        """Tests only - bring the cap counters to 0 so every case starts clean."""
        await self._counters.reset_all_proactive_counters(clinic_id)


class PgProactiveSendGuard:
    """The contract ``pema_contracts.scheduler.ProactiveSendGuard`` over Postgres, bound to ONE clinic (the
    table is keyed by ``clinic_id`` and the Protocol has no clinic argument). Atomicity is the one of
    ``ProactiveSendCounterStore``: nothing here reads then writes."""

    def __init__(self, counters: ProactiveSendCounterStore, clinic_id: UUID) -> None:
        self._counters = counters
        self._clinic_id = clinic_id

    async def reserve_slot(self, scope_key: str, day_key: str, max_per_day: int) -> ProactiveSlotResult:
        won = await self._counters.try_reserve_proactive_slot(
            self._clinic_id, scope_key, day_key, max_per_day
        )
        counter = await self._counters.get_proactive_counter(self._clinic_id, scope_key, day_key)
        return ProactiveSlotResult(reserved=won, count=counter.count, cap=max_per_day)

    async def refund_slot(self, scope_key: str, day_key: str) -> None:
        await self._counters.refund_proactive_slot(self._clinic_id, scope_key, day_key)

    async def reserve_cap_notice(self, scope_key: str, day_key: str) -> bool:
        return await self._counters.try_reserve_cap_notice(self._clinic_id, scope_key, day_key)

    async def revert_cap_notice(self, scope_key: str, day_key: str) -> None:
        await self._counters.revert_cap_notice(self._clinic_id, scope_key, day_key)


def utc_now() -> datetime:
    """The clock of a RUN is read once by the caller; this helper is only for entry points (tick, trial)."""
    return datetime.now(UTC)

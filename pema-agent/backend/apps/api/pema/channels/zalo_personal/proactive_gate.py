"""Safety gate in front of EVERY proactive message of a personal account.

New module (clinic safety of PLAN-AI01 section 5 and the C2 package brief; the original relied on the tuning
key ``SCHEDULER_MAX_PROACTIVE_PER_DAY`` and the scheduler guard only). It sits INSIDE
``ZaloPersonalChannel.send_text`` so that nothing can reach the bridge around it, whoever the caller is
(scheduler delivery, a tool, a staff action). The scheduler (package S) keeps its own per-job guard
(``proactive_send_guard``); the two use DIFFERENT counter keys (``zalo_personal:<account>:<thread>`` here), so
a message is counted once by each and neither interferes with the other. The bridge adds a third, independent
backstop (hard per-account ceilings).

Checks, in this order, first failure wins (a rejected ``SendResult`` with an ``ErrorCode``, never an
exception):

1. the process flag ``PEMA_ZALO_PERSONAL_ENABLED`` (``flag_enabled``): ``channel_unavailable``
2. the clinic switch ``channel_setting.enabled``: ``channel_unavailable``
3. the KILL SWITCH ``channel_setting.kill_switch_on``, read from the row on EVERY send (no cache), so
   flipping it in the admin UI stops the next message in every process: ``channel_kill_switch_on``
4. the send window ``send_window_start``..``send_window_end`` in the bot time zone (may wrap midnight):
   ``channel_outside_send_window``
5. ``requires_friend``: a direct-thread recipient must be a friend (live list from the bridge, cached 10
   minutes; an unreachable bridge means rejected, fail closed): ``channel_recipient_not_reachable``
6. the DAILY CAP per (account, thread, day): ``channel_setting.daily_cap`` or, when unset, the tuning key
   ``SCHEDULER_MAX_PROACTIVE_PER_DAY`` (default 10), reserved ATOMICALLY and refunded when the send fails:
   ``channel_daily_cap_reached``
7. the random GAP between two proactive sends of the account (``min_gap_seconds``..``max_gap_seconds``), so a
   burst of due jobs reads like a person typing, not a bot flushing a queue.

``ProactiveSendGuard`` (the atomic counter) is injected: production passes package S's Postgres
implementation (``INSERT ... ON CONFLICT DO UPDATE ... WHERE count < max``); ``InMemoryProactiveCounter`` is
the process-local fallback used by tests and by a deployment without S.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from pema.channels.zalo_personal.bridge_client import ZaloApi
from pema.channels.zalo_personal.channel_settings import ChannelPolicyReader, ChannelSettings
from pema.config.runtime_tuning_settings import bot_time_zone, get_tuning_int
from pema.shared.logger import create_logger
from pema.shared.zone_time import today_key
from pema_contracts.channel import ChannelKind, SendResult, SendStatus, ThreadKind
from pema_contracts.errors import ErrorCode
from pema_contracts.scheduler import ProactiveSendGuard, ProactiveSlotResult

log = create_logger("proactive-gate")

FRIEND_CACHE_TTL_SECONDS = 600
SCOPE_PREFIX = "zalo_personal"


class InMemoryProactiveCounter:
    """``ProactiveSendGuard`` kept in process memory. Atomic because asyncio runs one task at a time between
    awaits and ``reserve_slot`` does not await between the read and the write."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, str], int] = {}
        self._notices: set[tuple[str, str]] = set()

    async def reserve_slot(self, scope_key: str, day_key: str, max_per_day: int) -> ProactiveSlotResult:
        key = (scope_key, day_key)
        count = self._counts.get(key, 0)
        if count >= max_per_day:
            return ProactiveSlotResult(reserved=False, count=count, cap=max_per_day)
        self._counts[key] = count + 1
        return ProactiveSlotResult(reserved=True, count=count + 1, cap=max_per_day)

    async def refund_slot(self, scope_key: str, day_key: str) -> None:
        key = (scope_key, day_key)
        self._counts[key] = max(0, self._counts.get(key, 0) - 1)

    async def reserve_cap_notice(self, scope_key: str, day_key: str) -> bool:
        key = (scope_key, day_key)
        if key in self._notices:
            return False
        self._notices.add(key)
        return True

    async def revert_cap_notice(self, scope_key: str, day_key: str) -> None:
        self._notices.discard((scope_key, day_key))


@dataclass(frozen=True)
class Admission:
    """Result of ``ProactiveGate.admit``: either a rejection to return, or a reservation to settle."""

    rejection: SendResult | None = None
    scope_key: str | None = None
    day_key: str | None = None

    @property
    def admitted(self) -> bool:
        return self.rejection is None


def is_within_window(now_local: time, start: time | None, end: time | None) -> bool:
    """``True`` when no window is configured. A window whose start is after its end wraps midnight."""
    if start is None or end is None:
        return True
    if start <= end:
        return start <= now_local < end
    return now_local >= start or now_local < end


def _reject(code: ErrorCode, detail: str) -> Admission:
    return Admission(rejection=SendResult(status=SendStatus.REJECTED, error_code=code, detail=detail))


class ProactiveGate:
    def __init__(
        self,
        *,
        clinic_id: UUID,
        account_id: str,
        reader: ChannelPolicyReader,
        api: ZaloApi,
        flag_enabled: Callable[[], bool],
        counter: ProactiveSendGuard | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        uniform: Callable[[float, float], float] = random.uniform,
        monotonic: Callable[[], float] | None = None,
    ) -> None:
        self._clinic_id = clinic_id
        self._account_id = account_id
        self._reader = reader
        self._api = api
        self._flag_enabled = flag_enabled
        self._counter: ProactiveSendGuard = counter or InMemoryProactiveCounter()
        self._now = now
        self._sleep = sleep
        self._uniform = uniform
        self._monotonic = monotonic or (lambda: self._now().timestamp())
        self._friends: set[str] = set()
        self._friends_loaded_at: float | None = None
        self._last_proactive_at: float | None = None
        self.snapshot: ChannelSettings = ChannelSettings(channel=ChannelKind.ZALO_PERSONAL)
        """Last policy row read; ``capabilities()`` is synchronous and reports it."""

    def daily_cap(self, settings: ChannelSettings) -> int:
        if settings.daily_cap is not None:
            return settings.daily_cap
        return get_tuning_int("SCHEDULER_MAX_PROACTIVE_PER_DAY")

    async def refresh(self) -> ChannelSettings:
        self.snapshot = await self._reader.get_policy(self._clinic_id, ChannelKind.ZALO_PERSONAL)
        return self.snapshot

    async def admit(self, thread_id: str, thread_kind: ThreadKind) -> Admission:
        """Run checks 1-6 and RESERVE a cap slot. The caller must ``settle`` after the send."""
        if not self._flag_enabled():
            return _reject(ErrorCode.CHANNEL_UNAVAILABLE, "flag_off")
        settings = await self.refresh()
        if not settings.enabled:
            return _reject(ErrorCode.CHANNEL_UNAVAILABLE, "channel_disabled")
        if settings.kill_switch_on:
            return _reject(ErrorCode.CHANNEL_KILL_SWITCH_ON, "kill_switch_on")

        now = self._now()
        local = now.astimezone(ZoneInfo(bot_time_zone()))
        if not is_within_window(local.time(), settings.send_window_start, settings.send_window_end):
            return _reject(ErrorCode.CHANNEL_OUTSIDE_SEND_WINDOW, "outside_send_window")

        if (
            settings.requires_friend
            and thread_kind is ThreadKind.USER
            and not await self._is_friend(thread_id)
        ):
            return _reject(ErrorCode.CHANNEL_RECIPIENT_NOT_REACHABLE, "not_a_friend")

        cap = self.daily_cap(settings)
        scope_key = f"{SCOPE_PREFIX}:{self._account_id}:{thread_id}"
        day_key = today_key(bot_time_zone(), now)
        slot = await self._counter.reserve_slot(scope_key, day_key, cap)
        if not slot.reserved:
            log.warning("proactive daily cap reached", account_id=self._account_id, cap=cap)
            return _reject(ErrorCode.CHANNEL_DAILY_CAP_REACHED, "daily_cap_reached")

        try:
            await self._wait_gap(settings)
        except BaseException:
            await self._counter.refund_slot(scope_key, day_key)
            raise
        return Admission(scope_key=scope_key, day_key=day_key)

    async def settle(self, admission: Admission, *, sent: bool) -> None:
        """Keep the slot when the message left, give it back when it did not."""
        if not admission.admitted or admission.scope_key is None or admission.day_key is None:
            return
        if sent:
            self._last_proactive_at = self._monotonic()
            return
        await self._counter.refund_slot(admission.scope_key, admission.day_key)

    # ------------------------------------------------------------------------------------------ helpers

    async def _is_friend(self, uid: str) -> bool:
        now = self._monotonic()
        stale = self._friends_loaded_at is None or now - self._friends_loaded_at > FRIEND_CACHE_TTL_SECONDS
        if stale or uid not in self._friends:
            # A recipient missing from a cached list may be a NEW friend: refresh once before refusing.
            try:
                friends = await self._api.get_all_friends()
            except Exception as err:
                log.warning("cannot load the friend list - proactive send refused", err=err)
                return False
            self._friends = {str(f.get("userId", "")) for f in friends}
            self._friends_loaded_at = now
        return uid in self._friends

    async def _wait_gap(self, settings: ChannelSettings) -> None:
        low, high = settings.min_gap_seconds, settings.max_gap_seconds
        if high <= 0 or self._last_proactive_at is None:
            return
        wanted = self._uniform(float(low), float(high))
        elapsed = self._monotonic() - self._last_proactive_at
        remaining = wanted - elapsed
        if remaining > 0:
            await self._sleep(remaining)

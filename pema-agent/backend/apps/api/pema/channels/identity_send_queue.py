"""One send queue, one gap and one cap per clinic identity (package O, step O4). New module, no zalo-agent
original.

A channel account is the identity the customer sees ("Long"). Before O4 the gap lived in the per-thread rate
limiter and the cap in the personal-Zalo gate (per channel row, per thread); a second operator, or the agent
next to an operator, did not share either. This module is the one place that answers "may this identity send
now, and when":

* ``send`` runs ONE part of a message through the identity: the kill switch of its channel, then the gap. The
  gap is shared by everybody who sends through the identity (the agent, every operator, the scheduler's
  proactive sends when they go through ``reply_target_from_channel``): one lock per identity
  (``SendSlotBackend``,
  Redis in production) serialises the sends and a last-send timestamp spaces them by a random wait between the
  EFFECTIVE minimum and maximum gap of the identity (``clinic.actions.identities.effective_limits``: its own
  override, else the row of its channel). Separate identities never wait for each other.
* ``admit`` / ``settle`` are the per-MESSAGE half, called once before a message is cut into parts: it
  refuses an ``internal`` identity (a notifier never faces a customer), a disabled one, a channel whose
  kill switch is on,
  and, for a PROACTIVE message only, reserves one slot of the daily cap of the identity (refunded when the
  message did not leave). A reply inside a customer-started exchange respects the gap, not the cap.

Everything that waits takes its clock, its ``sleep`` and its ``uniform`` as arguments, so tests run without
sleeping. The backend is allowed to fail: a Redis outage is logged and the send goes ahead unspaced (the
in-process lock still serialises this process), exactly like the scheduler's send gate; the kill switch
and the
cap do not depend on Redis.

``send`` passes an identity it does not know, or one with ``purpose = internal``, straight through: the
internal notifier (package O3) is not a customer identity and has its own limits. The refusal of an internal
identity for a CUSTOMER message is in ``admit`` (``RegistryOutboundDelivery``) and in the clinic action
``deliver_queued_message``.
"""

from __future__ import annotations

import asyncio
import random
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from pema.channels.zalo_personal.proactive_gate import InMemoryProactiveCounter
from pema.config.runtime_tuning_settings import bot_time_zone
from pema.shared.logger import create_logger
from pema.shared.zone_time import today_key
from pema_contracts.channel import SendResult, SendStatus
from pema_contracts.errors import ErrorCode
from pema_contracts.ops import IdentityOut, IdentityPurpose
from pema_contracts.scheduler import ProactiveSendGuard

log = create_logger("identity-send-queue")

KEY_PREFIX = "pema:identity-send"
LOCK_TTL_MS = 120_000
"""A holder that dies mid-send frees the identity after this long."""
POLL_S = 0.025
CAP_SCOPE_PREFIX = "identity"

type IdentityLookup = Callable[[str], Awaitable[IdentityOut | None]]
"""``identities.identity_for_send`` bound to the clinic: the identity as the send path needs it, fresh."""


class SendSlotBackend(Protocol):
    """The slice of Redis the queue uses: a lock with a token and a last-send timestamp."""

    async def acquire(self, key: str, ttl_ms: int) -> str | None:
        """Take ``key`` for ``ttl_ms``; the owner token, or ``None`` when somebody else holds it."""
        ...

    async def release(self, key: str, token: str) -> None:
        """Release ``key`` only if ``token`` still owns it."""
        ...

    async def last_sent(self, key: str) -> float | None:
        """Epoch seconds of the last send of the identity, ``None`` when unknown."""
        ...

    async def mark_sent(self, key: str, at: float, ttl_s: int) -> None: ...


class InMemorySendSlotBackend:
    """Process-local backend for tests and a single-process run. ``clock`` returns epoch seconds."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._held: dict[str, tuple[str, float]] = {}
        self._last: dict[str, float] = {}

    async def acquire(self, key: str, ttl_ms: int) -> str | None:
        now = self._clock()
        current = self._held.get(key)
        if current is not None and current[1] > now:
            return None
        token = secrets.token_hex(8)
        self._held[key] = (token, now + ttl_ms / 1000)
        return token

    async def release(self, key: str, token: str) -> None:
        current = self._held.get(key)
        if current is not None and current[0] == token:
            del self._held[key]

    async def last_sent(self, key: str) -> float | None:
        return self._last.get(key)

    async def mark_sent(self, key: str, at: float, ttl_s: int) -> None:
        self._last[key] = at


_RELEASE_SCRIPT = (
    "if redis.call('get', KEYS[1]) == ARGV[1] then return redis.call('del', KEYS[1]) else return 0 end"
)


class RedisSendSlotBackend:
    """``SET key token NX PX ttl`` to take, a compare-and-delete script to release, ``SET``/``GET`` for the
    last-send timestamp (which expires by itself: after the longest gap there is nothing left to space)."""

    def __init__(self, redis: Any) -> None:
        self._redis = redis

    async def acquire(self, key: str, ttl_ms: int) -> str | None:
        token = secrets.token_hex(8)
        taken = await self._redis.set(key, token, nx=True, px=ttl_ms)
        return token if taken else None

    async def release(self, key: str, token: str) -> None:
        await self._redis.eval(_RELEASE_SCRIPT, 1, key, token)

    async def last_sent(self, key: str) -> float | None:
        raw = await self._redis.get(key)
        return None if raw is None else float(raw)

    async def mark_sent(self, key: str, at: float, ttl_s: int) -> None:
        await self._redis.set(key, repr(at), ex=max(1, ttl_s))


@dataclass(frozen=True)
class IdentityAdmission:
    """Result of ``IdentitySendQueue.admit``: a rejection to return, or a reservation to ``settle``."""

    rejection: SendResult | None = None
    scope_key: str | None = None
    day_key: str | None = None

    @property
    def admitted(self) -> bool:
        return self.rejection is None


def _rejected(code: ErrorCode, detail: str) -> IdentityAdmission:
    return IdentityAdmission(rejection=SendResult(status=SendStatus.REJECTED, error_code=code, detail=detail))


class IdentitySendQueue:
    def __init__(
        self,
        *,
        clinic_id: UUID | Callable[[], UUID],
        lookup: IdentityLookup,
        backend: SendSlotBackend | None = None,
        counter: ProactiveSendGuard | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        uniform: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self._clinic_id: Callable[[], UUID] = clinic_id if callable(clinic_id) else (lambda: clinic_id)
        self._lookup = lookup
        self._backend: SendSlotBackend = backend or InMemorySendSlotBackend(clock)
        self._counter: ProactiveSendGuard = counter or InMemoryProactiveCounter()
        self._clock = clock
        self._sleep = sleep
        self._uniform = uniform
        self._local: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------------------------- per message
    async def is_customer_facing(self, account_id: str) -> bool:
        """``True`` for a ``customer`` identity. An unknown account counts as customer-facing: the guard is
        only about the account known to be internal."""
        identity = await self._lookup(account_id)
        return identity is None or identity.purpose is IdentityPurpose.CUSTOMER

    async def admit(self, account_id: str, *, proactive: bool) -> IdentityAdmission:
        """Checks for ONE customer message, before it is cut into parts. First failure wins; a proactive
        message also reserves one slot of the identity's daily cap (``settle`` keeps or refunds it)."""
        identity = await self._lookup(account_id)
        if identity is None:
            return _rejected(ErrorCode.CHANNEL_UNAVAILABLE, "unknown_identity")
        if identity.purpose is IdentityPurpose.INTERNAL:
            return _rejected(ErrorCode.POLICY_DENIED, "internal_identity")
        if not identity.enabled:
            return _rejected(ErrorCode.CHANNEL_UNAVAILABLE, "identity_disabled")
        if identity.kill_switch_on:
            return _rejected(ErrorCode.CHANNEL_KILL_SWITCH_ON, "kill_switch_on")
        cap = identity.effective.daily_cap
        if not proactive or cap is None:
            return IdentityAdmission()
        scope_key = f"{CAP_SCOPE_PREFIX}:{account_id}"
        day_key = today_key(bot_time_zone(), datetime.fromtimestamp(self._clock(), UTC))
        slot = await self._counter.reserve_slot(scope_key, day_key, cap)
        if not slot.reserved:
            log.warning("identity daily cap reached", account_id=account_id, cap=cap)
            return _rejected(ErrorCode.CHANNEL_DAILY_CAP_REACHED, "daily_cap_reached")
        return IdentityAdmission(scope_key=scope_key, day_key=day_key)

    async def settle(self, admission: IdentityAdmission, *, sent: bool) -> None:
        """Keep the cap slot when the message left, give it back when it did not."""
        if sent or admission.scope_key is None or admission.day_key is None:
            return
        await self._counter.refund_slot(admission.scope_key, admission.day_key)

    # --------------------------------------------------------------------------------------- per part
    async def send(self, account_id: str, call: Callable[[], Awaitable[SendResult]]) -> SendResult:
        """Run ONE part through the identity: kill switch, then the shared gap. The daily cap is not touched
        here: ``admit`` reserved it once for the whole message."""
        identity = await self._lookup(account_id)
        if identity is None or identity.purpose is IdentityPurpose.INTERNAL:
            return await call()
        if identity.kill_switch_on:
            return SendResult(
                status=SendStatus.REJECTED,
                error_code=ErrorCode.CHANNEL_KILL_SWITCH_ON,
                detail="kill_switch_on",
            )
        limits = identity.effective
        local = self._local.setdefault(account_id, asyncio.Lock())
        async with local:  # FIFO inside this process, then the lock across processes
            lock_key = f"{KEY_PREFIX}:lock:{self._clinic_id()}:{account_id}"
            last_key = f"{KEY_PREFIX}:last:{self._clinic_id()}:{account_id}"
            token = await self._take(lock_key)
            try:
                await self._wait_gap(last_key, limits.send_gap_min_s, limits.send_gap_max_s)
                result = await call()
                if result.status is SendStatus.SENT:
                    await self._stamp(last_key, limits.send_gap_max_s)
                return result
            finally:
                if token is not None:
                    await self._release(lock_key, token)

    # ------------------------------------------------------------------------------------- internals
    async def _take(self, key: str) -> str | None:
        """The cross-process lock of the identity; ``None`` when the backend failed (fail open)."""
        while True:
            try:
                token = await self._backend.acquire(key, LOCK_TTL_MS)
            except Exception as err:
                log.warning("identity send lock unavailable, sending without it", err=err)
                return None
            if token is not None:
                return token
            await self._sleep(POLL_S)

    async def _release(self, key: str, token: str) -> None:
        try:
            await self._backend.release(key, token)
        except Exception as err:
            log.warning("identity send lock release failed (it expires by itself)", err=err)

    async def _wait_gap(self, last_key: str, low: int, high: int) -> None:
        if high <= 0:
            return
        try:
            last = await self._backend.last_sent(last_key)
        except Exception as err:
            log.warning("identity last-send time unavailable, not spacing this send", err=err)
            return
        if last is None:
            return
        wanted = self._uniform(float(low), float(high))
        remaining = wanted - (self._clock() - last)
        if remaining > 0:
            await self._sleep(remaining)

    async def _stamp(self, last_key: str, high: int) -> None:
        try:
            await self._backend.mark_sent(last_key, self._clock(), max(60, high * 2))
        except Exception as err:
            log.warning("identity last-send time not recorded", err=err)


_installed: IdentitySendQueue | None = None


def install_identity_send_queue(queue: IdentitySendQueue | None) -> None:
    """The process-wide queue ``reply_target_from_channel`` uses when no queue is passed: the agent's reply
    path and the scheduler build their targets without knowing about it. ``pema.composition`` installs it at
    startup; tests install their own or ``None``."""
    global _installed
    _installed = queue


def installed_identity_send_queue() -> IdentitySendQueue | None:
    return _installed

"""Locks of the scheduler (new tests, no zalo-agent source): the in-memory backend and, when
``PEMA_TEST_REDIS_URL`` points at a THROWAWAY Redis, the real ``RedisLockBackend``.

What Redis carries is only what SQL cannot express cheaply (see ``redis_locks``): the per-clinic tick lease and
the cross-process spacing of proactive sends per (clinic, account). Correctness of the job claim and of the cap
never depends on it (proved in ``test_scheduler_loop`` with workers that share NO lock at all).
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from redis.asyncio import Redis

from pema.scheduler.redis_locks import (
    InMemoryLockBackend,
    LockBackend,
    LockSendGate,
    RedisLockBackend,
    TickLease,
    send_gate_key,
    tick_lease_key,
)

REDIS_URL = os.environ.get("PEMA_TEST_REDIS_URL")


@pytest_asyncio.fixture(params=["memory", "redis"])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[LockBackend]:
    if request.param == "memory":
        yield InMemoryLockBackend()
        return
    if not REDIS_URL:
        pytest.skip("PEMA_TEST_REDIS_URL not set; no Redis to test against")
    client = Redis.from_url(REDIS_URL)  # pyright: ignore[reportUnknownMemberType]
    try:
        yield RedisLockBackend(client)
    finally:
        await client.aclose()


def unique(prefix: str) -> str:
    return f"pema:test:{prefix}:{uuid.uuid4().hex}"


async def test_acquire_is_exclusive_until_released_and_release_needs_the_owner_token(
    backend: LockBackend,
) -> None:
    """khoá loại trừ lẫn nhau tới khi nhả; chỉ chủ (token) mới nhả được"""
    key = unique("excl")
    token = await backend.acquire(key, 5000)
    assert token is not None
    assert await backend.acquire(key, 5000) is None

    await backend.release(key, "token-cua-nguoi-khac")  # a stranger cannot release it
    assert await backend.acquire(key, 5000) is None

    await backend.release(key, token)
    assert await backend.acquire(key, 5000) is not None


async def test_a_lock_expires_by_itself_and_remaining_ms_reports_the_time_left(backend: LockBackend) -> None:
    """khoá tự hết hạn; remaining_ms báo thời gian còn lại"""
    key = unique("ttl")
    assert await backend.acquire(key, 150) is not None
    assert 0 < await backend.remaining_ms(key) <= 150
    await asyncio.sleep(0.25)
    assert await backend.remaining_ms(key) == 0
    assert await backend.acquire(key, 150) is not None


async def test_a_worker_cannot_release_a_lock_that_expired_and_was_taken_by_another(
    backend: LockBackend,
) -> None:
    """worker chậm KHÔNG được nhả khoá đã hết hạn và đã bị worker khác giành (compare-and-delete)"""
    key = unique("stale")
    slow = await backend.acquire(key, 100)
    assert slow is not None
    await asyncio.sleep(0.2)
    fast = await backend.acquire(key, 5000)
    assert fast is not None

    await backend.release(key, slow)  # the slow worker wakes up late

    assert await backend.acquire(key, 5000) is None, "khoá của worker nhanh vẫn phải còn nguyên"


async def test_tick_lease_gives_a_clinic_to_one_worker_per_tick(backend: LockBackend) -> None:
    """cho thuê tick: chỉ 1 worker nhận phòng khám trong một tick, tick sau thì nhận lại"""
    clinic = uuid.uuid4()
    first = TickLease(backend, lambda: 200)
    second = TickLease(backend, lambda: 200)
    assert await first.try_hold(clinic) is True
    assert await second.try_hold(clinic) is False
    await asyncio.sleep(0.25)
    assert await second.try_hold(clinic) is True
    assert tick_lease_key(clinic).endswith(str(clinic))


async def test_send_gate_spaces_two_workers_sending_to_the_same_account_by_the_gap(
    backend: LockBackend,
) -> None:
    """cổng gửi: 2 worker cùng gửi cho MỘT account cách nhau tối thiểu gap; account khác không bị chặn lẫn nhau"""
    clinic = uuid.uuid4()
    gate_a = LockSendGate(backend, poll_ms=10)
    gate_b = LockSendGate(backend, poll_ms=10)
    key = send_gate_key(clinic, "acc-1")
    other_key = send_gate_key(clinic, "acc-2")
    stamps: list[float] = []

    async def go(gate: LockSendGate, k: str) -> None:
        await gate.wait_turn(k, 200)
        stamps.append(time.monotonic())

    await go(gate_a, other_key)  # another account: no wait at all
    started = time.monotonic()
    await asyncio.gather(go(gate_a, key), go(gate_b, key))

    same_account = sorted(stamps[1:])
    assert same_account[0] - started < 0.1, "người đầu tiên không phải chờ"
    assert same_account[1] - same_account[0] >= 0.15, "người thứ hai phải chờ ~gap sau người đầu"


async def test_send_gate_with_a_zero_gap_never_waits(backend: LockBackend) -> None:
    """gap = 0 thì không chờ gì"""
    gate = LockSendGate(backend)
    started = time.monotonic()
    await gate.wait_turn(unique("zero"), 0)
    await gate.wait_turn(unique("zero"), 0)
    assert time.monotonic() - started < 0.05

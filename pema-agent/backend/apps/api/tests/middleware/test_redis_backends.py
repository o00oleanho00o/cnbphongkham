"""Tests of the Redis implementations (no TypeScript original: zalo-agent had no Redis).

Set ``PEMA_TEST_REDIS_URL`` to a THROWAWAY Redis, for example::

    docker run -d --name pema-redis-test -p 127.0.0.1:56379:6379 redis:7-alpine
    PEMA_TEST_REDIS_URL=redis://127.0.0.1:56379/0 uv run pytest apps/api/tests/middleware/test_redis_backends.py

Every test uses its own key namespace, so nothing needs flushing. Without the variable the module is skipped.
The same behaviour contract is run against the in-memory store, so the two cannot drift.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from uuid import UUID

import pytest

from pema.middleware.message_batcher import (
    TRAN_TIN_DON,
    InMemoryPendingBatchStore,
    MessageBatcher,
    PendingBatchStore,
    StorePendingInbox,
)
from pema.middleware.redis_backends import RedisPendingBatchStore, RedisThreadRunChain, RedisTurnQueue
from pema.middleware.redis_ops import AsyncRedisOps
from pema.middleware.thread_run_chain import ClinicThreadLock, QueueThreadRunner, ThreadRef
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi, doi_cho_so_luong
from pema_contracts.agent_turn import PendingInbox, ThreadLock, TurnJob, TurnQueue
from pema_contracts.channel import InboundMessage
from pema_contracts.common import now_vn
from pema_contracts.testing import make_inbound

REDIS_URL = os.environ.get("PEMA_TEST_REDIS_URL")
if not REDIS_URL:
    pytest.skip("PEMA_TEST_REDIS_URL not set; no Redis to test against", allow_module_level=True)

CLINIC = UUID("00000000-0000-4000-8000-0000000000c1")


@pytest.fixture
async def ops() -> AsyncIterator[AsyncRedisOps]:
    assert REDIS_URL is not None
    instance = AsyncRedisOps.from_url(REDIS_URL)
    yield instance
    await instance.aclose()


@pytest.fixture
def ns() -> str:
    return f"pematest-{uuid.uuid4().hex[:8]}"


def msg(text: str, sender: str = "u-1", row: int | None = None) -> InboundMessage:
    return make_inbound(
        text, thread_id="t-1", sender_id=sender, update_id=f"u-{text}", msg_id=f"m-{text}", history_row_id=row
    )


@pytest.fixture(params=["memory", "redis"])
def store(request: pytest.FixtureRequest, ops: AsyncRedisOps, ns: str) -> PendingBatchStore:
    if request.param == "memory":
        return InMemoryPendingBatchStore()
    return RedisPendingBatchStore(ops, namespace=ns)


# ------------------------------------------------------------------------------------------ the store contract


async def test_store_append_get_pop_keeps_arrival_order_and_roundtrips_the_message(
    store: PendingBatchStore,
) -> None:
    """append/get/pop giữ thứ tự tới và trả lại đúng tin (cả hai bản cài đặt)"""
    first = await store.append("k", "u-1", msg("a", row=7), 1000.0, TRAN_TIN_DON)
    second = await store.append("k", "u-1", msg("b"), 2000.0, TRAN_TIN_DON)
    assert first.accepted
    assert second.accepted

    got = await store.get("k", "u-1")
    assert got is not None
    assert [m.text for m in got.messages] == ["a", "b"]
    assert got.messages[0].history_row_id == 7
    assert got.deadline_ms == 2000.0, "tin mới phải đẩy hạn lùi"

    popped = await store.pop("k", "u-1")
    assert popped is not None
    assert [m.text for m in popped.messages] == ["a", "b"]
    assert await store.get("k", "u-1") is None
    assert await store.pop("k", "u-1") is None, "pop là một lần: lần hai không còn gì"


async def test_store_cap_drops_the_new_message_without_moving_the_deadline(store: PendingBatchStore) -> None:
    """chạm trần thì BỎ tin mới, không dời hạn, đếm số tin bị bỏ"""
    for i in range(TRAN_TIN_DON):
        assert (await store.append("k", "u-1", msg(f"t{i}"), 1000.0, TRAN_TIN_DON)).accepted
    over = await store.append("k", "u-1", msg("thua"), 9999.0, TRAN_TIN_DON)
    assert over.accepted is False
    assert over.dropped == 1

    got = await store.get("k", "u-1")
    assert got is not None
    assert len(got.messages) == TRAN_TIN_DON
    assert got.deadline_ms == 1000.0
    assert got.dropped == 1


async def test_store_parked_batches_are_listed_and_only_a_parked_one_can_be_taken_mid_turn(
    store: PendingBatchStore,
) -> None:
    """chỉ batch đã đỗ (hết im lặng) mới lấy giữa lượt được"""
    await store.append("k", "u-1", msg("a"), 1000.0, TRAN_TIN_DON)
    assert await store.pop("k", "u-1", only_if_parked=True) is None, "còn đang gõ dở"
    assert await store.list_parked_thread_keys() == []

    await store.mark_parked("k", "u-1")
    assert await store.list_parked_thread_keys() == ["k"]
    taken = await store.pop("k", "u-1", only_if_parked=True)
    assert taken is not None
    assert taken.deadline_ms is None


async def test_store_mark_parked_on_a_missing_batch_creates_nothing(store: PendingBatchStore) -> None:
    """đỗ một batch không tồn tại thì không sinh ra rác"""
    await store.mark_parked("k", "u-ghost")
    assert await store.count() == 0


async def test_store_list_for_thread_follows_first_message_order_and_isolates_threads(
    store: PendingBatchStore,
) -> None:
    """list theo thread: đúng thứ tự tin ĐẦU TIÊN của mỗi người, không lẫn thread khác"""
    await store.append("k", "u-a", msg("A"), 1.0, TRAN_TIN_DON)
    await asyncio.sleep(0.01)
    await store.append("k", "u-b", msg("B"), 1.0, TRAN_TIN_DON)
    await store.append("k-khac", "u-a", msg("X"), 1.0, TRAN_TIN_DON)

    assert [b.sender_id for b in await store.list_for_thread("k")] == ["u-a", "u-b"]
    assert [b.sender_id for b in await store.list_for_thread("k-khac")] == ["u-a"]


async def test_store_remove_thread_and_clear(store: PendingBatchStore) -> None:
    """remove_thread dọn mọi người của thread; clear dọn tất cả"""
    await store.append("k", "u-a", msg("a"), 1.0, TRAN_TIN_DON)
    await store.append("k", "u-b", msg("b"), 1.0, TRAN_TIN_DON)
    await store.append("k-khac", "u-a", msg("c"), 1.0, TRAN_TIN_DON)

    removed = await store.remove_thread("k")
    assert sorted(b.sender_id for b in removed) == ["u-a", "u-b"]
    assert await store.list_for_thread("k") == []
    assert await store.count() == 1

    await store.clear()
    assert await store.count() == 0


# ------------------------------------------------------------------------------------------------- thread lock


async def test_redis_lock_serialises_two_holders_and_reports_busy(ops: AsyncRedisOps, ns: str) -> None:
    """khóa Redis: hai bên cùng thread nối tiếp nhau, và busy được báo đúng"""
    # Two chains over the same Redis stand for the API process and the worker process.
    worker = RedisThreadRunChain(ops, namespace=ns, poll_ms=5)
    api = RedisThreadRunChain(ops, namespace=ns, poll_ms=5)
    lock = ClinicThreadLock(worker, CLINIC)
    key = ThreadRef(CLINIC, "acc-1", "t-1").key
    events: list[str] = []
    release_first = asyncio.Event()

    async def first() -> None:
        async with lock.hold("acc-1", "t-1"):
            events.append("start:1")
            await release_first.wait()
            events.append("end:1")

    async def second() -> None:
        async with lock.hold("acc-1", "t-1"):
            events.append("start:2")

    t1 = asyncio.create_task(first())
    await doi_cho_den_khi(lambda: "start:1" in events, WaitOptions(mo_ta="người giữ khóa đầu"))
    t2 = asyncio.create_task(second())

    assert await api.is_busy(key) is True, "tiến trình API phải thấy thread đang bận"
    busy = await api.busy_for_ms(key)
    assert busy is not None
    await asyncio.sleep(0.05)
    assert events == ["start:1"], "bên thứ hai phải chờ"

    release_first.set()
    await asyncio.gather(t1, t2)
    assert events == ["start:1", "end:1", "start:2"]
    assert await api.is_busy(key) is False
    assert await api.busy_for_ms(key) is None


async def test_redis_lock_fires_the_free_hook_on_release_and_survives_a_failing_hook(
    ops: AsyncRedisOps, ns: str
) -> None:
    """nhả khóa thì bắn hook rảnh; một hook ném lỗi không nuốt hook sau"""
    chain = RedisThreadRunChain(ops, namespace=ns, poll_ms=5)
    fired: list[str] = []

    def bad(key: str) -> None:
        raise RuntimeError("hook hỏng")

    chain.on_thread_free(bad)
    chain.on_thread_free(fired.append)
    key = ThreadRef(CLINIC, "acc-1", "t-1").key
    async with chain.hold_key(key):
        pass
    assert fired == [key]


# ---------------------------------------------------------------------------------------------- turn queue


def job(text: str = "a", thread: str = "t-1") -> TurnJob:
    return TurnJob(
        job_id=uuid.uuid4(),
        clinic_id=CLINIC,
        account_id="acc-1",
        thread_id=thread,
        messages=[make_inbound(text, thread_id=thread)],
        enqueued_at=now_vn(),
    )


async def test_turn_queue_enqueue_claim_ack_and_the_thread_is_busy_until_ack(
    ops: AsyncRedisOps, ns: str
) -> None:
    """hàng đợi lượt: enqueue/claim/ack; thread bận từ lúc enqueue tới lúc ack"""
    chain = RedisThreadRunChain(ops, namespace=ns)
    queue: TurnQueue = RedisTurnQueue(ops, chain, namespace=ns)
    key = ThreadRef(CLINIC, "acc-1", "t-1").key
    fired: list[str] = []
    chain.on_thread_free(fired.append)

    j = job()
    await queue.enqueue(j)
    assert await chain.is_busy(key) is True, (
        "đã xếp hàng là phải đếm bận (không thì batch kế tiếp thành lượt thứ hai)"
    )

    claimed = await queue.claim(1)
    assert claimed is not None
    assert claimed.job_id == j.job_id
    assert claimed.messages[0].text == "a"
    assert await chain.is_busy(key) is True

    await queue.ack(j.job_id)
    assert await chain.is_busy(key) is False
    assert fired == [key]
    assert await queue.claim(0.1) is None


async def test_turn_queue_nack_retry_requeues_with_attempt_plus_one_and_keeps_the_thread_busy(
    ops: AsyncRedisOps, ns: str
) -> None:
    """nack(retry) đưa lại hàng đợi với attempt+1 và thread vẫn bận; nack(không retry) thả"""
    chain = RedisThreadRunChain(ops, namespace=ns)
    queue = RedisTurnQueue(ops, chain, namespace=ns)
    key = ThreadRef(CLINIC, "acc-1", "t-1").key

    j = job()
    await queue.enqueue(j)
    first = await queue.claim(1)
    assert first is not None
    await queue.nack(first.job_id, retry=True)
    assert await chain.is_busy(key) is True

    second = await queue.claim(1)
    assert second is not None
    assert second.job_id == j.job_id
    assert second.attempt == 2

    await queue.nack(second.job_id, retry=False)
    assert await chain.is_busy(key) is False
    assert await queue.claim(0.1) is None


async def test_turn_queue_reclaims_a_job_whose_worker_died(ops: AsyncRedisOps, ns: str) -> None:
    """worker chết sau khi claim: quá hạn visibility thì job quay lại hàng đợi"""
    chain = RedisThreadRunChain(ops, namespace=ns)
    queue = RedisTurnQueue(ops, chain, namespace=ns, visibility_timeout_ms=0)

    j = job()
    await queue.enqueue(j)
    assert await queue.claim(1) is not None  # claimed, never acked
    await asyncio.sleep(0.01)

    assert await queue.reclaim_expired() == 1
    again = await queue.claim(1)
    assert again is not None
    assert again.job_id == j.job_id


# ----------------------------------------------------------------------------- pending inbox and the batcher


async def test_pending_inbox_over_redis_serves_the_worker(ops: AsyncRedisOps, ns: str) -> None:
    """PendingInbox qua Redis: worker kéo được tin đỗ và id history của tin đang chờ"""
    store = RedisPendingBatchStore(ops, namespace=ns)
    key = ThreadRef(CLINIC, "acc-1", "t-1").key
    inbox: PendingInbox = StorePendingInbox(store, CLINIC)

    await store.append(key, "u-1", msg("a", row=5), 1.0, TRAN_TIN_DON)
    await store.append(key, "u-2", msg("b", sender="u-2", row=6), 1.0, TRAN_TIN_DON)
    assert sorted(await inbox.pending_history_ids("acc-1", "t-1")) == [5, 6]
    assert await inbox.take_injected("acc-1", "t-1") == [], "còn đang gõ dở thì chưa được kéo"

    await store.mark_parked(key, "u-1")
    await store.mark_parked(key, "u-2")
    taken = await StorePendingInbox(store, CLINIC).take_injected("acc-1", "t-1", "u-2")
    assert [m.text for m in taken] == ["b"], "có sender_id thì chỉ kéo tin của người đó"
    rest = await inbox.take_injected("acc-1", "t-1")
    assert [m.text for m in rest] == ["a"]


async def test_batcher_over_redis_parks_while_the_worker_holds_the_lock_and_dispatches_when_it_is_free(
    ops: AsyncRedisOps, ns: str
) -> None:
    """batcher + Redis: khóa do worker giữ thì đỗ, rảnh thì chốt (kiểm bằng thăm dò vì khác tiến trình)"""
    store = RedisPendingBatchStore(ops, namespace=ns)
    api_chain = RedisThreadRunChain(ops, namespace=ns)
    worker_chain = RedisThreadRunChain(ops, namespace=ns, poll_ms=5)
    batches: list[list[str]] = []

    async def default_handler(thread_key: str, batch: list[InboundMessage]) -> None:
        batches.append([m.text for m in batch])

    batcher = MessageBatcher(
        store, QueueThreadRunner(api_chain), default_handler=default_handler, parked_recheck_ms=20
    )
    key = ThreadRef(CLINIC, "acc-1", "t-1").key
    lock = ClinicThreadLock(worker_chain, CLINIC)
    try:
        hold = lock.hold("acc-1", "t-1")
        await hold.__aenter__()  # the worker is running a turn
        await batcher.enqueue_message(key, msg("a"), debounce_ms=20)
        await asyncio.sleep(0.15)
        assert batches == [], "worker còn giữ khóa thì chưa chốt"
        await batcher.enqueue_message(key, msg("b"), debounce_ms=20)
        await asyncio.sleep(0.1)
        assert batches == []

        await hold.__aexit__(None, None, None)
        await doi_cho_so_luong(
            lambda: len(batches), 1, WaitOptions(mo_ta="lượt chốt sau khi worker nhả khóa")
        )
        assert batches == [["a", "b"]]
    finally:
        await batcher.clear_pending_batches()


async def test_pending_inbox_and_thread_lock_satisfy_the_contract_protocols(
    ops: AsyncRedisOps, ns: str
) -> None:
    """kiểm kiểu: các adapter khớp Protocol của pema_contracts"""
    chain = RedisThreadRunChain(ops, namespace=ns)
    lock: ThreadLock = ClinicThreadLock(chain, CLINIC)
    inbox: PendingInbox = StorePendingInbox(RedisPendingBatchStore(ops, namespace=ns), CLINIC)
    assert lock is not None
    assert inbox is not None

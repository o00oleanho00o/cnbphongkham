"""The turn worker and ``process_turn_job`` (new module, no zalo-agent original): claim, guards, lock, ack/nack."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest

from pema.channels.message_turn_processor import MAX_JOB_ATTEMPTS, process_turn_job
from pema.channels.pipeline_testing import FakeEngine, TurnRig, answer
from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.send_reply_in_parts import reset_khu_trung_bao_loi
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema.workers.turn_worker import TurnWorker, TurnWorkerOptions
from pema_contracts.agent_turn import AgentTurnRequest, AgentTurnResult, TurnCallbacks, TurnJob
from pema_contracts.testing import FAKE_CLINIC_ID, InMemoryTurnQueue, new_turn_job

THREAD = "t-worker"


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    reset_khu_trung_bao_loi()
    yield
    reset_khu_trung_bao_loi()


async def job_for(rig: TurnRig, text: str = "chào", msg_id: str = "m1", attempt: int = 1) -> TurnJob:
    msg = await rig.receive(text, msg_id, thread_id=THREAD)
    job = new_turn_job(FAKE_CLINIC_ID, msg)
    return job.model_copy(update={"account_id": rig.config.id, "thread_id": THREAD, "attempt": attempt})


async def test_job_hop_le_chay_het_luot_roi_ack() -> None:
    rig = TurnRig.create(engine=FakeEngine(script=answer("chào anh")))
    queue = InMemoryTurnQueue()
    job = await job_for(rig)
    await queue.enqueue(job)
    claimed = await queue.claim(0)
    assert claimed is not None

    await process_turn_job(rig.services, queue, claimed)

    assert rig.sent_texts() == ["chào anh"]
    assert queue.acked == [job.job_id]


async def test_account_bi_tat_trong_luc_job_cho_trong_hang_thi_job_bi_bo_khong_chay_agent() -> None:
    """công tắc an toàn thắng tin đã xếp hàng"""
    rig = TurnRig.create()
    queue = InMemoryTurnQueue()
    job = await job_for(rig)
    rig.services.accounts.accounts[(FAKE_CLINIC_ID, rig.config.id)] = rig.config.model_copy(  # type: ignore[attr-defined]
        update={"enabled": False}
    )

    await process_turn_job(rig.services, queue, job)

    assert rig.engine.requests == []
    assert rig.api.sent == []
    assert queue.acked == [job.job_id]


async def test_account_khong_ton_tai_thi_job_bi_bo() -> None:
    rig = TurnRig.create()
    queue = InMemoryTurnQueue()
    job = (await job_for(rig)).model_copy(update={"account_id": "khong-co"})
    await process_turn_job(rig.services, queue, job)
    assert queue.acked == [job.job_id]
    assert rig.engine.requests == []


async def test_account_chua_chay_trong_worker_nay_thi_nack_thu_lai_roi_bo_sau_tran_so_lan() -> None:
    rig = TurnRig.create()
    rig.services.registry = InMemoryChannelRegistry()
    queue = InMemoryTurnQueue()

    first = await job_for(rig, attempt=1)
    await process_turn_job(rig.services, queue, first)
    last = await job_for(rig, msg_id="m2", attempt=MAX_JOB_ATTEMPTS)
    await process_turn_job(rig.services, queue, last)

    assert queue.nacked == [(first.job_id, True), (last.job_id, False)]
    assert rig.engine.requests == []
    assert rig.api.sent == []


async def test_loi_ha_tang_ngoai_luot_thi_nack_thu_lai() -> None:
    rig = TurnRig.create()
    queue = InMemoryTurnQueue()

    async def broken(*args: object, **kwargs: object) -> int:
        raise RuntimeError("DB down")

    rig.conversation.open_agent_turn = broken  # type: ignore[method-assign]
    job = await job_for(rig)
    await process_turn_job(rig.services, queue, job)

    assert queue.nacked == [(job.job_id, True)]
    assert queue.acked == []


async def test_hai_luot_cung_thread_chay_noi_tiep_khong_chong_len_nhau() -> None:
    order: list[str] = []
    release = asyncio.Event()

    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        label = request.batch[0].text
        order.append(f"start:{label}")
        if label == "một":
            await release.wait()
        order.append(f"end:{label}")
        return AgentTurnResult(text=f"trả lời {label}")

    rig = TurnRig.create(engine=FakeEngine(script=script))
    queue = InMemoryTurnQueue()
    one = await job_for(rig, "một", "m1")
    two = await job_for(rig, "hai", "m2")

    async def run(job: TurnJob) -> None:
        # The in-memory lock RAISES on overlap, so serialisation is the caller's job: this is what the Redis
        # ``ThreadLock`` does by waiting. Here the worker below serialises through a real lock-wait.
        await process_turn_job(rig.services, queue, job)

    first = asyncio.create_task(run(one))
    await doi_cho_den_khi(lambda: "start:một" in order, WaitOptions(mo_ta="lượt một bắt đầu"))
    release.set()
    await first
    await run(two)

    assert order == ["start:một", "end:một", "start:hai", "end:hai"]


async def test_worker_xu_ly_het_hang_doi_roi_dung_khi_stop() -> None:
    rig = TurnRig.create(engine=FakeEngine(script=answer("ok")))
    queue = InMemoryTurnQueue()
    for i in range(3):
        await queue.enqueue(await job_for(rig, f"tin {i}", f"m{i}"))

    worker = TurnWorker(rig.services, queue, TurnWorkerOptions(concurrency=1, block_seconds=0.01))
    task = asyncio.create_task(worker.run())
    await doi_cho_den_khi(lambda: len(queue.acked) == 3, WaitOptions(mo_ta="3 job được ack"))
    worker.stop()
    await asyncio.wait_for(task, timeout=2)

    assert len(rig.api.sent) == 3


async def test_worker_khong_chet_khi_hang_doi_loi() -> None:
    rig = TurnRig.create(engine=FakeEngine(script=answer("ok")))
    queue = InMemoryTurnQueue()
    original = queue.claim
    calls = {"n": 0}

    async def flaky(block_seconds: float) -> TurnJob | None:
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("redis down")
        return await original(block_seconds)

    queue.claim = flaky  # type: ignore[method-assign]
    await queue.enqueue(await job_for(rig))
    worker = TurnWorker(
        rig.services, queue, TurnWorkerOptions(concurrency=1, block_seconds=0.01, error_backoff_seconds=0.01)
    )
    task = asyncio.create_task(worker.run())
    await doi_cho_den_khi(
        lambda: len(queue.acked) == 1, WaitOptions(mo_ta="job được ack sau khi hàng đợi hồi phục")
    )
    worker.stop()
    await asyncio.wait_for(task, timeout=2)

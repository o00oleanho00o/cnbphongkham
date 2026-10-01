# ported from: src/zalo/message-turn-per-sender.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Nhiều người nhắn trong một nhóm. The batching by ``(thread, sender)`` is package C1 (``message_batcher``); what this
pipeline guarantees, and what is measured here, is: one turn per batch (one sender), the reply quotes the FIRST
message of that batch, the waiting messages of other people are excluded from the history of the turn
(``pending_history_ids`` is thread-wide), and turns of one thread run one after another under the ``ThreadLock``.
"""

from __future__ import annotations

from pema.channels.message_turn_processor import process_turn_job
from pema.channels.pipeline_testing import FakeEngine, TurnRig
from pema_contracts.agent_turn import AgentTurnRequest, AgentTurnResult, TokenUsage, TurnCallbacks, TurnJob
from pema_contracts.testing import InMemoryTurnQueue, new_turn_job

NHOM = "nhom-1"


def engine_vong_lai() -> FakeEngine:
    """Model giả: trả lời gắn với người đang hỏi Ở LƯỢT NÀY (tin CUỐI của batch)."""

    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        chu = request.batch[-1].text
        ai = next((t for t in ("Hải", "Nam", "Lan") if f"{t} hỏi" in chu), "?")
        return AgentTurnResult(text=f"trả lời cho {ai}", usage=TokenUsage(total_tokens=75, steps=1))

    return FakeEngine(script=script)


async def test_nhieu_nguoi_nhan_trong_mot_nhom_ba_nguoi_ba_luot_rieng_moi_cau_tra_loi_trich_dung_tin_cua_nguoi_do() -> (
    None
):
    """ba người: BA lượt riêng, mỗi câu trả lời trích đúng tin của người đó"""
    rig = TurnRig.create(engine=engine_vong_lai())
    for msg_id, chu, ten in (
        ("m-hai", "Hải hỏi giá vàng", "Hải"),
        ("m-nam", "Nam hỏi tỉ giá", "Nam"),
        ("m-lan", "Lan hỏi thời tiết", "Lan"),
    ):
        await rig.run([await rig.receive(chu, msg_id, thread_id=NHOM, sender=ten, is_group=True)])

    assert len(rig.api.sent) == 3, f"mong 3 câu trả lời riêng, nhận {len(rig.api.sent)}"
    # Mỗi câu trả lời phải trích tin của ĐÚNG người mà nó đang trả lời
    cap = sorted(f"{m.quote.sender_id if m.quote else None} <- {m.text}" for m in rig.api.sent)
    assert cap == [
        "u-Hải <- trả lời cho Hải",
        "u-Lan <- trả lời cho Lan",
        "u-Nam <- trả lời cho Nam",
    ]


async def test_nhieu_nguoi_nhan_trong_mot_nhom_tin_dang_cho_cua_nguoi_khac_khong_lot_vao_prompt_cua_luot_nay() -> (
    None
):
    """tin ĐANG CHỜ của người khác KHÔNG lọt vào prompt của lượt này"""
    # Tin đang chờ đã nằm trong lịch sử (ghi ngay lúc nhận) nên nếu không loại ra, nó vào prompt như một câu hỏi chưa
    # ai trả lời - model trả lời luôn cả câu đó, rồi lượt của người kia chạy và trả lời lần nữa. Việc loại là của
    # engine; pipeline phải đưa đủ id dòng của tin đang chờ (phạm vi THREAD) và KHÔNG đưa tin đó vào batch.
    seen: list[list[int]] = []

    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        assert callbacks is not None
        assert callbacks.pending_history_ids is not None
        seen.append(list(await callbacks.pending_history_ids()))
        return AgentTurnResult(text="ok", usage=TokenUsage(total_tokens=75, steps=1))

    rig = TurnRig.create(engine=FakeEngine(script=script))
    nam = await rig.receive("Nam hỏi tỉ giá", "m-nam-cho", thread_id=NHOM, sender="Nam", is_group=True)
    rig.pending.waiting.append(nam)

    await rig.run(
        [await rig.receive("Hải hỏi giá vàng", "m-hai-chay", thread_id=NHOM, sender="Hải", is_group=True)]
    )

    assert [m.text for m in rig.engine.requests[0].batch] == ["Hải hỏi giá vàng"], (
        "câu của chính lượt phải có"
    )
    assert seen == [[nam.history_row_id]], (
        "câu đang chờ của Nam sẽ có lượt riêng - phải được loại khỏi lịch sử"
    )


async def test_nhieu_nguoi_nhan_trong_mot_nhom_mot_nguoi_nhan_hai_tin_van_la_mot_luot() -> None:
    """một người nhắn hai tin vẫn là MỘT lượt - không tách theo tin"""
    rig = TurnRig.create(engine=engine_vong_lai())
    batch = [
        await rig.receive("Hải hỏi giá vàng", "m-1", thread_id=NHOM, sender="Hải", is_group=True),
        await rig.receive("và cả tỉ giá nữa", "m-2", thread_id=NHOM, sender="Hải", is_group=True),
    ]

    await rig.run(batch)

    assert len(rig.engine.requests) == 1
    assert len(rig.api.sent) == 1, f"một người phải ra đúng 1 câu trả lời, nhận {len(rig.api.sent)}"
    quote = rig.api.sent[0].quote
    assert quote is not None
    assert quote.msg_id == "m-1", "trích tin mở lượt của chính người đó"


async def test_nhieu_nguoi_nhan_trong_mot_nhom_ba_nguoi_nhan_luc_bot_ban_khi_ranh_van_du_ba_cau_tra_loi() -> (
    None
):
    """ba người nhắn lúc bot BẬN: khi rảnh vẫn đủ ba câu trả lời, không sót ai"""
    # Ba lượt cùng thread chạy NỐI TIẾP nhau qua `process_turn_job` (ThreadLock, thay cho `runOnThreadChain`).
    rig = TurnRig.create(engine=engine_vong_lai())
    queue = InMemoryTurnQueue()
    jobs: list[TurnJob] = []
    for msg_id, chu, ten in (
        ("m-b-hai", "Hải hỏi giá vàng", "Hải"),
        ("m-b-nam", "Nam hỏi tỉ giá", "Nam"),
        ("m-b-lan", "Lan hỏi thời tiết", "Lan"),
    ):
        msg = await rig.receive(chu, msg_id, thread_id=NHOM, sender=ten, is_group=True)
        job = new_turn_job(rig.clinic_id, msg)
        jobs.append(job.model_copy(update={"account_id": rig.config.id, "thread_id": NHOM}))
        await queue.enqueue(jobs[-1])

    while (job := await queue.claim(0)) is not None:
        await process_turn_job(rig.services, queue, job)

    assert len(rig.api.sent) == 3, f"mong 3 câu trả lời, nhận {len(rig.api.sent)}"
    assert sorted(m.quote.sender_id for m in rig.api.sent if m.quote) == ["u-Hải", "u-Lan", "u-Nam"]
    assert len(queue.acked) == 3

# ported from: src/zalo/message-turn-quote.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from pema.channels.pipeline_testing import FakeEngine, TurnRig, answer

NHOM = "nhom-1"
RIENG = "rieng-1"


def rig() -> TurnRig:
    return TurnRig.create(engine=FakeEngine(script=answer("Giá vàng hôm nay là...")))


async def test_process_batch_trich_dan_tin_nguoi_dung_trong_nhom_cau_tra_loi_trich_dung_tin_cua_nguoi_hoi() -> (
    None
):
    """trong NHÓM: câu trả lời trích đúng tin của người hỏi"""
    r = rig()
    await r.run([await r.receive("bot ơi giá vàng?", "m-hoi", thread_id=NHOM, is_group=True)])

    assert len(r.api.sent) == 1
    quote = r.api.sent[0].quote
    assert quote is not None
    assert quote.msg_id == "m-hoi"
    assert quote.sender_id == "u-Hải"
    assert quote.raw["content"] == "bot ơi giá vàng?"


async def test_process_batch_trich_dan_tin_nguoi_dung_chat_rieng_khong_trich_chi_co_hai_nguoi_trich_la_nhieu() -> (
    None
):
    """chat RIÊNG: KHÔNG trích - chỉ có hai người, trích là nhiễu"""
    r = rig()
    await r.run([await r.receive("chào bot", "m-rieng", thread_id=RIENG, is_group=False)])

    assert len(r.api.sent) == 1
    assert r.api.sent[0].quote is None


async def test_process_batch_trich_dan_tin_nguoi_dung_batch_nhieu_tin_trich_tin_dau_khong_phai_tin_cuoi() -> (
    None
):
    """batch NHIỀU tin: trích tin ĐẦU (tin mở lượt), không phải tin cuối"""
    r = rig()
    await r.run(
        [
            await r.receive("bot ơi tra giúp giá vàng", "m-dau", thread_id=NHOM, is_group=True, sender="Hải"),
            await r.receive("và cả tỉ giá nữa", "m-cuoi", thread_id=NHOM, is_group=True, sender="Nam"),
        ]
    )

    quote = r.api.sent[0].quote
    assert quote is not None
    assert quote.msg_id == "m-dau", "phải trích tin mở lượt"
    assert quote.msg_id != "m-cuoi"

# ported from: src/zalo/message-turn-timestamp.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Mốc giờ tin nhắn đi trọn hai lượt. The ``[dd/mm hh:mm] Name: text`` label the model reads is rendered by package D1
(``agent_turn_content``, ``history_to_model_messages``); those two label assertions of the original live in D1's
tests. What this pipeline guarantees, measured here: the instant the SENDER pressed send reaches the engine
untouched and is what the history row stores (never the instant the turn ended), and who said what is kept per
message in a multi-person batch.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pema.channels.pipeline_testing import TurnRig

THREAD = "t-gio"
GUI_LUC = datetime(2026, 8, 7, 17, 12, 0, tzinfo=UTC)


def history_rows(rig: TurnRig) -> list[tuple[str, str | None, datetime | None]]:
    return [
        (m.content, m.sender_name, m.created_at)
        for (_, a, t, m) in rig.conversation.messages
        if a == rig.config.id and t == THREAD and m.role == "user"
    ]


async def test_moc_gio_tin_nhan_di_tron_hai_luot_nhan_gio_cua_luot_nay_khop_nhan_cua_chinh_tin_do_o_luot_sau() -> (
    None
):
    """nhãn giờ của lượt này KHỚP nhãn của chính tin đó ở lượt sau"""
    rig = TurnRig.create()
    first = await rig.receive("giá vàng hôm nay", "m1", thread_id=THREAD, sent_at=GUI_LUC)
    await rig.run([first])
    await rig.run(
        [
            await rig.receive(
                "còn tỉ giá USD", "m2", thread_id=THREAD, sent_at=datetime(2026, 8, 7, 17, 20, tzinfo=UTC)
            )
        ]
    )

    turn1 = rig.engine.requests[0].batch[0]
    row = next(r for r in history_rows(rig) if "giá vàng hôm nay" in r[0])
    assert turn1.sent_at == GUI_LUC, "cùng một mốc ở lượt 1 (engine)"
    assert row[2] == GUI_LUC, "và ở lượt sau (đọc lại từ history): hai đường dựng không được trôi khỏi nhau"


async def test_moc_gio_tin_nhan_di_tron_hai_luot_nhan_gio_lay_tu_luc_gui_khong_phai_luc_luot_ket_thuc() -> (
    None
):
    """nhãn giờ lấy từ lúc GỬI, không phải lúc lượt kết thúc"""
    rig = TurnRig.create()
    await rig.run([await rig.receive("câu hỏi", "m1", thread_id=THREAD, sent_at=GUI_LUC)])

    assert rig.engine.requests[0].batch[0].sent_at == GUI_LUC


async def test_moc_gio_tin_nhan_di_tron_hai_luot_created_at_ghi_xuong_db_dung_bang_gio_gui_luot_dai_khong_lam_lech() -> (
    None
):
    """created_at ghi xuống DB đúng bằng giờ gửi - lượt dài không làm lệch"""
    rig = TurnRig.create()
    await rig.run([await rig.receive("câu hỏi", "m1", thread_id=THREAD, sent_at=GUI_LUC)])

    assert history_rows(rig)[0][2] == GUI_LUC


async def test_moc_gio_tin_nhan_di_tron_hai_luot_batch_nhieu_nguoi_luot_sau_doc_lai_dung_ai_noi_cau_nao() -> (
    None
):
    """batch NHIỀU NGƯỜI: lượt sau đọc lại đúng ai nói câu nào"""
    rig = TurnRig.create()
    await rig.run(
        [
            await rig.receive("mình hỏi giá vàng", "m1", thread_id=THREAD, sent_at=GUI_LUC, sender="Hải"),
            await rig.receive("mình hỏi tỉ giá", "m2", thread_id=THREAD, sender="Nam"),
        ]
    )

    names = {content: who for content, who, _ in history_rows(rig)}
    assert names["mình hỏi giá vàng"] == "Hải", "câu của Hải phải mang tên Hải"
    assert names["mình hỏi tỉ giá"] == "Nam", "câu của Nam phải mang tên Nam"
    assert [m.sender_name for m in rig.engine.requests[0].batch] == ["Hải", "Nam"]

# ported from: src/zalo/message-turn-history-write.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Tin người dùng nay vào lịch sử NGAY LÚC NHẬN, không đợi lượt chạy xong (``record_incoming_message``). Đổi đó mở ra
đúng một cái bẫy và đóng lại hai cái khác:

  BẪY MỞ RA: lúc lượt đọc lịch sử thì tin của CHÍNH nó đã nằm trong đó, nên không lọc là model nhận cùng một câu hỏi
  HAI lần. Bộ lọc là việc của engine (package D1, theo ``history_row_id``); phần của pipeline này là chuyển ĐỦ
  ``history_row_id`` của batch và của hàng chờ cho engine.

  BẪY ĐÓNG LẠI 1: lượt chết giữa chừng không còn làm mất tin khỏi lịch sử.
  BẪY ĐÓNG LẠI 2: thứ tự trong DB là thứ tự người ta gửi, không phải thứ tự lượt kết thúc.

The original asserted on the PROMPT the model saw (Vercel AI SDK mock model). The prompt is built by package D1
(``history_to_model_messages``); here the same invariants are asserted on what the pipeline hands to the engine: the
batch with its stamped ``history_row_id`` and the ``pending_history_ids`` callback.
"""

from __future__ import annotations

from pema.channels.pipeline_testing import FakeEngine, TurnRig, answer
from pema_contracts.agent_turn import AgentTurnRequest, AgentTurnResult, TurnCallbacks
from pema_contracts.turn_errors import AgentTurnError, ProviderErrorKind

ACC = "acc-1"
THREAD = "t-ghi"


def user_rows(rig: TurnRig, needle: str) -> list[str]:
    return [c for role, c in rig.conversation.contents(ACC, THREAD) if role == "user" and needle in c]


async def test_ghi_lich_su_ngay_luc_nhan_cau_hoi_cua_luot_nay_xuat_hien_dung_mot_lan_trong_prompt() -> None:
    """câu hỏi của lượt này xuất hiện ĐÚNG MỘT lần trong prompt"""
    rig = TurnRig.create()
    cau_hoi = "cho mình bảng giá tháng 8"
    msg = await rig.receive(cau_hoi, "m1", thread_id=THREAD)

    await rig.run([msg])

    batch = rig.engine.requests[0].batch
    assert [m.text for m in batch] == [cau_hoi], "câu hỏi vào batch của engine đúng một lần"
    assert batch[0].history_row_id is not None, (
        "engine lọc tin của chính lượt khỏi lịch sử theo history_row_id"
    )
    assert len(user_rows(rig, cau_hoi)) == 1, "pipeline không ghi thêm dòng nào"


async def test_ghi_lich_su_ngay_luc_nhan_cau_hoi_cu_giong_het_cau_moi_van_giu_nguyen_trong_lich_su() -> None:
    """câu hỏi CŨ giống hệt câu mới thì vẫn giữ nguyên trong lịch sử"""
    # Lọc theo id DÒNG chứ không theo nội dung: người ta hỏi lại đúng câu cũ là chuyện thường, nuốt mất câu cũ là
    # bot quên mất họ từng hỏi rồi.
    rig = TurnRig.create()
    cau_hoi = "giá vàng hôm nay"
    first = await rig.receive(cau_hoi, "m1", thread_id=THREAD)
    await rig.run([first])
    second = await rig.receive(cau_hoi, "m2", thread_id=THREAD)
    await rig.run([second])

    assert len(user_rows(rig, cau_hoi)) == 2, "một lần trong lịch sử, một lần là câu đang hỏi"
    ids = [r.batch[0].history_row_id for r in rig.engine.requests]
    assert ids[0] != ids[1], "hai câu giống nhau là hai dòng khác nhau, phân biệt bằng id dòng"


async def test_cua_so_lich_su_khong_teo_theo_co_batch_batch_nhieu_tin_model_van_thay_du_tin_cu() -> None:
    """batch nhiều tin: model VẪN thấy đủ N tin cũ"""
    # Phần "xin dư" cửa sổ là của engine (D1). Phần của pipeline: đưa ĐỦ cả batch kèm id dòng của từng tin để
    # engine biết chính xác bao nhiêu dòng phải loại.
    rig = TurnRig.create()
    for i in range(6):
        await rig.receive(f"tin cũ {i}", f"old{i}", thread_id=THREAD)
    batch = [
        await rig.receive("câu một", "b1", thread_id=THREAD),
        await rig.receive("câu hai", "b2", thread_id=THREAD),
        await rig.receive("câu ba", "b3", thread_id=THREAD),
    ]

    await rig.run(batch)

    request = rig.engine.requests[0]
    assert [m.text for m in request.batch] == ["câu một", "câu hai", "câu ba"]
    assert all(m.history_row_id is not None for m in request.batch), "mỗi tin mang id dòng của nó"


async def test_cua_so_lich_su_khong_teo_theo_co_batch_tin_dang_cho_trong_hang_gop_cung_duoc_xin_du() -> None:
    """tin đang CHỜ trong hàng gộp cũng được xin dư, không ăn vào cửa sổ"""
    seen: list[list[int]] = []

    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        assert callbacks is not None
        assert callbacks.pending_history_ids is not None
        seen.append(list(await callbacks.pending_history_ids()))
        return await answer("ok")(request, callbacks)

    rig = TurnRig.create(engine=FakeEngine(script=script))
    cho = await rig.receive("tin đang chờ", "b-cho", thread_id=THREAD)
    rig.pending.waiting.append(cho)

    await rig.run([await rig.receive("câu đang hỏi", "b1", thread_id=THREAD)])

    assert seen == [[cho.history_row_id]], "id của tin đang chờ phải tới engine để nó xin dư"


async def test_ghi_lich_su_ngay_luc_nhan_luot_tron_ven_tin_nguoi_dung_co_dung_mot_dong() -> None:
    """lượt trọn vẹn: tin người dùng có ĐÚNG một dòng"""
    rig = TurnRig.create()
    await rig.run([await rig.receive("chào bot", "m1", thread_id=THREAD)])

    assert len(user_rows(rig, "chào bot")) == 1, "ghi ở cả router lẫn lượt là model đọc thấy lặp"


async def test_ghi_lich_su_ngay_luc_nhan_luot_chet_vi_provider_loi_tin_nguoi_dung_van_con_nguyen() -> None:
    """lượt CHẾT vì provider lỗi: tin người dùng vẫn còn nguyên trong lịch sử"""

    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        raise AgentTurnError(ProviderErrorKind.TRANSIENT, "provider chết")

    rig = TurnRig.create(engine=FakeEngine(script=script))
    await rig.run([await rig.receive("câu hỏi lúc bot hỏng", "m1", thread_id=THREAD)])

    # Đếm ĐÚNG MỘT dòng chứ không chỉ "có mặt": nhánh lỗi trước đây tự ghi lại tin để cứu nó, ai đó khôi phục lại
    # dòng đó là tin bị ghi lần hai và model đọc thấy người dùng lặp.
    assert len(user_rows(rig, "câu hỏi lúc bot hỏng")) == 1, (
        "bỏ qua là bot quên, ghi lại lần nữa là model đọc lặp"
    )


async def test_ghi_lich_su_ngay_luc_nhan_thu_tu_tin_nguoi_dung_cau_chot_cua_agent() -> None:
    """thứ tự: tin người dùng -> câu chốt của agent"""
    rig = TurnRig.create()
    await rig.run([await rig.receive("hỏi gì đó", "m1", thread_id=THREAD)])

    assert [role for role, _ in rig.conversation.contents(ACC, THREAD)] == ["user", "assistant"]


async def test_gan_anh_vao_history_duong_dan_anh_tai_xong_duoc_gan_vao_dung_dong_da_ghi_luc_nhan() -> None:
    """đường dẫn ảnh tải xong được gắn vào ĐÚNG dòng đã ghi lúc nhận"""
    rig = TurnRig.create()
    msg = await rig.receive(
        "xem ảnh này", "m-anh", thread_id=THREAD, images=["http://x.example.invalid/0.jpg"]
    )

    async def persist(clinic_id: object, account_id: str, messages: list[object]) -> None:
        # Giả bước tải: chỉ đóng dấu local_path, không chạm mạng
        for m in messages:
            for image in m.images:  # type: ignore[attr-defined]
                image.local_path = f"media/{account_id}/{THREAD}/da-tai.jpg"

    rig.services.persist_images = persist  # type: ignore[assignment]
    await rig.run([msg])

    assert rig.conversation.images[msg.history_row_id or 0] == [f"media/{ACC}/{THREAD}/da-tai.jpg"], (
        "không gắn thì lượt sau không nạp lại được ảnh, và ảnh mất hẳn khi URL Zalo hết hạn"
    )

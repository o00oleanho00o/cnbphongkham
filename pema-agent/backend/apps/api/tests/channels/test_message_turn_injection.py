# ported from: src/zalo/message-turn-injection.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Test DÂY NỐI của việc tiêm tin giữa lượt vào đường chat thật.

Engine có test riêng cho phần đưa tin chen vào ngữ cảnh model, nhưng những HỆ QUẢ PHỤ - ghi history, báo "đã xem" -
nằm ở ``message_turn_processor`` và chỉ đo được ở đây. Đúng lớp lỗi từng dính hai lần trong dự án này: hàm viết
đúng, không ai nối, mà toàn bộ test vẫn xanh.

The fake engine does what the real loop does at a step boundary: it calls ``fetch_injected_messages``.
"""

from __future__ import annotations

from pema.channels.pipeline_testing import FakeEngine, TurnRig
from pema_contracts.agent_turn import AgentTurnRequest, AgentTurnResult, TokenUsage, TurnCallbacks
from pema_contracts.channel import InboundMessage

THREAD = "t-chen"


def engine_pulling(text: str, seen: list[list[InboundMessage]]) -> FakeEngine:
    async def script(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        assert callbacks is not None
        assert callbacks.fetch_injected_messages is not None
        seen.append(list(await callbacks.fetch_injected_messages()))
        return AgentTurnResult(text=text, usage=TokenUsage(total_tokens=75, steps=1))

    return FakeEngine(script=script)


def contents(rig: TurnRig) -> list[str]:
    return [c for _, c in rig.conversation.contents(rig.config.id, THREAD)]


async def test_process_batch_tin_nhan_them_giua_luot_tin_chen_vao_history_sau_tin_mo_dau_dung_thu_tu() -> (
    None
):
    """tin chen vào history SAU tin mở đầu, đúng thứ tự người ta đã gửi"""
    seen: list[list[InboundMessage]] = []
    rig = TurnRig.create(engine=engine_pulling("Đã ghi nhận cả hai ý", seen))
    # Dựng tin MỞ ĐẦU trước rồi mới tới tin chen, đúng thứ tự đời thật: router ghi từng tin vào lịch sử ngay lúc
    # nhận, mà tin mở đầu tới trước.
    mo_dau = await rig.receive("soạn giúp mình bài giảng", "m1", thread_id=THREAD)
    rig.pending.waiting.append(await rig.receive("đổi thành file word nhé", "m2", thread_id=THREAD))

    await rig.run([mo_dau])

    history = contents(rig)
    vi_tri_mo_dau = next(i for i, c in enumerate(history) if "soạn giúp mình bài giảng" in c)
    vi_tri_chen = next((i for i, c in enumerate(history) if "đổi thành file word nhé" in c), -1)
    assert vi_tri_chen >= 0, "TIN CHEN PHẢI CÓ TRONG HISTORY - thiếu là bot quên sạch câu người ta vừa nói"
    assert vi_tri_chen > vi_tri_mo_dau, "tin chen phải nằm SAU tin mở đầu, đúng thứ tự đã gửi"


async def test_process_batch_tin_nhan_them_giua_luot_tin_chen_vao_prompt_dung_mot_lan() -> None:
    """tin chen vào PROMPT đúng MỘT lần - không vừa lẫn trong lịch sử vừa mang nhãn"""
    # Bộ lọc là của engine (D1, theo history_row_id). Phần của pipeline: tin chen tới engine ĐÚNG MỘT lần, qua
    # callback, KHÔNG nằm trong batch mở lượt, và mang id dòng để engine loại nó khỏi phần lịch sử.
    seen: list[list[InboundMessage]] = []
    rig = TurnRig.create(engine=engine_pulling("ok", seen))
    mo_dau = await rig.receive("soạn giúp mình bài giảng", "m1", thread_id=THREAD)
    chen = await rig.receive("à mà xuất ra Word nhé", "m2", thread_id=THREAD)
    rig.pending.waiting.append(chen)

    await rig.run([mo_dau])

    assert [m.text for m in rig.engine.requests[0].batch] == ["soạn giúp mình bài giảng"]
    assert [[m.text for m in group] for group in seen] == [["à mà xuất ra Word nhé"]]
    assert seen[0][0].history_row_id == chen.history_row_id


async def test_process_batch_tin_nhan_them_giua_luot_tin_chen_duoc_bao_da_xem_nhu_tin_thuong() -> None:
    """tin chen được báo 'đã xem' như tin thường - không để người gửi tưởng tin rơi vào khoảng không"""
    seen: list[list[InboundMessage]] = []
    rig = TurnRig.create(engine=engine_pulling("ok", seen))
    rig.pending.waiting.append(await rig.receive("thêm ý này nữa", "m2", thread_id=THREAD))

    await rig.run([await rig.receive("câu hỏi đầu", "m1", thread_id=THREAD)])

    # 1 lần cho batch mở đầu + 1 lần cho tin chen
    assert len(rig.api.seen) == 2, f"mong 2 lần báo đã xem, nhận {len(rig.api.seen)}"


async def test_process_batch_tin_nhan_them_giua_luot_anh_cua_tin_chen_cung_duoc_luu_xuong_dia() -> None:
    """ảnh của tin chen cũng được lưu xuống đĩa như tin mở đầu"""
    # Thiếu bước này thì history chỉ còn dòng chữ "[gửi kèm N ảnh]" mà không đường dẫn nào: lượt sau bot không nạp
    # lại được ảnh, và ảnh mất hẳn khi URL Zalo hết hạn. Mất dữ liệu, không tự phục hồi được.
    seen: list[list[InboundMessage]] = []
    rig = TurnRig.create(engine=engine_pulling("ok", seen))
    saved: list[list[str]] = []

    async def persist(clinic_id: object, account_id: str, messages: list[InboundMessage]) -> None:
        saved.append([m.msg_id for m in messages])

    rig.services.persist_images = persist
    rig.pending.waiting.append(await rig.receive("xem ảnh này giúp mình", "m2", thread_id=THREAD))

    await rig.run([await rig.receive("câu hỏi đầu", "m1", thread_id=THREAD)])

    assert len(saved) == 2, f"mong 2 lần lưu (batch mở đầu + tin chen), nhận {len(saved)}"
    assert saved[0] == ["m1"], "lần đầu là batch mở đầu"
    assert saved[1] == ["m2"], "lần hai PHẢI là tin chen"


async def test_process_batch_tin_nhan_them_giua_luot_duong_dan_anh_cua_tin_chen_duoc_gan_vao_dong_cua_no() -> (
    None
):
    """đường dẫn ảnh của tin chen được GẮN vào dòng lịch sử của chính nó"""
    seen: list[list[InboundMessage]] = []
    rig = TurnRig.create(engine=engine_pulling("ok", seen))
    duong = f"media/{rig.config.id}/{THREAD}/chen-0.jpg"

    async def persist(clinic_id: object, account_id: str, messages: list[InboundMessage]) -> None:
        for m in messages:
            for image in m.images:
                image.local_path = duong

    rig.services.persist_images = persist
    chen = await rig.receive(
        "xem ảnh này giúp mình", "m2", thread_id=THREAD, images=["http://x.example.invalid/0.jpg"]
    )
    rig.pending.waiting.append(chen)

    await rig.run([await rig.receive("câu hỏi đầu", "m1", thread_id=THREAD)])

    assert rig.conversation.images[chen.history_row_id or 0] == [duong]


async def test_process_batch_tin_nhan_them_giua_luot_hang_cho_rong_thi_moi_thu_y_nhu_cu_doi_chung() -> None:
    """hàng chờ rỗng thì mọi thứ y như cũ - đối chứng"""
    seen: list[list[InboundMessage]] = []
    rig = TurnRig.create(engine=engine_pulling("chào anh", seen))

    await rig.run([await rig.receive("chào bot", "m1", thread_id=THREAD)])

    assert len([c for c in contents(rig) if "chào bot" in c]) == 1, "không được ghi trùng"
    assert len(rig.api.seen) == 1, "không có tin chen thì chỉ 1 lần báo đã xem"
    assert rig.sent_texts() == ["chào anh"]
    assert seen == [[]]


async def test_process_batch_tin_chen_cua_nguoi_khac_trong_nhom_khong_bi_cuop_khoi_luot_cua_ho() -> None:
    """(port) tin chen theo NGƯỜI GỬI: hàng chờ không biết người gửi thì nhóm không tiêm gì, tin ở lại cho lượt riêng"""
    # ``pema_contracts.PendingInbox.take_injected`` has no sender argument. A group with such an inbox injects
    # nothing (a person's waiting message must not be stolen by someone else's turn); a direct chat has one
    # possible sender and may use it.
    seen: list[list[InboundMessage]] = []
    rig = TurnRig.create(engine=engine_pulling("ok", seen))
    plain = _PlainPending(rig.pending.waiting)
    rig.services.pending = plain
    nam = await rig.receive("Nam hỏi tỉ giá", "m-nam", thread_id="nhom", sender="Nam", is_group=True)
    plain.waiting.append(nam)

    await rig.run(
        [await rig.receive("Hải hỏi giá vàng", "m-hai", thread_id="nhom", sender="Hải", is_group=True)]
    )

    assert seen == [[]], "tin của Nam không được kéo vào lượt của Hải"
    assert plain.waiting == [nam], "và vẫn nằm trong hàng chờ cho lượt riêng của Nam"


class _PlainPending:
    """A ``PendingInbox`` that implements ONLY the contract (no sender-aware method)."""

    def __init__(self, waiting: list[InboundMessage]) -> None:
        self.waiting = waiting

    async def take_injected(self, account_id: str, thread_id: str) -> list[InboundMessage]:
        mine = [m for m in self.waiting if m.thread_id == thread_id]
        self.waiting = [m for m in self.waiting if m.thread_id != thread_id]
        return mine

    async def pending_history_ids(self, account_id: str, thread_id: str) -> list[int]:
        return [m.history_row_id for m in self.waiting if m.history_row_id is not None]

# ported from: src/zalo/send-reply-quote.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Trích dẫn đi qua đường gửi thật: đính vào đâu, và bỏ lúc nào.

Hai bất biến quan trọng hơn cả việc "có trích dẫn":

  1. CHỈ ĐOẠN ĐẦU mang trích dẫn. Câu trả lời dài bị cắt làm nhiều tin; trích lại ở mỗi tin thì khối trích dẫn
     lặp đầy màn hình.
  2. Trích dẫn KHÔNG được làm mất chữ. Zalo từ chối thì gửi lại trơn - cùng luật đã dựng cho tổ hợp style
     ngày 05/08.

The send path is built by the real ``duong_gui_zca_js`` over a recording ``ZaloApi``, so the test also measures the
real payload shape (no ``styles``/``quote`` when empty), not only the logic above it.
"""

from __future__ import annotations

from pema.channels.pipeline_testing import immediate_enqueue_send
from pema.channels.send_reply_in_parts import ReplyTarget, send_reply_in_parts
from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.channels.zalo_personal.kenh_ca_nhan import duong_gui_zca_js
from pema.channels.zalo_personal.testing import FakeZaloApi
from pema_contracts.channel import QuoteRef, TextStyle, ThreadKind

RAW_QUOTE: dict[str, object] = {
    "content": "bot ơi tra giúp giá vàng",
    "msgType": "webchat",
    "uidFrom": "u-hai",
    "msgId": "m-1",
    "cliMsgId": "c-1",
    "ts": "1786122720000",
    "ttl": 0,
}
TRICH_DAN = QuoteRef(msg_id="m-1", cli_msg_id="c-1", sender_id="u-hai", raw=RAW_QUOTE)
STYLE_MAU = [TextStyle(start=0, length=3, style="b")]


def loi_may_chu(code: int) -> ZaloBridgeError:
    """Lỗi máy chủ Zalo trả về - dấu hiệu là có ``code`` dạng số, giống ZaloApiError thật"""
    return ZaloBridgeError("zalo_rejected", "Lỗi không xác định", code=code)


def tao_muc(api: FakeZaloApi, quote: QuoteRef | None) -> ReplyTarget:
    # Dựng đường gửi bằng chính ``duong_gui_zca_js``, không tự chế.
    return ReplyTarget(
        gui_mot_doan=duong_gui_zca_js(api, "thread", ThreadKind.GROUP),
        thread_key="acc:thread",
        thread_id="thread",
        thread_type=ThreadKind.GROUP,
        quote=quote,
    )


async def gui(target: ReplyTarget, text: str, styles: list[TextStyle] | None = None):  # type: ignore[no-untyped-def]
    return await send_reply_in_parts(target, text, styles or [], enqueue_send=immediate_enqueue_send)


async def test_send_reply_in_parts_dinh_trich_dan_cau_tra_loi_mot_doan_trich_dan_di_kem() -> None:
    """câu trả lời một đoạn: trích dẫn đi kèm"""
    api = FakeZaloApi()
    await gui(tao_muc(api, TRICH_DAN), "Giá vàng hôm nay là...")

    assert len(api.sent) == 1
    assert api.sent[0].quote == TRICH_DAN


async def test_send_reply_in_parts_dinh_trich_dan_khong_co_trich_dan_chat_rieng_khong_dinh_quote() -> None:
    """không có trích dẫn (chat riêng) thì KHÔNG đính trường quote"""
    api = FakeZaloApi()
    await gui(tao_muc(api, None), "Chào anh")

    assert len(api.sent) == 1
    assert api.sent[0].quote is None, "đính quote rỗng là đổi hẳn endpoint zca-js gọi tới"
    assert api.sent[0].styles == ()


async def test_send_reply_in_parts_dinh_trich_dan_bi_cat_nhieu_doan_chi_doan_dau_co_trich_dan() -> None:
    """câu trả lời bị cắt nhiều đoạn: CHỈ đoạn đầu có trích dẫn"""
    api = FakeZaloApi()
    # Trần mặc định ZALO_MAX_MESSAGE_CHARS = 2000 nên 5000 ký tự chắc chắn cắt
    dai = "Câu trả lời rất dài. " * 250
    await gui(tao_muc(api, TRICH_DAN), dai)

    assert len(api.sent) >= 2, f"phải cắt nhiều đoạn, đang có {len(api.sent)}"
    assert api.sent[0].quote == TRICH_DAN, "đoạn đầu phải trích"
    for i, part in enumerate(api.sent[1:], start=2):
        assert part.quote is None, f"đoạn {i} không được trích lại"


async def test_send_reply_in_parts_dinh_trich_dan_tin_duoc_trich_qua_dai_gui_khong_kem_trich_dan() -> None:
    """tin được trích QUÁ DÀI: gửi không kèm trích dẫn thay vì để Zalo chối"""
    api = FakeZaloApi()
    qua_dai = QuoteRef(
        msg_id="m-1", cli_msg_id="c-1", sender_id="u-hai", raw={**RAW_QUOTE, "content": "x" * 2000}
    )
    ket = await gui(tao_muc(api, qua_dai), "Trả lời ngắn")

    assert ket.error is None
    assert api.sent[0].quote is None, "không được đính khóa quote nào cả"
    assert api.sent[0].text == "Trả lời ngắn", "chữ phải y nguyên"


async def test_send_reply_in_parts_duong_lui_trich_dan_gui_lai_khong_kem_trich_dan_noi_dung_van_toi() -> None:
    """gửi lại KHÔNG kèm trích dẫn, nội dung vẫn tới nơi"""
    api = FakeZaloApi()
    api.fail_send_with = [loi_may_chu(118)]

    ket = await gui(tao_muc(api, TRICH_DAN), "Giá vàng hôm nay là...")

    assert ket.error is None, "không được coi là lượt hỏng"
    assert ket.sent_parts == 1
    assert api.send_attempts == 2, "đúng 2 lần gọi: lần đầu có trích dẫn, lần sau trơn"
    assert api.sent[0].quote is None, "lần thử lại phải BỎ HẲN trích dẫn"
    assert api.sent[0].text == "Giá vàng hôm nay là...", "chữ phải y nguyên"


async def test_send_reply_in_parts_duong_lui_trich_dan_lan_thu_lai_bo_ca_style_lan_trich_dan() -> None:
    """lần thử lại bỏ CẢ style LẪN trích dẫn - không đoán bên nào là thủ phạm"""
    api = FakeZaloApi()
    api.fail_send_with = [loi_may_chu(112)]

    await gui(tao_muc(api, TRICH_DAN), "Giá vàng", STYLE_MAU)

    assert api.send_attempts == 2
    assert api.sent[0].quote is None
    assert api.sent[0].styles == (), "lần thử lại chỉ còn đúng chữ trơn"


async def test_send_reply_in_parts_duong_lui_trich_dan_khong_gui_lai_khi_loi_la_dut_mang() -> None:
    """KHÔNG gửi lại khi lỗi là đứt mạng - tin có thể đã tới, gửi lại là nhân đôi"""
    api = FakeZaloApi()
    api.fail_send_with = [ZaloBridgeError("transport", "socket hang up")]

    ket = await gui(tao_muc(api, TRICH_DAN), "Giá vàng hôm nay là...")

    assert ket.error is not None, "phải báo hỏng lên trên"
    assert api.send_attempts == 1, "tuyệt đối không được gọi lần hai"


async def test_send_reply_in_parts_duong_lui_trich_dan_khong_style_khong_trich_dan_thi_khong_thu_lai() -> (
    None
):
    """không style, không trích dẫn thì KHÔNG thử lại - lần hai y hệt lần đầu"""
    api = FakeZaloApi()
    api.fail_send_with = [loi_may_chu(112)]

    ket = await gui(tao_muc(api, None), "Chữ trơn thôi")

    assert ket.error is not None
    assert api.send_attempts == 1, "thử lại y nguyên chỉ tổ tốn một lời gọi API"

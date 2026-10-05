# ported from: src/zalo/send-reply-style-fallback.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Đường lui khi Zalo từ chối tin CÓ ĐỊNH DẠNG.

Bất biến quan trọng nhất KHÔNG phải "định dạng đẹp" mà là "nội dung tới nơi". Luật kiểm style của Zalo là hộp
đen; 2026-08-05 một tổ hợp span hợp lệ trên giấy đã làm mất trọn câu trả lời sau 8 lượt tra web. Nên tổ hợp lạ chỉ
được phép làm tin NHẠT ĐI, không được làm mất chữ.
"""

from __future__ import annotations

from pema.channels.pipeline_testing import immediate_enqueue_send
from pema.channels.send_reply_in_parts import ReplyTarget, send_reply_in_parts
from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.channels.zalo_personal.kenh_ca_nhan import duong_gui_zca_js
from pema.channels.zalo_personal.testing import FakeZaloApi
from pema_contracts.channel import TextStyle, ThreadKind

STYLE_MAU = [TextStyle(start=0, length=3, style="b")]


def loi_may_chu(code: int) -> ZaloBridgeError:
    """Lỗi máy chủ Zalo trả về - dấu hiệu là có ``code`` dạng số, giống ZaloApiError thật"""
    return ZaloBridgeError("zalo_rejected", "Lỗi không xác định", code=code)


def tao_muc(api: FakeZaloApi) -> ReplyTarget:
    return ReplyTarget(
        gui_mot_doan=duong_gui_zca_js(api, "thread", ThreadKind.USER),
        thread_key="acc:thread",
        thread_id="thread",
        thread_type=ThreadKind.USER,
    )


async def test_send_reply_in_parts_zalo_tu_choi_tin_co_dinh_dang_gui_lai_khong_kem_styles_noi_dung_van_toi() -> (
    None
):
    """gửi lại KHÔNG kèm styles, nội dung vẫn tới nơi"""
    api = FakeZaloApi()
    api.fail_send_with = [loi_may_chu(112)]

    ket = await send_reply_in_parts(
        tao_muc(api), "Báo giá tháng 8", STYLE_MAU, enqueue_send=immediate_enqueue_send
    )

    assert ket.error is None, "không được coi là lượt hỏng"
    assert ket.sent_parts == 1
    assert api.send_attempts == 2, "phải có đúng 2 lần gọi: lần đầu có style, lần sau trơn"
    assert api.sent[0].styles == (), "lần thử lại phải BỎ HẲN styles"
    assert api.sent[0].text == "Báo giá tháng 8", "chữ phải y nguyên"


async def test_send_reply_in_parts_zalo_tu_choi_khong_gui_lai_khi_loi_la_dut_mang() -> None:
    """KHÔNG gửi lại khi lỗi là đứt mạng - tin có thể đã tới, gửi lại là nhân đôi"""
    # Lỗi không có `code` nghĩa là máy chủ chưa chắc đã từ chối. Nhân đôi tin trước mặt người dùng tệ hơn hẳn
    # so với một tin không gửi được.
    api = FakeZaloApi()
    api.fail_send_with = [ZaloBridgeError("transport", "socket hang up")]

    ket = await send_reply_in_parts(
        tao_muc(api), "Báo giá tháng 8", STYLE_MAU, enqueue_send=immediate_enqueue_send
    )

    assert ket.error is not None, "phải báo hỏng lên trên"
    assert api.send_attempts == 1, "tuyệt đối không được gọi lần hai"


async def test_send_reply_in_parts_zalo_tu_choi_khong_gui_lai_khi_tin_von_da_khong_co_style() -> None:
    """KHÔNG gửi lại khi tin vốn đã không có style - lần hai y hệt lần đầu"""
    api = FakeZaloApi()
    api.fail_send_with = [loi_may_chu(112), loi_may_chu(112)]

    ket = await send_reply_in_parts(tao_muc(api), "Chữ trơn thôi", [], enqueue_send=immediate_enqueue_send)

    assert ket.error is not None
    assert api.send_attempts == 1, "thử lại y nguyên chỉ tổ tốn một lời gọi API"


async def test_send_reply_in_parts_zalo_tu_choi_lan_thu_lai_cung_hong_thi_bao_hong_khong_nuot_loi() -> None:
    """lần thử lại cũng hỏng thì báo hỏng, không nuốt lỗi"""
    api = FakeZaloApi()
    api.fail_send_with = [loi_may_chu(112), loi_may_chu(112)]

    ket = await send_reply_in_parts(
        tao_muc(api), "Báo giá tháng 8", STYLE_MAU, enqueue_send=immediate_enqueue_send
    )

    assert ket.error is not None, "hỏng cả hai lần thì phải nói ra"
    assert api.send_attempts == 2
    assert ket.sent_parts == 0

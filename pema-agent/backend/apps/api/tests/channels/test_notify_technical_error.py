# ported from: src/zalo/notify-technical-error.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Khử trùng câu báo lỗi.

Provider chết vài phút mà người ta nhắn 5 lần là 5 tin y hệt nhau đổ xuống - vừa phiền vừa làm họ tưởng bot hỏng
nặng hơn thực tế. Một lần đã nói đủ ý "chờ rồi nhắn lại".

Nhưng khử theo CẢ loại lỗi, không chỉ theo thread: "bot chưa cấu hình xong" và "mạng chập" là hai chuyện khác nhau,
mỗi chuyện đáng được nói một lần.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.channels.pipeline_testing import immediate_enqueue_send
from pema.channels.send_reply_in_parts import ReplyTarget, notify_technical_error, reset_khu_trung_bao_loi
from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.channels.zalo_personal.kenh_ca_nhan import duong_gui_zca_js
from pema.channels.zalo_personal.testing import FakeZaloApi
from pema_contracts.channel import ThreadKind


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    reset_khu_trung_bao_loi()
    yield
    reset_khu_trung_bao_loi()


def muc(api: FakeZaloApi, thread_key: str) -> ReplyTarget:
    # Dựng đường gửi bằng chính `duong_gui_zca_js` chứ không tự chế.
    return ReplyTarget(
        gui_mot_doan=duong_gui_zca_js(api, thread_key, ThreadKind.USER),
        thread_key=thread_key,
        thread_id=thread_key,
        thread_type=ThreadKind.USER,
    )


async def test_notify_technical_error_khu_trung_bao_lan_dau() -> None:
    """báo lần đầu"""
    api = FakeZaloApi()
    await notify_technical_error(muc(api, "k-lan-dau"), "transient", enqueue_send=immediate_enqueue_send)
    assert len(api.sent) == 1


async def test_notify_technical_error_khu_trung_cung_thread_cung_loai_loi_chi_bao_mot_lan() -> None:
    """cùng thread + cùng loại lỗi thì chỉ báo MỘT lần"""
    # Đúng ca đã xảy ra 2026-08-04: hai lượt liên tiếp cùng chết vì 524, người nhắn nhận hai tin "trục trặc kỹ
    # thuật" giống hệt nhau.
    api = FakeZaloApi()
    for _ in range(4):
        await notify_technical_error(muc(api, "k-trung"), "transient", enqueue_send=immediate_enqueue_send)
    assert len(api.sent) == 1, f"mong đúng 1 câu, nhận {len(api.sent)}"


async def test_notify_technical_error_khu_trung_loai_loi_khac_van_duoc_bao() -> None:
    """LOẠI LỖI KHÁC vẫn được báo - hai chuyện khác nhau, không được nuốt"""
    api = FakeZaloApi()
    target = muc(api, "k-khac-loai")
    await notify_technical_error(target, "transient", enqueue_send=immediate_enqueue_send)
    await notify_technical_error(target, "cau_hinh", enqueue_send=immediate_enqueue_send)

    assert len(api.sent) == 2, "mỗi loại lỗi phải được nói một lần"
    assert api.sent[0].text != api.sent[1].text, "và phải là hai câu khác nhau"


async def test_notify_technical_error_khu_trung_thread_khac_van_duoc_bao() -> None:
    """THREAD KHÁC vẫn được báo - người này im không có nghĩa người kia cũng im"""
    api = FakeZaloApi()
    await notify_technical_error(muc(api, "k-thread-a"), "transient", enqueue_send=immediate_enqueue_send)
    await notify_technical_error(muc(api, "k-thread-b"), "transient", enqueue_send=immediate_enqueue_send)
    assert len(api.sent) == 2


async def test_notify_technical_error_gui_hong_van_nuot_loi() -> None:
    """gửi hỏng vẫn nuốt lỗi - đây đã là đường cứu cánh, hỏng nốt thì chỉ còn log"""
    api = FakeZaloApi()
    api.fail_send_with = [ZaloBridgeError("transport", "Zalo từ chối")]
    await notify_technical_error(muc(api, "k-gui-hong"), "transient", enqueue_send=immediate_enqueue_send)
    # Không ném ra ngoài là đủ - nhánh except của lượt gọi hàm này ở cuối, ném thêm ở đây là lỗi thứ hai đè lên
    # lỗi đang xử lý.

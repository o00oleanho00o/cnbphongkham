# ported from: src/zalo/message-receipts.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.channels.zalo_personal.message_receipts import (
    drain_pending_receipts,
    send_delivered_receipt,
    send_seen_receipt,
)
from pema.channels.zalo_personal.testing import FakeZaloApi
from pema_contracts.channel import InboundMessage, ThreadKind
from pema_contracts.testing import make_inbound

GROUP_ID = "group-7"


def message(raw_override: dict[str, object] | None = None, **fields: object) -> InboundMessage:
    raw: dict[str, object] = {
        "msgId": "msg-1",
        "cliMsgId": "cli-1",
        "uidFrom": "user-9",
        "idTo": "self-1",
        "msgType": "webchat",
        "st": 1,
        "at": 2,
        "cmd": 3,
        "ts": "1700000000000",
        **(raw_override or {}),
    }
    defaults: dict[str, object] = {
        "account_id": "acc-chinh",
        "thread_id": "thread-1",
        "sender_id": "user-9",
        "raw": raw,
        **fields,
    }
    return make_inbound("chào bot", **defaults)  # pyright: ignore[reportArgumentType]


class FailingApi(FakeZaloApi):
    async def send_delivered_event(self, is_seen, params, thread_type):  # type: ignore[no-untyped-def, override]
        raise ZaloBridgeError("transport", "mạng rớt")

    async def send_seen_event(self, params, thread_type):  # type: ignore[no-untyped-def, override]
        raise ZaloBridgeError("transport", "mạng rớt")


async def test_send_delivered_receipt_dung_du_9_field_tu_payload_goc_is_seen_false() -> None:
    """dựng đủ 9 field từ payload gốc, isSeen=false"""
    api = FakeZaloApi()
    send_delivered_receipt(api, message())
    await drain_pending_receipts()

    assert len(api.delivered) == 1
    is_seen, params, thread_kind = api.delivered[0]
    assert is_seen is False, "đây mới là 'đã nhận', 'đã xem' đi đường riêng"
    assert thread_kind is ThreadKind.USER
    assert list(params) == [
        {
            "msgId": "msg-1",
            "cliMsgId": "cli-1",
            "uidFrom": "user-9",
            "idTo": "self-1",
            "msgType": "webchat",
            "st": 1,
            "at": 2,
            "cmd": 3,
            "ts": "1700000000000",
        }
    ]


async def test_send_delivered_receipt_thieu_field_bat_buoc_thi_bo_qua_khong_goi_api() -> None:
    """thiếu field bắt buộc thì bỏ qua, không gọi API"""
    api = FakeZaloApi()
    send_delivered_receipt(api, message({"msgId": ""}))
    send_delivered_receipt(api, message({"uidFrom": ""}))
    send_delivered_receipt(api, message({"idTo": ""}))
    await drain_pending_receipts()
    assert len(api.delivered) == 0


async def test_send_delivered_receipt_api_loi_khong_lam_vo_luong_tra_loi() -> None:
    """API lỗi không làm vỡ luồng trả lời"""
    api = FailingApi()
    send_delivered_receipt(api, message())
    await drain_pending_receipts()
    # Không có exception chưa bắt là đạt


async def test_send_seen_receipt_gui_ca_batch_trong_1_lan_goi_dung_thread_type_cua_nhom() -> None:
    """gửi cả batch trong 1 lần gọi, đúng thread type của nhóm"""
    api = FakeZaloApi()

    def group_msg(msg_id: str) -> InboundMessage:
        return message(
            {"msgId": msg_id, "idTo": GROUP_ID},
            thread_id=GROUP_ID,
            thread_kind=ThreadKind.GROUP,
            is_group=True,
        )

    send_seen_receipt(api, [group_msg("m1"), group_msg("m2")])
    await drain_pending_receipts()

    assert len(api.seen) == 1
    params, thread_kind = api.seen[0]
    assert thread_kind is ThreadKind.GROUP
    assert len(params) == 2


async def test_send_seen_receipt_loai_tin_khac_thread_zca_js_bat_buoc_cung_1_thread() -> None:
    """loại tin khác thread - zca-js bắt buộc cùng 1 thread mỗi lần gọi"""
    api = FakeZaloApi()
    send_seen_receipt(api, [message(), message(thread_id="thread-khac")])
    await drain_pending_receipts()

    assert len(api.seen[0][0]) == 1


async def test_send_seen_receipt_batch_rong_thi_khong_goi_api() -> None:
    """batch rỗng thì không gọi API"""
    api = FakeZaloApi()
    send_seen_receipt(api, [])
    await drain_pending_receipts()
    assert len(api.seen) == 0

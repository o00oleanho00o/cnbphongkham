# ported from: src/zalo/zalo-message-parser.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import re
from datetime import UTC, datetime

from pema.channels.zalo_personal.zalo_message_parser import describe_for_history, parse_incoming_message
from pema_contracts.channel import InboundKind, ThreadKind

SELF_ID = "self-999"

USER = 0
GROUP = 1


def test_parse_incoming_message_doc_tin_nhan_text_thuong() -> None:
    """đọc tin nhắn text thường"""
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "thread-1",
            "type": USER,
            "isSelf": False,
            "data": {
                "content": "chào bot",
                "uidFrom": "user-1",
                "dName": "Hải",
                "msgId": "m1",
                "cliMsgId": "c1",
            },
        },
    )

    assert msg.text == "chào bot"
    assert len(msg.images) == 0
    assert msg.thread_id == "thread-1"
    assert msg.sender_id == "user-1"
    assert msg.sender_name == "Hải"
    assert msg.is_group is False
    assert msg.kind is InboundKind.TEXT
    assert msg.update_id == "m1"


def test_parse_incoming_message_doc_anh_kem_caption_caption_thanh_text_anh_vao_images() -> None:
    """đọc ảnh kèm caption - caption thành text, ảnh vào images"""
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "thread-1",
            "type": USER,
            "data": {
                "msgType": "chat.photo",
                "content": {
                    "title": "ảnh này là gì",
                    "thumb": "https://z.example.invalid/thumb.jpg",
                    "hd": "https://z.example.invalid/hd.jpg",
                },
                "uidFrom": "user-1",
            },
        },
    )

    assert msg.text == "ảnh này là gì"
    assert len(msg.images) == 1
    # Payload chỉ có thumb + hd: mức "normal" không có bản vừa nên lùi về hd
    assert msg.images[0].url == "https://z.example.invalid/hd.jpg"
    assert msg.kind is InboundKind.IMAGE


def test_parse_incoming_message_du_bien_the_mac_dinh_lay_ban_normal_khong_lay_hd() -> None:
    """có đủ biến thể thì mặc định lấy bản normal, KHÔNG lấy hd (hd đắt gấp mấy lần token)"""
    content = {
        "title": "vé số",
        "thumb": "https://z.example.invalid/thumb.jpg",
        "normalUrl": "https://z.example.invalid/normal.jpg",
        "hd": "https://z.example.invalid/hd.jpg",
    }
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "thread-1",
            "type": USER,
            "data": {"msgType": "chat.photo", "content": content, "uidFrom": "user-1"},
        },
    )
    assert msg.images[0].url == "https://z.example.invalid/normal.jpg"

    # Đổi mức chất lượng thì đổi ảnh lấy về - dùng khi cần đọc chi tiết rất nhỏ
    hd_msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "thread-1",
            "type": USER,
            "data": {"msgType": "chat.photo", "content": content, "uidFrom": "user-1"},
        },
        "hd",
    )
    assert hd_msg.images[0].url == "https://z.example.invalid/hd.jpg"


def test_parse_incoming_message_khong_nhan_media_khong_phai_anh_lam_image() -> None:
    """không nhận media không phải ảnh làm image"""
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "thread-1",
            "data": {
                "msgType": "chat.video.msg",
                "content": {"title": "clip", "href": "https://z.example.invalid/clip.mp4"},
                "uidFrom": "user-1",
            },
        },
    )

    assert len(msg.images) == 0
    assert msg.text == "clip"


def test_parse_incoming_message_nhan_dien_mention_bot() -> None:
    """nhận diện @mention bot"""
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "group-1",
            "type": GROUP,
            "data": {"content": "@bot giúp tôi", "uidFrom": "user-1", "mentions": [{"uid": SELF_ID}]},
        },
    )

    assert msg.mentions_me is True
    assert msg.is_group is True
    assert msg.thread_kind is ThreadKind.GROUP


def test_parse_incoming_message_mention_nguoi_khac_khong_tinh_la_mention_bot() -> None:
    """mention người khác không tính là mention bot"""
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "group-1",
            "type": GROUP,
            "data": {"content": "@Nam ơi", "uidFrom": "user-1", "mentions": [{"uid": "user-2"}]},
        },
    )

    assert msg.mentions_me is False


def test_parse_incoming_message_payload_rong_khong_crash_tra_ve_gia_tri_mac_dinh() -> None:
    """payload rỗng không làm crash, trả về giá trị mặc định"""
    msg = parse_incoming_message("acc-test", SELF_ID, {})

    assert msg.text == ""
    assert msg.thread_id == ""
    assert msg.sender_id == ""
    assert msg.sender_name == "Người dùng"
    assert msg.thread_kind is ThreadKind.USER
    assert msg.is_group is False
    assert msg.mentions_me is False
    assert len(msg.images) == 0


def test_parse_incoming_message_giu_data_goc_trong_raw_de_tool_dung_lai() -> None:
    """giữ data gốc trong rawData để tool dùng lại"""
    data = {"content": "hi", "uidFrom": "user-1", "msgId": "m42"}
    msg = parse_incoming_message("acc-test", SELF_ID, {"threadId": "t", "data": data})

    assert msg.raw == data
    assert msg.msg_id == "m42"


def test_parse_incoming_message_payload_hong_khong_nem_loi() -> None:
    """payload sai kiểu (data không phải object, content là số) vẫn ra một tin rỗng, không ném lỗi"""
    msg = parse_incoming_message("acc-test", SELF_ID, {"threadId": 5, "data": "oops", "type": "x"})

    assert msg.thread_id == "5"
    assert msg.text == ""
    assert msg.raw == {}


def test_describe_for_history_tin_chi_co_anh_van_co_chu() -> None:
    """tin chỉ có ảnh vẫn phải có chữ"""
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "t",
            "data": {"msgType": "chat.photo", "content": {"normalUrl": "https://z.example.invalid/n.jpg"}},
        },
    )
    assert describe_for_history(msg) == "[gửi kèm 1 ảnh]"
    assert describe_for_history(parse_incoming_message("acc-test", SELF_ID, {})) == "[ảnh]"


# `sentAt` là mốc giờ DUY NHẤT của một tin: vừa vào `created_at` lúc lưu history, vừa thành nhãn `[dd/mm hh:mm]`
# model đọc. Parser là nơi duy nhất sinh ra nó cho tin thật, nên thiếu ở đây là cả hai chỗ kia cùng sai.

NHAN_LUC = datetime(2026, 8, 7, 16, 37, 0, tzinfo=UTC)


def test_parse_incoming_message_moc_gio_gui_doc_gio_gui_tu_data_ts_chu_khong_lay_gio_nhan() -> None:
    """đọc giờ gửi từ data.ts chứ không lấy giờ nhận"""
    gui_luc = datetime(2026, 8, 7, 16, 30, 0, tzinfo=UTC)
    msg = parse_incoming_message(
        "acc-test",
        SELF_ID,
        {
            "threadId": "t",
            "data": {"content": "hi", "uidFrom": "u1", "ts": str(int(gui_luc.timestamp() * 1000))},
        },
        "normal",
        NHAN_LUC,
    )

    assert msg.sent_at == gui_luc
    assert msg.sent_at != NHAN_LUC, "không được lấy giờ nhận khi đã có giờ gửi"


def test_parse_incoming_message_moc_gio_gui_payload_thieu_ts_van_co_sent_at() -> None:
    """payload thiếu ts vẫn có sentAt (rơi về giờ nhận) - trường này KHÔNG bao giờ rỗng"""
    msg = parse_incoming_message("acc-test", SELF_ID, {}, "normal", NHAN_LUC)
    assert msg.sent_at == NHAN_LUC


def test_parse_incoming_message_moc_gio_gui_sent_at_luon_la_iso_hop_le_o_mui_gio_vn() -> None:
    """sentAt luôn là mốc hợp lệ - trên dây là ISO 8601 +07:00 (contract), cùng instant với giờ gửi"""
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    msg = parse_incoming_message(
        "acc-test", SELF_ID, {"threadId": "t", "data": {"content": "hi", "ts": str(now_ms)}}
    )
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+07:00$", msg.sent_at.isoformat())

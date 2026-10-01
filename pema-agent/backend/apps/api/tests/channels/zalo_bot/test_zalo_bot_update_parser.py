# ported from: src/zalo-bot/zalo-bot-update-parser.test.ts
from __future__ import annotations

import time
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate, unwrap_webhook_payload
from pema.channels.zalo_bot.zalo_bot_update_parser import doi_update_sang_parsed_message
from pema_contracts.channel import InboundKind, ThreadKind

# Payload copied from the official Webhook documentation (synthetic ids).
UPDATE_THAT: dict[str, Any] = {
    "event_name": "message.text.received",
    "message": {
        "from": {"id": "6ede9afa66b88fe6d6a9", "display_name": "Ted", "is_bot": False},
        "chat": {"id": "6ede9afa66b88fe6d6a9", "chat_type": "PRIVATE"},
        "text": "Xin chào",
        "message_id": "2d758cb5e222177a4e35",
        "date": 1750316131602,
    },
}


def update(**message_patch: Any) -> ZaloBotUpdate:
    data = deepcopy(UPDATE_THAT)
    for key, value in message_patch.items():
        if value is None:
            data["message"].pop(key, None)
        else:
            data["message"][key] = value
    return ZaloBotUpdate.model_validate(data)


def test_doi_duoc_payload_nguyen_van_cua_tai_lieu() -> None:
    """đổi được payload nguyên văn của tài liệu"""
    m = doi_update_sang_parsed_message("bot-1", ZaloBotUpdate.model_validate(UPDATE_THAT))
    assert m is not None
    assert m.text == "Xin chào"
    assert m.sender_name == "Ted"
    assert m.thread_id == "6ede9afa66b88fe6d6a9"
    assert m.account_id == "bot-1"
    assert m.is_group is False
    assert m.thread_kind is ThreadKind.USER
    assert m.update_id == "2d758cb5e222177a4e35", "khóa chống trùng là message_id"


def test_date_la_mili_giay_doi_ra_dung_nam_2025_khong_phai_nam_57xxx() -> None:
    """`date` là MILIGIÂY - đổi ra đúng năm 2025, không phải năm 57xxx"""
    m = doi_update_sang_parsed_message("bot-1", ZaloBotUpdate.model_validate(UPDATE_THAT))
    assert m is not None
    assert m.sent_at.astimezone(UTC).year == 2025


def test_bo_tin_cua_bot_khac_chong_hai_bot_noi_chuyen_vo_tan() -> None:
    """bỏ tin của BOT khác - chống hai bot nói chuyện vô tận"""
    data = deepcopy(UPDATE_THAT)
    data["message"]["from"] = {"id": "b2", "display_name": "Bot Kia", "is_bot": True}
    assert doi_update_sang_parsed_message("bot-1", ZaloBotUpdate.model_validate(data)) is None


def test_nhom_ra_dung_thread_type_va_is_group() -> None:
    """nhóm ra đúng threadType và isGroup"""
    m = doi_update_sang_parsed_message("bot-1", update(chat={"id": "g1", "chat_type": "GROUP"}))
    assert m is not None
    assert m.is_group is True
    assert m.thread_kind is ThreadKind.GROUP
    assert m.thread_id == "g1"


def test_tin_nhom_luon_mentions_me_zalo_chi_day_khi_bot_duoc_nhac_toi() -> None:
    """tin nhóm luôn mentionsMe - Zalo chỉ đẩy khi bot được nhắc tới"""
    # Unlike the personal channel, where the bot receives EVERY group message and must filter the @mention
    # itself.
    m = doi_update_sang_parsed_message("bot-1", update(chat={"id": "g1", "chat_type": "GROUP"}))
    assert m is not None
    assert m.mentions_me is True


def test_anh_doc_duoc_ca_photo_lan_photo_url_va_caption_thanh_text() -> None:
    """ảnh: đọc được cả `photo` lẫn `photo_url`, và caption thành text"""
    u = ZaloBotUpdate.model_validate(
        {
            "event_name": "message.image.received",
            "message": {
                **UPDATE_THAT["message"],
                "text": None,
                "photo": "https://a.test/1.jpg",
                "caption": "cái bảng",
            },
        }
    )
    m = doi_update_sang_parsed_message("bot-1", u)
    assert m is not None
    assert [i.url for i in m.images] == ["https://a.test/1.jpg"]
    assert m.text == "cái bảng"
    assert m.kind is InboundKind.IMAGE

    u2 = ZaloBotUpdate.model_validate(
        {
            "event_name": "message.image.received",
            "message": {**UPDATE_THAT["message"], "text": None, "photo_url": "https://a.test/2.jpg"},
        }
    )
    m2 = doi_update_sang_parsed_message("bot-1", u2)
    assert m2 is not None
    assert [i.url for i in m2.images] == ["https://a.test/2.jpg"]


def _label(event_name: str, **extra: Any) -> str | None:
    u = ZaloBotUpdate.model_validate(
        {"event_name": event_name, "message": {**UPDATE_THAT["message"], "text": None, **extra}}
    )
    m = doi_update_sang_parsed_message("bot-1", u)
    return None if m is None else m.text


def test_sticker_tin_thoai_loai_la_ra_nhan_khong_phai_tin_rong() -> None:
    """sticker / tin thoại / loại lạ ra NHÃN, không phải tin rỗng"""
    # An empty message builds a blank agent turn: the model cannot tell what was sent and answers at random.
    assert _label("message.sticker.received", sticker="s1") == "[gửi một sticker]"
    assert _label("message.voice.received", voice_url="https://v.test/a.m4a") == "[gửi một tin thoại]"
    assert _label("message.unsupported.received") == "[gửi một nội dung bot chưa đọc được]"


def test_anh_khong_moi_duoc_url_thi_co_nhan_khong_de_tin_bien_mat_im_lang() -> None:
    """ảnh KHÔNG moi được URL thì có NHÃN - không để tin biến mất im lặng"""
    # A patch for a message-loss bug: Zalo renames the image field -> empty text and empty images ->
    # ``should_respond`` skips with ``record: False`` -> the message never enters history. The channel has no
    # ``offset``, so it is lost.
    u = ZaloBotUpdate.model_validate(
        {"event_name": "message.image.received", "message": {**UPDATE_THAT["message"], "text": None}}
    )
    m = doi_update_sang_parsed_message("bot-1", u)
    assert m is not None
    assert "ảnh" in m.text, f"ảnh không moi được URL mà không có nhãn: {m.text!r}"
    assert m.images == []


def test_anh_khong_bi_gan_nhan_no_co_duong_rieng_qua_images() -> None:
    """ảnh KHÔNG bị gắn nhãn - nó có đường riêng qua `images`"""
    u = ZaloBotUpdate.model_validate(
        {
            "event_name": "message.image.received",
            "message": {**UPDATE_THAT["message"], "text": None, "photo": "https://a.test/1.jpg"},
        }
    )
    m = doi_update_sang_parsed_message("bot-1", u)
    assert m is not None
    assert m.text == "", "ảnh bị gắn nhãn thừa - nó đã nằm trong images rồi"
    assert len(m.images) == 1


def test_update_khong_co_message_thi_tra_none_khong_nem() -> None:
    """update không có message thì trả null, không ném"""
    assert (
        doi_update_sang_parsed_message("bot-1", ZaloBotUpdate.model_validate({"event_name": "gì đó lạ"}))
        is None
    )


def test_date_hong_thi_lay_gio_hien_tai_chu_khong_ra_invalid_date() -> None:
    """`date` hỏng thì lấy giờ hiện tại chứ không ra Invalid Date"""
    # Between two marks taken AROUND the call rather than against a fixed year.
    truoc = time.time()
    m = doi_update_sang_parsed_message("bot-1", update(date=0))
    sau = time.time()
    assert m is not None
    assert truoc - 1 <= m.sent_at.timestamp() <= sau + 1, f"sent_at {m.sent_at} nằm ngoài [{truoc}, {sau}]"
    assert isinstance(m.sent_at, datetime)


def test_date_qua_lon_khong_lam_vo_parser() -> None:
    """(thêm) `date` ngoài miền datetime không làm ném lỗi"""
    m = doi_update_sang_parsed_message("bot-1", update(date=1e30))
    assert m is not None


def test_tin_nhom_cua_kenh_bot_khong_sinh_trich_dan_raw_khong_co_msg_type() -> None:
    """tin NHÓM của kênh bot KHÔNG sinh trích dẫn - lưới chắn phải tường minh"""
    # ``quote`` of the original comes from ``rawData.msgType``; the bot payload has no such field, and
    # ``ChannelCapabilities .supports_quote`` is False. This makes the accidental net a guarded one.
    m = doi_update_sang_parsed_message(
        "bot-1", update(chat={"id": "g1", "chat_type": "GROUP"}, text="cho hỏi bảng giá")
    )
    assert m is not None
    assert m.is_group is True, "fixture phải là tin NHÓM - chat riêng vốn không trích"
    assert "msgType" not in m.raw


def test_thieu_message_id_thi_khoa_chong_trung_la_hash_on_dinh_cua_payload() -> None:
    """(thêm) thiếu message_id: update_id là hash ổn định, hai lần parse ra cùng một khóa"""
    a = doi_update_sang_parsed_message("bot-1", update(message_id=None))
    b = doi_update_sang_parsed_message("bot-1", update(message_id=None))
    assert a is not None
    assert b is not None
    assert a.update_id.startswith("h:")
    assert a.update_id == b.update_id


def test_webhook_boc_result_con_polling_tra_thang() -> None:
    """(thêm) webhook gói update trong {ok, result}; polling trả thẳng - cùng một parser"""
    wrapped = {"ok": True, "result": UPDATE_THAT}
    assert unwrap_webhook_payload(wrapped)["event_name"] == "message.text.received"
    assert unwrap_webhook_payload(UPDATE_THAT)["event_name"] == "message.text.received"

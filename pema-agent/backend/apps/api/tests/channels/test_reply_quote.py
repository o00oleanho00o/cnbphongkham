# ported from: src/zalo/reply-quote.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Module thuần - không chạm env/DB. The original builds a zca-js ``ParsedMessage``; here the input is an
``InboundMessage`` whose ``raw`` is the zca-js ``data`` object (all data synthetic).
"""

from __future__ import annotations

from typing import Any

from pema.channels.reply_quote import (
    la_loai_trich_dan_duoc,
    so_byte_trich_dan,
    trich_dan_trong_ngan_sach,
    trich_dan_tu_tin,
)
from pema_contracts.channel import ChannelKind, InboundMessage, ThreadKind
from pema_contracts.testing import make_inbound


def tin_nhom(raw_data: dict[str, Any] | None = None, **extra: object) -> InboundMessage:
    """Payload thật của một tin text trong nhóm, đủ 8 trường `SendMessageQuote` cần."""
    raw: dict[str, Any] = {
        "content": "bot ơi tra giúp giá vàng",
        "msgType": "webchat",
        "propertyExt": {"color": 0, "size": 0, "type": 0, "subType": 0, "ext": ""},
        "uidFrom": "u-hai",
        "msgId": "m-1",
        "cliMsgId": "c-1",
        "ts": "1786122720000",
        "ttl": 0,
        **(raw_data or {}),
    }
    fields: dict[str, object] = {
        "channel": ChannelKind.ZALO_PERSONAL,
        "account_id": "acc-1",
        "thread_id": "g-1",
        "thread_kind": ThreadKind.GROUP,
        "is_group": True,
        "sender_id": "u-hai",
        "msg_id": "m-1",
        "cli_msg_id": "c-1",
        "mentions_me": True,
        "raw": raw,
        **extra,
    }
    return make_inbound("bot ơi tra giúp giá vàng", **fields)  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------- khi nào trích


def test_trich_dan_tu_tin_when_to_quote_group_builds_all_8_fields_taken_verbatim_from_the_raw_payload() -> (
    None
):
    """nhóm: dựng đủ 8 trường zca-js cần, lấy nguyên từ payload gốc"""
    q = trich_dan_tu_tin(tin_nhom())
    assert q is not None
    assert q.raw == {
        "content": "bot ơi tra giúp giá vàng",
        "msgType": "webchat",
        "propertyExt": {"color": 0, "size": 0, "type": 0, "subType": 0, "ext": ""},
        "uidFrom": "u-hai",
        "msgId": "m-1",
        "cliMsgId": "c-1",
        "ts": "1786122720000",
        "ttl": 0,
    }
    # key order is the one of JSON.stringify of the original object literal
    assert list(q.raw) == ["content", "msgType", "propertyExt", "uidFrom", "msgId", "cliMsgId", "ts", "ttl"]
    # the three ids of the contract come from msgId / cliMsgId / uidFrom
    assert (q.msg_id, q.cli_msg_id, q.sender_id) == ("m-1", "c-1", "u-hai")


def test_trich_dan_tu_tin_when_to_quote_private_chat_does_not_quote_two_people_so_a_quote_adds_nothing() -> (
    None
):
    """chat RIÊNG không trích - hai người thì trích dẫn không thêm thông tin gì"""
    rieng = tin_nhom(is_group=False, thread_kind=ThreadKind.USER)
    assert trich_dan_tu_tin(rieng) is None


def test_trich_dan_tu_tin_when_to_quote_numeric_ts_is_accepted_and_turned_into_the_string_zca_js_expects() -> (
    None
):
    """ts dạng SỐ vẫn nhận, đổi về chuỗi đúng kiểu zca-js chờ"""
    q = trich_dan_tu_tin(tin_nhom({"ts": 1786122720000}))
    assert q is not None
    assert q.raw["ts"] == "1786122720000"
    q_float = trich_dan_tu_tin(tin_nhom({"ts": 1786122720000.0}))  # a JSON number may arrive as a float
    assert q_float is not None
    assert q_float.raw["ts"] == "1786122720000"


def test_trich_dan_tu_tin_when_to_quote_missing_ttl_becomes_0_no_undefined_leaks_into_the_payload() -> None:
    """thiếu ttl thì về 0, không để undefined lọt xuống payload"""
    for raw in ({"ttl": None}, {"ttl": "5"}, {"ttl": True}):
        q = trich_dan_tu_tin(tin_nhom(raw))
        assert q is not None
        assert q.raw["ttl"] == 0, raw
    absent = tin_nhom()
    del absent.raw["ttl"]
    q_absent = trich_dan_tu_tin(absent)
    assert q_absent is not None
    assert q_absent.raw["ttl"] == 0
    q_set = trich_dan_tu_tin(tin_nhom({"ttl": 3600}))
    assert q_set is not None
    assert q_set.raw["ttl"] == 3600


# ------------------------------------------------------------- loại tin zca-js từ chối trích
# Hai loại dưới đây zca-js NÉM `ZaloApiError` không kèm mã số (`sendMessage.ts`, khối `if (quote)`). Lỗi không
# mã thì `laLoiMayChuTuChoi` không nhận ra là máy chủ từ chối, nên đường lui không chạy và cả câu trả lời mất
# trắng. Phải chặn TRƯỚC khi gọi.


def test_trich_dan_tu_tin_types_zca_js_refuses_group_poll_is_not_quoted() -> None:
    """group.poll: không trích"""
    assert trich_dan_tu_tin(tin_nhom({"msgType": "group.poll"})) is None


def test_trich_dan_tu_tin_types_zca_js_refuses_webchat_with_non_string_content_is_not_quoted() -> None:
    """webchat mà content KHÔNG phải chuỗi: không trích"""
    assert trich_dan_tu_tin(tin_nhom({"msgType": "webchat", "content": {"title": "x", "href": "y"}})) is None


def test_trich_dan_tu_tin_types_zca_js_refuses_photo_with_object_content_is_still_quoted_do_not_block_by_mistake() -> (
    None
):
    """ảnh (chat.photo, content là object): VẪN trích - đừng chặn nhầm"""
    q = trich_dan_tu_tin(tin_nhom({"msgType": "chat.photo", "content": {"title": "ảnh", "href": "u"}}))
    assert q is not None
    assert q.raw["msgType"] == "chat.photo"


def test_trich_dan_tu_tin_types_zca_js_refuses_the_rule_matches_exactly_the_two_zca_js_conditions_no_more_no_less() -> (
    None
):
    """luật gốc khớp đúng hai điều kiện của zca-js, không hơn không kém"""
    assert la_loai_trich_dan_duoc("group.poll", "chữ") is False
    assert la_loai_trich_dan_duoc("webchat", {"a": 1}) is False
    assert la_loai_trich_dan_duoc("webchat", "chữ") is True
    assert la_loai_trich_dan_duoc("chat.photo", {"a": 1}) is True
    assert la_loai_trich_dan_duoc("share.file", {"a": 1}) is True


# ------------------------------------------------------------- thiếu định danh thì không trích


def test_trich_dan_tu_tin_missing_identifiers_missing_msg_id_zalo_cannot_find_the_original_so_the_quote_is_dropped() -> (
    None
):
    """thiếu msgId: Zalo không tìm ra tin gốc nên bỏ trích dẫn"""
    _thieu_dinh_danh("msgId")


def test_trich_dan_tu_tin_missing_identifiers_missing_cli_msg_id_zalo_cannot_find_the_original_so_the_quote_is_dropped() -> (
    None
):
    """thiếu cliMsgId: Zalo không tìm ra tin gốc nên bỏ trích dẫn"""
    _thieu_dinh_danh("cliMsgId")


def test_trich_dan_tu_tin_missing_identifiers_missing_uid_from_zalo_cannot_find_the_original_so_the_quote_is_dropped() -> (
    None
):
    """thiếu uidFrom: Zalo không tìm ra tin gốc nên bỏ trích dẫn"""
    _thieu_dinh_danh("uidFrom")


def test_trich_dan_tu_tin_missing_identifiers_missing_ts_zalo_cannot_find_the_original_so_the_quote_is_dropped() -> (
    None
):
    """thiếu ts: Zalo không tìm ra tin gốc nên bỏ trích dẫn"""
    _thieu_dinh_danh("ts")


def _thieu_dinh_danh(truong: str) -> None:
    assert trich_dan_tu_tin(tin_nhom({truong: ""})) is None
    assert trich_dan_tu_tin(tin_nhom({truong: None})) is None
    thieu = tin_nhom()
    del thieu.raw[truong]
    assert trich_dan_tu_tin(thieu) is None


def test_trich_dan_tu_tin_missing_identifiers_synthetic_message_of_a_scheduled_turn_empty_raw_is_not_quoted() -> (
    None
):
    """tin TỔNG HỢP của lượt theo lịch (rawData rỗng) không trích"""
    # `buildSyntheticMessage` để msgId/cliMsgId rỗng có chủ đích - không có tin thật nào để mà trích. Đây là
    # cửa chặn thứ hai sau việc scheduler không đặt `quote` trên ReplyTarget của nó.
    tong_hop = tin_nhom(msg_id="synthetic", cli_msg_id="", raw={})
    assert trich_dan_tu_tin(tong_hop) is None


# ------------------------------------------------------------- trichDanTrongNganSach

TRAN = 3250


def test_trich_dan_trong_ngan_sach_without_a_quote_the_budget_stays_whole_for_the_bot_text() -> None:
    """không có trích dẫn: trần giữ nguyên cho chữ của bot"""
    r = trich_dan_trong_ngan_sach(None, TRAN)
    assert r.quote is None
    assert r.tran_con_lai == TRAN
    assert r.bo_vi_qua_dai is False


def test_trich_dan_trong_ngan_sach_short_quote_is_kept_and_exactly_what_it_takes_is_subtracted_from_the_budget() -> (
    None
):
    """trích dẫn ngắn: giữ, và TRỪ đúng phần nó chiếm khỏi trần"""
    q = trich_dan_tu_tin(tin_nhom())
    assert q is not None
    r = trich_dan_trong_ngan_sach(q, TRAN)
    assert r.quote is q
    assert r.tran_con_lai == TRAN - so_byte_trich_dan(q)
    assert r.tran_con_lai < TRAN, "phải trừ thật, không được để nguyên trần"


def test_trich_dan_trong_ngan_sach_overlong_quote_is_dropped_and_the_whole_budget_goes_back_to_the_text() -> (
    None
):
    """trích dẫn QUÁ DÀI: bỏ hẳn, trả trần nguyên vẹn cho chữ"""
    # Người ta dán một đoạn dài rồi bot trích lại: riêng khối trích dẫn đã vượt trần, mà
    # `chia_theo_ngan_sach_byte` chỉ đo chữ của bot nên vẫn báo mọi đoạn đều lọt - tin đầu bị Zalo chối mà
    # không ai hiểu vì sao.
    dai = "x" * 2000
    q = trich_dan_tu_tin(tin_nhom({"content": dai}))
    assert q is not None
    r = trich_dan_trong_ngan_sach(q, TRAN)
    assert r.quote is None, "mất khối trang trí còn hơn mất cả tin"
    assert r.tran_con_lai == TRAN
    assert r.bo_vi_qua_dai is True, "phải nói ra để nơi gọi ghi log"


# ------------------------------------------------------------- additions of the port


def test_so_byte_trich_dan_is_the_utf8_length_of_the_compact_json_of_the_full_quote() -> None:
    """(port) so_byte_trich_dan = byte UTF-8 của JSON gọn (không dấu cách, không escape chữ có dấu) của quote.raw"""
    q = trich_dan_tu_tin(tin_nhom({"content": "Giá 😀"}))
    assert q is not None
    json_gon = (
        '{"content":"Giá 😀","msgType":"webchat","propertyExt":{"color":0,"size":0,"type":0,"subType":0,"ext":""},'
        '"uidFrom":"u-hai","msgId":"m-1","cliMsgId":"c-1","ts":"1786122720000","ttl":0}'
    )
    assert so_byte_trich_dan(q) == len(json_gon.encode("utf-8"))
    # "á" is 2 bytes, the emoji 4: the count is bytes, not characters or UTF-16 units
    assert len(json_gon.encode("utf-8")) == len(json_gon) + 1 + 3


def test_trich_dan_tu_tin_leaves_out_content_and_property_ext_when_the_payload_has_none() -> None:
    """(port) JSON.stringify bỏ trường undefined: raw không có content/propertyExt thì quote cũng không có"""
    raw = tin_nhom({"msgType": "chat.photo"}).raw  # webchat without a string content is never quoted
    del raw["content"]
    del raw["propertyExt"]
    q = trich_dan_tu_tin(tin_nhom(raw=raw))
    assert q is not None
    assert list(q.raw) == ["msgType", "uidFrom", "msgId", "cliMsgId", "ts", "ttl"]
    assert q.raw["msgType"] == "chat.photo"

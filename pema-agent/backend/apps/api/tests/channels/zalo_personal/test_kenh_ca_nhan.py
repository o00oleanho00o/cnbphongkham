# ported from: src/zalo/kenh-ca-nhan.ts
"""``ZaloPersonalChannel``: the ``ChannelPort`` of a personal account and its optional abilities.

The original had no test file for ``kenhCaNhan`` (it was covered through ``account-manager-kenh.test.ts`` and the
message-turn tests); these cases pin the contract of the Python port.
"""

from __future__ import annotations

import asyncio
import json

from pema.channels.zalo_personal.bridge_signing import compute_signature
from pema.channels.zalo_personal.channel_settings import ChannelSettings
from pema.channels.zalo_personal.testing import FakeZaloApi, StaticPolicyReader, make_personal_channel
from pema_contracts.channel import (
    ChannelKind,
    GroupChannel,
    MediaChannel,
    ReactionChannel,
    ReadReceiptChannel,
    SendStatus,
    ThreadKind,
    TypingChannel,
)
from pema_contracts.testing import make_inbound

SECRET = "bridge-test-secret-0123456789"


def test_kenh_ca_nhan_dung_cac_protocol_nang_luc_tuy_chon() -> None:
    channel = make_personal_channel()
    assert channel.kind is ChannelKind.ZALO_PERSONAL
    for protocol in (TypingChannel, ReadReceiptChannel, ReactionChannel, MediaChannel, GroupChannel):
        assert isinstance(channel, protocol), protocol


def test_kenh_ca_nhan_capabilities_mang_dinh_dang_va_tran_ngay() -> None:
    channel = make_personal_channel(
        reader=StaticPolicyReader(
            ChannelSettings(
                channel=ChannelKind.ZALO_PERSONAL, enabled=True, daily_cap=7, requires_friend=True
            )
        )
    )
    channel.gate.snapshot = channel.gate.snapshot.__class__(
        channel=ChannelKind.ZALO_PERSONAL, enabled=True, daily_cap=7, requires_friend=True
    )

    caps = channel.capabilities()

    assert caps.supports_formatting is True
    assert caps.supports_quote is True
    assert caps.daily_cap == 7
    assert caps.requires_friend is True
    assert caps.supports_typing_indicator
    assert caps.supports_read_receipt
    assert caps.supports_reactions
    assert caps.blocked_tools == {}, "kênh cá nhân không chặn tool nào (khác kênh bot)"


def test_verify_webhook_chap_nhan_chu_ky_dung_va_tu_choi_chu_ky_sai() -> None:
    channel = make_personal_channel()
    body = json.dumps({"type": "message"}).encode()
    import time

    ts = int(time.time())
    good = {"X-Pema-Timestamp": str(ts), "X-Pema-Signature": compute_signature(SECRET, ts, body)}
    bad = {
        "X-Pema-Timestamp": str(ts),
        "X-Pema-Signature": compute_signature("other-secret-0123456789", ts, body),
    }

    assert channel.verify_webhook(good, body) is True
    assert channel.verify_webhook(bad, body) is False
    assert channel.verify_webhook({}, body) is False


def test_verify_webhook_khong_co_secret_thi_luon_tu_choi() -> None:
    channel = make_personal_channel(secret=None)
    assert channel.verify_webhook({"X-Pema-Timestamp": "1", "X-Pema-Signature": "x"}, b"{}") is False


def envelope(**message: object) -> dict[str, object]:
    return {
        "type": "message",
        "self_id": "self-999",
        "message": {
            "threadId": "t1",
            "type": 0,
            "isSelf": False,
            "data": {"content": "chào bot", "uidFrom": "user-1", "dName": "Hải", "msgId": "m1", **message},
        },
    }


def test_parse_inbound_chuan_hoa_tin_nhan_cua_bridge() -> None:
    channel = make_personal_channel()
    msg = channel.parse_inbound(envelope())
    assert msg is not None
    assert (msg.text, msg.thread_id, msg.sender_id, msg.update_id) == ("chào bot", "t1", "user-1", "m1")
    assert msg.channel is ChannelKind.ZALO_PERSONAL


def test_parse_inbound_bo_qua_su_kien_khong_phai_tin_nhan_va_tin_echo() -> None:
    channel = make_personal_channel()
    assert channel.parse_inbound({"type": "friend_event"}) is None
    assert channel.parse_inbound({"type": "message", "message": "oops"}) is None
    echo = envelope()
    echo["message"]["isSelf"] = True  # type: ignore[index]
    assert channel.parse_inbound(echo) is None
    assert channel.parse_inbound({"type": "message", "message": {"data": {}}}) is None, "không có thread"


async def test_send_text_gui_tin_tra_loi_qua_api_voi_proactive_false() -> None:
    api = FakeZaloApi()
    channel = make_personal_channel(api)
    result = await channel.send_text("t1", "xin chào")
    assert result.status is SendStatus.SENT
    assert result.external_message_id == "sent-1"
    assert (api.sent[0].text, api.sent[0].proactive, api.sent[0].thread_type) == (
        "xin chào",
        False,
        ThreadKind.USER,
    )


async def test_react_dung_dung_icon_va_icon_la_roi_ve_tim() -> None:
    api = FakeZaloApi()
    channel = make_personal_channel(api)
    msg = make_inbound("hi", msg_id="m9", thread_id="t1")

    await channel.react(msg, "rose")
    await channel.react(msg, "khong-co-icon-nay")

    assert [r[0] for r in api.reactions] == ["rose", "heart"]


async def test_tag_member_mention_chi_phu_phan_ten_va_dung_do_dai_utf16() -> None:
    api = FakeZaloApi()
    channel = make_personal_channel(api)

    await channel.tag_member("g1", "uid-2", "@Hải Nam 😀 xem giúp", mention_len=9)
    await channel.tag_member("g1", "uid-3", "@Lan ơi")

    first, second = api.sent
    assert first.mentions == ({"pos": 0, "uid": "uid-2", "len": 9},)
    assert second.mentions == ({"pos": 0, "uid": "uid-3", "len": 4},), (
        "không có mention_len: tới khoảng trắng đầu"
    )
    assert first.thread_type is ThreadKind.GROUP


async def test_mark_seen_khong_cho_bridge_va_khong_nem_loi() -> None:
    api = FakeZaloApi()
    channel = make_personal_channel(api)
    msg = make_inbound(
        "hi",
        msg_id="m1",
        thread_id="t1",
        raw={"msgId": "m1", "cliMsgId": "c1", "uidFrom": "u1", "idTo": "self-1"},
    )
    await channel.mark_seen([msg])
    from pema.channels.zalo_personal.message_receipts import drain_pending_receipts

    await drain_pending_receipts()
    assert len(api.seen) == 1


async def test_start_typing_ban_ngay_va_stop_dung_han() -> None:
    api = FakeZaloApi()
    channel = make_personal_channel(api)
    stop = channel.start_typing("t1", ThreadKind.USER)
    await asyncio.sleep(0.01)
    stop()
    assert api.typing[0] == ("t1", ThreadKind.USER)

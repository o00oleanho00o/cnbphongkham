# ported from: src/middleware/allowlist-filter.test.ts
from __future__ import annotations

from pema.middleware.allowlist_filter import should_respond
from pema_contracts.agents import Allowlist, AllowlistMode
from pema_contracts.channel import InboundImage, ThreadKind
from pema_contracts.testing import fake_account_config, make_inbound


def _account(**patch: object):
    return fake_account_config(**patch)


def test_bo_qua_tin_do_chinh_bot_gui() -> None:
    """bỏ qua tin do chính bot gửi"""
    decision = should_respond(_account(), make_inbound(is_self=True))
    assert decision.respond is False


def test_bo_qua_tin_khong_co_text_lan_anh_sticker_voice() -> None:
    """bỏ qua tin không có text lẫn ảnh (sticker, voice...)"""
    decision = should_respond(_account(), make_inbound("   "))
    assert decision.respond is False


def test_nhan_tin_chi_co_anh_khong_co_chu() -> None:
    """nhận tin chỉ có ảnh, không có chữ"""
    msg = make_inbound("", images=[InboundImage(url="https://example.test/a.jpg")])
    assert should_respond(_account(), msg).respond is True


def test_bo_qua_group_khi_account_tat_tra_loi_group() -> None:
    """bỏ qua group khi account tắt trả lời group"""
    account = _account(respond_to_groups=False)
    msg = make_inbound(is_group=True, thread_kind=ThreadKind.GROUP, mentions_me=True)
    assert should_respond(account, msg).respond is False


def test_group_khong_mention_passive_listen_khong_tra_loi_nhung_ghi_history() -> None:
    """group không @mention + passive listen: không trả lời nhưng ghi history"""
    msg = make_inbound(is_group=True, thread_kind=ThreadKind.GROUP, mentions_me=False)
    decision = should_respond(_account(), msg)
    assert decision.respond is False
    assert decision.record is True


def test_group_khong_mention_tat_passive_listen_bo_qua_han() -> None:
    """group không @mention + tắt passive listen: bỏ qua hẳn"""
    account = _account(group_passive_listen=False)
    msg = make_inbound(is_group=True, thread_kind=ThreadKind.GROUP, mentions_me=False)
    decision = should_respond(account, msg)
    assert decision.respond is False
    assert decision.record is False


def test_thread_tat_bot_khong_tra_loi_nhung_van_ghi_history() -> None:
    """thread tắt bot: không trả lời nhưng vẫn ghi history"""
    decision = should_respond(_account(), make_inbound(), False)
    assert decision.respond is False
    assert decision.record is True


def test_ngoai_allowlist_thi_khong_ghi_gi_ke_ca_khi_thread_tat_bot() -> None:
    """ngoài allowlist thì không ghi gì kể cả khi thread tắt bot"""
    account = _account(allowlist=Allowlist(mode=AllowlistMode.LIST, user_ids=["user-9"]))
    decision = should_respond(account, make_inbound(sender_id="user-1"), False)
    assert decision.record is False


def test_tin_cua_chinh_bot_khong_bao_gio_duoc_ghi_passive() -> None:
    """tin của chính bot không bao giờ được ghi passive"""
    decision = should_respond(_account(), make_inbound(is_self=True))
    assert decision.record is False


def test_tin_duoc_tra_loi_thi_cung_duoc_ghi_history() -> None:
    """tin được trả lời thì cũng được ghi history"""
    decision = should_respond(_account(), make_inbound())
    assert decision.respond is True
    assert decision.record is True


def test_tra_loi_trong_group_khi_co_mention_bot() -> None:
    """trả lời trong group khi có @mention bot"""
    msg = make_inbound(is_group=True, thread_kind=ThreadKind.GROUP, mentions_me=True)
    assert should_respond(_account(), msg).respond is True


def test_tra_loi_trong_group_khong_can_mention_khi_group_require_mention_false() -> None:
    """trả lời trong group không cần mention khi groupRequireMention=false"""
    account = _account(group_require_mention=False)
    msg = make_inbound(is_group=True, thread_kind=ThreadKind.GROUP, mentions_me=False)
    assert should_respond(account, msg).respond is True


def test_chan_sender_ngoai_allowlist_khi_mode_list() -> None:
    """chặn sender ngoài allowlist khi mode=list"""
    account = _account(allowlist=Allowlist(mode=AllowlistMode.LIST, user_ids=["user-9"]))
    decision = should_respond(account, make_inbound(sender_id="user-1"))
    assert decision.respond is False
    assert "allowlist" in decision.reason


def test_cho_qua_sender_nam_trong_allowlist_khi_mode_list() -> None:
    """cho qua sender nằm trong allowlist khi mode=list"""
    account = _account(allowlist=Allowlist(mode=AllowlistMode.LIST, user_ids=["user-1"]))
    assert should_respond(account, make_inbound(sender_id="user-1")).respond is True


def test_mode_all_thi_khong_loc_theo_user_ids() -> None:
    """mode=all thì không lọc theo userIds"""
    account = _account(allowlist=Allowlist(mode=AllowlistMode.ALL, user_ids=["user-9"]))
    assert should_respond(account, make_inbound(sender_id="user-1")).respond is True

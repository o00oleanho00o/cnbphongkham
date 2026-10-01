# ported from: src/zalo/account-manager-kenh.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Sổ ``running`` phải mô tả được KÊNH, không riêng ``ZaloApi``. This file ports the personal-account half of the
original (the Bot half belongs to package C1's ``bot_account_runner``) and adds the clinic safety switches:

* the process flag and the clinic switch must both be on;
* nothing starts without a stored credential (the channel is dormant until a QR scan);
* an account the bridge already runs is attached, not logged in again.
"""

from __future__ import annotations

from uuid import UUID

import pytest

from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.send_reply_in_parts import DoanCanGui
from pema.channels.zalo_personal.account_manager import AccountManager
from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.channels.zalo_personal.channel_settings import ChannelSettings
from pema.channels.zalo_personal.credential_vault import CredentialVault
from pema.channels.zalo_personal.kenh_ca_nhan import duong_gui_zca_js
from pema.channels.zalo_personal.testing import FakeBridge, StaticPolicyReader
from pema_contracts.channel import ChannelKind, ThreadKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.testing import FAKE_CLINIC_ID, InMemoryAccountStore, fake_account_config

CA_NHAN = "acc-kenh-ca-nhan"
CLINIC: UUID = FAKE_CLINIC_ID


class Rig:
    def __init__(self, *, enabled: bool = True, flag: bool = True, with_credential: bool = True) -> None:
        self.accounts = InMemoryAccountStore(
            fake_account_config(id=CA_NHAN, channel=ChannelKind.ZALO_PERSONAL, label="Cá nhân")
        )
        self.bridge = FakeBridge()
        self.registry = InMemoryChannelRegistry()
        self.reader = StaticPolicyReader(
            ChannelSettings(channel=ChannelKind.ZALO_PERSONAL, enabled=enabled, version=1)
        )
        self.vault = CredentialVault(self.accounts, encrypt=lambda s: "enc:" + s, decrypt=lambda s: s[4:])
        self.flag = flag
        self.manager = AccountManager(
            accounts=self.accounts,
            vault=self.vault,
            bridge=self.bridge,
            registry=self.registry,
            policy_reader=self.reader,
            flag_enabled=lambda: self.flag,
            bridge_secret=lambda: "secret-0123456789abcdef",
        )
        self.with_credential = with_credential

    async def seed_credential(self) -> None:
        await self.vault.save_credentials(
            CLINIC, CA_NHAN, {"cookie": [], "imei": "imei-1", "userAgent": "ua"}
        )


@pytest.fixture
def rig() -> Rig:
    return Rig()


async def test_so_account_dang_chay_kenh_ca_nhan_vao_so_kenh_api_la_api_da_gan_duong_gui_goi_dung_api_send_message(
    rig: Rig,
) -> None:
    """kênh CÁ NHÂN vào sổ: `kenh.api` là api đã gắn, `duongGui` gọi đúng `api.sendMessage`"""
    config = await rig.accounts.get_account(CLINIC, CA_NHAN)
    assert config is not None
    await rig.manager.attach_account(CLINIC, config, "self-1")

    kenh = rig.manager.get_running_account_kenh(CLINIC, CA_NHAN)
    assert kenh is not None, "account cá nhân đang chạy mà không lấy được kênh"
    api = rig.bridge.apis[CA_NHAN]
    assert kenh.api is api, "`kenh.api` phải LÀ api đã gắn, không phải bản sao khác"
    assert rig.registry.get_running(CLINIC, CA_NHAN) is kenh, "scheduler lấy kênh qua registry dùng chung"

    await duong_gui_zca_js(kenh.api, "t1", ThreadKind.USER)(DoanCanGui("xin chào"))
    assert [(m.thread_id, m.text) for m in api.sent] == [("t1", "xin chào")]


async def test_so_account_dang_chay_api_chi_lay_duoc_qua_kenh_khong_con_loi_tat_theo_account_id(
    rig: Rig,
) -> None:
    """`api` zca-js chỉ lấy được qua kênh - không còn lối tắt theo accountId"""
    # `getRunningAccountApi` đã bị XÓA: mọi caller của nó đều đi tiếp một bước giống hệt nhau (tự dựng đường gửi),
    # tức nó là cái bẫy có hình dạng tiện lợi. Còn thuộc tính nào tên như vậy nghĩa là lối tắt đã quay lại.
    assert not hasattr(AccountManager, "get_running_account_api")
    assert not hasattr(rig.manager, "get_running_account_api")


async def test_so_account_dang_chay_stop_account_don_luon_kenh_khong_de_lai_duong_gui_cho_account_da_dung(
    rig: Rig,
) -> None:
    """`stopAccount` dọn luôn kênh - không để lại đường gửi cho account đã dừng"""
    config = await rig.accounts.get_account(CLINIC, CA_NHAN)
    assert config is not None
    await rig.manager.attach_account(CLINIC, config, "self-1")
    assert rig.manager.get_running_account_kenh(CLINIC, CA_NHAN) is not None

    await rig.manager.stop_account(CLINIC, CA_NHAN)

    assert rig.manager.get_running_account_kenh(CLINIC, CA_NHAN) is None, (
        "còn kênh sau khi dừng nghĩa là scheduler vẫn gửi được cho account đã tắt"
    )
    assert rig.registry.get_running(CLINIC, CA_NHAN) is None
    assert CA_NHAN in rig.bridge.stopped, "và bridge cũng phải đóng listener"


async def test_so_account_dang_chay_account_bi_tat_giua_luc_khoi_dong_khong_vao_so_va_listener_da_dung(
    rig: Rig,
) -> None:
    """account bị TẮT giữa lúc khởi động: không vào sổ VÀ listener đã dừng"""
    # `bridge.start_account` mất một vòng mạng (đăng nhập Zalo), đủ rộng để người vận hành bấm TẮT trong lúc chờ.
    await rig.seed_credential()
    rig.bridge.before_start_returns = lambda: rig.accounts.accounts.__setitem__(
        (CLINIC, CA_NHAN), rig.accounts.accounts[(CLINIC, CA_NHAN)].model_copy(update={"enabled": False})
    )

    await rig.manager.start_account(CLINIC, CA_NHAN)

    assert rig.manager.get_running_account_kenh(CLINIC, CA_NHAN) is None, (
        "account đã tắt mà vẫn có kênh trong sổ"
    )
    assert rig.manager.is_account_running(CLINIC, CA_NHAN) is False
    assert CA_NHAN in rig.bridge.stopped, "listener phải DỪNG THẬT, không chỉ vắng mặt trong sổ"


async def test_start_account_chua_quet_qr_thi_khong_chay_gi_ca_kenh_ngu_cho_toi_khi_co_credential(
    rig: Rig,
) -> None:
    """(mới) không có credential đã lưu -> không khởi động, bridge không bị gọi: chỉ quét QR mới tạo credential"""
    with pytest.raises(DomainError) as info:
        await rig.manager.start_account(CLINIC, CA_NHAN)

    assert info.value.code is ErrorCode.INVALID_STATE
    assert rig.bridge.started == []
    assert rig.manager.is_account_running(CLINIC, CA_NHAN) is False


async def test_start_account_co_credential_thi_dua_cho_bridge_va_vao_so(rig: Rig) -> None:
    """(mới) credential đã giải mã được giao cho bridge trong lần start, kèm trạng thái kill switch"""
    await rig.seed_credential()
    await rig.manager.start_account(CLINIC, CA_NHAN)

    (account_id, clinic_ref, credential, kill) = rig.bridge.started[0]
    assert account_id == CA_NHAN
    assert clinic_ref == str(CLINIC), "webhook path nhận id phòng khám khi worker không biết slug"
    assert credential["imei"] == "imei-1"
    assert kill.on is False
    assert rig.manager.is_account_running(CLINIC, CA_NHAN)


async def test_start_account_cong_tac_phong_kham_tat_hoac_co_tat_thi_khong_khoi_dong() -> None:
    """(mới) cờ tiến trình và công tắc phòng khám đều phải bật"""
    off_flag = Rig(flag=False)
    await off_flag.seed_credential()
    with pytest.raises(DomainError) as flag_error:
        await off_flag.manager.start_account(CLINIC, CA_NHAN)
    assert flag_error.value.code is ErrorCode.CHANNEL_UNAVAILABLE

    off_switch = Rig(enabled=False)
    await off_switch.seed_credential()
    with pytest.raises(DomainError) as switch_error:
        await off_switch.manager.start_account(CLINIC, CA_NHAN)
    assert switch_error.value.code is ErrorCode.CHANNEL_UNAVAILABLE
    assert off_flag.bridge.started == off_switch.bridge.started == []


async def test_start_account_bridge_da_chay_san_thi_gan_vao_khong_dang_nhap_lai(rig: Rig) -> None:
    """(mới) mỗi lần đăng nhập Zalo là một rủi ro bị khóa: bridge đã `connected` thì chỉ attach"""
    await rig.seed_credential()
    rig.bridge.states[CA_NHAN] = "connected"

    await rig.manager.start_account(CLINIC, CA_NHAN)

    assert rig.bridge.started == [], "không được gọi start lần nữa"
    assert rig.manager.is_account_running(CLINIC, CA_NHAN)
    assert rig.bridge.kill_switch is not None
    assert rig.bridge.kill_switch.on is False, "nhưng vẫn đồng bộ kill switch"


async def test_start_account_kill_switch_dang_bat_duoc_day_xuong_bridge_cung_lan_start() -> None:
    """(mới) kill switch đang bật được truyền vào bridge ngay trong lần start"""
    rig = Rig()
    rig.reader.settings = ChannelSettings(
        channel=ChannelKind.ZALO_PERSONAL,
        enabled=True,
        kill_switch_on=True,
        kill_switch_reason="bridge_blocked",
        version=2,
    )
    await rig.seed_credential()
    await rig.manager.start_account(CLINIC, CA_NHAN)

    assert rig.bridge.started[0][3].on is True


async def test_start_account_bridge_loi_thi_bao_kenh_khong_kha_dung(rig: Rig) -> None:
    """(mới) bridge hỏng khi start -> DomainError channel_unavailable, không vào sổ"""
    await rig.seed_credential()
    rig.bridge.fail_start = ZaloBridgeError("transport", "down")

    with pytest.raises(DomainError) as info:
        await rig.manager.start_account(CLINIC, CA_NHAN)

    assert info.value.code is ErrorCode.CHANNEL_UNAVAILABLE
    assert rig.manager.is_account_running(CLINIC, CA_NHAN) is False


async def test_attach_account_la_la_chan_cuoi_khong_gan_tai_khoan_bot() -> None:
    """lá chắn cuối: `attach_account` chỉ đúng với kênh cá nhân"""
    rig = Rig()
    bot = fake_account_config(id="bot-1", channel=ChannelKind.ZALO_BOT)
    with pytest.raises(DomainError):
        await rig.manager.attach_account(CLINIC, bot, "x")


async def test_start_all_accounts_co_tat_thi_khong_khoi_dong_account_nao() -> None:
    """(mới) cờ tắt -> start_all không chạm bridge"""
    rig = Rig(flag=False)
    await rig.seed_credential()
    await rig.manager.start_all_accounts()
    assert rig.bridge.started == []
    assert rig.bridge.stop_all_calls == 0


async def test_start_all_accounts_loi_mot_account_khong_chan_account_khac() -> None:
    """không account nào chạy vẫn KHÔNG chết (bỏ qua và ghi log)"""
    rig = Rig()  # no credential: start fails, start_all must swallow it
    await rig.manager.start_all_accounts()
    assert rig.manager.get_running_accounts() == []


async def test_stop_all_accounts_dong_het_va_goi_stop_all_cua_bridge(rig: Rig) -> None:
    """(mới) dừng khẩn cấp: sổ trống và bridge nhận stop-all"""
    config = await rig.accounts.get_account(CLINIC, CA_NHAN)
    assert config is not None
    await rig.manager.attach_account(CLINIC, config, "self-1")

    await rig.manager.stop_all_accounts()

    assert rig.manager.get_running_accounts() == []
    assert rig.bridge.stop_all_calls == 1


async def test_the_gate_of_an_attached_account_uses_the_counter_of_its_clinic(rig: Rig) -> None:
    """cổng gửi chủ động của account dùng bộ đếm của ĐÚNG phòng khám (Postgres), không phải bộ đếm trong RAM"""
    from pema.channels.zalo_personal.proactive_gate import InMemoryProactiveCounter

    asked: list[UUID] = []
    shared = InMemoryProactiveCounter()

    def counter_for(clinic_id: UUID) -> InMemoryProactiveCounter:
        asked.append(clinic_id)
        return shared

    manager = AccountManager(
        accounts=rig.accounts,
        vault=rig.vault,
        bridge=rig.bridge,
        registry=rig.registry,
        policy_reader=rig.reader,
        flag_enabled=lambda: True,
        bridge_secret=lambda: "secret-0123456789abcdef",
        counter_for=counter_for,
    )
    config = await rig.accounts.get_account(CLINIC, CA_NHAN)
    assert config is not None
    await manager.attach_account(CLINIC, config, "self-1")
    kenh = manager.get_running_account_kenh(CLINIC, CA_NHAN)
    assert kenh is not None
    assert asked == [CLINIC]
    assert kenh.gate._counter is shared  # pyright: ignore[reportPrivateUsage]

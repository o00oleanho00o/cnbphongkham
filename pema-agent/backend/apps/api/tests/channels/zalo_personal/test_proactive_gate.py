"""Clinic safety gate in front of every proactive message (new module): flag, clinic switch, kill switch, send
window, friend, atomic daily cap with refund, random gap. Everything is decided by a rejected ``SendResult``."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta

import pytest

from pema.channels.zalo_personal.bridge_client import ZaloBridgeError
from pema.channels.zalo_personal.channel_settings import ChannelSettings
from pema.channels.zalo_personal.kenh_ca_nhan import ZaloPersonalChannel
from pema.channels.zalo_personal.proactive_gate import InMemoryProactiveCounter, is_within_window
from pema.channels.zalo_personal.testing import FakeZaloApi, StaticPolicyReader, make_personal_channel
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.channel import ChannelKind, SendResult, SendStatus, ThreadKind
from pema_contracts.errors import ErrorCode

# 2026-09-20 03:00 UTC = 10:00 in Asia/Ho_Chi_Minh
NOW = datetime(2026, 9, 20, 3, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    reset_tuning_provider()
    yield
    reset_tuning_provider()


def settings(**fields: object) -> ChannelSettings:
    base: dict[str, object] = {"channel": ChannelKind.ZALO_PERSONAL, "enabled": True, "version": 1}
    return ChannelSettings(**{**base, **fields})  # type: ignore[arg-type]


def channel_with(
    api: FakeZaloApi | None = None, reader: StaticPolicyReader | None = None, **kwargs: object
) -> tuple[ZaloPersonalChannel, FakeZaloApi, StaticPolicyReader]:
    api = api or FakeZaloApi()
    reader = reader or StaticPolicyReader(settings(requires_friend=False))
    return make_personal_channel(api, reader=reader, now=lambda: NOW, **kwargs), api, reader  # type: ignore[arg-type]


async def proactive(channel: ZaloPersonalChannel, thread: str = "t1") -> SendResult:
    return await channel.send_text(thread, "nhắc lịch hẹn", proactive=True)


async def test_tin_tra_loi_khong_proactive_khong_bi_gate_chan_ke_ca_khi_kill_switch_bat() -> None:
    """kill switch chỉ chặn tin CHỦ ĐỘNG; trả lời một tin vừa tới thì không"""
    channel, api, reader = channel_with()
    reader.settings = settings(kill_switch_on=True)

    result = await channel.send_text("t1", "trả lời", proactive=False)

    assert result.status is SendStatus.SENT
    assert api.sent[0].proactive is False


async def test_co_tien_trinh_tat_thi_moi_tin_chu_dong_bi_tu_choi_channel_unavailable() -> None:
    channel, api, _ = channel_with(flag=False)
    result = await proactive(channel)
    assert (result.status, result.error_code) == (SendStatus.REJECTED, ErrorCode.CHANNEL_UNAVAILABLE)
    assert api.sent == []


async def test_cong_tac_phong_kham_tat_thi_tin_chu_dong_bi_tu_choi() -> None:
    channel, api, reader = channel_with()
    reader.settings = settings(enabled=False)
    result = await proactive(channel)
    assert result.error_code is ErrorCode.CHANNEL_UNAVAILABLE
    assert api.sent == []


async def test_kill_switch_co_hieu_luc_ngay_o_tin_ke_tiep_khong_cache() -> None:
    """đọc lại hàng cấu hình ở MỌI lần gửi: bật kill switch ở UI là tin kế tiếp bị chặn"""
    channel, api, reader = channel_with()
    first = await proactive(channel)
    reader.settings = settings(kill_switch_on=True, kill_switch_reason="emergency")
    second = await proactive(channel)
    reader.settings = settings(kill_switch_on=False)
    third = await proactive(channel, "t2")

    assert first.status is SendStatus.SENT
    assert (second.status, second.error_code) == (SendStatus.REJECTED, ErrorCode.CHANNEL_KILL_SWITCH_ON)
    assert third.status is SendStatus.SENT
    assert len(api.sent) == 2
    assert reader.reads >= 3


async def test_ngoai_cua_so_gui_thi_tin_chu_dong_bi_tu_choi() -> None:
    channel, api, reader = channel_with()
    reader.settings = settings(
        send_window_start=time(13, 0), send_window_end=time(17, 0)
    )  # now = 10:00 local
    result = await proactive(channel)
    assert result.error_code is ErrorCode.CHANNEL_OUTSIDE_SEND_WINDOW
    assert api.sent == []


def test_cua_so_gui_co_the_van_qua_nua_dem() -> None:
    assert is_within_window(time(23, 0), time(22, 0), time(6, 0))
    assert is_within_window(time(5, 59), time(22, 0), time(6, 0))
    assert not is_within_window(time(12, 0), time(22, 0), time(6, 0))
    assert is_within_window(time(12, 0), None, None)
    assert not is_within_window(time(17, 0), time(8, 0), time(17, 0)), "cuối cửa sổ là mở nửa khoảng"


async def test_nguoi_nhan_khong_phai_ban_be_thi_tin_chu_dong_bi_tu_choi() -> None:
    api = FakeZaloApi(friends=[{"userId": "friend-1"}])
    channel, _, reader = channel_with(api)
    reader.settings = settings(requires_friend=True)

    stranger = await proactive(channel, "stranger-1")
    friend = await proactive(channel, "friend-1")

    assert stranger.error_code is ErrorCode.CHANNEL_RECIPIENT_NOT_REACHABLE
    assert friend.status is SendStatus.SENT


async def test_nhom_khong_can_kiem_tra_ban_be() -> None:
    channel, api, reader = channel_with()
    reader.settings = settings(requires_friend=True)
    result = await channel.send_text("group-1", "thông báo", thread_kind=ThreadKind.GROUP, proactive=True)
    assert result.status is SendStatus.SENT
    assert api.sent[0].thread_id == "group-1"


async def test_khong_lay_duoc_danh_sach_ban_be_thi_tu_choi_fail_closed() -> None:
    class BrokenFriends(FakeZaloApi):
        async def get_all_friends(self):  # type: ignore[no-untyped-def, override]
            raise ZaloBridgeError("transport", "down")

    channel, _, reader = channel_with(BrokenFriends())
    reader.settings = settings(requires_friend=True)
    result = await proactive(channel, "u1")
    assert result.error_code is ErrorCode.CHANNEL_RECIPIENT_NOT_REACHABLE


async def test_tran_tin_chu_dong_moi_ngay_mac_dinh_la_scheduler_max_proactive_per_day_10() -> None:
    channel, api, _ = channel_with()
    results = [await proactive(channel) for _ in range(12)]

    assert [r.status for r in results].count(SendStatus.SENT) == 10
    assert results[10].error_code is ErrorCode.CHANNEL_DAILY_CAP_REACHED
    assert len(api.sent) == 10


async def test_tran_cau_hinh_duoc_theo_kenh_va_theo_tuning() -> None:
    channel, api, reader = channel_with()
    reader.settings = settings(daily_cap=2)
    for _ in range(3):
        await proactive(channel)
    assert len(api.sent) == 2, "daily_cap của kênh thắng"

    install_tuning_provider(StaticTuningProvider({"SCHEDULER_MAX_PROACTIVE_PER_DAY": 3}))
    channel2, api2, _ = channel_with()
    for _ in range(5):
        await proactive(channel2)
    assert len(api2.sent) == 3, "không có daily_cap thì theo SCHEDULER_MAX_PROACTIVE_PER_DAY"


async def test_tran_dem_rieng_tung_cuoc_tro_chuyen_va_tung_ngay() -> None:
    counter = InMemoryProactiveCounter()
    clock = {"now": NOW}
    api = FakeZaloApi()
    channel = make_personal_channel(
        api,
        reader=StaticPolicyReader(settings(daily_cap=1, requires_friend=False)),
        counter=counter,
        now=lambda: clock["now"],
    )

    assert (await proactive(channel, "a")).status is SendStatus.SENT
    assert (await proactive(channel, "a")).status is SendStatus.REJECTED
    assert (await proactive(channel, "b")).status is SendStatus.SENT, "thread khác có suất riêng"
    clock["now"] = NOW + timedelta(days=1)
    assert (await proactive(channel, "a")).status is SendStatus.SENT, "sang ngày mới thì đếm lại"


async def test_gui_hong_thi_hoan_lai_suat_khong_dot_tran_vi_tin_khong_di() -> None:
    api = FakeZaloApi()
    api.fail_send_with = [ZaloBridgeError("transport", "down")]
    channel, _, reader = channel_with(api)
    reader.settings = settings(daily_cap=1, requires_friend=False)

    with pytest.raises(ZaloBridgeError):
        await proactive(channel)
    retry = await proactive(channel)

    assert retry.status is SendStatus.SENT, "suất đã được hoàn lại"


async def test_bridge_tu_choi_vi_kill_switch_hoac_bi_khoa_la_ket_qua_bi_tu_choi_va_hoan_suat() -> None:
    api = FakeZaloApi()
    api.fail_send_with = [ZaloBridgeError("kill_switch", "x"), ZaloBridgeError("blocked", "x")]
    channel, _, reader = channel_with(api)
    reader.settings = settings(daily_cap=1, requires_friend=False)

    killed = await proactive(channel)
    blocked = await proactive(channel)
    ok = await proactive(channel)

    assert killed.error_code is ErrorCode.CHANNEL_KILL_SWITCH_ON
    assert blocked.error_code is ErrorCode.CHANNEL_UNAVAILABLE
    assert ok.status is SendStatus.SENT


async def test_may_chu_zalo_tu_choi_thi_nem_loi_de_pipeline_thu_lai_khong_style() -> None:
    api = FakeZaloApi()
    api.fail_send_with = [ZaloBridgeError("zalo_rejected", "x", code=112)]
    channel, _, _ = channel_with(api)
    with pytest.raises(ZaloBridgeError) as info:
        await proactive(channel)
    assert info.value.code == 112


async def test_khoang_nghi_ngau_nhien_giua_hai_tin_chu_dong() -> None:
    slept: list[float] = []
    clock = {"now": NOW}

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)
        clock["now"] += timedelta(seconds=seconds)

    channel = make_personal_channel(
        FakeZaloApi(),
        reader=StaticPolicyReader(settings(min_gap_seconds=10, max_gap_seconds=20, requires_friend=False)),
        now=lambda: clock["now"],
        sleep=fake_sleep,
        uniform=lambda low, high: high,
    )

    await proactive(channel, "a")
    clock["now"] += timedelta(seconds=5)
    await proactive(channel, "b")

    assert slept == [15.0], "đợi nốt phần còn thiếu để đủ 20 giây kể từ tin trước"
    await asyncio.sleep(0)

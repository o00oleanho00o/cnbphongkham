# ported from: src/zalo/busy-wait-notice.test.ts
"""Reassurance sentence when the bot has been busy for too long.

The invariant that matters most is not "can it send" but "does NOT send when not yet worth it": the sender
already has three signals (typing, seen, reaction), so sending early is noise and one wasted call to an
unofficial API.

The send path is injected (``send_in_parts``): the real ``send_reply_in_parts`` is package C2's. Here it is
built from the SAME pieces the wiring uses (``reply_target_tu_kenh`` over a ``ChannelPort``), with a
``FakeChannel`` underneath.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from pema.channels.busy_wait_notice import CAU_TRAN_AN, maybe_notify_busy_wait
from pema.channels.reply_target_tu_kenh import DoanCanGui, ReplyTarget, reply_target_tu_kenh
from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.middleware import rate_limiter
from pema.middleware.thread_run_chain import InProcessThreadRunChain
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema_contracts.channel import ChannelCapabilities, ChannelKind, ThreadKind
from pema_contracts.testing import FakeChannel


@dataclass
class Outcome:
    sent_parts: int


def make_channel() -> FakeChannel:
    return FakeChannel(caps=ChannelCapabilities(channel=ChannelKind.ZALO_BOT, can_send_proactive=True))


async def send_in_parts(target: ReplyTarget, text: str) -> Outcome:
    """The minimal send path: one part through the per-thread queue, like ``send_reply_in_parts`` does."""
    await rate_limiter.enqueue_send(target.thread_key, lambda: target.gui_mot_doan(DoanCanGui(text)))
    return Outcome(sent_parts=1)


def muc(channel: FakeChannel, thread_key: str) -> ReplyTarget:
    return reply_target_tu_kenh(
        kenh=channel, thread_id=thread_key, thread_kind=ThreadKind.USER, thread_key=thread_key
    )


def set_threshold(ms: int) -> None:
    install_tuning_provider(
        StaticTuningProvider({"BUSY_ACK_AFTER_MS": ms, "SEND_DELAY_MIN_MS": 0, "SEND_DELAY_MAX_MS": 0})
    )


def chiem_thread(chain: InProcessThreadRunChain, thread_key: str) -> Callable[[], None]:
    release = asyncio.Event()

    async def blocked() -> None:
        await release.wait()

    chain.run_on_thread_chain(thread_key, blocked)
    return release.set


async def sleep(ms: int) -> None:
    await asyncio.sleep(ms / 1000)


async def test_khong_gui_khi_thread_dang_ranh_khong_co_ai_de_ma_tran_an() -> None:
    """KHÔNG gửi khi thread đang rảnh - không có ai để mà trấn an"""
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(10)
    assert (
        await maybe_notify_busy_wait(muc(channel, "k-ranh"), busy=chain, send_in_parts=send_in_parts) is False
    )
    assert channel.sent == []


async def test_khong_gui_khi_ban_chua_du_lau_luc_nay_dau_nhap_da_noi_thay_roi() -> None:
    """KHÔNG gửi khi bận CHƯA đủ lâu - lúc này dấu 'đang nhập' đã nói thay rồi"""
    # The invariant that keeps the feature from becoming annoying.
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(5_000)
    nha = chiem_thread(chain, "k-chua-lau")
    await sleep(20)

    assert (
        await maybe_notify_busy_wait(muc(channel, "k-chua-lau"), busy=chain, send_in_parts=send_in_parts)
        is False
    )
    assert channel.sent == []
    nha()
    await sleep(10)


async def test_gui_khi_da_ban_qua_nguong() -> None:
    """gửi khi đã bận QUÁ ngưỡng"""
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(20)
    nha = chiem_thread(chain, "k-lau")

    async def busy_long_enough() -> bool:
        return (await chain.busy_for_ms("k-lau") or 0) >= 20

    await doi_cho_den_khi(busy_long_enough, WaitOptions(mo_ta="thread k-lau bận đủ 20ms"))

    assert (
        await maybe_notify_busy_wait(muc(channel, "k-lau"), busy=chain, send_in_parts=send_in_parts) is True
    )
    assert [p.text for p in channel.sent] == [CAU_TRAN_AN]
    nha()
    await sleep(10)


async def test_khong_nhac_lai_trong_cung_quang_cho_noi_hai_lan_chi_lam_nguoi_ta_sot_ruot_them() -> None:
    """không nhắc lại trong cùng quãng chờ - nói hai lần chỉ làm người ta sốt ruột thêm"""
    # The threshold is ALSO the quiet period, so it must be wider than the time one call takes.
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(200)
    nha = chiem_thread(chain, "k-nhac-lai")

    async def busy_long_enough() -> bool:
        return (await chain.busy_for_ms("k-nhac-lai") or 0) >= 200

    await doi_cho_den_khi(busy_long_enough, WaitOptions(mo_ta="thread k-nhac-lai bận đủ 200ms"))

    for _ in range(3):
        await maybe_notify_busy_wait(muc(channel, "k-nhac-lai"), busy=chain, send_in_parts=send_in_parts)

    assert len(channel.sent) == 1, f"mong đúng 1 câu, nhận {len(channel.sent)}"
    nha()
    await sleep(10)


async def test_im_khi_thread_dang_co_tin_di_ra_khong_chen_ngang_giua_cau_tra_loi_dang_cat_nhieu_doan() -> (
    None
):
    """IM khi thread đang có tin đi ra - không chen ngang giữa câu trả lời đang cắt nhiều đoạn"""
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(20)
    nha = chiem_thread(chain, "k-dang-gui")
    await sleep(60)

    # Keep the send queue busy with a send that is not finished.
    release_send = asyncio.Event()

    async def blocked_send() -> None:
        await release_send.wait()

    sending = rate_limiter.enqueue_send("k-dang-gui", blocked_send)
    await sleep(10)

    assert (
        await maybe_notify_busy_wait(muc(channel, "k-dang-gui"), busy=chain, send_in_parts=send_in_parts)
        is False
    ), "đang gửi dở thì phải im"
    assert channel.sent == []

    release_send.set()
    await sending
    nha()
    await sleep(30)


async def test_dat_0_la_tat_han_ke_ca_khi_da_ban_rat_lau() -> None:
    """đặt 0 là tắt hẳn - kể cả khi đã bận rất lâu"""
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(0)
    nha = chiem_thread(chain, "k-tat")
    await sleep(60)

    assert (
        await maybe_notify_busy_wait(muc(channel, "k-tat"), busy=chain, send_in_parts=send_in_parts) is False
    )
    assert channel.sent == []
    nha()
    await sleep(10)


async def test_dong_ho_cho_tinh_tu_luc_thread_bat_dau_ban_khong_dat_lai_theo_tung_luot() -> None:
    """đồng hồ chờ tính từ lúc thread BẮT ĐẦU bận, không đặt lại theo từng lượt"""
    # Runs that follow each other in one wait must not refresh the clock, or the longest wait would never
    # reach the threshold and would never be reassured.
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(40)
    nha1 = chiem_thread(chain, "k-noi-tiep")
    await sleep(30)
    nha2 = chiem_thread(chain, "k-noi-tiep")  # the second run joins the chain while the first still runs
    await sleep(30)

    assert (
        await maybe_notify_busy_wait(muc(channel, "k-noi-tiep"), busy=chain, send_in_parts=send_in_parts)
        is True
    ), "tổng thời gian chờ đã vượt ngưỡng nên phải trấn an"
    nha1()
    nha2()
    await sleep(20)


async def test_thread_ranh_tro_lai_thi_dong_ho_ve_moc_moi_quang_cho_sau_dem_lai_tu_dau() -> None:
    """thread rảnh trở lại thì đồng hồ về mốc mới - quãng chờ sau đếm lại từ đầu"""
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(30)
    nha = chiem_thread(chain, "k-doi-quang")
    await sleep(60)
    nha()
    await sleep(20)  # the lock is released

    assert await chain.busy_for_ms("k-doi-quang") is None, "rảnh rồi thì không còn mốc nào"

    nha2 = chiem_thread(chain, "k-doi-quang")
    await sleep(5)
    assert (
        await maybe_notify_busy_wait(muc(channel, "k-doi-quang"), busy=chain, send_in_parts=send_in_parts)
        is False
    ), "quãng chờ MỚI phải đếm lại từ đầu, không kế thừa thời gian của quãng trước"
    nha2()
    await sleep(10)


async def test_patient_channel_khong_tu_gui_cau_tran_an() -> None:
    """clinic: `allowed=False` (hồ sơ patient_channel) thì không gửi dù đã bận rất lâu"""
    chain = InProcessThreadRunChain()
    channel = make_channel()
    set_threshold(20)
    nha = chiem_thread(chain, "k-patient")
    await sleep(60)

    assert (
        await maybe_notify_busy_wait(
            muc(channel, "k-patient"), busy=chain, send_in_parts=send_in_parts, allowed=False
        )
        is False
    )
    assert channel.sent == []
    nha()
    await sleep(10)

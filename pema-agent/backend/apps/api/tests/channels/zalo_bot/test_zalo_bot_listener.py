# ported from: src/zalo-bot/zalo-bot-listener.test.ts
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from pema.channels.zalo_bot.testing import FakeBotClient, make_update
from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate
from pema.channels.zalo_bot.zalo_bot_listener import bat_dau_vong_poll

TIN = make_update("hi")


def ignore(_: str, __: ZaloBotUpdate) -> None:
    return None


def ngu_gia() -> tuple[list[float], Callable[[float], Awaitable[None]]]:
    """A fake sleep: records the retreat periods instead of waiting."""
    quang: list[float] = []

    async def ngu(ms: float) -> None:
        quang.append(ms)

    return quang, ngu


async def doi_vong_chay() -> None:
    await asyncio.sleep(0.02)


async def test_poll_rong_khong_phai_loi_khong_lui_poll_lai_ngay() -> None:
    """poll RỖNG không phải lỗi - không lùi, poll lại ngay"""
    # Silence is the permanent state. Treating 408 as an error makes the bot retreat to the ceiling and answer
    # slowly for minutes although the network is perfectly healthy.
    client = FakeBotClient(updates=[None, None, None])
    quang, ngu = ngu_gia()
    v = bat_dau_vong_poll(account_id="b1", client=client, on_update=ignore, ngu_ms=ngu)
    await doi_vong_chay()
    v.dung()
    client.release()
    assert quang == [], f"poll rỗng mà vẫn lùi: {quang}"
    assert client.polls >= 3


async def test_loi_thi_lui_va_lui_nhan_doi_qua_tung_lan_lien_tiep() -> None:
    """lỗi thì LÙI, và lùi NHÂN ĐÔI qua từng lần liên tiếp"""
    # Measured: hammering polls is answered 429 by nginx. Not retreating is running into the wall.
    client = FakeBotClient(updates=[RuntimeError("429")] * 3)
    quang, ngu = ngu_gia()
    v = bat_dau_vong_poll(
        account_id="b1",
        client=client,
        on_update=ignore,
        ngu_ms=ngu,
        lui_ban_dau_ms=100,
        lui_toi_da_ms=1000,
    )
    await doi_vong_chay()
    v.dung()
    client.release()
    assert quang[:3] == [100, 200, 400]


async def test_lui_co_tran_khong_tang_vo_han() -> None:
    """lùi có TRẦN, không tăng vô hạn"""
    client = FakeBotClient(updates=[RuntimeError("x")] * 8)
    quang, ngu = ngu_gia()
    v = bat_dau_vong_poll(
        account_id="b1",
        client=client,
        on_update=ignore,
        ngu_ms=ngu,
        lui_ban_dau_ms=100,
        lui_toi_da_ms=300,
    )
    await doi_vong_chay()
    v.dung()
    client.release()
    assert max(quang) <= 300, f"vượt trần: {quang}"


async def test_poll_thanh_cong_dat_lai_muc_lui() -> None:
    """poll thành công ĐẶT LẠI mức lùi"""
    # Without it a passing network blip leaves the bot retreating at the maximum FOREVER: a silent failure
    # that only shows as a bot that gets slower and slower.
    client = FakeBotClient(updates=[RuntimeError("x"), RuntimeError("x"), None, RuntimeError("x")])
    quang, ngu = ngu_gia()
    v = bat_dau_vong_poll(
        account_id="b1",
        client=client,
        on_update=ignore,
        ngu_ms=ngu,
        lui_ban_dau_ms=100,
        lui_toi_da_ms=1000,
    )
    await doi_vong_chay()
    v.dung()
    client.release()
    assert quang == [100, 200, 100], f"không đặt lại sau lần poll thành công: {quang}"


async def test_on_update_nem_thi_vong_van_chay_tiep_va_khong_bi_tinh_la_loi_mang() -> None:
    """onUpdate NÉM thì vòng vẫn chạy tiếp và KHÔNG bị tính là lỗi mạng"""
    # A locked DB or a full disk makes ``on_update`` raise. Letting it fall into the network branch would make
    # the bot retreat 60 seconds for a completely different cause.
    client = FakeBotClient(updates=[TIN, TIN, TIN])
    quang, ngu = ngu_gia()

    def boom(_: str, __: ZaloBotUpdate) -> None:
        raise RuntimeError("DB khoá")

    v = bat_dau_vong_poll(account_id="b1", client=client, on_update=boom, ngu_ms=ngu)
    await doi_vong_chay()
    v.dung()
    client.release()
    assert quang == [], f"onUpdate ném mà vòng lại lùi: {quang}"
    assert client.polls >= 3, f"vòng dừng sau khi onUpdate ném (mới poll {client.polls} lần)"


async def test_co_tin_thi_poll_lai_ngay_get_updates_chi_tra_mot_update_moi_lan() -> None:
    """có tin thì poll lại NGAY - getUpdates chỉ trả một update mỗi lần"""
    client = FakeBotClient(updates=[TIN, TIN, TIN])
    received: list[ZaloBotUpdate] = []
    quang, ngu = ngu_gia()
    v = bat_dau_vong_poll(
        account_id="b1", client=client, on_update=lambda _, u: received.append(u), ngu_ms=ngu
    )
    await doi_vong_chay()
    v.dung()
    client.release()
    assert len(received) == 3, "không kéo hết tin đang chờ"
    assert quang == [], "nghỉ giữa các tin - sẽ tụt lại khi người ta nhắn liền mấy câu"


async def test_dung_giua_luc_poll_dang_bay_thi_bo_tin_do_khong_xu_ly() -> None:
    """dung() giữa lúc poll ĐANG BAY thì BỎ tin đó, không xử lý"""
    # The ``except`` branch had the ``stopped`` guard; the SUCCESS branch did not. The fake holds the call
    # until the test releases it: the shape of a call in flight when the operator switches the account off.
    gate: asyncio.Future[ZaloBotUpdate] = asyncio.get_running_loop().create_future()

    class InFlight:
        async def get_updates(self, timeout_giay: int = 30) -> ZaloBotUpdate | None:
            return await gate

    handled = 0

    def count(_: str, __: ZaloBotUpdate) -> None:
        nonlocal handled
        handled += 1

    async def no_sleep(ms: float) -> None:
        return None

    v = bat_dau_vong_poll(account_id="b1", client=InFlight(), on_update=count, ngu_ms=no_sleep)
    await doi_vong_chay()
    v.dung()
    gate.set_result(TIN)  # the message arrives AFTER the stop
    await doi_vong_chay()
    assert handled == 0, "đã tắt account mà vẫn xử lý thêm một tin"
    assert v.task.done()


async def test_on_update_async_nem_cung_bi_bat_khong_thanh_unhandled_rejection() -> None:
    """onUpdate ASYNC ném cũng bị bắt - không thành unhandled rejection"""
    client = FakeBotClient(updates=[TIN, TIN, TIN])
    quang, ngu = ngu_gia()
    loop = asyncio.get_running_loop()
    leaked: list[object] = []
    previous = loop.get_exception_handler()
    loop.set_exception_handler(lambda _loop, context: leaked.append(context))

    async def boom(_: str, __: ZaloBotUpdate) -> None:
        await asyncio.sleep(0)
        raise RuntimeError("router async hỏng")

    try:
        v = bat_dau_vong_poll(account_id="b1", client=client, on_update=boom, ngu_ms=ngu)
        await doi_vong_chay()
        v.dung()
        client.release()
        await doi_vong_chay()
        assert leaked == [], f"{len(leaked)} lỗi lọt ra ngoài"
        assert quang == [], "lỗi của onUpdate bị tính nhầm thành lỗi mạng"
        assert client.polls >= 2, "vòng dừng sau khi onUpdate async ném"
    finally:
        loop.set_exception_handler(previous)


async def test_dung_thi_vong_dung_khong_poll_them() -> None:
    """dung() thì vòng dừng, không poll thêm"""
    client = FakeBotClient(updates=[TIN] * 6)
    _, ngu = ngu_gia()
    v = bat_dau_vong_poll(account_id="b1", client=client, on_update=ignore, ngu_ms=ngu)
    await doi_vong_chay()
    v.dung()
    client.release()
    await doi_vong_chay()
    sau_khi_dung = client.polls
    await doi_vong_chay()
    assert client.polls == sau_khi_dung, "vẫn poll sau khi đã dừng"

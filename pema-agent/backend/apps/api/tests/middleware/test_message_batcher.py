# ported from: src/middleware/message-batcher.test.ts
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from pema.middleware.message_batcher import TRAN_TIN_DON, InMemoryPendingBatchStore, MessageBatcher
from pema.middleware.thread_run_chain import InProcessThreadRunChain
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi, doi_cho_so_luong
from pema_contracts.channel import InboundMessage
from pema_contracts.testing import make_inbound


@pytest.fixture
async def chain() -> InProcessThreadRunChain:
    return InProcessThreadRunChain()


@pytest.fixture
async def batcher(chain: InProcessThreadRunChain) -> AsyncIterator[MessageBatcher]:
    instance = MessageBatcher(InMemoryPendingBatchStore(), chain)
    yield instance
    await instance.clear_pending_batches()


async def sleep(ms: int) -> None:
    await asyncio.sleep(ms / 1000)


def make_message(text: str, sender_id: str = "user-1") -> InboundMessage:
    return make_inbound(
        text,
        account_id="acc-test",
        thread_id="thread-1",
        sender_id=sender_id,
        update_id=f"u-{text}-{sender_id}",
        msg_id=f"m-{text}",
        cli_msg_id=f"c-{text}",
    )


type Handler = Callable[[list[InboundMessage]], Awaitable[None]]


def collecting(batches: list[list[str]]) -> Handler:
    async def handler(batch: list[InboundMessage]) -> None:
        batches.append([m.text for m in batch])

    return handler


async def noop(batch: list[InboundMessage]) -> None:
    return None


async def is_clean(batcher: MessageBatcher) -> bool:
    return await batcher.active_thread_count() == 0


# ---------------------------------------------------------------------------------------------- message-batcher


async def test_gop_cac_tin_gan_nhau_cung_thread_thanh_1_luot(batcher: MessageBatcher) -> None:
    """gộp các tin gần nhau cùng thread thành 1 lượt"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    await batcher.enqueue_message("k-gop", make_message("a"), handler, 30)
    await batcher.enqueue_message("k-gop", make_message("b"), handler, 30)
    await batcher.enqueue_message("k-gop", make_message("c"), handler, 30)
    # Wait until the thing HAPPENS instead of guessing how many ms are enough.
    await doi_cho_so_luong(lambda: len(batches), 1, WaitOptions(mo_ta="số lượt đã chạy"))

    assert len(batches) == 1
    assert batches[0] == ["a", "b", "c"]


async def test_thread_khac_nhau_khong_bi_gop_lan_vao_nhau(batcher: MessageBatcher) -> None:
    """thread khác nhau không bị gộp lẫn vào nhau"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    await batcher.enqueue_message("k-t1", make_message("x"), handler, 30)
    await batcher.enqueue_message("k-t2", make_message("y"), handler, 30)
    await doi_cho_so_luong(lambda: len(batches), 2, WaitOptions(mo_ta="số lượt đã chạy"))

    assert len(batches) == 2
    assert [len(b) for b in batches] == [1, 1]


async def test_tin_moi_den_trong_luc_cho_se_reset_dong_ho_debounce(batcher: MessageBatcher) -> None:
    """tin mới đến trong lúc chờ sẽ reset đồng hồ debounce"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    await batcher.enqueue_message("k-reset", make_message("a"), handler, 60)
    await sleep(40)
    await batcher.enqueue_message("k-reset", make_message("b"), handler, 60)

    # Mark 70 ms: without the reset the first turn would already have run at the 60 ms mark.
    await sleep(30)
    assert len(batches) == 0

    await doi_cho_so_luong(lambda: len(batches), 1, WaitOptions(mo_ta="lượt gộp sau khi reset debounce"))
    assert len(batches) == 1
    assert len(batches[0]) == 2


async def test_cac_luot_cung_thread_chay_tuan_tu_khong_chong_lan(batcher: MessageBatcher) -> None:
    """các lượt cùng thread chạy tuần tự, không chồng lấn"""
    events: list[str] = []
    release_first = asyncio.Event()

    async def handler(batch: list[InboundMessage]) -> None:
        tag = batch[0].text
        events.append(f"start:{tag}")
        if tag == "A":
            await release_first.wait()
        events.append(f"end:{tag}")

    await batcher.enqueue_message("k-tuantu", make_message("A"), handler, 20)
    await sleep(60)
    assert events == ["start:A"], "lượt A phải đã chạy và đang bị chặn"

    await batcher.enqueue_message("k-tuantu", make_message("B"), handler, 20)
    await sleep(60)
    assert events == ["start:A"], "lượt B phải xếp hàng, không chạy chồng lên A"

    release_first.set()
    await sleep(60)
    assert events == ["start:A", "end:A", "start:B", "end:B"]


async def test_thread_chay_xong_thi_bo_khoi_map_khong_ro_ri_theo_so_thread_tung_nhan(
    batcher: MessageBatcher,
) -> None:
    """thread chạy xong thì bỏ khỏi Map - không rò rỉ theo số thread từng nhắn"""
    for i in range(20):
        await batcher.enqueue_message(f"k-ro-ri-{i}", make_message(f"t{i}"), noop, 10)
    assert await batcher.active_thread_count() >= 20, "đang chờ thì phải có mặt trong Map"

    await doi_cho_den_khi(lambda: is_clean(batcher), WaitOptions(mo_ta="chạy xong phải dọn sạch"))


async def test_clear_pending_batches_huy_tin_dang_cho_handler_khong_chay(batcher: MessageBatcher) -> None:
    """clearPendingBatches hủy tin đang chờ, handler không chạy"""
    called = False

    async def handler(batch: list[InboundMessage]) -> None:
        nonlocal called
        called = True

    await batcher.enqueue_message("k-huy", make_message("z"), handler, 30)

    await batcher.clear_pending_batches()
    await sleep(90)  # a negative assertion: waiting on "it happened" would prove nothing

    assert called is False


# --------------------------------------------------------------------- tin đến trong lúc thread đang bận
# This group locks condition (b): a batch closes only when NO turn is running on the thread. It is the cure
# for the real case of 2026-08-04: a document turn that ran 249 s, two messages sent meanwhile became two
# agent turns and each redid the whole job from scratch.


def chiem_thread(
    chain: InProcessThreadRunChain, thread_key: str, events: list[str] | None = None
) -> Callable[[], None]:
    """Build a long run that holds the thread; returns the function that releases it."""
    release = asyncio.Event()

    async def long_turn() -> None:
        if events is not None:
            events.append("start:lượt-dài")
        await release.wait()
        if events is not None:
            events.append("end:lượt-dài")

    chain.run_on_thread_chain(thread_key, long_turn)
    return release.set


async def test_nhieu_cum_tin_roi_rac_trong_luc_ban_gop_thanh_dung_mot_luot(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """nhiều cụm tin rời rạc trong lúc bận GỘP thành ĐÚNG MỘT lượt"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    nha = chiem_thread(chain, "k-ban-gop")
    await sleep(20)

    await batcher.enqueue_message("k-ban-gop", make_message("a"), handler, 25)
    await sleep(60)  # past the merge window: the old path would already have closed a turn for "a" alone
    await batcher.enqueue_message("k-ban-gop", make_message("b"), handler, 25)
    await sleep(60)
    await batcher.enqueue_message("k-ban-gop", make_message("c"), handler, 25)
    await sleep(60)

    assert len(batches) == 0, "không lượt nào được chạy khi thread còn bận"

    nha()
    await doi_cho_so_luong(lambda: len(batches), 1, WaitOptions(mo_ta="lượt chạy sau khi thread rảnh"))

    assert len(batches) == 1, f"mong ĐÚNG 1 lượt, nhận {len(batches)}"
    assert batches[0] == ["a", "b", "c"]


async def test_van_cho_im_lang_du_debounce_sau_khi_thread_ranh_khong_cuop_co_giua_cum_tin(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """vẫn chờ im lặng đủ debounce SAU KHI thread rảnh - không cướp cò giữa cụm tin"""
    events: list[str] = []
    batches: list[list[str]] = []
    handler = collecting(batches)

    nha = chiem_thread(chain, "k-ban-cho-them", events)
    await doi_cho_den_khi(lambda: "start:lượt-dài" in events, WaitOptions(mo_ta="lượt dài chiếm thread"))

    # ``enqueue_message`` puts "a" in the queue before it returns.
    await batcher.enqueue_message("k-ban-cho-them", make_message("a"), handler, 60)
    nha()  # the thread becomes free while the merge window is still running
    await doi_cho_den_khi(lambda: "end:lượt-dài" in events, WaitOptions(mo_ta="lượt dài nhả thread"))
    await batcher.enqueue_message("k-ban-cho-them", make_message("b"), handler, 60)

    # A NEGATIVE assertion ("must not run yet") so it keeps a sleep.
    await sleep(30)
    assert len(batches) == 0, "còn trong cửa sổ gộp thì chưa được chạy"

    await doi_cho_so_luong(lambda: len(batches), 1, WaitOptions(mo_ta="lượt gộp sau khi thread rảnh"))
    assert len(batches) == 1
    assert batches[0] == ["a", "b"], "tin b phải kịp vào cùng lượt với a"


async def test_cham_tran_thi_bo_tin_moi_phan_da_don_van_chay_tron(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """chạm trần thì BỎ tin mới, phần đã dồn vẫn chạy trọn"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    nha = chiem_thread(chain, "k-ban-tran")
    await sleep(20)

    for i in range(TRAN_TIN_DON + 5):
        await batcher.enqueue_message("k-ban-tran", make_message(f"t{i}"), handler, 25)
    await sleep(60)
    nha()
    await doi_cho_so_luong(lambda: len(batches), 1, WaitOptions(mo_ta="lượt chạy sau khi thread rảnh"))

    assert len(batches) == 1
    assert len(batches[0]) == TRAN_TIN_DON, "phải dừng đúng ở trần, không phình theo số tin gửi"
    # Drop the NEW messages, not push old ones out: the old ones were sent first and the turn answers in
    # order.
    assert batches[0][0] == "t0"


async def test_bao_cho_caller_biet_tin_nao_bi_bo_khong_thi_tin_bien_mat_khoi_ca_history(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """báo cho caller biết tin nào BỊ BỎ - không thì tin biến mất khỏi cả history"""
    nha = chiem_thread(chain, "k-tra-ve")
    await sleep(20)

    results: list[bool] = []
    for i in range(TRAN_TIN_DON + 3):
        results.append(await batcher.enqueue_message("k-tra-ve", make_message(f"t{i}"), noop, 25))

    assert sum(results) == TRAN_TIN_DON, "đúng số tin lọt vào batch phải trả true"
    assert results[TRAN_TIN_DON:] == [False, False, False], "mọi tin sau khi chạm trần phải trả false"

    nha()
    await sleep(120)


async def test_job_lich_hen_chiem_thread_cung_gom_tin_y_het_luot_agent(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """job lịch hẹn chiếm thread cũng gom tin y hệt lượt agent"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    nha = chiem_thread(chain, "k-job-gom")
    await sleep(20)
    await batcher.enqueue_message("k-job-gom", make_message("hỏi-lúc-job-chạy"), handler, 25)
    await sleep(60)
    assert len(batches) == 0

    nha()
    await doi_cho_so_luong(lambda: len(batches), 1, WaitOptions(mo_ta="lượt sau khi job nhả thread"))
    assert batches == [["hỏi-lúc-job-chạy"]]


async def test_lay_tin_dang_do_lay_tin_da_do_va_xoa_khoi_hang_cho_khong_de_chay_them_luot_nua(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """layTinDangDo lấy tin đã đỗ và XÓA khỏi hàng chờ - không để chạy thêm lượt nữa"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    nha = chiem_thread(chain, "k-lay-tin-do")
    await sleep(20)
    await batcher.enqueue_message("k-lay-tin-do", make_message("chen-1"), handler, 25)
    await batcher.enqueue_message("k-lay-tin-do", make_message("chen-2"), handler, 25)
    await sleep(60)  # the merge window is over -> the batch is parked

    da_lay = await batcher.lay_tin_dang_do("k-lay-tin-do", "user-1")
    assert [m.text for m in da_lay] == ["chen-1", "chen-2"]

    nha()
    await doi_cho_den_khi(lambda: is_clean(batcher), WaitOptions(mo_ta="lấy xong phải dọn sạch hàng chờ"))
    await sleep(60)
    assert len(batches) == 0, "đã lấy rồi thì KHÔNG được chạy thêm lượt nào cho mấy tin đó"


async def test_lay_tin_dang_do_tra_rong_khi_cum_tin_con_dang_go_do_khong_cat_doi_giua_chung(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """layTinDangDo trả RỖNG khi cụm tin còn đang gõ dở - không cắt đôi giữa chừng"""
    nha = chiem_thread(chain, "k-lay-som")
    await sleep(20)
    await batcher.enqueue_message("k-lay-som", make_message("đang gõ dở"), noop, 200)
    await sleep(20)  # far from the end of the merge window

    assert await batcher.lay_tin_dang_do("k-lay-som", "user-1") == []

    await batcher.clear_pending_batches()
    nha()
    await sleep(30)


async def test_don_xong_chay_het_thi_map_sach_duong_moi_khong_ro_ri(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """dồn xong chạy hết thì Map sạch - đường mới không rò rỉ"""
    nha = chiem_thread(chain, "k-ban-ro-ri")
    await sleep(20)
    await batcher.enqueue_message("k-ban-ro-ri", make_message("x"), noop, 20)
    await sleep(50)
    nha()

    await doi_cho_den_khi(
        lambda: is_clean(batcher), WaitOptions(mo_ta="chạy xong phải dọn sạch cả pending lẫn chain")
    )


# ---------------------------------------------------------------------------------------- run_on_thread_chain


async def test_goi_truc_tiep_khong_qua_enqueue_message_van_xau_chuoi_dung_thread(
    chain: InProcessThreadRunChain,
) -> None:
    """gọi trực tiếp (không qua enqueueMessage) vẫn xâu chuỗi đúng thread - scheduler dùng lại y hệt tin nhắn"""
    events: list[str] = []
    release_first = asyncio.Event()

    async def run_a() -> None:
        events.append("start:A")
        await release_first.wait()
        events.append("end:A")

    async def run_b() -> None:
        events.append("start:B")

    task_a = chain.run_on_thread_chain("k-chain-tructiep", run_a)
    await sleep(20)
    assert events == ["start:A"], "A phải đã chạy và đang bị chặn"

    task_b = chain.run_on_thread_chain("k-chain-tructiep", run_b)
    await sleep(20)
    assert events == ["start:A"], "B phải xếp hàng, chưa được chạy khi A còn dở"

    release_first.set()
    await asyncio.gather(task_a, task_b)
    assert events == ["start:A", "end:A", "start:B"]


async def test_tin_nhan_va_job_goi_truc_tiep_tren_cung_thread_key_khong_chong_lan_nhau(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """tin nhắn (enqueueMessage) và job gọi trực tiếp runOnThreadChain trên CÙNG threadKey không chồng lấn
    nhau"""
    events: list[str] = []
    release_job = asyncio.Event()

    async def job() -> None:
        events.append("start:job")
        await release_job.wait()
        events.append("end:job")

    # The "scheduled" job takes the place first, like the scheduler dispatching through the chain.
    job_run = chain.run_on_thread_chain("k-tin-va-job", job)

    await sleep(20)

    async def message_turn(batch: list[InboundMessage]) -> None:
        events.append("start:tin")

    await batcher.enqueue_message("k-tin-va-job", make_message("tin-nguoi-dung"), message_turn, 10)

    await sleep(40)
    assert events == ["start:job"], "tin nhắn phải chờ job lịch hẹn xong, không đọc history nửa chừng"

    release_job.set()
    await job_run
    await doi_cho_den_khi(lambda: "start:tin" in events, WaitOptions(mo_ta="lượt tin chạy sau job"))
    assert events == ["start:job", "end:job", "start:tin"]


async def test_tra_ve_dung_promise_cua_fn_loi_ben_trong_fn_khong_bi_nuot_voi_caller_dang_await_truc_tiep(
    chain: InProcessThreadRunChain,
) -> None:
    """trả về đúng promise của fn - lỗi bên trong fn không bị nuốt mất với caller đang await trực tiếp"""

    async def fails() -> None:
        raise RuntimeError("job hỏng")

    with pytest.raises(RuntimeError, match="job hỏng"):
        await chain.run_on_thread_chain("k-chain-loi", fails)


async def test_khoa_nha_ca_khi_fn_nem_loi_thread_khong_bi_ket_ban(chain: InProcessThreadRunChain) -> None:
    """gắn ở CẢ hai nhánh của `then` nên `fn` ném lỗi cũng vẫn nhả khoá"""

    async def fails() -> None:
        raise RuntimeError("job hỏng")

    with pytest.raises(RuntimeError):
        await chain.run_on_thread_chain("k-nha-khoa", fails)
    assert await chain.is_busy("k-nha-khoa") is False
    assert await chain.busy_for_ms("k-nha-khoa") is None


# ------------------------------------------------------------------------------------------- huyBatchCuaThread
# Cancel the queue of a thread, used when that thread's context is wiped. Without it the parked batch would
# still run and write the old message back into the history that was just cleaned.


async def test_huy_tin_dang_cho_bi_huy_handler_khong_bao_gio_chay(batcher: MessageBatcher) -> None:
    """tin đang chờ bị hủy - handler KHÔNG bao giờ chạy"""
    ran = 0

    async def handler(batch: list[InboundMessage]) -> None:
        nonlocal ran
        ran += 1

    await batcher.enqueue_message("k-huy", make_message("a"), handler, 30)
    await batcher.enqueue_message("k-huy", make_message("b"), handler, 30)

    count = await batcher.huy_batch_cua_thread("k-huy")

    assert count == 2, "phải báo đúng số tin vừa hủy"
    await sleep(80)  # past the debounce: if the timer were alive the handler would have run
    assert ran == 0, "hủy rồi mà vẫn chạy là ghi lại tin vào lịch sử vừa xóa"


async def test_khong_dung_hang_cho_cua_thread_khac(batcher: MessageBatcher) -> None:
    """KHÔNG đụng hàng chờ của thread khác"""
    other_ran = 0

    async def handler(batch: list[InboundMessage]) -> None:
        nonlocal other_ran
        other_ran += 1

    await batcher.enqueue_message("k-huy-2", make_message("x"), noop, 30)
    await batcher.enqueue_message("k-con-lai", make_message("y"), handler, 30)

    await batcher.huy_batch_cua_thread("k-huy-2")

    await doi_cho_so_luong(lambda: other_ran, 1, WaitOptions(mo_ta="thread khác chạy bình thường"))
    assert other_ran == 1


async def test_thread_khong_co_gi_trong_hang_cho_thi_tra_0_khong_no(batcher: MessageBatcher) -> None:
    """thread không có gì trong hàng chờ thì trả 0, không nổ"""
    assert await batcher.huy_batch_cua_thread("k-khong-co-gi") == 0


async def test_huy_xong_thi_thread_do_khong_con_giu_cho_trong_bo_nho(batcher: MessageBatcher) -> None:
    """hủy xong thì thread đó không còn giữ chỗ trong bộ nhớ"""
    truoc = await batcher.active_thread_count()
    await batcher.enqueue_message("k-ro-ri", make_message("z"), noop, 5000)
    assert await batcher.active_thread_count() == truoc + 1

    await batcher.huy_batch_cua_thread("k-ro-ri")
    assert await batcher.active_thread_count() == truoc, "còn entry là còn giữ timer 5 giây"


async def test_huy_xong_khong_de_lai_timer_song_process_phai_thoat_duoc_ngay(batcher: MessageBatcher) -> None:
    """hủy xong KHÔNG để lại timer sống - process phải thoát được ngay"""
    # Dropping the entry from the map is enough to keep the handler from running, so measuring behaviour alone
    # would stay green if ``cancel`` were forgotten. A forgotten timer keeps the loop alive until it fires.
    truoc = batcher.timer_count()
    await batcher.enqueue_message("k-timer", make_message("t"), noop, 30_000)
    assert batcher.timer_count() == truoc + 1, "phải gieo được đúng một timer thì phép đo mới có nghĩa"

    await batcher.huy_batch_cua_thread("k-timer")
    assert batcher.timer_count() == truoc, "timer 30 giây bị bỏ quên là process không thoát được"


# ------------------------------------------------------------------------------------ gộp theo từng người gửi
# The merge queue is keyed by ``(thread, SENDER)``. Merging is for ONE person's messages (Zalo splits an image
# from its caption, people type a clarifying line). Merging by thread would make two people who @mention the
# bot in one beat share a turn and get ONE answer, with nobody knowing who it was for.


async def test_hai_nguoi_nhan_cung_nhip_hai_luot_rieng_moi_luot_mot_nguoi(batcher: MessageBatcher) -> None:
    """hai người nhắn cùng nhịp: HAI lượt riêng, mỗi lượt một người"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    await batcher.enqueue_message("k-hai-nguoi", make_message("Hải hỏi giá vàng", "u-hai"), handler, 20)
    await batcher.enqueue_message("k-hai-nguoi", make_message("Nam hỏi tỉ giá", "u-nam"), handler, 20)
    await doi_cho_so_luong(lambda: len(batches), 2, WaitOptions(mo_ta="hai lượt riêng"))

    assert len(batches) == 2, f"mong 2 lượt riêng, nhận {len(batches)}"
    assert sorted("|".join(b) for b in batches) == ["Hải hỏi giá vàng", "Nam hỏi tỉ giá"], (
        "không được trộn lời hai người vào một lượt"
    )


async def test_mot_nguoi_nhan_nhieu_tin_van_gop_lam_mot_dung_ly_do_bo_gop_ton_tai(
    batcher: MessageBatcher,
) -> None:
    """MỘT người nhắn nhiều tin vẫn gộp làm một - đúng lý do bộ gộp tồn tại"""
    batches: list[list[str]] = []
    handler = collecting(batches)

    await batcher.enqueue_message("k-mot-nguoi", make_message("[ảnh]", "u-hai"), handler, 30)
    await sleep(10)
    await batcher.enqueue_message("k-mot-nguoi", make_message("cái này là gì?", "u-hai"), handler, 30)
    await doi_cho_so_luong(lambda: len(batches), 1, WaitOptions(mo_ta="lượt gộp một người"))
    await sleep(60)

    assert batches == [["[ảnh]", "cái này là gì?"]]


async def test_ba_nguoi_nhan_luc_bot_ban_khi_ranh_chay_du_ba_luot_khong_bo_sot_ai(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """ba người nhắn lúc bot BẬN: khi rảnh chạy đủ ba lượt, không bỏ sót ai"""
    # The case most likely to break in the key change: the wake receives the THREAD key, and the queue is now
    # keyed by person; looking up one key would miss two people and they would never be answered.
    batches: list[list[str]] = []
    handler = collecting(batches)

    nha = chiem_thread(chain, "k-ba-nguoi")
    try:
        await sleep(20)
        for ai in ("u-a", "u-b", "u-c"):
            await batcher.enqueue_message("k-ba-nguoi", make_message(f"hỏi bởi {ai}", ai), handler, 20)
        await sleep(60)  # the merge window is over -> all three park because the thread is busy
        assert len(batches) == 0, "thread bận thì chưa lượt nào được chạy"
    finally:
        nha()
    await doi_cho_so_luong(lambda: len(batches), 3, WaitOptions(mo_ta="số lượt của ba người"))

    assert len(batches) == 3, f"mong 3 lượt, nhận {len(batches)}"
    assert sorted("|".join(b) for b in batches) == ["hỏi bởi u-a", "hỏi bởi u-b", "hỏi bởi u-c"]
    await doi_cho_den_khi(lambda: is_clean(batcher), WaitOptions(mo_ta="chạy hết rồi phải dọn sạch"))


async def test_lay_tin_dang_do_chi_keo_tin_cua_chinh_nguoi_dang_duoc_tra_loi(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """layTinDangDo chỉ kéo tin của CHÍNH người đang được trả lời"""
    nha = chiem_thread(chain, "k-chen-rieng")
    await sleep(20)
    await batcher.enqueue_message("k-chen-rieng", make_message("Hải nói thêm", "u-hai"), noop, 20)
    await batcher.enqueue_message("k-chen-rieng", make_message("Nam hỏi riêng", "u-nam"), noop, 20)
    await sleep(60)

    # Ask in REVERSE insertion order. Asking forward makes the assertion empty: the function removes the entry
    # after taking it, so a version that ignores ``sender_id`` would still give the right result.
    cua_nam = await batcher.lay_tin_dang_do("k-chen-rieng", "u-nam")
    assert [m.text for m in cua_nam] == ["Nam hỏi riêng"]

    # Hải's message MUST still be in the queue to become its own turn.
    cua_hai = await batcher.lay_tin_dang_do("k-chen-rieng", "u-hai")
    assert [m.text for m in cua_hai] == ["Hải nói thêm"]

    nha()
    await sleep(60)


async def test_id_tin_dang_cho_lay_moi_nguoi_trong_thread_khac_pham_vi_voi_lay_tin_dang_do(
    batcher: MessageBatcher,
) -> None:
    """idTinDangCho lấy MỌI người trong thread - khác phạm vi với layTinDangDo"""
    hai = make_message("Hải chờ", "u-hai")
    nam = make_message("Nam chờ", "u-nam")
    hai.history_row_id = 11
    nam.history_row_id = 22
    await batcher.enqueue_message("k-id-cho", hai, noop, 60_000)
    await batcher.enqueue_message("k-id-cho", nam, noop, 60_000)
    # Another thread must not leak in.
    la = make_message("thread khác", "u-hai")
    la.history_row_id = 99
    await batcher.enqueue_message("k-id-cho-khac", la, noop, 60_000)

    assert sorted(await batcher.id_tin_dang_cho("k-id-cho")) == [11, 22]
    assert await batcher.id_tin_dang_cho("k-id-cho-khac") == [99]


async def test_thu_tu_luot_la_thu_tu_tin_dau_tien_cua_moi_nguoi_toi(
    batcher: MessageBatcher, chain: InProcessThreadRunChain
) -> None:
    """thứ tự lượt là thứ tự tin ĐẦU TIÊN của mỗi người tới"""
    # No ``sorted`` here: the order itself is what is measured.
    batches: list[list[str]] = []
    handler = collecting(batches)

    nha = chiem_thread(chain, "k-thu-tu-nguoi")
    await sleep(20)
    await batcher.enqueue_message("k-thu-tu-nguoi", make_message("A trước", "u-a"), handler, 20)
    await batcher.enqueue_message("k-thu-tu-nguoi", make_message("B giữa", "u-b"), handler, 20)
    await batcher.enqueue_message("k-thu-tu-nguoi", make_message("C sau", "u-c"), handler, 20)
    await sleep(60)

    nha()
    await doi_cho_so_luong(lambda: len(batches), 3, WaitOptions(mo_ta="ba lượt"))

    assert batches == [["A trước"], ["B giữa"], ["C sau"]]


async def test_huy_batch_cua_thread_don_hang_cho_cua_moi_nguoi_trong_thread(batcher: MessageBatcher) -> None:
    """huyBatchCuaThread dọn hàng chờ của MỌI người trong thread"""
    await batcher.enqueue_message("k-huy-nhieu", make_message("a", "u-a"), noop, 60_000)
    await batcher.enqueue_message("k-huy-nhieu", make_message("b", "u-b"), noop, 60_000)
    await batcher.enqueue_message("k-huy-nhieu", make_message("c", "u-b"), noop, 60_000)
    await batcher.enqueue_message("k-thread-khac", make_message("d", "u-a"), noop, 60_000)

    assert await batcher.huy_batch_cua_thread("k-huy-nhieu") == 3, "phải đếm cả 3 tin của 2 người"
    assert len(await batcher.id_tin_dang_cho("k-huy-nhieu")) == 0, "không được sót hàng chờ của ai"

    # Another thread must stay untouched.
    assert await batcher.huy_batch_cua_thread("k-thread-khac") == 1


async def test_tran_tin_don_tinh_theo_tung_nguoi_khong_phai_ca_thread(batcher: MessageBatcher) -> None:
    """trần tin dồn tính theo TỪNG NGƯỜI, không phải cả thread"""
    # One spammer must not make someone else's messages get dropped.
    for i in range(TRAN_TIN_DON):
        await batcher.enqueue_message("k-tran-rieng", make_message(f"spam-{i}", "u-spam"), noop, 60_000)
    assert (
        await batcher.enqueue_message("k-tran-rieng", make_message("spam-thua", "u-spam"), noop, 60_000)
        is False
    ), "người đã chạm trần thì tin mới bị bỏ"
    assert (
        await batcher.enqueue_message("k-tran-rieng", make_message("người khác", "u-khac"), noop, 60_000)
        is True
    ), "người khác vẫn phải được nhận"

# ported from: src/zalo-bot/bot-message-router.test.ts
"""Entry point of the BOT ACCOUNT channel.

The most important invariant here is heavier than on the personal channel: ``getUpdates`` has NO ``offset`` to
acknowledge a read, so a message taken is GONE from Zalo's queue. If it is not written to history AT ONCE, a
process dying in between loses the message for good.

Differences from the original test: everything is in memory (``make_router_stack``), the turn does not run
here (the batcher enqueues a ``TurnJob``), and the cases about the Inbox of record, the busy-wait notice per
policy profile and the merge into one ``TurnJob`` are new.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from pema.channels.record_incoming_message import InboxRecordError
from pema.channels.reply_target_tu_kenh import DoanCanGui, ReplyTarget
from pema.channels.zalo_bot.bot_message_router import RouteOutcome
from pema.channels.zalo_bot.nang_luc_kenh_bot import ZALO_BOT_CAPABILITIES
from pema.channels.zalo_bot.testing import RouterStack, make_router_stack, make_update, next_turn_job
from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.middleware.message_batcher import TRAN_TIN_DON
from pema_contracts.agents import Allowlist, AllowlistMode
from pema_contracts.channel import ChannelKind, ThreadKind
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.testing import FakeChannel, fake_account_config

ACC = "acc-bot"


def kenh() -> FakeChannel:
    """A fake channel that records what is sent out and never touches the network."""
    return FakeChannel(caps=ZALO_BOT_CAPABILITIES, account=ACC)


@pytest.fixture
async def stack() -> RouterStack:
    install_tuning_provider(
        StaticTuningProvider(
            {
                "SEND_DELAY_MIN_MS": 0,
                "SEND_DELAY_MAX_MS": 0,
                "MESSAGE_BATCH_DEBOUNCE_MS": 20,
                "BUSY_ACK_AFTER_MS": 0,
            }
        )
    )
    return make_router_stack()


def contents(s: RouterStack, thread_id: str) -> list[str]:
    return s.conversation.contents(s.clinic_id, ACC, thread_id)


async def test_ghi_vao_history_ngay_get_updates_khong_co_offset_nen_mat_la_mat_han(
    stack: RouterStack,
) -> None:
    """ghi vào history NGAY - `getUpdates` không có offset nên mất là mất hẳn"""
    outcome = await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("chào bot", thread_id="t-ghi-ngay")
    )
    assert contents(stack, "t-ghi-ngay") == ["chào bot"]
    assert outcome is RouteOutcome.ENQUEUED
    await stack.batcher.clear_pending_batches()


async def test_ghi_dung_mot_dong_moi_tin_theo_dung_thu_tu_toi(stack: RouterStack) -> None:
    """ghi đúng MỘT dòng mỗi tin, theo đúng thứ tự tới"""
    for i, text in enumerate(["một", "hai", "ba"]):
        await stack.router.route_bot_update(
            stack.clinic_id, ACC, kenh(), make_update(text, thread_id="t-thu-tu", message_id=f"m-tt-{i}")
        )
    assert contents(stack, "t-thu-tu") == ["một", "hai", "ba"]
    await stack.batcher.clear_pending_batches()


async def test_bo_tin_cua_bot_khac_chong_hai_bot_noi_chuyen_vo_tan(stack: RouterStack) -> None:
    """BỎ tin của bot khác - chống hai bot nói chuyện vô tận"""
    outcome = await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("xin chào", thread_id="t-bot-khac", is_bot=True)
    )
    assert outcome is RouteOutcome.IGNORED
    assert contents(stack, "t-bot-khac") == []


async def test_ghi_nhan_ca_nguoi_nhan_khong_chi_thread(stack: RouterStack) -> None:
    """ghi nhận CẢ người nhắn, không chỉ thread"""
    await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("chào", thread_id="t-contact")
    )
    assert any(user == "u-synthetic-1" for _, user, _ in stack.conversation.contacts), (
        "người nhắn không được ghi nhận - dashboard sẽ không thấy ai"
    )
    await stack.batcher.clear_pending_batches()


async def test_update_khong_co_message_thi_bo_qua_em_khong_nem(stack: RouterStack) -> None:
    """update KHÔNG có message thì bỏ qua êm, không ném"""
    from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate

    outcome = await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), ZaloBotUpdate.model_validate({"event_name": "gì đó lạ"})
    )
    assert outcome is RouteOutcome.IGNORED


async def test_tin_thieu_thread_id_bi_bo_khong_ghi_rac_vao_bang_threads(stack: RouterStack) -> None:
    """tin THIẾU threadId bị bỏ, không ghi rác vào bảng threads"""
    # The parser leaves the thread id empty when the payload has neither ``chat.id`` nor ``from.id``. Without
    # the guard an empty thread id row is written and the queue key would be garbage nobody can trace.
    update = make_update("tin hong", thread_id="", sender_id="")
    outcome = await stack.router.route_bot_update(stack.clinic_id, ACC, kenh(), update)
    assert outcome is RouteOutcome.NO_THREAD
    assert contents(stack, "") == [], "tin thiếu threadId vẫn được ghi"
    assert stack.conversation.threads == {}


async def test_account_khong_ton_tai_thi_bo_qua_em(stack: RouterStack) -> None:
    """account không tồn tại thì bỏ qua êm"""
    outcome = await stack.router.route_bot_update(
        stack.clinic_id, "khong-co-that", kenh(), make_update("x", thread_id="t")
    )
    assert outcome is RouteOutcome.UNKNOWN_ACCOUNT


async def test_ghi_nhan_thread_va_nguoi_nhan_de_dashboard_thay(stack: RouterStack) -> None:
    """ghi nhận thread và người nhắn để dashboard thấy"""
    await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("chào", thread_id="t-ghi-nhan")
    )
    assert stack.conversation.threads[(ACC, "t-ghi-nhan")]["display_name"] == "Người Thử"
    await stack.batcher.clear_pending_batches()


async def test_tin_nhom_ten_nhom_de_trong_vi_bot_api_khong_doc_duoc_thong_tin_nhom(
    stack: RouterStack,
) -> None:
    """tin NHÓM: tên nhóm để TRỐNG vì Bot API không đọc được thông tin nhóm"""
    # ``getChat``/``getChatMember`` answer 404 (measured). Using the sender name as the group name would show
    # a member's name on the dashboard as if it were the group.
    await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("@bot ơi", thread_id="t-nhom", group=True)
    )
    assert stack.conversation.threads[(ACC, "t-nhom")]["display_name"] == ""
    assert stack.conversation.threads[(ACC, "t-nhom")]["thread_type"] == 1
    await stack.batcher.clear_pending_batches()


async def test_tin_bi_bo_vi_hang_cho_cham_tran_van_vao_history(stack: RouterStack) -> None:
    """tin bị bỏ vì hàng chờ chạm trần VẪN vào history"""
    thread_id = "t-tran"
    from pema.middleware.thread_run_chain import ThreadRef

    thread_key = ThreadRef(stack.clinic_id, ACC, thread_id).key
    release = asyncio.Event()

    async def blocked() -> None:
        await release.wait()

    stack.chain.run_on_thread_chain(thread_key, blocked)
    await asyncio.sleep(0.01)

    so_thua = 3
    tong = TRAN_TIN_DON + so_thua
    outcomes = [
        await stack.router.route_bot_update(
            stack.clinic_id, ACC, kenh(), make_update(f"tin-{i}", thread_id=thread_id, message_id=f"m{i}")
        )
        for i in range(tong)
    ]

    da_ghi = contents(stack, thread_id)
    assert len(da_ghi) == tong, f"mong {tong} dòng, nhận {len(da_ghi)}"

    # The assertion above is necessary but not enough: the record happens unconditionally BEFORE
    # ``enqueue_message``, so it is green even when the queue cap does not exist. Point at the messages that
    # were DROPPED.
    assert outcomes[TRAN_TIN_DON:] == [RouteOutcome.DROPPED_AT_CAP] * so_thua
    for i in range(so_thua):
        text = f"tin-{TRAN_TIN_DON + i}"
        assert text in da_ghi, f'tin bị bỏ "{text}" phải có trong history'

    # Clean the parked batch BEFORE releasing, otherwise it would run.
    await stack.batcher.clear_pending_batches()
    release.set()
    await asyncio.sleep(0.03)
    assert await stack.queue.claim(0) is None


# ------------------------------------------------------------------------------------- new in Pema


async def test_batch_chot_thanh_mot_turn_job_gop_cac_tin_cua_mot_nguoi(stack: RouterStack) -> None:
    """(mới) các tin gần nhau của một người thành MỘT TurnJob cho worker, mang id dòng history"""
    for i, text in enumerate(["ảnh", "cái này là gì?"]):
        await stack.router.route_bot_update(
            stack.clinic_id, ACC, kenh(), make_update(text, thread_id="t-job", message_id=f"mj-{i}")
        )

    job = await next_turn_job(stack.queue)
    assert [m.text for m in job.messages] == ["ảnh", "cái này là gì?"]
    assert [m.history_row_id for m in job.messages] == [1, 2], "tin phải mang id dòng history đã ghi lúc nhận"
    assert (job.clinic_id, job.account_id, job.thread_id) == (stack.clinic_id, ACC, "t-job")
    assert await stack.queue.claim(0) is None, "đúng MỘT job, không phải hai"


async def test_ghi_inbox_truoc_roi_history_va_tin_trung_update_id_khong_ghi_lan_hai(
    stack: RouterStack,
) -> None:
    """(mới) Inbox ghi theo update_id; cùng update_id lần hai -> DUPLICATE, không ghi history, không xếp hàng"""
    update = make_update("chào", thread_id="t-inbox", message_id="m-inbox")
    first = await stack.router.route_bot_update(stack.clinic_id, ACC, kenh(), update)
    again = await stack.router.route_bot_update(stack.clinic_id, ACC, kenh(), update)

    assert first is RouteOutcome.ENQUEUED
    assert again is RouteOutcome.DUPLICATE
    assert len(stack.inbox.recorded) == 1
    assert contents(stack, "t-inbox") == ["chào"]
    await stack.batcher.clear_pending_batches()


async def test_loi_inbox_strict_thi_ne_ra_va_chua_ghi_history_de_webhook_thu_lai_an_toan(
    stack: RouterStack,
) -> None:
    """(mới) strict_inbox: lỗi Inbox ném ra TRƯỚC khi ghi history, để Zalo gửi lại không sinh trùng"""
    stack.inbox.fail = True
    with pytest.raises(InboxRecordError):
        await stack.router.route_bot_update(
            stack.clinic_id, ACC, kenh(), make_update("chào", thread_id="t-strict"), strict_inbox=True
        )
    assert contents(stack, "t-strict") == []


async def test_loi_inbox_khi_polling_thi_ghi_log_va_van_xu_ly_tin(stack: RouterStack) -> None:
    """(mới) polling không thử lại được: lỗi Inbox chỉ ghi log, tin vẫn tới agent"""
    stack.inbox.fail = True
    outcome = await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("chào", thread_id="t-poll")
    )
    assert outcome is RouteOutcome.ENQUEUED
    await stack.batcher.clear_pending_batches()


async def test_loi_ghi_history_van_xu_ly_tin_nhu_ban_goc(stack: RouterStack) -> None:
    """lỗi ghi history: log rồi vẫn trả lời (như bản gốc)"""
    stack.conversation.fail_append = True
    outcome = await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("chào", thread_id="t-hist-loi")
    )
    assert outcome is RouteOutcome.ENQUEUED
    await stack.batcher.clear_pending_batches()


async def test_sender_ngoai_allowlist_khong_ghi_gi_ca_inbox(stack: RouterStack) -> None:
    """(mới) ngoài allowlist: không ghi history, không ghi Inbox, không xếp hàng"""
    account = fake_account_config(
        id=ACC,
        channel=ChannelKind.ZALO_BOT,
        allowlist=Allowlist(mode=AllowlistMode.LIST, user_ids=["u-khac"]),
    )
    s = make_router_stack(account=account)
    outcome = await s.router.route_bot_update(
        s.clinic_id, ACC, kenh(), make_update("alo", thread_id="t-ngoai")
    )
    assert outcome is RouteOutcome.SKIPPED
    assert s.conversation.contents(s.clinic_id, ACC, "t-ngoai") == []
    assert s.inbox.recorded == []


async def test_thread_tat_bot_chi_ghi_khong_xep_hang(stack: RouterStack) -> None:
    """(mới) thread tắt bot: ghi history + Inbox nhưng không có lượt agent"""
    stack.conversation.disabled_threads.add((ACC, "t-tat"))
    outcome = await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("alo", thread_id="t-tat")
    )
    assert outcome is RouteOutcome.RECORDED_ONLY
    assert contents(stack, "t-tat") == ["alo"]
    assert len(stack.inbox.recorded) == 1
    await asyncio.sleep(0.06)
    assert await stack.queue.claim(0) is None


# ----------------------------------------------------------------------- busy-wait notice by policy profile


@dataclass
class _Outcome:
    sent_parts: int


async def _busy_stack_and_send(profile: PolicyProfileKey) -> list[str]:
    install_tuning_provider(
        StaticTuningProvider(
            {
                "SEND_DELAY_MIN_MS": 0,
                "SEND_DELAY_MAX_MS": 0,
                "MESSAGE_BATCH_DEBOUNCE_MS": 5_000,
                "BUSY_ACK_AFTER_MS": 20,
            }
        )
    )
    sent: list[str] = []

    async def send_in_parts(target: ReplyTarget, text: str) -> _Outcome:
        await target.gui_mot_doan(DoanCanGui(text))
        sent.append(text)
        return _Outcome(sent_parts=1)

    account = fake_account_config(id=ACC, channel=ChannelKind.ZALO_BOT, policy_profile=profile)
    s = make_router_stack(account=account, send_in_parts=send_in_parts)
    from pema.middleware.thread_run_chain import ThreadRef

    thread_key = ThreadRef(s.clinic_id, ACC, "t-ban").key
    release = asyncio.Event()

    async def blocked() -> None:
        await release.wait()

    s.chain.run_on_thread_chain(thread_key, blocked)
    await asyncio.sleep(0.06)  # busy for longer than the 20 ms threshold
    channel = kenh()
    await s.router.route_bot_update(s.clinic_id, ACC, channel, make_update("alo", thread_id="t-ban"))
    await asyncio.sleep(0.1)
    await s.batcher.clear_pending_batches()
    release.set()
    assert channel.kind is ChannelKind.ZALO_BOT
    assert channel.caps.supports_formatting is False
    return [p.text for p in channel.sent]


async def test_staff_assistant_nhan_cau_tran_an_khi_bot_ban_lau() -> None:
    """(mới) staff_assistant: người nhắn lúc bot bận lâu nhận câu trấn an"""
    assert len(await _busy_stack_and_send(PolicyProfileKey.STAFF_ASSISTANT)) == 1


async def test_patient_channel_khong_tu_gui_cau_tran_an_vi_chua_ai_duyet_cau_do() -> None:
    """(mới) patient_channel: KHÔNG tự gửi chữ nào cho bệnh nhân khi chưa người duyệt"""
    assert await _busy_stack_and_send(PolicyProfileKey.PATIENT_CHANNEL) == []


async def test_thread_kind_cua_tin_nhom_duoc_ghi_la_group(stack: RouterStack) -> None:
    """(mới) tin nhóm vào TurnJob với thread_kind GROUP"""
    await stack.router.route_bot_update(
        stack.clinic_id, ACC, kenh(), make_update("@bot", thread_id="g1", group=True, message_id="mg1")
    )
    job = await next_turn_job(stack.queue)
    assert job.messages[0].thread_kind is ThreadKind.GROUP

# ported from: src/zalo/message-turn-processor.ts
"""Xử lý 1 lượt: batch tin đã gộp -> agent -> trả lời xuống kênh -> ghi history.

Worker side of the pipeline (PLAN-AI01 section 4): the API process closed a batch and put a ``TurnJob`` on the
``TurnQueue``; ``process_turn_job`` claims the per-thread lock (the original got "các lượt cùng thread
luôn chạy
tuần tự" from the batcher; here ``ThreadLock``, a Redis lock, does it across worker processes) and runs
``process_batch``.

Mở lượt TRƯỚC rồi mới chạy: có id ngay từ dòng log đầu tiên, và nhánh lỗi có chỗ mà gắn trace vào. Toàn
bộ phần
xử lý chạy trong ngữ cảnh lượt để mọi dòng log bên trong - kể cả log của các tool vốn tự tạo logger riêng - tự
mang account_id/thread_id/turn_id.

``channel`` mang năng lực của KÊNH (xem ``pema_contracts.channel``): kênh cá nhân có đủ 5, kênh bot có 2.
Năng lực
thiếu thì bỏ qua chứ không ném (``isinstance`` against the optional Protocols).

Forced deviations:

* ``runAgentTurn`` (Vercel AI SDK loop) is ``AgentEngine.run_turn`` (package D1); every failure of the
engine is an
  ``AgentTurnError`` whose ``kind`` replaces ``phanLoaiLoiProvider(err)``; ``traceLuotHong`` is
  ``pema_contracts.turn_errors.failed_turn_step``;
* the stores are the Protocols of ``pema_contracts`` (``HistoryStore``, ``UsageStore``), all async, all
keyed by
  ``clinic_id``; media, summary and the sender-aware batcher come through ``turn_ports``;
* ``options.resolveModel`` (a test seam of the original) has no counterpart: tests pass a fake
``AgentEngine``;
* policy (PLAN-AI01 section 5), added WITHOUT removing any ported feature: the profile of the account/agent
  (``effective_profile_key``) builds the ``PolicyContext``; ``on_outbound`` gates the reply (see
  ``deliver_chat_reply``); a turn the engine HANDED OFF (red flag, patient media, identity) opens a
  review item
  for a person and sends nothing; the canned technical apology is held as a draft in ``patient_channel``;
  sent replies are also written to the Inbox of record (``clinic.message``) through
  ``AgentFacingClinicActions.record_outbound_message``.

``previous behaviour kept``: the receipts ("đã xem"), the auto-reaction and the typing indicator are best
effort
and never delay or break the answer; the turn is closed (usage + trace) exactly once, the error branch only
closes a turn that was never closed (``finishAgentTurn`` is an UPDATE and ``saveTurnTrace`` an INSERT: closing
twice would overwrite the real tokens with zero and double the trace rows).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine, Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pema.channels.deliver_chat_reply import DeliveryDeps, KetQuaGiao, deliver_chat_reply
from pema.channels.reply_quote import trich_dan_tu_tin
from pema.channels.send_reply_in_parts import (
    EnqueueSend,
    ReplyTarget,
    notify_technical_error,
    reply_target_from_channel,
)
from pema.channels.turn_ports import (
    HoldForReview,
    ImagePersister,
    ThreadSummarizer,
)
from pema.policy.review import (
    build_media_flag_item,
    build_outbound_review_item,
    build_red_flag_item,
)
from pema.shared.logger import create_logger
from pema.shared.turn_log_context import TurnLogContext, run_in_turn_log_context
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.agent_turn import (
    AgentEngine,
    AgentTurnRequest,
    PendingInbox,
    StepTrace,
    ThreadLock,
    TokenUsage,
    TurnCallbacks,
    TurnJob,
    TurnQueue,
)
from pema_contracts.agents import AccountConfig, AccountStore, AgentStore
from pema_contracts.channel import (
    ChannelPort,
    ChannelRegistry,
    InboundMessage,
    ReactionChannel,
    ReadReceiptChannel,
    TypingChannel,
)
from pema_contracts.clinic_actions import AgentFacingClinicActions
from pema_contracts.conversation import HistoryStore, StoredMessage, UsageStore
from pema_contracts.conversations import MessageStatus
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    OutboundAction,
    OutboundOrigin,
    PolicyContext,
    PolicyHooks,
    effective_profile_key,
)
from pema_contracts.review import ReviewItemCreate
from pema_contracts.roles import ActorType
from pema_contracts.turn_errors import (
    AgentTurnError,
    ProviderErrorKind,
    ProviderErrorReason,
    failed_turn_step,
)

log = create_logger("message-turn")

MAX_JOB_ATTEMPTS = 3
"""A job that keeps failing for infrastructure reasons is dropped after this many claims (the user already got
the technical-error reply or a review item; an endless retry would only repeat it)."""


@dataclass
class TurnServices:
    """Everything the turn needs, injected (the original reached the stores through module imports)."""

    engine: AgentEngine
    history: HistoryStore
    usage: UsageStore
    accounts: AccountStore
    agents: AgentStore
    hooks: PolicyHooks
    pending: PendingInbox
    registry: ChannelRegistry
    thread_lock: ThreadLock | None = None
    clinic_actions: AgentFacingClinicActions | None = None
    persist_images: ImagePersister | None = None
    summarize_thread: ThreadSummarizer | None = None
    enqueue_send: EnqueueSend | None = None


_background: set[asyncio.Task[None]] = set()


def _fire(coro: Coroutine[Any, Any, None]) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def drain_background() -> None:
    """Wait for the fire-and-forget work scheduled so far (tests and shutdown)."""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


def image_paths_of(images: Sequence[object]) -> list[str]:
    """``imagePathsOf`` (media-store.ts): the stored paths of the images that were downloaded."""
    return [p for p in (getattr(i, "local_path", None) for i in images) if isinstance(p, str) and p]


async def gan_anh_vao_history(
    services: TurnServices, clinic_id: UUID, danh_sach: Sequence[InboundMessage]
) -> None:
    """Gắn đường dẫn ảnh vào các dòng đã ghi, sau khi lượt agent tải xong.

    Bỏ qua tin chưa có ``history_row_id`` thay vì ném: đây là bước LÀM TỐT THÊM (ảnh để lượt sau xem
    lại), không
    đáng giết một lượt đang chạy tốt."""
    for msg in danh_sach:
        paths = image_paths_of(msg.images)
        if msg.history_row_id is not None and paths:
            await services.history.set_message_images(clinic_id, msg.history_row_id, paths)


async def policy_context_for(
    services: TurnServices,
    clinic_id: UUID,
    config: AccountConfig,
    latest: InboundMessage,
    request_id: str | None,
) -> PolicyContext:
    agent = await services.agents.get_agent_for_account(clinic_id, config)
    key = effective_profile_key(config.policy_profile, agent.policy_profile)
    return PolicyContext(
        clinic_id=clinic_id,
        account_id=config.id,
        agent_id=agent.id,
        channel=latest.channel,
        thread_id=latest.thread_id,
        profile=DEFAULT_PROFILES[key],
        request_id=request_id,
    )


async def process_batch(
    services: TurnServices,
    clinic_id: UUID,
    config: AccountConfig,
    channel: ChannelPort,
    batch: list[InboundMessage],
    *,
    job_id: UUID | None = None,
    request_id: str | None = None,
) -> None:
    latest = batch[-1]
    turn_id = await services.usage.open_agent_turn(clinic_id, config.id, latest.thread_id)
    await run_in_turn_log_context(
        TurnLogContext(account_id=config.id, thread_id=latest.thread_id, turn_id=turn_id),
        lambda: _xu_ly_luot(services, clinic_id, config, channel, batch, turn_id, job_id, request_id),
    )


async def _xu_ly_luot(
    services: TurnServices,
    clinic_id: UUID,
    config: AccountConfig,
    channel: ChannelPort,
    batch: list[InboundMessage],
    turn_id: int,
    job_id: UUID | None,
    request_id: str | None,
) -> None:
    latest = batch[-1]
    thread_key = f"{config.id}:{latest.thread_id}"
    # Trích tin ĐẦU batch, không phải `latest`: đó là tin mở lượt, thường mang câu hỏi chính, và không xê
    # dịch khi
    # có tin chen giữa lượt. Khác chỗ bám của auto-react và biên nhận (cả hai nhắm `latest`) - cố ý, vì
    # hai việc
    # khác nhau: reaction là phản hồi tin VỪA tới, trích dẫn là chỉ ra tin ĐANG được trả lời.
    # `trich_dan_tu_tin`
    # tự bỏ qua chat riêng.
    reply_target = reply_target_from_channel(
        channel, latest.thread_id, latest.thread_kind, thread_key, quote=trich_dan_tu_tin(batch[0])
    )

    policy = await policy_context_for(services, clinic_id, config, latest, request_id)
    agent_ctx = ActionContext(
        clinic_id=clinic_id, actor_type=ActorType.AGENT, source=ActionSource.AGENT, request_id=request_id
    )
    inbox = _InboxLink(services, agent_ctx, latest)
    base_key = str(job_id) if job_id is not None else f"turn-{turn_id}"

    async def hold_for_review(
        text: str, *, origin: OutboundOrigin, extra: dict[str, object] | None = None
    ) -> str | None:
        # ``on_outbound`` only DECIDED (HOLD_FOR_REVIEW); opening the item is the job of this caller. The
        # ``job_id`` is stable for the job (and the origin), so a retried turn finds the first item.
        conversation_id = await inbox.conversation_id()
        item = build_outbound_review_item(
            policy,
            text,
            origin,
            job_id=f"{base_key}:{origin.value}",
            conversation_ref=str(conversation_id) if conversation_id is not None else None,
        )
        if extra:
            item = item.model_copy(update={"payload": {**(item.payload or {}), **extra}})
        return await _open_review_item(services, agent_ctx, item)

    async def notify_failure(loai_loi: str | None) -> None:
        await _notify_failure(services, policy, reply_target, hold_for_review, loai_loi)

    delivery = DeliveryDeps(
        history=services.history,
        hooks=services.hooks,
        policy=policy,
        enqueue_send=services.enqueue_send,
        hold_for_review=hold_for_review,
        notify_failure=notify_failure,
    )

    # Mảng do CHỖ NÀY sở hữu: engine chỉ append vào. Lượt ném lỗi vẫn còn đủ những step đã chạy được -
    # trước đây
    # mảng nằm trong agent-loop nên throw là mất sạch, lượt chạy tốt 5 step rồi step 6 gặp 500 không để
    # lại dấu
    # vết nào.
    trace: list[StepTrace] = []

    log.info(
        "Xử lý lượt tin nhắn",
        batch_size=len(batch),
        images=sum(len(m.images) for m in batch),
    )

    # "Đã xem" cho cả lượt: bot bắt đầu xử lý = giống người mở hội thoại ra đọc. Tin bị lọc (passive listen)
    # không có bước này - báo đã xem rồi im lặng sẽ khiến người nhắn tưởng bot đang soạn trả lời. Hai
    # việc PHỤ:
    # kênh nào không có thì bỏ qua, không dựng stub ném lỗi.
    await _acknowledge(channel, config, batch, latest)

    # Giữ "đang nhập" xuyên suốt: qua cả lượt LLM lẫn delay của rate-limiter, dừng trong finally kể cả
    # khi agent
    # ném lỗi
    stop_typing: Callable[[], None] = _noop
    if config.typing_indicator_enabled and isinstance(channel, TypingChannel):
        stop_typing = channel.start_typing(latest.thread_id, latest.thread_kind)

    # Lượt đã chốt sổ (usage + trace) chưa. Nhánh except dùng cờ này để không chốt lần hai.
    turn_finished = False

    # Tin người dùng nhắn thêm GIỮA lượt, đã được kéo vào ngữ cảnh của model. Mảng do CHỖ NÀY sở hữu,
    # cùng nếp với
    # `trace`: engine chỉ lo đưa tin vào input cho model, còn mọi hệ quả phụ - báo "đã xem", thả
    # reaction, lưu ảnh
    # - là việc ở đây.
    async def lay_tin_chen() -> Sequence[InboundMessage]:
        moi = await _take_injected(services, clinic_id, config.id, latest)
        if not moi:
            return moi
        await _acknowledge(channel, config, moi, moi[-1])
        # AWAIT chứ không fire-and-forget: `local_path` phải có TRƯỚC khi dựng nội dung cho model, và
        # trước khi
        # gắn vào history. Thiếu nó thì history chỉ còn dòng chữ "[gửi kèm N ảnh]" mà không đường dẫn nào.
        if services.persist_images is not None:
            await services.persist_images(clinic_id, config.id, list(moi))
        await gan_anh_vao_history(services, clinic_id, moi)
        return moi

    async def lay_id_dang_cho() -> Sequence[int]:
        # Phạm vi THREAD, khác `lay_tin_chen` ngay trên (theo người gửi): tin đang chờ của người KHÁC
        # cũng phải ra
        # khỏi lịch sử của lượt này, không thì nó vào prompt như một câu hỏi chưa ai trả lời và model trả lời
        # luôn - rồi lượt của người kia trả lời lần nữa
        return await services.pending.pending_history_ids(config.id, latest.thread_id, clinic_id)

    def ghi_nhan_da_gui(noi_dung: str) -> None:
        # Tin do TOOL gửi thẳng xuống kênh trong lượt này (file, ảnh, tag). Ghi NGAY lúc gửi: tin người
        # dùng đã
        # được ghi lúc NHẬN, nên gửi lúc nào ghi lúc ấy là ra đúng thứ tự thật, và lượt chết giữa chừng cũng
        # không đánh rơi. The callback is synchronous (``TurnCallbacks.record_tool_sent``): the write
        # runs as a
        # task that ``drain_background`` / the end of the turn awaits.
        if not noi_dung.strip():
            return
        _fire(_append_tool_sent(services, clinic_id, config.id, latest.thread_id, noi_dung.strip()))

    callbacks = TurnCallbacks(
        fetch_injected_messages=lay_tin_chen,
        pending_history_ids=lay_id_dang_cho,
        record_tool_sent=ghi_nhan_da_gui,
        trace=trace,
    )

    try:
        # Lưu ảnh xuống đĩa TRƯỚC lượt agent: agent đọc từ đĩa (khỏi tải 2 lần) và các lượt sau nạp lại
        # được ảnh
        # này từ history. Dòng lịch sử của tin đã ghi từ lúc NHẬN, giờ mới có đường dẫn ảnh để gắn vào.
        if services.persist_images is not None:
            await services.persist_images(clinic_id, config.id, batch)
        await gan_anh_vao_history(services, clinic_id, batch)

        result = await services.engine.run_turn(
            AgentTurnRequest(
                clinic_id=clinic_id, account_id=config.id, batch=batch, request_id=request_id, turn_id=turn_id
            ),
            callbacks,
        )
        await services.usage.finish_agent_turn(clinic_id, turn_id, result.usage)
        # Từ đây trở đi lượt đã CHỐT SỔ THẬT. Nhánh except bên dưới không được chốt lại nữa.
        turn_finished = True
        # Trace lưu ở đây chứ không trong engine: chỗ này vốn đã là nơi chốt usage của lượt, gom một mối
        # cho dễ
        # tìm.
        if trace:
            await services.usage.save_turn_trace(clinic_id, turn_id, trace)
        await drain_background()

        if result.handed_off:
            # A policy hook stopped the turn BEFORE the model (red flag, media, identity): the caller owns the
            # hand-off. A person gets a review item and the patient gets nothing automatic.
            await _hand_off(services, agent_ctx, inbox, policy, batch, result.hand_off_reason)
            return

        if not result.text:
            log.debug("Agent không trả text (có thể chỉ thả reaction)")
            return

        # Làm sạch + chính sách + gửi + ghi history gói trong `deliver_chat_reply`. Lớp làm sạch đặt ở
        # tầng caller
        # chứ không trong `send_reply_in_parts`: hàm đó còn phục vụ scheduler, mà lượt theo lịch có luật
        # `[SILENT]` riêng - lọc chung sẽ phá logic đó.
        giao = await deliver_chat_reply(
            reply_target, delivery, clinic_id, config.id, latest.thread_id, result.text
        )
        await _record_outbound(inbox, giao, result.text)
        if giao.hong:
            return

        # Memory lớp 2: gộp tin cũ vào summary - fire-and-forget sau khi đã trả lời; the summariser
        # swallows its own
        # errors.
        if services.summarize_thread is not None:
            _fire(services.summarize_thread(clinic_id, config.id, latest.thread_id))
    except Exception as err:
        # Tin của người dùng KHÔNG cần cứu ở đây: đã vào lịch sử từ lúc nhận, nên lượt chết cách nào cũng
        # không
        # đánh rơi.
        #
        # Trace của những step ĐÃ chạy được là thứ quý nhất lúc này: lượt đi tốt 5 step rồi step 6 gặp 500 thì
        # đây là toàn bộ manh mối. CHỈ chốt sổ khi lượt CHƯA từng chốt (xem docstring của module).
        # Phân loại để chọn ĐÚNG câu báo. Một câu cho mọi thứ khiến "bot sai cấu hình" (chờ bao lâu cũng
        # không tự
        # hết) đọc y hệt "mạng chập vài giây".
        loai_loi = err.kind if isinstance(err, AgentTurnError) else ProviderErrorKind.UNKNOWN
        safe = err.safe_message if isinstance(err, AgentTurnError) else type(err).__name__

        if not turn_finished:
            # Lượt chết TRƯỚC khi chạy được step nào (sai khóa, router 404, chưa cấu hình) không có dòng
            # `usage_steps` nào, nên nó BIẾN MẤT khỏi trang Trace, đúng ca hỏng phổ biến nhất của bản cài
            # mới. Ghi
            # một bước tổng hợp để lượt vừa lên được danh sách vừa có thứ để đọc khi bấm vào.
            steps = trace or [
                failed_turn_step(ProviderErrorReason(error_kind=loai_loi.value, message=safe[:300]))
            ]
            await services.usage.save_turn_trace(clinic_id, turn_id, steps)
            # Token thì KHÔNG biết - lỗi ném ra từ giữa lượt không mang theo usage - nên để 0 và đọc số
            # step trên
            # trang Trace.
            await services.usage.finish_agent_turn(
                clinic_id,
                turn_id,
                TokenUsage(input_tokens=0, output_tokens=0, total_tokens=0, steps=len(trace)),
            )
        log.error("Lỗi xử lý lượt tin nhắn", err=err, loai_loi=loai_loi.value, steps=len(trace))
        # Báo cho người nhắn thay vì im lặng bỏ treo. KHÔNG ghi câu này vào history: nó là thông báo hệ
        # thống, để
        # lại chỉ khiến lượt sau model neo vào tiền lệ hỏng.
        await notify_failure(loai_loi.value)
    finally:
        stop_typing()


async def _append_tool_sent(
    services: TurnServices, clinic_id: UUID, account_id: str, thread_id: str, content: str
) -> None:
    await services.history.append_message(
        clinic_id, account_id, thread_id, StoredMessage(role="assistant", content=content)
    )


def _noop() -> None:
    return None


async def _acknowledge(
    channel: ChannelPort, config: AccountConfig, batch: Sequence[InboundMessage], latest: InboundMessage
) -> None:
    """``baoDaXem`` + ``tuThaCamXuc``: the sender must see the bot received the message. Best effort."""
    if isinstance(channel, ReadReceiptChannel):
        try:
            await channel.mark_seen(batch)
        except Exception as err:
            log.debug("Báo đã xem thất bại", err=err)
    if isinstance(channel, ReactionChannel) and config.auto_react_enabled and latest.msg_id:
        _fire(_auto_react(channel, config, latest))


async def _auto_react(channel: ReactionChannel, config: AccountConfig, msg: InboundMessage) -> None:
    """Báo cho người nhắn biết bot đã nhận: thả reaction vào tin vừa gửi. Không await ở luồng chính và tự
    nuốt lỗi
    - reaction hỏng không được làm chậm hay chết đường trả lời."""
    try:
        await channel.react(msg, config.auto_react_icon)
    except Exception as err:
        log.debug("Auto-react thất bại", err=err)


async def _take_injected(
    services: TurnServices, clinic_id: UUID, account_id: str, latest: InboundMessage
) -> Sequence[InboundMessage]:
    # Theo NGƯỜI GỬI: batch nay là của đúng một người, và tin của người khác trong nhóm đã có lượt riêng
    # - kéo vào đây là cướp mất lượt đó. ``PendingInbox.take_injected`` carries the sender for that.
    return await services.pending.take_injected(account_id, latest.thread_id, latest.sender_id, clinic_id)


# ----------------------------------------------------------------------------------------- Inbox and review


class _InboxLink:
    """Lazy link to the Inbox conversation of the turn (``clinic.conversation``). The job carries no
    conversation
    id, so it is resolved through ``record_inbound_message``, which is idempotent on ``update_id``."""

    def __init__(self, services: TurnServices, ctx: ActionContext, latest: InboundMessage) -> None:
        self._services = services
        self._ctx = ctx
        self._latest = latest
        self._conversation_id: UUID | None = None
        self._resolved = False

    async def conversation_id(self) -> UUID | None:
        if self._resolved:
            return self._conversation_id
        self._resolved = True
        actions = self._services.clinic_actions
        if actions is None:
            return None
        try:
            ref = await actions.record_inbound_message(self._ctx, self._latest)
            self._conversation_id = ref.conversation_id
        except Exception as err:
            log.warning("cannot resolve the Inbox conversation", err=err)
        return self._conversation_id

    async def record_outbound(
        self,
        text: str,
        status: MessageStatus,
        review_item_id: UUID | None = None,
        error_code: str | None = None,
    ) -> None:
        actions = self._services.clinic_actions
        conversation_id = await self.conversation_id()
        if actions is None or conversation_id is None:
            return
        try:
            await actions.record_outbound_message(
                self._ctx,
                conversation_id=conversation_id,
                text=text,
                status=status,
                review_item_id=review_item_id,
                error_code=error_code,
            )
        except Exception as err:
            log.warning("cannot record the outbound message in the Inbox", err=err)


async def _record_outbound(inbox: _InboxLink, giao: KetQuaGiao, text: str) -> None:
    if giao.held_for_review:
        # The review item itself is the Inbox record (``has_pending_review``); nothing was sent.
        return
    if giao.da_gui:
        await inbox.record_outbound(giao.da_gui, MessageStatus.SENT)
    elif giao.hong and not giao.dropped:
        await inbox.record_outbound(text, MessageStatus.FAILED)


async def _open_review_item(services: TurnServices, ctx: ActionContext, item: ReviewItemCreate) -> str | None:
    """``AgentFacingClinicActions.create_review_item`` (idempotent on ``item.job_id``). ``None`` when it could
    not be created: the caller then does NOT send the text it wanted to hold."""
    actions = services.clinic_actions
    if actions is None:
        return None
    try:
        created = await actions.create_review_item(ctx, item)
    except Exception as err:
        log.error("cannot create the review item", err=err, kind=item.kind.value)
        return None
    return str(created.id)


async def _hand_off(
    services: TurnServices,
    ctx: ActionContext,
    inbox: _InboxLink,
    policy: PolicyContext,
    batch: Sequence[InboundMessage],
    reason: str | None,
) -> None:
    """The engine stopped before the model (``before_llm`` answered ``HAND_OFF``).

    ``inbound_media``: nothing to do but log. When it reports that the escalation FAILED (``*_failed``) or
    gives a code this package does not know, the item is opened here with the SAME ``job_id``
    a code this package does not know, the item is opened here with the SAME ``job_id``
    (``create_review_item`` is idempotent, so the worst case is the one item), always with the Inbox
    ``conversation_ref``; unknown codes are treated as the safest case, a triage alert for a doctor.
    """
    code = (reason or "").lower()
    if code in ("red_flag", "inbound_media"):
        log.warning("turn handed off to a person", reason=code, opened_by="policy_hook")
        return
    conversation_id = await inbox.conversation_id()
    conversation_ref = str(conversation_id) if conversation_id is not None else None
    if code == "inbound_media_flag_failed":
        item = build_media_flag_item(policy, batch, conversation_ref=conversation_ref)
    else:
        item = build_red_flag_item(
            policy, batch, [code] if code else ["unknown"], conversation_ref=conversation_ref
        )
    item_id = await _open_review_item(services, ctx, item)
    log.warning(
        "turn handed off to a person",
        reason=code,
        kind=item.kind.value,
        review_item_created=item_id is not None,
    )


async def _notify_failure(
    services: TurnServices,
    policy: PolicyContext,
    target: ReplyTarget,
    hold_for_review: HoldForReview,
    loai_loi: str | None,
) -> None:
    """The canned apology (``notifyTechnicalError``) goes through the same policy gate as any outbound text:
    sent at once in ``staff_assistant``; in ``patient_channel`` it is held as a draft for a person (who
    also learns
    the agent failed) instead of being sent unreviewed."""
    from pema.channels.send_reply_in_parts import cau_loi_theo_loai

    canned = cau_loi_theo_loai(loai_loi)
    try:
        decision = await services.hooks.on_outbound(
            policy, canned, proactive=False, origin=OutboundOrigin.TURN_REPLY
        )
    except Exception as err:
        log.error("policy hook failed for the technical-error reply - not sent", err=err)
        return
    if decision.action is OutboundAction.SEND:
        await notify_technical_error(target, loai_loi, enqueue_send=services.enqueue_send)
    elif decision.action is OutboundAction.HOLD_FOR_REVIEW:
        await hold_for_review(
            canned, origin=OutboundOrigin.TURN_REPLY, extra={"agent_failed": True, "error_kind": loai_loi}
        )


# --------------------------------------------------------------------------------------------- the job loop


async def process_turn_job(services: TurnServices, queue: TurnQueue, job: TurnJob) -> None:
    """One ``TurnJob`` from the queue: guards, the per-thread lock, the turn, ack/nack.

    * the account must exist, be enabled and RUN in this worker (``registry``); otherwise the job is acked and
      dropped when the account is gone or disabled (the safety switch must win over a queued message) and
      nacked
      with a retry when it is merely not running yet (the bridge may still be starting);
    * turns of one thread never overlap: ``ThreadLock`` (Redis) replaces the in-process ``runOnThreadChain``;
    * ``process_batch`` handles every turn failure itself (reply or review item); an exception that still
    escapes
      is infrastructure (database down): the job is retried up to ``MAX_JOB_ATTEMPTS`` times.
    """
    config = await services.accounts.get_account(job.clinic_id, job.account_id)
    if config is None or not config.enabled:
        log.info("job dropped: account missing or disabled", account_id=job.account_id)
        await queue.ack(job.job_id)
        return
    channel = services.registry.get_running(job.clinic_id, job.account_id)
    if channel is None:
        retry = job.attempt < MAX_JOB_ATTEMPTS
        log.warning("account not running in this worker", account_id=job.account_id, retry=retry)
        await queue.nack(job.job_id, retry=retry)
        return
    try:
        if services.thread_lock is not None:
            async with services.thread_lock.hold(job.account_id, job.thread_id, job.clinic_id):
                await process_batch(
                    services,
                    job.clinic_id,
                    config,
                    channel,
                    list(job.messages),
                    job_id=job.job_id,
                    request_id=job.request_id,
                )
        else:
            await process_batch(
                services,
                job.clinic_id,
                config,
                channel,
                list(job.messages),
                job_id=job.job_id,
                request_id=job.request_id,
            )
    except Exception as err:
        retry = job.attempt < MAX_JOB_ATTEMPTS
        log.error("turn job failed outside the turn", err=err, account_id=job.account_id, retry=retry)
        await queue.nack(job.job_id, retry=retry)
        return
    await queue.ack(job.job_id)

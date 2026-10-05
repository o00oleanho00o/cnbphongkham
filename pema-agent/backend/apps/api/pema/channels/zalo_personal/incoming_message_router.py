# ported from: src/zalo/incoming-message-router.ts
"""Mọi tin đến (kể cả tin sẽ bị lọc): ghi contact + thread ("auto-collected"). Đọc config mới nhất từ DB
mỗi tin để
sửa policies từ dashboard ăn ngay.

Same shape as the bot router of package C1: ... allowlist -> record incoming -> batcher -> ``TurnQueue``
... There
is NO in-process turn: the batcher (API process) closes a batch and enqueues a ``TurnJob`` that the
worker runs
(``message_turn_processor``).

Forced deviations:

* everything is async and carries ``clinic_id``; stores are the ports of ``pema_contracts.conversation``;
* the modules of package C1 (allowlist filter, ``record_incoming_message``, payload anomaly watch,
message batcher,
  busy-wait notice) and D2 (media store, thread display names) are reached through the small Protocols
  below. They
  are the exact seams ``RouterDeps`` lists; package G wires the real objects, tests use fakes;
* ``api`` (zca-js) is the bridge-backed ``ZaloApi``; the raw message is the ``message`` of a bridge
``message``
  event.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast
from uuid import UUID

from pema.channels.send_reply_in_parts import ReplyTarget, reply_target_from_channel
from pema.channels.zalo_personal.bridge_client import ZaloApi
from pema.channels.zalo_personal.kenh_ca_nhan import ZaloPersonalChannel
from pema.channels.zalo_personal.message_receipts import send_delivered_receipt
from pema.channels.zalo_personal.zalo_message_parser import parse_incoming_message
from pema.config.runtime_tuning_settings import get_tuning
from pema.shared.logger import create_logger
from pema_contracts.agents import AccountConfig, AccountStore
from pema_contracts.channel import InboundMessage

log = create_logger("message-router")


@dataclass(frozen=True)
class RespondDecision:
    """``shouldRespond`` of ``middleware/allowlist-filter.ts`` (package C1)."""

    respond: bool
    record: bool = False
    reason: str = ""


class AllowlistFilter(Protocol):
    def __call__(
        self, config: AccountConfig, msg: InboundMessage, bot_enabled: bool, /
    ) -> RespondDecision: ...


class IncomingRecorder(Protocol):
    """``ghiTinDenVaoHistory`` (C1 ``record_incoming_message``): history + Inbox at receipt, stamps
    ``msg.history_row_id``. ``luu_anh_ngay`` downloads the images now (no agent turn will do it)."""

    async def __call__(self, clinic_id: UUID, msg: InboundMessage, /, *, luu_anh_ngay: bool) -> int: ...


class PayloadAnomalyReporter(Protocol):
    """``reportPayloadAnomalies`` (C1): logs unexpected payload shapes, ids only."""

    def __call__(self, account_id: str, msg: InboundMessage, /) -> None: ...


class MessageBatcher(Protocol):
    """``enqueueMessage`` of ``message-batcher.ts`` (C1, Redis): debounce + merge, then a ``TurnJob`` on the
    ``TurnQueue``. ``False`` = dropped because the pending queue of the thread hit its ceiling."""

    async def enqueue_message(self, clinic_id: UUID, thread_key: str, msg: InboundMessage, /) -> bool: ...


class BusyWaitNotifier(Protocol):
    """``maybeNotifyBusyWait`` (C1 ``busy_wait_notice``): reassurance text when a thread is busy for a
    long time."""

    async def __call__(self, target: ReplyTarget, /) -> None: ...


class ImagePersister(Protocol):
    """``persistBatchImages`` (D2 ``media_store``): downloads images, stamps ``InboundImage.local_path``."""

    async def __call__(self, clinic_id: UUID, account_id: str, messages: list[InboundMessage], /) -> None: ...


class ImageAttacher(Protocol):
    """``setMessageImages`` after the download (D2 ``history_store``)."""

    async def __call__(self, clinic_id: UUID, msg: InboundMessage, /) -> None: ...


class ContactActivity(Protocol):
    """The one method of ``ContactStore`` (D2) the router calls: ``recordContactActivity``."""

    async def record_contact_activity(
        self, clinic_id: UUID, account_id: str, user_id: str, display_name: str
    ) -> None: ...


class ThreadActivity(Protocol):
    """The two ``ThreadStore`` (D2) methods the router calls: ``recordThreadActivity``, ``isBotEnabled``."""

    async def record_thread_activity(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        thread_id: str,
        thread_type: int,
        display_name: str,
        sender_name: str,
    ) -> None: ...

    async def is_bot_enabled(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool: ...


class ThreadNames(Protocol):
    """``hasDisplayName`` / ``setThreadDisplayName`` of ``thread-store.ts`` (D2). ``ThreadStore`` of the
    contract
    has no such pair; an additive method on D2's implementation satisfies this Protocol."""

    async def has_display_name(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool: ...

    async def set_thread_display_name(
        self, clinic_id: UUID, account_id: str, thread_id: str, name: str
    ) -> None: ...


@dataclass
class RouterDeps:
    accounts: AccountStore
    contacts: ContactActivity
    threads: ThreadActivity
    thread_names: ThreadNames
    should_respond: AllowlistFilter
    record_incoming: IncomingRecorder
    report_anomalies: PayloadAnomalyReporter
    batcher: MessageBatcher
    busy_notifier: BusyWaitNotifier | None
    persist_images: ImagePersister | None
    attach_images: ImageAttacher | None


_background: set[asyncio.Task[None]] = set()


def _fire(coro: Awaitable[None]) -> None:
    task = asyncio.ensure_future(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


async def drain_background() -> None:
    """Wait for the fire-and-forget work scheduled so far (tests and shutdown)."""
    while _background:
        await asyncio.gather(*list(_background), return_exceptions=True)


async def route_incoming_message(
    deps: RouterDeps,
    clinic_id: UUID,
    channel: ZaloPersonalChannel,
    raw: Mapping[str, object],
    *,
    self_id: str | None = None,
) -> None:
    """One raw message of the bridge: record, filter, batch."""
    account_id = channel.account_id
    config = await deps.accounts.get_account(clinic_id, account_id)
    if config is None:
        return
    api: ZaloApi = channel.api
    me = self_id or api.get_own_id()

    msg = parse_incoming_message(config.id, me, raw, str(get_tuning("ZALO_IMAGE_QUALITY")))

    # Chạy TRƯỚC mọi nhánh return bên dưới: tin thiếu thread_id bị bỏ qua lặng lẽ ở ngay dòng dưới, không
    # cảnh báo
    # ở đây thì không còn chỗ nào biết
    deps.report_anomalies(config.id, msg)
    if not msg.thread_id:
        # A message without a thread has nowhere to be answered and nothing to be recorded against: it is
        # reported above and dropped here, explicitly (the original relied on the allowlist filter to do it).
        return

    if not msg.is_self and msg.thread_id:
        # "Đã nhận" cho MỌI tin về tới listener, kể cả tin sắp bị lọc - client Zalo thật cũng báo nhận tự
        # động,
        # không phụ thuộc người dùng có đọc hay không
        send_delivered_receipt(api, msg)
        await deps.contacts.record_contact_activity(clinic_id, config.id, msg.sender_id, msg.sender_name)
        await deps.threads.record_thread_activity(
            clinic_id,
            account_id=config.id,
            thread_id=msg.thread_id,
            thread_type=1 if msg.is_group else 0,
            display_name="" if msg.is_group else msg.sender_name,
            sender_name=msg.sender_name,
        )
        if msg.is_group and not await deps.thread_names.has_display_name(clinic_id, config.id, msg.thread_id):
            _fire(_resolve_group_name(deps, clinic_id, config.id, api, msg.thread_id))

    bot_enabled = await deps.threads.is_bot_enabled(clinic_id, config.id, msg.thread_id)
    decision = deps.should_respond(config, msg, bot_enabled)

    if not decision.respond:
        if decision.record:
            # Không có lượt agent nào sắp chạy nên phải tự tải ảnh
            await deps.record_incoming(clinic_id, msg, luu_anh_ngay=True)
        log.debug(
            "Ghi passive, không trả lời" if decision.record else "Bỏ qua tin",
            account_id=config.id,
            thread_id=msg.thread_id,
            reason=decision.reason,
        )
        return

    # Ghi TRƯỚC khi xếp hàng, không đợi lượt agent chạy xong: thứ tự trong lịch sử phải là thứ tự người
    # ta gửi.
    # Ảnh để lượt agent tải (nó AWAIT vì cần `local_path` trước khi dựng nội dung cho model) rồi gắn vào chính
    # dòng này.
    #
    # Nhờ ghi ở đây mà nhánh "chạm trần hàng chờ" bên dưới không còn phải tự ghi lấy: tin bị bỏ sẽ không
    # mất khỏi
    # lịch sử, dù `send_delivered_receipt` đã báo "đã nhận" và người ta đinh ninh bot có nghe.
    # Bọc try/except vì bước này nay chạy TRƯỚC `enqueue_message`: DB khoá hay đĩa đầy mà ném ra thì tin
    # không chỉ
    # mất khỏi lịch sử, nó còn không bao giờ tới được lượt trả lời. Ghi hỏng là chuyện đáng báo động nhưng vẫn
    # phải trả lời người ta.
    try:
        await deps.record_incoming(clinic_id, msg, luu_anh_ngay=False)
    except Exception as err:
        log.error(
            "Không ghi được tin vào history - vẫn trả lời",
            account_id=config.id,
            thread_id=msg.thread_id,
            err=err,
        )

    thread_key = f"{config.id}:{msg.thread_id}"
    accepted = await deps.batcher.enqueue_message(clinic_id, thread_key, msg)

    if not accepted:
        # Tin đã nằm trong lịch sử rồi, nhưng KHÔNG lượt nào tải ảnh cho nó nữa - phải tự tải, không thì dòng
        # này mãi mãi không có đường dẫn ảnh
        if msg.images and deps.persist_images is not None and deps.attach_images is not None:
            _fire(_persist_dropped_images(deps, clinic_id, config.id, msg))
        log.warning(
            "Tin bị bỏ khỏi lượt vì hàng chờ chạm trần - đã ghi vào history để bot còn biết",
            account_id=config.id,
            thread_id=msg.thread_id,
        )

    # Bot đã bận rất lâu thì nói một câu cho người ta biết vẫn đang làm. Hàm này tự quyết có đáng gửi hay
    # không
    # (mặc định chỉ gửi sau khi dấu "đang nhập..." đã tắt). Fire-and-forget và tự nuốt lỗi: đây là việc phụ,
    # không được làm chậm đường nhận tin.
    #
    # Dựng đích qua `reply_target_from_channel` chứ không viết tay: các trường mang theo
    # (`tran_ky_tu_mot_tin`,
    # `mang_dinh_dang`) đều TÙY CHỌN nên quên là trình biên dịch im lặng.
    if deps.busy_notifier is not None:
        target = reply_target_from_channel(channel, msg.thread_id, msg.thread_kind, thread_key)
        _fire(_notify_busy(deps.busy_notifier, target, msg.thread_id))


async def _notify_busy(notifier: BusyWaitNotifier, target: ReplyTarget, thread_id: str) -> None:
    try:
        await notifier(target)
    except Exception as err:
        log.debug("Gửi câu trấn an thất bại", thread_id=thread_id, err=err)


async def _persist_dropped_images(
    deps: RouterDeps, clinic_id: UUID, account_id: str, msg: InboundMessage
) -> None:
    try:
        if deps.persist_images is None or deps.attach_images is None:
            return
        await deps.persist_images(clinic_id, account_id, [msg])
        await deps.attach_images(clinic_id, msg)
    except Exception as err:
        log.debug("Không gắn được ảnh vào history", thread_id=msg.thread_id, err=err)


async def _resolve_group_name(
    deps: RouterDeps, clinic_id: UUID, account_id: str, api: ZaloApi, thread_id: str
) -> None:
    """Lấy tên group 1 lần khi gặp lần đầu, cache vào bảng threads."""
    try:
        info = await api.get_group_info(thread_id)
        grid = cast("dict[str, Any]", info.get("gridInfoMap") or {})
        entry = cast("dict[str, Any]", grid.get(thread_id) or {})
        name: object = entry.get("name") or info.get("name")
        if name:
            await deps.thread_names.set_thread_display_name(clinic_id, account_id, thread_id, str(name))
    except Exception as err:
        log.debug("Không lấy được tên nhóm - để trống", account_id=account_id, thread_id=thread_id, err=err)

# ported from: src/zalo-bot/bot-message-router.ts
"""The intake path of the BOT ACCOUNT channel: allowlist -> record the incoming message -> batcher ->
``TurnQueue``.

A separate router and not the shared personal one: that router calls three things the Bot API does NOT have,
the "received" receipt, the automatic reaction, and ``getGroupInfo`` to look up a group name. Pushing three
``if channel has...`` branches into the router that serves the real account adds surface that can break the
channel already running, to save about thirty lines.

What is SHARED is truly shared, not copied: ``should_respond``, ``ghi_tin_den_vao_history``, the batcher,
``maybe_notify_busy_wait``.

The invariant that matters most here is heavier than on the personal channel: ``getUpdates`` has NO ``offset``
to acknowledge a read, so a message taken is GONE from Zalo's queue. If it is not recorded AT ONCE, a process
dying in between loses the message for good. (A webhook delivery IS retried by Zalo, which is why that path
records the update in ``agent.channel_update_seen`` and undoes the mark when processing fails.)

Forced deviations (CONTRACTS section 4, decision 6):

* The turn does NOT run here. The batcher hands a closed batch to ``make_turn_job_handler``, which enqueues a
  ``TurnJob`` on the ``TurnQueue``; the worker runs it (``processBatch`` is package C2's
  ``message_turn_processor``).
* Stores are ``async`` and take ``clinic_id``; the account is read from ``AccountStore``.
* New: the Inbox of record is written through ``AgentFacingClinicActions`` (see ``record_incoming_message``);
  with ``strict_inbox`` an Inbox failure is raised so a webhook can be retried, without it the failure is
  logged and the message still goes to the agent (polling cannot be retried).
* New: no busy-wait reassurance in ``patient_channel`` (nobody approved that text), see ``busy_wait_notice``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID, uuid4

from pema.channels.busy_wait_notice import ReplySender, maybe_notify_busy_wait
from pema.channels.payload_anomaly_watch import report_payload_anomalies
from pema.channels.record_incoming_message import (
    HistoryWriter,
    ImagePersister,
    InboxRecordError,
    InboxWriter,
    gan_anh_vao_history,
    ghi_tin_den_vao_history,
    webhook_action_context,
)
from pema.channels.reply_target_tu_kenh import reply_target_tu_kenh
from pema.channels.zalo_bot.zalo_bot_api_types import ZaloBotUpdate
from pema.channels.zalo_bot.zalo_bot_update_parser import doi_update_sang_parsed_message
from pema.middleware.allowlist_filter import should_respond
from pema.middleware.message_batcher import DefaultBatchHandler, MessageBatcher
from pema.middleware.thread_run_chain import ThreadBusy, ThreadRef
from pema.shared.logger import create_logger
from pema_contracts.agent_turn import TurnJob, TurnQueue
from pema_contracts.agents import AccountConfig, AccountStore, AgentStore
from pema_contracts.channel import ChannelPort, InboundMessage, ThreadKind
from pema_contracts.common import now_vn
from pema_contracts.policy import PolicyProfileKey, effective_profile_key

_log = create_logger("bot-message-router")

_background: set[asyncio.Task[None]] = set()


class RouteOutcome(StrEnum):
    UNKNOWN_ACCOUNT = "unknown_account"
    IGNORED = "ignored"
    NO_THREAD = "no_thread"
    SKIPPED = "skipped"
    RECORDED_ONLY = "recorded_only"
    DUPLICATE = "duplicate"
    ENQUEUED = "enqueued"
    DROPPED_AT_CAP = "dropped_at_cap"


class BotConversation(HistoryWriter, Protocol):
    """The part of ``ConversationStore`` the intake path uses (history, contacts, threads)."""

    async def record_contact_activity(
        self, clinic_id: UUID, account_id: str, user_id: str, display_name: str
    ) -> None: ...

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


@dataclass
class BotRouterDeps:
    accounts: AccountStore
    conversation: BotConversation
    batcher: MessageBatcher
    thread_busy: ThreadBusy
    inbox: InboxWriter | None = None
    agents: AgentStore | None = None
    persist_images: ImagePersister | None = None
    send_in_parts: ReplySender | None = None
    """``send_reply_in_parts`` of package C2, used only for the busy-wait reassurance. ``None`` disables it.
    """


def make_turn_job_handler(queue: TurnQueue) -> DefaultBatchHandler:
    """Default handler of the batcher: a closed batch becomes a ``TurnJob`` queued for the worker."""

    async def handler(thread_key: str, batch: list[InboundMessage]) -> None:
        ref = ThreadRef.parse(thread_key)
        await queue.enqueue(
            TurnJob(
                job_id=uuid4(),
                clinic_id=ref.clinic_id,
                account_id=ref.account_id,
                thread_id=ref.thread_id,
                messages=batch,
                enqueued_at=now_vn(),
            )
        )

    return handler


def _thread_type_int(kind: ThreadKind) -> int:
    return 1 if kind is ThreadKind.GROUP else 0


class BotMessageRouter:
    def __init__(self, deps: BotRouterDeps) -> None:
        self._d = deps

    async def route_bot_update(
        self,
        clinic_id: UUID,
        account_id: str,
        kenh: ChannelPort,
        update: ZaloBotUpdate,
        *,
        strict_inbox: bool = False,
    ) -> RouteOutcome:
        """``routeBotUpdate``. Raises ``InboxRecordError`` only when ``strict_inbox`` and the Inbox write
        failed."""
        d = self._d
        config = await d.accounts.get_account(clinic_id, account_id)
        if config is None:
            # This channel has no ``offset``, so every early return is a permanent loss: leave at least one
            # line.
            _log.warning("Nhận tin cho account không tồn tại - bỏ tin", account_id=account_id)
            return RouteOutcome.UNKNOWN_ACCOUNT

        msg = doi_update_sang_parsed_message(config.id, update)
        if msg is None:
            # Another bot's message, or an update with no message. Debug only: it is normal, but total silence
            # makes it impossible to trace when Zalo changes the payload shape.
            _log.debug("Bỏ qua update", account_id=config.id, event_name=update.event_name)
            return RouteOutcome.IGNORED

        # Runs BEFORE the return below: a message with no thread id is dropped on the next line, and without a
        # warning here nothing says so. If Zalo renames ``chat.id`` EVERY message is swallowed forever in
        # silence, and this channel has no ``offset`` to take it back, so the damage is heavier than on the
        # personal channel.
        report_payload_anomalies(config.id, msg)
        if not msg.thread_id:
            return RouteOutcome.NO_THREAD

        await d.conversation.record_contact_activity(clinic_id, config.id, msg.sender_id, msg.sender_name)
        await d.conversation.record_thread_activity(
            clinic_id,
            account_id=config.id,
            thread_id=msg.thread_id,
            thread_type=_thread_type_int(msg.thread_kind),
            # The Bot API has NO method that reads group info (``getChat`` answers 404), so the group name
            # stays empty and the dashboard shows the id. The personal channel can look it up, so it has a
            # name.
            display_name="" if msg.is_group else msg.sender_name,
            sender_name=msg.sender_name,
        )

        decision = should_respond(
            config, msg, await d.conversation.is_bot_enabled(clinic_id, config.id, msg.thread_id)
        )

        if not decision.respond:
            if decision.record:
                await self._record(clinic_id, config, msg, luu_anh_ngay=True, strict_inbox=strict_inbox)
            _log.debug(
                "Ghi passive, không trả lời" if decision.record else "Bỏ qua tin",
                account_id=config.id,
                thread_id=msg.thread_id,
                reason=decision.reason,
            )
            return RouteOutcome.RECORDED_ONLY if decision.record else RouteOutcome.SKIPPED

        # Record BEFORE queueing, same reason as the personal channel: the order in history must be the order
        # people sent, and a turn that dies midway must not drop the message. For the bot channel one more,
        # heavier reason: ``getUpdates`` has NO ``offset`` to acknowledge a read, so a message taken is GONE
        # from Zalo's queue. If it is not recorded now, a process dying here loses it for good.
        recorded = await self._record(clinic_id, config, msg, luu_anh_ngay=False, strict_inbox=strict_inbox)
        if recorded == "duplicate":
            return RouteOutcome.DUPLICATE

        thread_key = ThreadRef(clinic_id, config.id, msg.thread_id).key
        accepted = await d.batcher.enqueue_message(thread_key, msg)

        if not accepted:
            # The message is in history already, but NO turn will download its image any more: do it here,
            # otherwise the row never gets an image path. The bot channel DOES receive images (the Bot API
            # hands them over as URLs), so this branch cannot be dropped.
            if msg.images and d.persist_images is not None:
                self._spawn(self._persist_dropped(clinic_id, config.id, msg))
            _log.warning(
                "Tin bị bỏ khỏi lượt vì hàng chờ chạm trần - đã ghi vào history để bot còn biết",
                account_id=config.id,
                thread_id=msg.thread_id,
            )
            outcome = RouteOutcome.DROPPED_AT_CAP
        else:
            outcome = RouteOutcome.ENQUEUED

        if d.send_in_parts is not None:
            self._spawn(self._notify_busy(clinic_id, config, kenh, msg, thread_key, d.send_in_parts))
        return outcome

    # ------------------------------------------------------------------ helpers
    async def _record(
        self,
        clinic_id: UUID,
        config: AccountConfig,
        msg: InboundMessage,
        *,
        luu_anh_ngay: bool,
        strict_inbox: bool,
    ) -> str:
        d = self._d
        try:
            result = await ghi_tin_den_vao_history(
                clinic_id=clinic_id,
                account_id=config.id,
                msg=msg,
                luu_anh_ngay=luu_anh_ngay,
                history=d.conversation,
                inbox=d.inbox,
                ctx=webhook_action_context(clinic_id),
                persist_images=d.persist_images,
            )
        except InboxRecordError:
            if strict_inbox:
                raise
            _log.error(
                "Không ghi được tin vào Inbox - vẫn xử lý tiếp (polling không thử lại được)",
                account_id=config.id,
                thread_id=msg.thread_id,
            )
            return "inbox_failed"
        except Exception as err:
            _log.error(
                "Không ghi được tin vào history - vẫn trả lời",
                err=err,
                account_id=config.id,
                thread_id=msg.thread_id,
            )
            return "history_failed"
        return "duplicate" if result.duplicate else "ok"

    async def _persist_dropped(self, clinic_id: UUID, account_id: str, msg: InboundMessage) -> None:
        d = self._d
        if d.persist_images is None:
            return
        try:
            await d.persist_images(clinic_id, account_id, [msg])
            await gan_anh_vao_history(clinic_id, d.conversation, [msg])
        except Exception as err:
            _log.debug("Không gắn được ảnh vào history", err=err, thread_id=msg.thread_id)

    async def _notify_busy(
        self,
        clinic_id: UUID,
        config: AccountConfig,
        kenh: ChannelPort,
        msg: InboundMessage,
        thread_key: str,
        send_in_parts: ReplySender,
    ) -> None:
        # Fire-and-forget side job: it must never slow the intake or surface an error.
        try:
            allowed = await self._busy_notice_allowed(clinic_id, config)
            if not allowed:
                return
            await maybe_notify_busy_wait(
                reply_target_tu_kenh(
                    kenh=kenh, thread_id=msg.thread_id, thread_kind=msg.thread_kind, thread_key=thread_key
                ),
                busy=self._d.thread_busy,
                send_in_parts=send_in_parts,
            )
        except Exception as err:
            _log.debug("Gửi câu trấn an thất bại", err=err, thread_id=msg.thread_id)

    async def _busy_notice_allowed(self, clinic_id: UUID, config: AccountConfig) -> bool:
        agent_profile = config.policy_profile
        if self._d.agents is not None:
            agent_profile = (await self._d.agents.get_agent_for_account(clinic_id, config)).policy_profile
        # No automatic text to a patient that no human approved (PLAN-AI01 section 5).
        return effective_profile_key(config.policy_profile, agent_profile) is PolicyProfileKey.STAFF_ASSISTANT

    @staticmethod
    def _spawn(coro: Coroutine[object, object, None]) -> None:
        task = asyncio.ensure_future(coro)
        _background.add(task)
        task.add_done_callback(_background.discard)

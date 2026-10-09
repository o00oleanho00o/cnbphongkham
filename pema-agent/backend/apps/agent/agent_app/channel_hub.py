"""Runs the chat channels plugins register and sends the agent's replies back through them.

The hub starts each channel of an enabled plugin and stops it when the plugin goes away. What a channel hears
is stored like any message (once per channel message id) and marked for delivery. When its turn is over the
reply is sent in parts the channel accepts, in the order the messages came within a conversation. A send that
fails is retried with growing pauses, from this or any other process; one the channel refuses for good, or
that keeps failing, is marked failed. Delivery is at least once: a process that dies in the middle of a send
may make the next one repeat a part.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, replace
from typing import Any, Final

from agent_app.dispatcher import Dispatcher
from agent_app.ingress import IngressRecord
from agentcore.channels import (
    ChannelAdapter,
    ChannelSendError,
    InboundMessage,
    OutboundMessage,
    Receive,
    split_reply,
)

MAX_INBOUND_CHARS: Final = 8000
MAX_ERROR_CHARS: Final = 500
CLOSE_GRACE_S: Final = 5.0

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class DeliverySettings:
    tick_s: float = 2.0
    """How often channels are matched with the enabled plugins and due replies looked for."""
    max_attempts: int = 4
    backoff_s: tuple[float, ...] = (2.0, 10.0, 60.0)
    send_timeout_s: float = 30.0
    stale_s: float = 120.0
    """A send claimed longer ago than this belongs to a dead process and is taken over."""
    start_timeout_s: float = 30.0
    start_retry_s: float = 30.0
    max_concurrent: int = 4
    batch: int = 50


class ChannelHub:
    def __init__(
        self,
        dispatcher: Dispatcher,
        *,
        channels: Callable[[], Sequence[ChannelAdapter]],
        refresh: Callable[[], Awaitable[None]] | None = None,
        settings: DeliverySettings | None = None,
        failure_reply: str = "",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._dispatcher = dispatcher
        self._ingress = dispatcher.ingress
        self._channels = channels
        self._refresh = refresh
        self.settings = settings or DeliverySettings()
        self._failure_reply = failure_reply.strip()
        self._clock = clock
        self._running: dict[str, ChannelAdapter] = {}
        self._errors: dict[str, str] = {}
        self._retry_at: dict[str, float] = {}
        self._inflight: set[int] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self._slots = asyncio.Semaphore(self.settings.max_concurrent)
        dispatcher.on_finished(self._finished)

    @property
    def running(self) -> list[str]:
        return sorted(self._running)

    def status(self) -> list[dict[str, Any]]:
        adapters = {a.name: a for a in self._channels()} | self._running
        return [
            {
                "name": name,
                "running": name in self._running,
                "error": self._errors.get(name),
                "max_text_chars": adapter.capabilities.max_text_chars,
                "markdown": adapter.capabilities.markdown,
            }
            for name, adapter in sorted(adapters.items())
        ]

    async def run(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception as err:  # the next tick tries again
                logger.warning("channel tick failed (%s)", type(err).__name__)
            await asyncio.sleep(self.settings.tick_s)

    async def tick(self) -> None:
        if self._refresh is not None:
            try:
                await self._refresh()
            except Exception as err:  # channels keep running as they are
                logger.warning("plugin refresh failed (%s)", type(err).__name__)
        await self.sync()
        await self.schedule_due()

    async def sync(self) -> None:
        """Starts the channels of enabled plugins and stops the ones whose plugin went away."""
        wanted = {adapter.name: adapter for adapter in self._channels()}
        for name, adapter in list(self._running.items()):
            if wanted.get(name) is not adapter:
                await self._stop(name, adapter)
        for name in [n for n in self._errors if n not in wanted]:
            self._errors.pop(name, None)
            self._retry_at.pop(name, None)
        for name, adapter in wanted.items():
            if name in self._running or self._clock() < self._retry_at.get(name, -math.inf):
                continue
            try:
                await asyncio.wait_for(adapter.start(self._receiver(name)), self.settings.start_timeout_s)
            except Exception as err:  # a channel that cannot start must not stop the others
                self._errors[name] = _describe(err)
                self._retry_at[name] = self._clock() + self.settings.start_retry_s
                logger.warning("channel %s did not start (%s)", name, type(err).__name__)
                continue
            self._running[name] = adapter
            self._errors.pop(name, None)
            self._retry_at.pop(name, None)
            logger.info("channel %s started", name)

    async def schedule_due(self) -> None:
        if not self._running:
            return
        due = await self._ingress.due_deliveries(
            self._dispatcher.tenant_id,
            list(self._running),
            stale_s=self.settings.stale_s,
            limit=self.settings.batch,
        )
        for record in due:
            self._schedule(record.id)

    async def close(self, grace_s: float = CLOSE_GRACE_S) -> None:
        """Lets sends in flight finish for ``grace_s``, then stops every channel. Unsent replies stay due."""
        if self._tasks:
            _, pending = await asyncio.wait(set(self._tasks), timeout=grace_s)
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
        for name, adapter in list(self._running.items()):
            await self._stop(name, adapter)

    async def deliver(self, ingress_id: int) -> bool:
        """Sends the reply of one message if it is due, resuming after the parts already out; False when it
        was not due (or is held back by an earlier reply of its conversation)."""
        settings = self.settings
        record = await self._ingress.claim_delivery(
            self._dispatcher.tenant_id, ingress_id, stale_s=settings.stale_s
        )
        if record is None:
            return False
        adapter = self._running.get(record.channel)
        if adapter is None:
            await self._ingress.retry_delivery(
                record.id, "the channel is not running", after_s=settings.tick_s
            )
            return False
        if record.status == "done" and record.reply is not None:
            text = record.reply.text
        elif self._failure_reply:
            text = self._failure_reply  # the turn failed; the person still hears back
        else:
            await self._ingress.finish_delivery(
                record.id, "skipped", f"no reply: {record.error_kind or record.status}"
            )
            return True
        parts = split_reply(text, adapter.capabilities.max_text_chars)
        if not parts:
            await self._ingress.finish_delivery(record.id, "skipped", "empty reply")
            return True
        for index in range(record.delivered_parts, len(parts)):
            message = OutboundMessage(
                conversation_id=record.conversation_id,
                text=parts[index],
                user_id=record.user_id,
                reply_to=record.external_id,
                part=index + 1,
                parts=len(parts),
                metadata=record.metadata,
            )
            try:
                await asyncio.wait_for(adapter.send(message), settings.send_timeout_s)
            except ChannelSendError as err:
                return await self._failed(
                    record, _describe(err), retryable=err.retryable, after_s=err.retry_after_s
                )
            except TimeoutError:
                return await self._failed(record, "the send timed out", retryable=True)
            except Exception as err:  # a channel bug is retried like a network error
                return await self._failed(record, _describe(err), retryable=True)
            await self._ingress.delivery_progress(record.id, index + 1)
        await self._ingress.finish_delivery(record.id, "sent")
        return True

    def _receiver(self, name: str) -> Receive:
        async def receive(inbound: InboundMessage) -> None:
            if not inbound.message_id or not inbound.conversation_id or not inbound.user_id:
                logger.warning("channel %s handed over a message without ids; dropped", name)
                return
            if not inbound.text.strip():
                return
            # A channel speaks only for itself, and long texts are cut like at the HTTP gateway.
            inbound = replace(inbound, channel=name, text=inbound.text[:MAX_INBOUND_CHARS])
            await self._dispatcher.accept(inbound, deliver=True)

        return receive

    def _finished(self, record: IngressRecord) -> None:
        if record.channel in self._running:
            self._schedule(record.id)

    def _schedule(self, ingress_id: int) -> None:
        if ingress_id in self._inflight:
            return
        self._inflight.add(ingress_id)
        task = asyncio.create_task(self._deliver_task(ingress_id), name=f"deliver {ingress_id}")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _deliver_task(self, ingress_id: int) -> None:
        settled = False
        try:
            async with self._slots:
                settled = await self.deliver(ingress_id)
        except Exception as err:  # the reply stays due; the next tick tries again
            logger.warning("delivery of message %d failed (%s)", ingress_id, type(err).__name__)
        finally:
            self._inflight.discard(ingress_id)
        if not settled:
            return
        try:
            await self.schedule_due()  # a later reply of the same conversation may have waited for this one
        except Exception as err:
            logger.warning("looking for due replies failed (%s)", type(err).__name__)

    async def _failed(
        self, record: IngressRecord, error: str, *, retryable: bool, after_s: float | None = None
    ) -> bool:
        """True when the reply is given up for good."""
        settings = self.settings
        if not retryable or record.delivery_attempts >= settings.max_attempts:
            await self._ingress.finish_delivery(record.id, "failed", error)
            logger.warning(
                "reply to message %d not delivered after %d attempt(s)", record.id, record.delivery_attempts
            )
            return True
        pause = settings.backoff_s[min(record.delivery_attempts, len(settings.backoff_s)) - 1]
        await self._ingress.retry_delivery(
            record.id, error, after_s=after_s if after_s is not None else pause
        )
        return False

    async def _stop(self, name: str, adapter: ChannelAdapter) -> None:
        self._running.pop(name, None)
        try:
            await asyncio.wait_for(adapter.stop(), self.settings.start_timeout_s)
        except Exception as err:  # it is gone from the hub either way
            logger.warning("channel %s did not stop cleanly (%s)", name, type(err).__name__)
        logger.info("channel %s stopped", name)


def _describe(err: BaseException) -> str:
    text = str(err)
    return (f"{type(err).__name__}: {text}" if text else type(err).__name__)[:MAX_ERROR_CHARS]

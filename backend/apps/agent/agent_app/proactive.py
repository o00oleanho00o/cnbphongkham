"""How the agent writes to a chat on its own (a case's turn, a reminder): the instruction goes into the queue
like a message from the conversation, so the turn, the reply and the send take the usual way. The message
carries ``PROACTIVE``: it is never answered with the apology meant for customers, never merged into a
customer's turn, and an answer of ``SKIP`` sends nothing."""

from __future__ import annotations

import asyncio

from agent_app.dispatcher import Dispatcher
from agent_app.ingress import OPEN_DELIVERY
from agent_app.plugins import ProactiveSent
from agentcore.channels import PROACTIVE, InboundMessage


class DispatcherOutbox:
    """``send_to`` is what plugins get as ``ctx.proactive`` and the case engine sends its turns with."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        *,
        turn_timeout_s: float = 180.0,
        delivery_timeout_s: float = 300.0,
        poll_s: float = 2.0,
    ) -> None:
        self._dispatcher = dispatcher
        self._turn_timeout_s = turn_timeout_s
        self._delivery_timeout_s = delivery_timeout_s
        self._poll_s = poll_s

    async def send_to(
        self, *, channel: str, conversation_id: str, user_id: str, message_id: str, instruction: str
    ) -> ProactiveSent:
        """Has the agent answer ``instruction`` and sends the answer to the chat, unless it is ``SKIP``;
        ``counted`` when the customer was written to, or may have been. The same ``message_id`` runs once."""
        dispatcher = self._dispatcher
        inbound = InboundMessage(
            channel=channel,
            conversation_id=conversation_id,
            user_id=user_id,
            message_id=message_id,
            text=instruction,
            metadata={PROACTIVE: "1"},
        )
        record, _ = await dispatcher.accept(inbound, deliver=True)
        record = await dispatcher.wait(record.id, self._turn_timeout_s)
        if not record.finished:
            return ProactiveSent(True, "the turn was still running")
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._delivery_timeout_s
        while record.delivery in OPEN_DELIVERY and loop.time() < deadline:
            await asyncio.sleep(self._poll_s)
            fresh = await dispatcher.ingress.get(dispatcher.tenant_id, record.id)
            record = fresh or record
        if record.delivery == "sent":
            return ProactiveSent(True)
        if record.delivery == "sending":
            return ProactiveSent(True, "still being sent")
        if record.delivery == "pending":
            # It would go out whenever the channel comes back, long after it made sense.
            await dispatcher.ingress.finish_delivery(record.id, "skipped", "not sent in time")
            return ProactiveSent(False, "not sent in time")
        return ProactiveSent(False, record.delivery_error or record.error_kind or str(record.delivery))

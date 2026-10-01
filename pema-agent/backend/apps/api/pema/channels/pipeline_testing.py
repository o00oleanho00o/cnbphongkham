"""Test doubles of the shared turn pipeline (import in tests only, like ``pema_contracts.testing``).

The ``AgentEngine``, the conversation stores, the clinic actions and the pending inbox are ports of other
packages; here they are minimal in-memory fakes so the pipeline (``message_turn_processor``,
``deliver_chat_reply``, ``send_reply_in_parts``) is tested on its own, with synthetic data.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from pema.channels.message_turn_processor import TurnServices, drain_background, process_batch
from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_personal.kenh_ca_nhan import ZaloPersonalChannel
from pema.channels.zalo_personal.message_receipts import drain_pending_receipts
from pema.channels.zalo_personal.testing import FakeZaloApi, make_personal_channel
from pema.channels.zalo_personal.zalo_message_parser import describe_for_history
from pema_contracts.actions import ActionContext
from pema_contracts.agent_turn import (
    AgentTurnRequest,
    AgentTurnResult,
    StepTrace,
    ThreadLock,
    TokenUsage,
    TurnCallbacks,
)
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import (
    ChannelKind,
    ChannelRegistry,
    InboundImage,
    InboundKind,
    InboundMessage,
    ThreadKind,
)
from pema_contracts.clinic_actions import InboxRef
from pema_contracts.common import now_vn
from pema_contracts.conversation import StoredMessage
from pema_contracts.conversations import MessageStatus
from pema_contracts.policy import PermissivePolicyHooks, PolicyHooks, PolicyProfileKey
from pema_contracts.review import ReviewItemCreate, ReviewItemOut, ReviewStatus
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    InMemoryAccountStore,
    InMemoryAgentStore,
    InMemoryThreadLock,
    fake_account_config,
    fake_agent_profile,
    make_inbound,
)

__all__ = [
    "FAKE_CLINIC_ID",
    "FakeActions",
    "FakeConversation",
    "FakeEngine",
    "FakePending",
    "TurnRig",
    "answer",
    "immediate_enqueue_send",
    "make_services",
]


async def immediate_enqueue_send(thread_key: str, task: Callable[[], Awaitable[object]]) -> object:
    """``enqueueSend`` without the random delay (the production queue sleeps before every send)."""
    return await task()


@dataclass
class TurnRow:
    id: int
    usage: TokenUsage | None = None
    trace: list[StepTrace] = field(default_factory=list[StepTrace])
    finished: int = 0
    trace_saves: int = 0


@dataclass
class FakeConversation:
    """``HistoryStore`` + ``UsageStore`` (the subset the turn uses), keyed like the real ones."""

    messages: list[tuple[int, str, str, StoredMessage]] = field(
        default_factory=list[tuple[int, str, str, StoredMessage]]
    )
    turns: dict[int, TurnRow] = field(default_factory=dict[int, TurnRow])
    images: dict[int, list[str]] = field(default_factory=dict[int, list[str]])
    _next_message: int = 1
    _next_turn: int = 1

    async def append_message(
        self, clinic_id: UUID, account_id: str, thread_id: str, message: StoredMessage
    ) -> int:
        row_id = self._next_message
        self._next_message += 1
        self.messages.append((row_id, account_id, thread_id, message))
        return row_id

    async def set_message_images(self, clinic_id: UUID, message_id: int, images: list[str]) -> None:
        self.images[message_id] = images

    async def get_recent_messages(
        self, clinic_id: UUID, account_id: str, thread_id: str, limit: int | None = None
    ) -> list[StoredMessage]:
        rows = [m for (_, a, t, m) in self.messages if a == account_id and t == thread_id]
        return rows[-limit:] if limit else rows

    async def list_messages_paged(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[StoredMessage]:
        return await self.get_recent_messages(clinic_id, account_id, thread_id, limit)

    async def open_agent_turn(
        self, clinic_id: UUID, account_id: str, thread_id: str, source: object = None
    ) -> int:
        turn_id = self._next_turn
        self._next_turn += 1
        self.turns[turn_id] = TurnRow(id=turn_id)
        return turn_id

    async def finish_agent_turn(self, clinic_id: UUID, turn_id: int, usage: TokenUsage) -> None:
        row = self.turns[turn_id]
        row.usage = usage
        row.finished += 1

    async def save_turn_trace(self, clinic_id: UUID, turn_id: int, steps: list[StepTrace]) -> None:
        row = self.turns[turn_id]
        row.trace = list(steps)
        row.trace_saves += 1

    async def append_step(self, clinic_id: UUID, turn_id: int, step: StepTrace) -> None:
        self.turns[turn_id].trace.append(step)

    def contents(self, account_id: str, thread_id: str) -> list[tuple[str, str]]:
        return [(m.role, m.content) for (_, a, t, m) in self.messages if a == account_id and t == thread_id]


@dataclass
class FakePending:
    """``PendingInbox`` (plus the sender-aware extension). ``waiting`` holds the injected messages."""

    waiting: list[InboundMessage] = field(default_factory=list[InboundMessage])
    taken: int = 0

    async def take_injected(self, account_id: str, thread_id: str) -> Sequence[InboundMessage]:
        mine = [m for m in self.waiting if m.thread_id == thread_id]
        self.waiting = [m for m in self.waiting if m.thread_id != thread_id]
        self.taken += len(mine)
        return mine

    async def take_injected_for_sender(
        self, account_id: str, thread_id: str, sender_id: str
    ) -> list[InboundMessage]:
        mine = [m for m in self.waiting if m.thread_id == thread_id and m.sender_id == sender_id]
        self.waiting = [m for m in self.waiting if m not in mine]
        self.taken += len(mine)
        return mine

    async def pending_history_ids(self, account_id: str, thread_id: str) -> Sequence[int]:
        return [
            m.history_row_id
            for m in self.waiting
            if m.thread_id == thread_id and m.history_row_id is not None
        ]


type EngineScript = Callable[[AgentTurnRequest, TurnCallbacks | None], Awaitable[AgentTurnResult]]


@dataclass
class FakeEngine:
    """``AgentEngine`` with a script. The default answers ``"ok"``."""

    script: EngineScript | None = None
    requests: list[AgentTurnRequest] = field(default_factory=list[AgentTurnRequest])

    async def run_turn(
        self, request: AgentTurnRequest, callbacks: TurnCallbacks | None = None
    ) -> AgentTurnResult:
        self.requests.append(request)
        if self.script is not None:
            return await self.script(request, callbacks)
        return AgentTurnResult(
            text="ok", usage=TokenUsage(input_tokens=60, output_tokens=15, total_tokens=75, steps=1)
        )


def answer(text: str) -> EngineScript:
    async def run(request: AgentTurnRequest, callbacks: TurnCallbacks | None) -> AgentTurnResult:
        return AgentTurnResult(
            text=text, usage=TokenUsage(input_tokens=60, output_tokens=15, total_tokens=75, steps=1)
        )

    return run


@dataclass
class FakeActions:
    """``AgentFacingClinicActions`` (the subset the pipeline calls)."""

    conversation_id: UUID = field(default_factory=uuid4)
    review_items: dict[str, ReviewItemOut] = field(default_factory=dict[str, ReviewItemOut])
    created: list[ReviewItemCreate] = field(default_factory=list[ReviewItemCreate])
    outbound: list[tuple[str, MessageStatus, UUID | None]] = field(
        default_factory=list[tuple[str, MessageStatus, UUID | None]]
    )
    fail_create: bool = False

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        return InboxRef(conversation_id=self.conversation_id, duplicate=True)

    async def record_outbound_message(
        self,
        ctx: ActionContext,
        *,
        conversation_id: UUID,
        text: str,
        status: MessageStatus,
        proactive: bool = False,
        review_item_id: UUID | None = None,
        error_code: str | None = None,
    ) -> InboxRef:
        self.outbound.append((text, status, review_item_id))
        return InboxRef(conversation_id=conversation_id)

    async def create_review_item(self, ctx: ActionContext, request: ReviewItemCreate) -> ReviewItemOut:
        if self.fail_create:
            raise RuntimeError("review service down")
        self.created.append(request)
        existing = self.review_items.get(request.job_id)
        if existing is not None:
            return existing
        item = ReviewItemOut(
            id=uuid4(),
            kind=request.kind,
            origin=request.origin,
            status=ReviewStatus.PENDING,
            conversation_id=UUID(request.conversation_ref) if request.conversation_ref else None,
            patient_id=None,
            patient_code=request.patient_ref,
            draft_text=request.draft_text,
            payload=request.payload,
            sources=request.sources,
            risk_level=request.risk_level,
            red_flags=request.red_flags,
            requires_doctor=request.risk_level.value == "red_flag",
            job_id=request.job_id,
            created_at=now_vn(),
            version=1,
        )
        self.review_items[request.job_id] = item
        return item


class _NoChannels:
    def get_running(self, clinic_id: UUID, account_id: str) -> None:
        return None

    def list_running(self, clinic_id: UUID) -> list[object]:
        return []


def make_services(
    *,
    engine: FakeEngine | None = None,
    conversation: FakeConversation | None = None,
    pending: FakePending | None = None,
    hooks: PolicyHooks | None = None,
    registry: ChannelRegistry | None = None,
    actions: FakeActions | None = None,
    accounts: InMemoryAccountStore | None = None,
    agents: InMemoryAgentStore | None = None,
    **extra: object,
) -> TurnServices:
    conv = conversation or FakeConversation()
    return TurnServices(
        engine=engine or FakeEngine(),
        history=conv,  # type: ignore[arg-type]
        usage=conv,  # type: ignore[arg-type]
        accounts=accounts or InMemoryAccountStore(),
        agents=agents or InMemoryAgentStore(),
        hooks=hooks or PermissivePolicyHooks(),
        pending=pending or FakePending(),
        registry=registry or _NoChannels(),  # type: ignore[arg-type]
        thread_lock=cast("ThreadLock", InMemoryThreadLock()),
        clinic_actions=actions,  # type: ignore[arg-type]
        enqueue_send=immediate_enqueue_send,
        **extra,  # type: ignore[arg-type]
    )


@dataclass
class TurnRig:
    """Everything a turn test needs: a recording ``ZaloApi``, the personal channel over it, the fakes, and
    ``receive`` which does what the router does at receipt (records, stamps ``history_row_id``)."""

    api: FakeZaloApi
    channel: ZaloPersonalChannel
    conversation: FakeConversation
    engine: FakeEngine
    pending: FakePending
    config: AccountConfig
    services: TurnServices
    actions: FakeActions | None = None
    clinic_id: UUID = FAKE_CLINIC_ID

    @staticmethod
    def create(
        *,
        engine: FakeEngine | None = None,
        profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
        hooks: PolicyHooks | None = None,
        actions: FakeActions | None = None,
        **config_patch: object,
    ) -> TurnRig:
        api = FakeZaloApi()
        config = fake_account_config(
            channel=ChannelKind.ZALO_PERSONAL,
            id=api.account_id,
            agent_id="agent-test",
            policy_profile=profile,
            typing_indicator_enabled=False,
            auto_react_enabled=False,
            **config_patch,
        )
        agents = InMemoryAgentStore(fake_agent_profile(policy_profile=profile))
        accounts = InMemoryAccountStore(config)
        conversation = FakeConversation()
        pending = FakePending()
        the_engine = engine or FakeEngine()
        channel = make_personal_channel(api, config=config)
        registry = InMemoryChannelRegistry()
        registry.register(FAKE_CLINIC_ID, channel)
        services = make_services(
            registry=registry,
            engine=the_engine,
            conversation=conversation,
            pending=pending,
            hooks=hooks,
            actions=actions,
            accounts=accounts,
            agents=agents,
        )
        return TurnRig(
            api=api,
            channel=channel,
            conversation=conversation,
            engine=the_engine,
            pending=pending,
            config=config,
            services=services,
            actions=actions,
        )

    async def receive(
        self,
        text: str,
        msg_id: str,
        *,
        thread_id: str = "t-1",
        sender: str = "Hải",
        is_group: bool = False,
        sent_at: datetime | None = None,
        images: Sequence[str] = (),
        record: bool = True,
    ) -> InboundMessage:
        """Build the inbound message and record it in the history, exactly like the router does at receipt."""
        raw: dict[str, object] = {
            "content": text,
            "msgType": "webchat",
            "uidFrom": f"u-{sender}",
            "idTo": "self-1",
            "msgId": msg_id,
            "cliMsgId": f"c-{msg_id}",
            "ts": "1786122720000",
            "ttl": 0,
        }
        fields: dict[str, object] = {
            "channel": ChannelKind.ZALO_PERSONAL,
            "account_id": self.config.id,
            "thread_id": thread_id,
            "sender_id": f"u-{sender}",
            "sender_name": sender,
            "update_id": msg_id,
            "msg_id": msg_id,
            "cli_msg_id": f"c-{msg_id}",
            "is_group": is_group,
            "thread_kind": ThreadKind.GROUP if is_group else ThreadKind.USER,
            "mentions_me": is_group,
            "raw": raw,
            "images": [InboundImage(url=url) for url in images],
            "kind": InboundKind.IMAGE if images else InboundKind.TEXT,
        }
        if sent_at is not None:
            fields["sent_at"] = sent_at
        msg = make_inbound(text, **fields)  # pyright: ignore[reportArgumentType]
        if record:
            msg.history_row_id = await self.conversation.append_message(
                self.clinic_id,
                self.config.id,
                thread_id,
                StoredMessage(
                    role="user",
                    content=describe_for_history(msg),
                    sender_name=sender,
                    sender_id=msg.sender_id,
                    created_at=msg.sent_at,
                ),
            )
        return msg

    async def run(self, batch: list[InboundMessage], *, job_id: UUID | None = None) -> None:
        await process_batch(self.services, self.clinic_id, self.config, self.channel, batch, job_id=job_id)
        await drain_background()
        await drain_pending_receipts()

    def sent_texts(self) -> list[str]:
        return [m.text for m in self.api.sent]

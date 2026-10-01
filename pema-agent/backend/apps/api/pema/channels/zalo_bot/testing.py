"""Test doubles for the Zalo Bot channel, in the spirit of ``pema_contracts.testing``. Import in tests only.

Nothing here talks to a network, a database or Redis. Every identifier and name is synthetic.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import httpx

from pema.channels.busy_wait_notice import ReplySender
from pema.channels.record_incoming_message import ImagePersister
from pema.channels.registry import InMemoryChannelRegistry
from pema.channels.zalo_bot.bot_message_router import BotMessageRouter, BotRouterDeps, make_turn_job_handler
from pema.channels.zalo_bot.zalo_bot_api_client import LoiZaloBotApi, ZaloBotClient
from pema.channels.zalo_bot.zalo_bot_api_types import KetQuaGuiTin, ZaloBotUpdate
from pema.middleware.message_batcher import InMemoryPendingBatchStore, MessageBatcher
from pema.middleware.thread_run_chain import InProcessThreadRunChain
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema_contracts.actions import ActionContext
from pema_contracts.agent_turn import TurnJob
from pema_contracts.agents import AccountConfig
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.clinic_actions import InboxRef
from pema_contracts.conversation import StoredMessage
from pema_contracts.testing import InMemoryAccountStore, InMemoryTurnQueue, fake_account_config

SYNTHETIC_TOKEN = "123456789:token-bi-mat-khong-duoc-lo"  # noqa: S105 - a fake token for tests
SYNTHETIC_UPDATE: dict[str, Any] = {
    "event_name": "message.text.received",
    "message": {
        "from": {"id": "u-synthetic-1", "display_name": "Người Thử", "is_bot": False},
        "chat": {"id": "u-synthetic-1", "chat_type": "PRIVATE"},
        "text": "Xin chào",
        "message_id": "mid-0001",
        "date": 1750316131602,
    },
}


def make_update(
    text: str = "Xin chào",
    *,
    thread_id: str = "u-synthetic-1",
    sender_id: str = "u-synthetic-1",
    message_id: str = "mid-0001",
    group: bool = False,
    is_bot: bool = False,
    **message_extra: Any,
) -> ZaloBotUpdate:
    message: dict[str, Any] = {
        "from": {"id": sender_id, "display_name": "Người Thử", "is_bot": is_bot},
        "chat": {"id": thread_id, "chat_type": "GROUP" if group else "PRIVATE"},
        "text": text,
        "message_id": message_id,
        "date": 1750316131602,
        **message_extra,
    }
    return ZaloBotUpdate.model_validate({"event_name": "message.text.received", "message": message})


def mock_client(
    handler: Callable[[httpx.Request], httpx.Response], token: str = SYNTHETIC_TOKEN
) -> ZaloBotClient:
    """A REAL ``ZaloBotClient`` over ``httpx.MockTransport``: exercises the real request/response code, no
    network."""
    return ZaloBotClient(token, goc_api="https://x.test", transport=httpx.MockTransport(handler))


@dataclass
class FakeBotClient:
    """``BotApiClient`` double. ``updates`` is a script: an item is returned (or raised when it is an
    exception) by one ``get_updates`` call; once it is empty ``get_updates`` hangs, like a real quiet long
    poll, so a loop does not spin while a test is measuring."""

    me: dict[str, Any] = field(default_factory=lambda: {"id": "bot-synthetic", "display_name": "Bot Thử"})
    me_error: Exception | None = None
    webhook_url: str = ""
    webhook_info_error: Exception | None = None
    updates: list[ZaloBotUpdate | Exception | None] = field(
        default_factory=list[ZaloBotUpdate | Exception | None]
    )
    sent: list[tuple[str, str, str | None]] = field(default_factory=list[tuple[str, str, str | None]])
    send_error: Exception | None = None
    chat_actions: list[str] = field(default_factory=list[str])
    deleted_webhooks: int = 0
    set_webhooks: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    polls: int = 0
    closed: bool = False
    _release: asyncio.Event = field(default_factory=asyncio.Event)

    async def get_me(self) -> dict[str, Any]:
        if self.me_error is not None:
            raise self.me_error
        return self.me

    async def get_updates(self, timeout_giay: int = 30) -> ZaloBotUpdate | None:
        self.polls += 1
        if not self.updates:
            await self._release.wait()
            return None
        item = self.updates.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> KetQuaGuiTin:
        if self.send_error is not None:
            raise self.send_error
        self.sent.append((chat_id, text, parse_mode))
        return KetQuaGuiTin(message_id=f"m-{len(self.sent)}", date=1750316131602)

    async def send_chat_action(self, chat_id: str, action: str = "typing") -> object:
        self.chat_actions.append(chat_id)
        return {}

    async def get_webhook_info(self) -> dict[str, Any]:
        if self.webhook_info_error is not None:
            raise self.webhook_info_error
        return {"url": self.webhook_url}

    async def delete_webhook(self) -> object:
        self.deleted_webhooks += 1
        self.webhook_url = ""
        return {}

    async def set_webhook(self, url: str, secret_token: str) -> object:
        self.set_webhooks.append((url, secret_token))
        self.webhook_url = url
        return {}

    def release(self) -> None:
        """Wake a hanging ``get_updates`` (it then returns ``None``)."""
        self._release.set()

    async def aclose(self) -> None:
        self.closed = True
        self._release.set()


def token_error(code: int = 401) -> LoiZaloBotApi:
    return LoiZaloBotApi("getMe thất bại: Invalid token", "getMe", 200, code)


@dataclass
class FakeConversation:
    """The slice of ``ConversationStore`` the intake path uses, backed by lists."""

    rows: dict[tuple[UUID, str, str], list[StoredMessage]] = field(
        default_factory=dict[tuple[UUID, str, str], list[StoredMessage]]
    )
    images: dict[int, list[str]] = field(default_factory=dict[int, list[str]])
    contacts: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])
    threads: dict[tuple[str, str], dict[str, object]] = field(
        default_factory=dict[tuple[str, str], dict[str, object]]
    )
    disabled_threads: set[tuple[str, str]] = field(default_factory=set[tuple[str, str]])
    fail_append: bool = False
    _next_id: int = 1

    async def append_message(
        self, clinic_id: UUID, account_id: str, thread_id: str, message: StoredMessage
    ) -> int:
        if self.fail_append:
            raise RuntimeError("history unavailable")
        row_id = self._next_id
        self._next_id += 1
        self.rows.setdefault((clinic_id, account_id, thread_id), []).append(
            message.model_copy(update={"id": row_id})
        )
        return row_id

    async def set_message_images(self, clinic_id: UUID, message_id: int, images: list[str]) -> None:
        self.images[message_id] = images

    async def record_contact_activity(
        self, clinic_id: UUID, account_id: str, user_id: str, display_name: str
    ) -> None:
        self.contacts.append((account_id, user_id, display_name))

    async def record_thread_activity(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        thread_id: str,
        thread_type: int,
        display_name: str,
        sender_name: str,
    ) -> None:
        self.threads[(account_id, thread_id)] = {
            "thread_type": thread_type,
            "display_name": display_name,
            "sender_name": sender_name,
        }

    async def is_bot_enabled(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool:
        return (account_id, thread_id) not in self.disabled_threads

    def contents(self, clinic_id: UUID, account_id: str, thread_id: str) -> list[str]:
        return [m.content for m in self.rows.get((clinic_id, account_id, thread_id), [])]


class FakeInbox:
    """``AgentFacingClinicActions.record_inbound_message`` double (idempotent on ``update_id``). Only the
    method the channel layer calls is implemented."""

    def __init__(self) -> None:
        self.recorded: list[InboundMessage] = []
        self._seen: set[str] = set()
        self.fail = False

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        if self.fail:
            raise RuntimeError("inbox unavailable")
        if message.update_id in self._seen:
            return InboxRef(conversation_id=UUID(int=1), duplicate=True)
        self._seen.add(message.update_id)
        self.recorded.append(message)
        return InboxRef(conversation_id=UUID(int=1), message_id=UUID(int=len(self.recorded) + 1))


@dataclass
class RouterStack:
    """Everything the intake path needs, in memory: accounts, history, batcher, queue, router."""

    clinic_id: UUID
    accounts: InMemoryAccountStore
    conversation: FakeConversation
    inbox: FakeInbox
    chain: InProcessThreadRunChain
    batcher: MessageBatcher
    queue: InMemoryTurnQueue
    router: BotMessageRouter
    registry: InMemoryChannelRegistry


def make_router_stack(
    *,
    account: AccountConfig | None = None,
    with_inbox: bool = True,
    persist_images: ImagePersister | None = None,
    send_in_parts: ReplySender | None = None,
) -> RouterStack:
    """A synthetic clinic with one bot account (``staff_assistant`` and an allowlist open to all unless
    given)."""
    config = account or fake_account_config(id="acc-bot", channel=ChannelKind.ZALO_BOT)
    accounts = InMemoryAccountStore(config)
    conversation = FakeConversation()
    inbox = FakeInbox()
    chain = InProcessThreadRunChain()
    queue = InMemoryTurnQueue()
    batcher = MessageBatcher(InMemoryPendingBatchStore(), chain, default_handler=make_turn_job_handler(queue))
    router = BotMessageRouter(
        BotRouterDeps(
            accounts=accounts,
            conversation=conversation,
            batcher=batcher,
            thread_busy=chain,
            inbox=inbox if with_inbox else None,
            persist_images=persist_images,
            send_in_parts=send_in_parts,
        )
    )
    return RouterStack(
        config.clinic_id,
        accounts,
        conversation,
        inbox,
        chain,
        batcher,
        queue,
        router,
        InMemoryChannelRegistry(),
    )


async def next_turn_job(queue: InMemoryTurnQueue) -> TurnJob:
    """Wait until a ``TurnJob`` is on the queue and claim it (the batcher closes it after the debounce)."""
    found: list[TurnJob] = []

    async def got_job() -> bool:
        job = await queue.claim(0)
        if job is not None:
            found.append(job)
        return job is not None

    await doi_cho_den_khi(got_job, WaitOptions(mo_ta="TurnJob trên hàng đợi"))
    return found[0]

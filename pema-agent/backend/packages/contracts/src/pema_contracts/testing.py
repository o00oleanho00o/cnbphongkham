"""Test doubles for the contract ports, shared by every package so nobody re-invents them.

Import in tests only (``from pema_contracts.testing import FakeChannel``). Nothing here talks to a
network or a database. Each fake implements the Protocol it stands for, so ``isinstance`` checks in the
contract tests keep them honest.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pema_contracts.agent_turn import GeneratedText, TurnJob
from pema_contracts.agents import AccountConfig, AccountStore, AgentProfile, AgentStore
from pema_contracts.channel import (
    ChannelCapabilities,
    ChannelKind,
    InboundMessage,
    QuoteRef,
    SendResult,
    SendStatus,
    TextStyle,
    ThreadKind,
)
from pema_contracts.common import now_vn
from pema_contracts.policy import PolicyProfileKey


def make_inbound(
    text: str = "xin chao",
    *,
    channel: ChannelKind = ChannelKind.ZALO_BOT,
    account_id: str = "acc-1",
    thread_id: str = "thread-1",
    sender_id: str = "user-1",
    update_id: str = "u-1",
    msg_id: str = "m-1",
    **extra: object,
) -> InboundMessage:
    """A valid synthetic inbound message. ``extra`` overrides any field."""
    data: dict[str, object] = {
        "channel": channel,
        "account_id": account_id,
        "update_id": update_id,
        "thread_id": thread_id,
        "sender_id": sender_id,
        "sender_name": "Synthetic User",
        "text": text,
        "msg_id": msg_id,
        "sent_at": now_vn(),
        **extra,
    }
    return InboundMessage.model_validate(data)


FAKE_CLINIC_ID = UUID("00000000-0000-4000-8000-000000000001")
"""Fixed synthetic clinic id for tests that do not care which clinic."""


def fake_agent_profile(**patch: object) -> AgentProfile:
    """``fakeAgentProfile`` (src/shared/fake-agent-profile.ts): an agent for building a ``ToolContext``.

    Disables NO tool by default: a test that needs the agent layer to filter passes ``disabled_tools``
    explicitly, so reading the test shows which layer it exercises. The policy profile defaults to
    ``staff_assistant`` here (unlike production, which defaults to the safe one) so engine tests are not
    accidentally run under review mode.
    """
    data: dict[str, object] = {
        "id": "agent-test",
        "clinic_id": FAKE_CLINIC_ID,
        "name": "Agent test",
        "policy_profile": PolicyProfileKey.STAFF_ASSISTANT,
        **patch,
    }
    return AgentProfile.model_validate(data)


def fake_account_config(**patch: object) -> AccountConfig:
    data: dict[str, object] = {
        "id": "acc-1",
        "clinic_id": FAKE_CLINIC_ID,
        "label": "Account test",
        "channel": ChannelKind.ZALO_BOT,
        "agent_id": "agent-test",
        "policy_profile": PolicyProfileKey.STAFF_ASSISTANT,
        **patch,
    }
    return AccountConfig.model_validate(data)


@dataclass
class SentPart:
    thread_id: str
    text: str
    thread_kind: ThreadKind
    styles: Sequence[TextStyle]
    quote: QuoteRef | None
    proactive: bool


@dataclass
class FakeChannel:
    """In-memory ``ChannelPort``. Records every part; ``reject_with`` makes every send a rejection."""

    caps: ChannelCapabilities
    secret: str = "ok"  # noqa: S105 - a fake webhook secret
    account: str = "acc-1"
    sent: list[SentPart] = field(default_factory=list[SentPart])
    reject_with: SendResult | None = None

    @property
    def kind(self) -> ChannelKind:
        return self.caps.channel

    @property
    def account_id(self) -> str:
        return self.account

    def capabilities(self) -> ChannelCapabilities:
        return self.caps

    def verify_webhook(self, headers: Mapping[str, str], body: bytes) -> bool:
        return headers.get("x-secret") == self.secret and bool(body)

    def parse_inbound(self, update: Mapping[str, object]) -> InboundMessage | None:
        text = update.get("text")
        if not isinstance(text, str):
            return None
        return make_inbound(text, channel=self.kind, account_id=self.account)

    async def send_text(
        self,
        thread_id: str,
        text: str,
        *,
        thread_kind: ThreadKind = ThreadKind.USER,
        styles: Sequence[TextStyle] = (),
        quote: QuoteRef | None = None,
        proactive: bool = False,
    ) -> SendResult:
        if self.reject_with is not None:
            return self.reject_with
        self.sent.append(SentPart(thread_id, text, thread_kind, tuple(styles), quote, proactive))
        return SendResult(
            status=SendStatus.SENT, external_message_id=f"fake-{len(self.sent)}", sent_at=now_vn()
        )


class InMemoryTurnQueue:
    """``TurnQueue`` without Redis. ``claim`` returns immediately (no blocking)."""

    def __init__(self) -> None:
        self._pending: deque[TurnJob] = deque()
        self._in_flight: dict[UUID, TurnJob] = {}
        self.acked: list[UUID] = []
        self.nacked: list[tuple[UUID, bool]] = []

    async def enqueue(self, job: TurnJob) -> None:
        self._pending.append(job)

    async def claim(self, block_seconds: float) -> TurnJob | None:
        if not self._pending:
            return None
        job = self._pending.popleft()
        self._in_flight[job.job_id] = job
        return job

    async def ack(self, job_id: UUID) -> None:
        self._in_flight.pop(job_id, None)
        self.acked.append(job_id)

    async def nack(self, job_id: UUID, *, retry: bool) -> None:
        job = self._in_flight.pop(job_id, None)
        self.nacked.append((job_id, retry))
        if retry and job is not None:
            self._pending.append(job.model_copy(update={"attempt": job.attempt + 1}))


class _Hold:
    def __init__(self, lock: InMemoryThreadLock, key: tuple[str, str]) -> None:
        self._lock = lock
        self._key = key

    async def __aenter__(self) -> None:
        if self._key in self._lock.held:
            raise RuntimeError("thread lock already held: turns of one thread must be serialised")
        self._lock.held.add(self._key)

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._lock.held.discard(self._key)


class InMemoryThreadLock:
    """``ThreadLock`` for single-process tests. Re-entering a held key raises instead of waiting, so a
    test fails loudly when two turns of the same thread overlap."""

    def __init__(self) -> None:
        self.held: set[tuple[str, str]] = set()

    def hold(self, account_id: str, thread_id: str, clinic_id: UUID | None = None) -> _Hold:
        """``clinic_id`` is accepted for the protocol and ignored: the fake is for single-clinic tests."""
        return _Hold(self, (account_id, thread_id))


@dataclass
class FakeTextGenerator:
    """``TextGenerator`` that returns scripted text and records the prompts it received."""

    reply: Callable[[str], str] = lambda prompt: "summary"
    prompts: list[str] = field(default_factory=list[str])
    truncated: bool = False

    async def generate_text(self, prompt: str, *, max_output_tokens: int | None = None) -> GeneratedText:
        self.prompts.append(prompt)
        return GeneratedText(text=self.reply(prompt), truncated=self.truncated)


def new_turn_job(clinic_id: UUID | None = None, *messages: InboundMessage) -> TurnJob:
    return TurnJob(
        job_id=uuid4(),
        clinic_id=clinic_id or uuid4(),
        account_id="acc-1",
        thread_id="thread-1",
        messages=list(messages) or [make_inbound()],
        enqueued_at=now_vn(),
    )


class InMemoryAccountStore:
    """``AccountStore`` for tests of the channels, the scheduler and the engine. Secrets are kept in clear
    here (it is a fake)."""

    def __init__(self, *accounts: AccountConfig) -> None:
        self.accounts: dict[tuple[UUID, str], AccountConfig] = {(a.clinic_id, a.id): a for a in accounts}
        self.bot_tokens: dict[tuple[UUID, str], str] = {}
        self.credentials: dict[tuple[UUID, str], str | None] = {}

    async def get_account(self, clinic_id: UUID, account_id: str) -> AccountConfig | None:
        return self.accounts.get((clinic_id, account_id))

    async def list_accounts(self, clinic_id: UUID) -> list[AccountConfig]:
        return [a for (c, _), a in self.accounts.items() if c == clinic_id]

    async def list_all_enabled_accounts(self) -> list[AccountConfig]:
        return [a for a in self.accounts.values() if a.enabled]

    async def create_account(
        self, clinic_id: UUID, *, account_id: str, label: str, channel: ChannelKind, agent_id: str | None
    ) -> AccountConfig:
        account = AccountConfig(
            id=account_id, clinic_id=clinic_id, label=label, channel=channel, agent_id=agent_id or "default"
        )
        self.accounts[(clinic_id, account_id)] = account
        return account

    async def update_account(
        self, clinic_id: UUID, account_id: str, patch: dict[str, object]
    ) -> AccountConfig | None:
        current = self.accounts.get((clinic_id, account_id))
        if current is None:
            return None
        updated = AccountConfig.model_validate({**current.model_dump(), **patch})
        self.accounts[(clinic_id, account_id)] = updated
        return updated

    async def delete_account(self, clinic_id: UUID, account_id: str) -> bool:
        return self.accounts.pop((clinic_id, account_id), None) is not None

    async def get_bot_token(self, clinic_id: UUID, account_id: str) -> str | None:
        return self.bot_tokens.get((clinic_id, account_id))

    async def set_bot_token(self, clinic_id: UUID, account_id: str, token: str) -> None:
        self.bot_tokens[(clinic_id, account_id)] = token

    async def get_credential(self, clinic_id: UUID, account_id: str) -> str | None:
        return self.credentials.get((clinic_id, account_id))

    async def set_credential(self, clinic_id: UUID, account_id: str, credential: str | None) -> None:
        self.credentials[(clinic_id, account_id)] = credential


class InMemoryAgentStore:
    def __init__(self, *agents: AgentProfile) -> None:
        self.agents: dict[tuple[UUID, str], AgentProfile] = {(a.clinic_id, a.id): a for a in agents}

    async def get_agent(self, clinic_id: UUID, agent_id: str) -> AgentProfile | None:
        return self.agents.get((clinic_id, agent_id))

    async def get_agent_for_account(self, clinic_id: UUID, account: AccountConfig) -> AgentProfile:
        found = self.agents.get((clinic_id, account.agent_id))
        return found or await self.ensure_default_agent(clinic_id)

    async def ensure_default_agent(self, clinic_id: UUID) -> AgentProfile:
        for (c, _), agent in self.agents.items():
            if c == clinic_id and agent.is_default:
                return agent
        agent = AgentProfile(id="default", clinic_id=clinic_id, name="Default", is_default=True)
        self.agents[(clinic_id, agent.id)] = agent
        return agent

    async def list_agents(self, clinic_id: UUID) -> list[AgentProfile]:
        return [a for (c, _), a in self.agents.items() if c == clinic_id]

    async def create_agent(
        self, clinic_id: UUID, *, agent_id: str, name: str, icon: str, persona: str
    ) -> AgentProfile:
        agent = AgentProfile(id=agent_id, clinic_id=clinic_id, name=name, icon=icon, persona=persona)
        self.agents[(clinic_id, agent_id)] = agent
        return agent

    async def update_agent(
        self, clinic_id: UUID, agent_id: str, patch: dict[str, object]
    ) -> AgentProfile | None:
        current = self.agents.get((clinic_id, agent_id))
        if current is None:
            return None
        updated = AgentProfile.model_validate({**current.model_dump(), **patch})
        self.agents[(clinic_id, agent_id)] = updated
        return updated

    async def delete_agent(self, clinic_id: UUID, agent_id: str) -> tuple[bool, str | None]:
        removed = self.agents.pop((clinic_id, agent_id), None)
        return (removed is not None, None if removed is not None else "not found")


_: AccountStore = InMemoryAccountStore()
_agent_store: AgentStore = InMemoryAgentStore()

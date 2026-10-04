# ported from: none (the ``chayLuot`` helper of run-agent-turn.test.ts, shared with ``evals/``)
"""``EngineHarness``: builds an ``AgentEngineDeps`` over the fakes (fake model, fake tool registry, fake
conversation, in-memory account/agent stores and channel registry) and runs one turn. Import in tests only.

The account is the one of the original tests (``acc-test`` pointing at an agent that does not exist, so the
default agent answers) on a personal-account-like channel; policy profile ``staff_assistant`` unless patched,
because the engine tests are not meant to run under review mode (``fake_agent_profile`` says the same).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from pema.agent.agent_loop import AgentEngineDeps, ModelResolver, run_agent_turn
from pema.agent.history_to_model_messages import StoredImage
from pema.agent.model_types import ChatModel, ModelCompletion
from pema.agent.streaming_model_test_helper import Scripted, ScriptedModel
from pema.agent.testing import FakeToolRegistry, make_caps
from pema.agent.testing_conversation import FakeConversation
from pema_contracts.agent_turn import AgentTurnRequest, AgentTurnResult, StepTrace, TurnCallbacks
from pema_contracts.agents import AccountConfig, AgentProfile
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.policy import PermissivePolicyHooks, PolicyHooks
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    FakeChannel,
    InMemoryAccountStore,
    InMemoryAgentStore,
    fake_account_config,
    fake_agent_profile,
    make_inbound,
)

ACCOUNT_ID = "acc-test"
THREAD_ID = "thread-1"


def tin_nhan(text: str = "hôm nay ngày mấy", **extra: object) -> InboundMessage:
    """The message of the original tests (``tinNhan()``); ``extra`` overrides any field."""
    fields: dict[str, object] = {
        "channel": ChannelKind.ZALO_PERSONAL,
        "account_id": ACCOUNT_ID,
        "thread_id": THREAD_ID,
        "sender_id": "user-1",
        "sender_name": "Hải",
        "update_id": "u-1",
        "msg_id": "m1",
        "cli_msg_id": "c1",
        **extra,
    }
    return make_inbound(text, **fields)  # type: ignore[arg-type]


def fake_account(**patch: object) -> AccountConfig:
    fields: dict[str, object] = {
        "id": ACCOUNT_ID,
        "channel": ChannelKind.ZALO_PERSONAL,
        "agent_id": "khong-co-agent-nay",
        "auto_react_enabled": False,
        "typing_indicator_enabled": False,
        **patch,
    }
    return fake_account_config(**fields)


async def no_sleep(_seconds: float) -> None:
    """Instant wait: the rate-limit branch would sleep 5 s for real otherwise."""


@dataclass
class TurnRun:
    result: AgentTurnResult
    trace: list[StepTrace]
    model: ScriptedModel
    callbacks: TurnCallbacks


@dataclass
class EngineHarness:
    conversation: FakeConversation = field(default_factory=FakeConversation)
    registry: FakeToolRegistry = field(default_factory=FakeToolRegistry)
    policy: PolicyHooks = field(default_factory=PermissivePolicyHooks)
    account: AccountConfig = field(default_factory=fake_account)
    agent: AgentProfile = field(default_factory=lambda: fake_agent_profile(id="default", is_default=True))
    images: dict[str, StoredImage] = field(default_factory=dict[str, StoredImage])
    channel_running: bool = True

    def deps(self, model: ChatModel) -> AgentEngineDeps:
        from pema.channels.registry import InMemoryChannelRegistry

        channels = InMemoryChannelRegistry()
        if self.channel_running:
            channels.register(FAKE_CLINIC_ID, FakeChannel(caps=make_caps(), account=self.account.id))

        def resolve(*_args: object) -> ChatModel:
            return model

        resolver: ModelResolver = resolve

        async def download(_url: str) -> StoredImage | None:
            return None

        return AgentEngineDeps(
            accounts=InMemoryAccountStore(self.account),
            agents=InMemoryAgentStore(self.agent),
            conversation=self.conversation,
            image_descriptions=self.conversation,
            tools=self.registry,
            channels=channels,
            load_image=self.images.get,
            download_image=download,
            policy=self.policy,
            resolve_model=resolver,
            sleep=no_sleep,
            retry_initial_delay_s=0.0,
        )

    async def run(
        self,
        script: Sequence[Scripted],
        batch: Sequence[InboundMessage] | None = None,
        *,
        isolated: bool = False,
        fetch_injected: Callable[[], Awaitable[Sequence[InboundMessage]]] | None = None,
        callbacks: TurnCallbacks | None = None,
        model: ScriptedModel | None = None,
    ) -> TurnRun:
        """Run one turn against a model that plays ``script``. Raises ``AgentTurnError`` like the engine."""
        scripted = model or ScriptedModel(script)
        cb = callbacks or TurnCallbacks()
        if fetch_injected is not None:
            cb.fetch_injected_messages = fetch_injected
        request = AgentTurnRequest(
            clinic_id=FAKE_CLINIC_ID,
            account_id=self.account.id,
            batch=list(batch) if batch is not None else [tin_nhan()],
            isolated=isolated,
        )
        result = await run_agent_turn(self.deps(scripted), request, cb)
        return TurnRun(result=result, trace=cb.trace, model=scripted, callbacks=cb)


def completion(text: str) -> Callable[[], ModelCompletion]:
    """Script entry shorthand."""
    from pema.agent.streaming_model_test_helper import tra_loi

    return lambda: tra_loi(text)

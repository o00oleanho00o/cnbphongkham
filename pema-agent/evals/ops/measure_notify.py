"""The notification chain under load, timed with fakes. New module, no zalo-agent original.

The unit under test is the REAL ``NotificationConsumer`` of package O3 (the chain: in-app, push, the personal
Zalo bell after the ack timeout, the team group, the on-call contact) over ``InMemoryChainStore`` and fake
senders. Two kinds of number come out, and the report keeps them apart:

* chain delay, in VIRTUAL seconds: the time between the outbox row being due and the moment each provider is
  called. It is decided by the chain (in-app, push, the team group and the on-call contact at once, the bell
  after the ack timeout, never when the operator acknowledged), not by a network;
* provider time, in REAL microseconds (``time.perf_counter_ns``): what the code around the fake costs, that is
  the text rendering, the PII mask, the guards and the fake call. It is the floor under the latency of a real
  provider; the network time of Zalo, a push service or the bridge is NOT measured here (nothing real runs).

Operators, notices and the share that acknowledge in time are parameters of the scenario.
"""

from __future__ import annotations

import random
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from evals.care.stats import Latency
from pema.care.routing_types import OnCallRow
from pema.clinic.actions.notification_chain import NotifyTarget, PushTarget
from pema.notify.consumer import NotificationConsumer
from pema.notify.providers import (
    FakePushProvider,
    InAppProvider,
    OnCallBellProvider,
    PushResult,
    TeamGroupProvider,
    ZaloBellProvider,
)
from pema.notify.testing import (
    EPOCH,
    FakeClock,
    FakeInternalSender,
    InMemoryChainStore,
    payload,
    settings,
    target,
)
from pema.notify.text import PushMessage
from pema.notify.types import StepResult
from pema.policy.pii import mask_pii
from pema_contracts.live import LiveEventType
from pema_contracts.ops import (
    NotificationLogStatus,
    NotificationProvider,
    NotificationRecipientKind,
    NotificationState,
    NotifySettingsOut,
    PushPlatform,
)

ACK_TIMEOUT_S = 180
LINK_MARK = "\nMở: "
"""The line that starts the deep link in the text of the bell and the group (``render_chat_text``)."""


@dataclass(frozen=True)
class NotifyParameters:
    operators: int = 5
    notices_per_operator: int = 40
    group_notices: int = 200
    on_call_notices: int = 20
    ack_share: float = 0.5
    """The share of user notices acknowledged before the ack timeout (so the bell never rings for them)."""
    seed: int = 20261006


@dataclass
class Timing:
    """Real nanoseconds around each fake, and the virtual delay at each call."""

    clock: FakeClock
    origin: datetime
    real_ns: dict[NotificationProvider, list[int]] = field(
        default_factory=lambda: {provider: [] for provider in NotificationProvider}
    )
    chain_delay_s: dict[NotificationProvider, list[float]] = field(
        default_factory=lambda: {provider: [] for provider in NotificationProvider}
    )

    def record(self, provider: NotificationProvider, started_ns: int) -> None:
        self.real_ns[provider].append(time.perf_counter_ns() - started_ns)
        self.chain_delay_s[provider].append((self.clock.now - self.origin).total_seconds())


class TimedInApp(InAppProvider):
    def __init__(self, timing: Timing) -> None:
        super().__init__(emit=self._emit_event)
        self._timing = timing
        self.events: list[tuple[LiveEventType, UUID | None]] = []

    def _emit_event(self, kind: LiveEventType, ident: UUID | None) -> None:
        self.events.append((kind, ident))

    async def send(self, notice_id: UUID) -> StepResult:
        started = time.perf_counter_ns()
        result = await super().send(notice_id)
        self._timing.record(NotificationProvider.IN_APP, started)
        return result


class TimedPush(FakePushProvider):
    def __init__(self, timing: Timing) -> None:
        super().__init__()
        self._timing = timing

    async def send(self, tokens: Sequence[PushTarget], message: PushMessage) -> PushResult:
        started = time.perf_counter_ns()
        result = await super().send(tokens, message)
        self._timing.record(NotificationProvider.PUSH, started)
        return result


class TimedBell(ZaloBellProvider):
    def __init__(self, sender: FakeInternalSender, timing: Timing) -> None:
        super().__init__(sender)
        self._timing = timing

    async def send(
        self, payload: Mapping[str, object], target: NotifyTarget, settings: NotifySettingsOut
    ) -> StepResult:
        started = time.perf_counter_ns()
        result = await super().send(payload, target, settings)
        self._timing.record(NotificationProvider.ZALO_BELL, started)
        return result


class TimedGroup(TeamGroupProvider):
    def __init__(self, sender: FakeInternalSender, timing: Timing) -> None:
        super().__init__(sender)
        self._timing = timing

    async def send(self, payload: Mapping[str, object], settings: NotifySettingsOut) -> StepResult:
        started = time.perf_counter_ns()
        result = await super().send(payload, settings)
        self._timing.record(NotificationProvider.TEAM_GROUP, started)
        return result


@dataclass(frozen=True)
class ProviderTiming:
    provider: NotificationProvider
    calls: int
    real_us: Latency
    """Microseconds of the code around the fake (the ``Latency`` slots hold microseconds here)."""
    chain_delay_s: tuple[float, float]
    """Smallest and largest virtual delay from "due" to "called"; ``(0, 0)`` when never called."""


@dataclass(frozen=True)
class NotifyReport:
    parameters: NotifyParameters
    notices: int
    by_provider: tuple[ProviderTiming, ...]
    sent: int
    skipped: int
    failed: int
    pending_at_end: int
    acked_before_bell: int
    bell_rung_after_ack: int
    bell_rung_unacked: int
    unacked_total: int
    texts_checked: int
    texts_with_pii: int


def _microseconds(samples_ns: Sequence[int]) -> Latency:
    # ``Latency.from_ns`` divides by 1e6 (nanoseconds to milliseconds); a thousand times more makes it microseconds.
    return Latency.from_ns([value * 1000 for value in samples_ns])


async def measure_notify(params: NotifyParameters | None = None) -> NotifyReport:
    use = params or NotifyParameters()
    rng = random.Random(use.seed)
    clock = FakeClock(EPOCH)
    store = InMemoryChainStore(clock)
    store.settings = settings(push_enabled=True, ack_timeout_s=ACK_TIMEOUT_S)
    timing = Timing(clock, EPOCH)
    sender = FakeInternalSender()
    consumer = NotificationConsumer(
        store=store,
        in_app=TimedInApp(timing),
        bell=TimedBell(sender, timing),
        group=TimedGroup(sender, timing),
        on_call=OnCallBellProvider(sender),
        push=TimedPush(timing),
        clock=clock,
    )
    store.on_call = [
        OnCallRow(
            id=UUID(int=7), zalo_number="0000000001", owner="Trực (mẫu)", valid_from=EPOCH.replace(month=1)
        )
    ]

    operators = [uuid4() for _ in range(use.operators)]
    for index, user in enumerate(operators):
        store.targets[user] = target(
            user,
            zalo=f"zalo-op-{index}",
            pushes=(PushTarget(uuid4(), PushPlatform.ANDROID, f"synthetic-token-{index}"),),
        )
    user_notices = [
        store.add(NotificationRecipientKind.USER, user, body=payload())
        for user in operators
        for _ in range(use.notices_per_operator)
    ]
    for _ in range(use.group_notices):
        store.add(NotificationRecipientKind.TEAM_GROUP, None, body=payload())
    for _ in range(use.on_call_notices):
        store.add(NotificationRecipientKind.ON_CALL, None, body=payload(event="handoff_on_call"))

    batch = len(store.rows) + 10
    await consumer.run_once(limit=batch)  # first pass: in-app, push, group, on-call; the bell is scheduled
    acked = {notice for notice in user_notices if rng.random() < use.ack_share}
    for notice_id in acked:
        store.ack(notice_id)
    clock.advance(seconds=ACK_TIMEOUT_S)
    await consumer.run_once(limit=batch)  # second pass: the bell of the notices nobody acknowledged

    by_provider = tuple(
        ProviderTiming(
            provider,
            len(timing.real_ns[provider]),
            _microseconds(timing.real_ns[provider]),
            (min(timing.chain_delay_s[provider]), max(timing.chain_delay_s[provider]))
            if timing.chain_delay_s[provider]
            else (0.0, 0.0),
        )
        for provider in (
            NotificationProvider.IN_APP,
            NotificationProvider.PUSH,
            NotificationProvider.ZALO_BELL,
            NotificationProvider.TEAM_GROUP,
        )
    )
    rows = list(store.rows.values())
    rung = {
        entry.outbox_id
        for entry in store.log
        if entry.provider is NotificationProvider.ZALO_BELL and entry.status is NotificationLogStatus.SENT
    }
    unacked = set(user_notices) - acked
    texts = [text for _, text in sender.sent]
    # the guard of the product runs on the summary and the label; the deep link carries an id only and is
    # checked apart (its last UUID group can be 12 digits, which the national-id pattern would flag)
    bodies = [text.split(LINK_MARK)[0] for text in texts]
    return NotifyReport(
        parameters=use,
        notices=len(rows),
        by_provider=by_provider,
        sent=sum(1 for row in rows if row.state is NotificationState.SENT),
        skipped=sum(1 for row in rows if row.state is NotificationState.SKIPPED),
        failed=sum(1 for row in rows if row.state is NotificationState.FAILED),
        pending_at_end=sum(1 for row in rows if row.state is NotificationState.PENDING),
        acked_before_bell=len(acked),
        bell_rung_after_ack=len(rung & acked),
        bell_rung_unacked=len(rung & unacked),
        unacked_total=len(unacked),
        texts_checked=len(texts),
        texts_with_pii=sum(1 for body in bodies if mask_pii(body).changed),
    )

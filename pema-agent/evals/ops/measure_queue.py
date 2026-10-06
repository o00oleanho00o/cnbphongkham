"""One identity under load: queue wait and gap compliance. New module, no zalo-agent original.

The unit under test is the REAL ``IdentitySendQueue`` of package O4 (``pema.channels.identity_send_queue``): the
kill switch, the proactive daily cap, the shared gap, the per-identity lock. Only the clock, the sleep, the random
source and the channel are fakes, so nothing sleeps for real and the numbers are in VIRTUAL seconds (what a
customer would wait on a clinic whose limits are the ones below), not in wall time.

Two runs per identity:

* ``simulate_identity``: the traffic of a working morning in time order. Every send request (an operator's reply,
  the care agent's automatic reply, a proactive reminder of the scheduler) arrives at its own time, asks the
  queue and leaves when the gap allows. One identity is one single server, and different identities do not
  share any state (the lock key and the last-send stamp carry the account id), so each identity is simulated on
  its own clock. ``queue wait`` = the time between the request and the moment the message leaves.
* ``burst``: every request of the identity at the same instant, concurrently (``asyncio.gather``): the worst
  case of the lock. It must still leave one gap apart.

Gap compliance: every pair of consecutive messages that left through one identity is at least the identity's
MINIMUM gap apart, whoever sent them. The numbers of the limits (gap, cap, arrivals) are the parameters of the
scenario, printed in the report; they are not measurements.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from uuid import UUID

from evals.care.stats import Latency, percentile
from pema.channels.identity_send_queue import IdentitySendQueue, InMemorySendSlotBackend
from pema_contracts.channel import ChannelKind, SendResult, SendStatus
from pema_contracts.common import VN_TZ
from pema_contracts.errors import ErrorCode
from pema_contracts.ops import EffectiveLimits, IdentityOut, IdentityPurpose, LimitOverrides

CLINIC_ID = UUID(int=1)
EPSILON = 1e-6
"""Float slack of the virtual clock (sums of many sleeps)."""
MORNING = datetime(2026, 9, 21, 7, 0, tzinfo=VN_TZ).timestamp()
"""The virtual day starts at 07:00 clinic time, so a four hour run never crosses the midnight that resets
the daily cap."""

AGENT = "agent"
SCHEDULER = "scheduler"


@dataclass(frozen=True)
class Request:
    """One send request: when it arrives (seconds after the start), who asks, and whether it is proactive."""

    at: float
    sender: str
    proactive: bool = False


@dataclass(frozen=True)
class IdentityScenario:
    account_id: str
    gap_min_s: int
    gap_max_s: int
    daily_cap: int | None
    requests: tuple[Request, ...]


@dataclass(frozen=True)
class Leave:
    """A message that left: when it was asked for, when it left, by whom."""

    asked_at: float
    left_at: float
    sender: str
    proactive: bool

    @property
    def wait(self) -> float:
        return self.left_at - self.asked_at


@dataclass(frozen=True)
class IdentityResult:
    account_id: str
    requested: int
    sent: int
    rejected_cap: int
    rejected_other: int
    gap_min_s: int
    gap_max_s: int
    leaves: tuple[Leave, ...] = field(default_factory=tuple)

    @property
    def gaps(self) -> list[float]:
        times = [leave.left_at for leave in self.leaves]
        return [later - earlier for earlier, later in pairwise(times)]

    @property
    def gap_violations(self) -> int:
        return sum(1 for gap in self.gaps if gap < self.gap_min_s - EPSILON)

    @property
    def waits(self) -> list[float]:
        return [leave.wait for leave in self.leaves]

    def waits_of(self, sender: str) -> list[float]:
        return [leave.wait for leave in self.leaves if leave.sender == sender]

    @property
    def senders(self) -> list[str]:
        return sorted({leave.sender for leave in self.leaves})

    @property
    def drain_s(self) -> float:
        """From the first request to the last message leaving."""
        if not self.leaves:
            return 0.0
        return self.leaves[-1].left_at - min(leave.asked_at for leave in self.leaves)


class VirtualClock:
    """Moves only when somebody sleeps (or the driver sets it): a test measures the waits it asked for."""

    def __init__(self, start: float) -> None:
        self.now = start

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.now += seconds
        await asyncio.sleep(0)


def identity_row(scenario: IdentityScenario) -> IdentityOut:
    return IdentityOut(
        id=scenario.account_id,
        label=f"Danh tính {scenario.account_id}",
        channel=ChannelKind.ZALO_PERSONAL,
        purpose=IdentityPurpose.CUSTOMER,
        enabled=True,
        channel_enabled=True,
        kill_switch_on=False,
        bridge_state=None,
        overrides=LimitOverrides(),
        effective=EffectiveLimits(
            send_gap_min_s=scenario.gap_min_s, send_gap_max_s=scenario.gap_max_s, daily_cap=scenario.daily_cap
        ),
    )


def build_queue(scenario: IdentityScenario, clock: VirtualClock, rng: random.Random) -> IdentitySendQueue:
    row = identity_row(scenario)

    async def lookup(account_id: str) -> IdentityOut | None:
        return row if account_id == row.id else None

    return IdentitySendQueue(
        clinic_id=CLINIC_ID,
        lookup=lookup,
        backend=InMemorySendSlotBackend(clock.clock),
        clock=clock.clock,
        sleep=clock.sleep,
        uniform=rng.uniform,
    )


async def _send_one(
    queue: IdentitySendQueue, clock: VirtualClock, scenario: IdentityScenario, request: Request, base: float
) -> tuple[Leave | None, ErrorCode | None]:
    """Admit, then send one message through the identity. Returns what left, or why it was refused."""
    admission = await queue.admit(scenario.account_id, proactive=request.proactive)
    if admission.rejection is not None:
        return None, admission.rejection.error_code
    left: list[float] = []

    async def call() -> SendResult:
        left.append(clock.now)
        return SendResult(status=SendStatus.SENT, external_message_id=f"ext-{len(left)}")

    result = await queue.send(scenario.account_id, call)
    await queue.settle(admission, sent=result.status is SendStatus.SENT)
    if result.status is not SendStatus.SENT or not left:
        return None, result.error_code
    return Leave(base + request.at, left[0], request.sender, request.proactive), None


async def simulate_identity(scenario: IdentityScenario, *, seed: int) -> IdentityResult:
    """The requests in time order through one identity (single server, virtual clock)."""
    clock = VirtualClock(MORNING)
    queue = build_queue(scenario, clock, random.Random(seed))
    leaves: list[Leave] = []
    cap_rejected = other_rejected = 0
    for request in sorted(scenario.requests, key=lambda r: r.at):
        clock.now = max(clock.now, MORNING + request.at)  # the request arrives; the server may still be busy
        leave, refusal = await _send_one(queue, clock, scenario, request, MORNING)
        if leave is not None:
            leaves.append(leave)
        elif refusal is ErrorCode.CHANNEL_DAILY_CAP_REACHED:
            cap_rejected += 1
        else:
            other_rejected += 1
    return IdentityResult(
        scenario.account_id,
        len(scenario.requests),
        len(leaves),
        cap_rejected,
        other_rejected,
        scenario.gap_min_s,
        scenario.gap_max_s,
        tuple(leaves),
    )


async def burst(scenario: IdentityScenario, *, seed: int) -> IdentityResult:
    """All requests at the same instant, concurrently: the lock and the gap must still serialise them."""
    clock = VirtualClock(MORNING)
    queue = build_queue(scenario, clock, random.Random(seed))
    outcomes = await asyncio.gather(
        *(
            _send_one(queue, clock, scenario, Request(0.0, r.sender, r.proactive), MORNING)
            for r in scenario.requests
        )
    )
    leaves = sorted((leave for leave, _ in outcomes if leave is not None), key=lambda leave: leave.left_at)
    cap_rejected = sum(
        1 for leave, code in outcomes if leave is None and code is ErrorCode.CHANNEL_DAILY_CAP_REACHED
    )
    other = sum(
        1 for leave, code in outcomes if leave is None and code is not ErrorCode.CHANNEL_DAILY_CAP_REACHED
    )
    return IdentityResult(
        scenario.account_id,
        len(scenario.requests),
        len(leaves),
        cap_rejected,
        other,
        scenario.gap_min_s,
        scenario.gap_max_s,
        tuple(leaves),
    )


# ----------------------------------------------------------------------------------------- scenario
@dataclass(frozen=True)
class LoadParameters:
    """The knobs of the scenario. Printed in the report; none of them is a measurement."""

    threads: int = 200
    operators: int = 5
    agent_replies: int = 40
    reminders: int = 20
    other_identity_replies: int = 30
    window_s: int = 2 * 3600
    gap_min_s: int = 15
    gap_max_s: int = 45
    daily_cap: int | None = 12
    other_gap_min_s: int = 5
    other_gap_max_s: int = 15
    seed: int = 20261006


def operator_name(index: int) -> str:
    return f"operator-{index + 1}"


def build_scenarios(params: LoadParameters) -> tuple[IdentityScenario, IdentityScenario]:
    """200 synthetic threads on identity ``long``: each thread arrives at a random time of the window, one of
    the five operators replies 20 to 120 seconds later (a person types), the agent also sends automatic replies
    and the scheduler proactive reminders; a second identity ``hoa`` carries a lighter load of its own."""
    rng = random.Random(params.seed)
    arrivals = sorted(rng.uniform(0, params.window_s) for _ in range(params.threads))
    requests: list[Request] = [
        Request(arrival + rng.uniform(20, 120), operator_name(index % params.operators))
        for index, arrival in enumerate(arrivals)
    ]
    requests += [Request(rng.uniform(0, params.window_s), AGENT) for _ in range(params.agent_replies)]
    requests += [
        Request(rng.uniform(0, params.window_s), SCHEDULER, proactive=True) for _ in range(params.reminders)
    ]
    long = IdentityScenario("long", params.gap_min_s, params.gap_max_s, params.daily_cap, tuple(requests))
    other = [
        Request(rng.uniform(0, params.window_s), operator_name(index % params.operators))
        for index in range(params.other_identity_replies)
    ]
    hoa = IdentityScenario("hoa", params.other_gap_min_s, params.other_gap_max_s, None, tuple(other))
    return long, hoa


@dataclass(frozen=True)
class QueueReport:
    parameters: LoadParameters
    timed: tuple[IdentityResult, ...]
    burst: IdentityResult
    wait_by_sender: dict[str, Latency]

    @property
    def violations(self) -> int:
        return sum(result.gap_violations for result in (*self.timed, self.burst))


def seconds_summary(values: Sequence[float]) -> tuple[float, float, float]:
    """p50, p95, max in seconds (0 for no data)."""
    return percentile(values, 50), percentile(values, 95), max(values) if values else 0.0


async def measure_queue(params: LoadParameters | None = None) -> QueueReport:
    use = params or LoadParameters()
    long, hoa = build_scenarios(use)
    timed_long = await simulate_identity(long, seed=use.seed)
    timed_hoa = await simulate_identity(hoa, seed=use.seed + 1)
    burst_long = await burst(long, seed=use.seed + 2)
    by_sender = {
        sender: Latency(
            len(timed_long.waits_of(sender)),
            *seconds_summary(timed_long.waits_of(sender)),
        )
        for sender in timed_long.senders
    }
    return QueueReport(use, (timed_long, timed_hoa), burst_long, by_sender)

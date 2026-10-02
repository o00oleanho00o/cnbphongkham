"""In-memory fakes of the ports of package M for tests (not imported by production code).

New module, like ``pema_contracts.testing``. Everything is synthetic: codes such as ``P900`` do not exist, the
account and thread ids are made up. The fakes count their calls so a test can assert how many times the
"LLM" (``FakeHarness``) was called.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pema.care.events import CareEvent
from pema.care.models import ControlState
from pema.care.ports import (
    CareAgentSnapshot,
    ChannelTarget,
    DeferredSend,
    HarnessDecision,
    HarnessRequest,
    PatientContext,
    SendOutcome,
    TickFinding,
)
from pema.care.window import SendWindow
from pema_contracts.installation import installation_clinic_id_or_none
from pema_contracts.scheduler import ProactiveSlotResult

FIXTURE_CLINIC_ID = UUID("00000000-0000-4000-8000-0000000000c1")


class FakeClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


def vn(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    """A wall time in Asia/Ho_Chi_Minh (UTC+7, no DST), as an aware datetime."""
    return datetime(year, month, day, hour, minute, tzinfo=UTC) - timedelta(hours=7)


@dataclass
class ActionRow:
    care_agent_id: UUID
    action_type: str
    disposition: str
    depth: str | None
    at: datetime


class InMemoryCareStore:
    """``CareStore`` + ``PatientDirectory`` over dicts."""

    def __init__(self) -> None:
        self.agents: dict[UUID, CareAgentSnapshot] = {}
        self.refs: dict[str, UUID] = {}
        self.states: dict[UUID, ControlState] = {}
        self.actions: list[ActionRow] = []
        self.last_tick: dict[UUID, datetime] = {}

    def add_patient(
        self, patient_ref: str, *, paused: bool = False, clinic_id: UUID | None = None
    ) -> CareAgentSnapshot:
        agent = CareAgentSnapshot(
            id=uuid4(),
            clinic_id=clinic_id or installation_clinic_id_or_none() or FIXTURE_CLINIC_ID,
            patient_id=uuid4(),
            profile="patient_channel",
            paused=paused,
        )
        self.agents[agent.id] = agent
        self.refs[patient_ref] = agent.id
        return agent

    async def get_care_agent(self, care_agent_id: UUID) -> CareAgentSnapshot | None:
        return self.agents.get(care_agent_id)

    async def get_control_state(self, patient_id: UUID) -> ControlState:
        return self.states.get(patient_id, ControlState.AUTO)

    async def list_active_care_agents(self, *, after: UUID | None, limit: int) -> Sequence[CareAgentSnapshot]:
        ordered = sorted((a for a in self.agents.values() if not a.paused), key=lambda a: a.id)
        if after is not None:
            ordered = [a for a in ordered if a.id > after]
        return ordered[:limit]

    async def record_action(
        self, care_agent_id: UUID, *, action_type: str, disposition: str, depth: str | None, at: datetime
    ) -> None:
        self.actions.append(ActionRow(care_agent_id, action_type, disposition, depth, at))

    async def touch_last_tick(self, care_agent_ids: Sequence[UUID], at: datetime) -> None:
        for care_agent_id in care_agent_ids:
            self.last_tick[care_agent_id] = at

    async def care_agent_id_for(self, patient_ref: str) -> UUID | None:
        return self.refs.get(patient_ref)


class FakeContextLoader:
    def __init__(
        self,
        *,
        channel: ChannelTarget | None = ChannelTarget("acct-fake", "thread-fake"),
        marketing_opt_out: bool = False,
    ) -> None:
        self._channel = channel
        self._opt_out = marketing_opt_out
        self.calls = 0

    async def load(self, agent: CareAgentSnapshot, event: CareEvent) -> PatientContext:
        self.calls += 1
        return PatientContext(
            patient_ref=event.patient_ref,
            patient_id=agent.patient_id,
            channel=self._channel,
            marketing_opt_out=self._opt_out,
        )


class FakeHarness:
    """The "LLM": counts calls and remembers the order of the events it was asked about."""

    def __init__(self, decision: HarnessDecision | None = None, *, fail: bool = False) -> None:
        self.decision = decision or HarnessDecision(text="Xin chào (mẫu)", action_type="reply", depth="D1")
        self.fail = fail
        self.requests: list[HarnessRequest] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    async def process(self, request: HarnessRequest) -> HarnessDecision:
        self.requests.append(request)
        if self.fail:
            raise RuntimeError("model unavailable")
        return self.decision


class FakeChannel:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.sent: list[tuple[ChannelTarget, str, bool]] = []

    async def send(self, target: ChannelTarget, text: str, *, proactive: bool) -> SendOutcome:
        self.sent.append((target, text, proactive))
        return SendOutcome(ok=self.ok, error_code=None if self.ok else "fake_rejected")


class FakeScheduler:
    def __init__(self) -> None:
        self.deferred: list[DeferredSend] = []

    async def defer_send(self, request: DeferredSend) -> None:
        self.deferred.append(request)


class FakeReview:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.drafts: list[tuple[UUID, str, str, str]] = []

    async def create_draft(
        self, agent: CareAgentSnapshot, patient_ref: str, text: str, reason: str
    ) -> str | None:
        self.drafts.append((agent.id, patient_ref, text, reason))
        return str(uuid4()) if self.ok else None


class FakeGuard:
    """``ProactiveSendGuard`` over a dict (the atomic part is trivially atomic in one event loop)."""

    def __init__(self) -> None:
        self.counts: dict[tuple[str, str], int] = {}

    async def reserve_slot(self, scope_key: str, day_key: str, max_per_day: int) -> ProactiveSlotResult:
        key = (scope_key, day_key)
        current = self.counts.get(key, 0)
        if current >= max_per_day:
            return ProactiveSlotResult(reserved=False, count=current, cap=max_per_day)
        self.counts[key] = current + 1
        return ProactiveSlotResult(reserved=True, count=current + 1, cap=max_per_day)

    async def refund_slot(self, scope_key: str, day_key: str) -> None:
        key = (scope_key, day_key)
        self.counts[key] = max(0, self.counts.get(key, 0) - 1)

    async def reserve_cap_notice(self, scope_key: str, day_key: str) -> bool:
        return True

    async def revert_cap_notice(self, scope_key: str, day_key: str) -> None:
        return None


class FixedWindow:
    def __init__(self, window: SendWindow | None = None) -> None:
        self.window = window or SendWindow()

    async def get(self, clinic_id: UUID) -> SendWindow:
        return self.window


class AlwaysAutoSend:
    """``AutonomyPolicy`` that lets everything go out (stands in for an agent above L0)."""

    async def may_auto_send(self, agent: CareAgentSnapshot, decision: HarnessDecision, now: datetime) -> bool:
        return True


@dataclass
class FakeTickRules:
    """Findings by ``patient_ref``; one batch call per ``findings`` call (``batches`` counts them)."""

    needs_draft: Mapping[str, bool] = field(default_factory=dict[str, bool])
    refs: Mapping[UUID, str] = field(default_factory=dict[UUID, str])
    batches: int = 0

    async def findings(self, agents: Sequence[CareAgentSnapshot], now: datetime) -> Sequence[TickFinding]:
        self.batches += 1
        found: list[TickFinding] = []
        for agent in agents:
            ref = self.refs.get(agent.id)
            if ref is not None and ref in self.needs_draft:
                found.append(
                    TickFinding(
                        care_agent_id=agent.id,
                        patient_ref=ref,
                        kind="stale_pending",
                        needs_draft=self.needs_draft[ref],
                    )
                )
        return found

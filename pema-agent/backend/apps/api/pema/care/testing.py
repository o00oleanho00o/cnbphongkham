"""In-memory fakes of the ports of package M for tests (not imported by production code).

New module, like ``pema_contracts.testing``. Everything is synthetic: codes such as ``P900`` do not exist, the
account and thread ids are made up. The fakes count their calls so a test can assert how many times the
"LLM" (``FakeHarness``) was called.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

from pema.agent.model_types import ChatModel
from pema.care.autonomy import KillSwitchState
from pema.care.budget import TurnBudget, TurnMode
from pema.care.events import CareEvent
from pema.care.handoff_types import DepthLlmOutput, HandoffConfig, InvalidTransitionError, level_code
from pema.care.models import ControlState, TaskStatus
from pema.care.ports import (
    AutonomyOverride,
    CareAgentSnapshot,
    ChannelTarget,
    ControlSnapshot,
    DeferredSend,
    DepthError,
    FreeSlot,
    HandoffRequestSnapshot,
    HandoffSettings,
    HandoffSpec,
    HarnessDecision,
    HarnessRequest,
    KbSourceBrief,
    OpenedHandoff,
    PatientContext,
    ReleaseSpec,
    SendOutcome,
    SlotQuery,
    TickFinding,
)
from pema.care.specialists.delegate import DelegationService
from pema.care.specialists.reviewer import ChecklistRunner, ReviewChecklist, StaticChecklist
from pema.care.specialists.runner import LlmSpecialistRunner
from pema.care.specialists.scope import CareTurnScope
from pema.care.specialists.spec import REVIEWER_ID
from pema.care.specialists.store import all_specs
from pema.care.specialists.toolkit import SpecialistToolkit
from pema.care.task_result import TaskResult
from pema.care.window import SendWindow
from pema_contracts.clinic_actions import AgentFacingClinicActions
from pema_contracts.common import JsonObject
from pema_contracts.installation import installation_clinic_id_or_none
from pema_contracts.knowledge import KbHit
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


# ------------------------------------------------------------------------------------- M2b fakes
class InMemoryControlStore:
    """``ControlStore`` over dicts. It shares the control states and the action log with an
    ``InMemoryCareStore`` so a turn loop built on that store sees every transition. Atomic like the SQL
    one (no ``await`` between the check and the change)."""

    def __init__(self, care: InMemoryCareStore) -> None:
        self.care = care
        self.requests: list[HandoffRequestSnapshot] = []
        self.controls: dict[UUID, ControlSnapshot] = {}
        self.memory: list[tuple[UUID, str, str]] = []
        self.override_log: list[tuple[UUID, AutonomyOverride]] = []

    def _agent(self, patient_id: UUID) -> CareAgentSnapshot:
        for agent in self.care.agents.values():
            if agent.patient_id == patient_id:
                return agent
        raise InvalidTransitionError("no care agent for this patient")

    def _state(self, patient_id: UUID) -> ControlState:
        return self.care.states.get(patient_id, ControlState.AUTO)

    def _open(self, patient_id: UUID) -> HandoffRequestSnapshot | None:
        for request in reversed(self.requests):
            if request.patient_id == patient_id and request.outcome is None:
                return request
        return None

    def _replace(self, request: HandoffRequestSnapshot) -> None:
        self.requests = [request if r.id == request.id else r for r in self.requests]

    def _log(self, agent: CareAgentSnapshot, action: str, depth: str | None, at: datetime) -> None:
        self.care.actions.append(ActionRow(agent.id, action, "paused", depth, at))

    async def get_control(self, patient_id: UUID) -> ControlSnapshot:
        return self.controls.get(patient_id, ControlSnapshot(self._state(patient_id)))

    async def agent_for_patient(self, patient_id: UUID) -> CareAgentSnapshot | None:
        try:
            return self._agent(patient_id)
        except InvalidTransitionError:
            return None

    async def record_action(
        self, care_agent_id: UUID, *, action_type: str, disposition: str, depth: str | None, at: datetime
    ) -> None:
        await self.care.record_action(
            care_agent_id, action_type=action_type, disposition=disposition, depth=depth, at=at
        )

    async def get_open_request(self, patient_id: UUID) -> HandoffRequestSnapshot | None:
        return self._open(patient_id)

    async def open_handoff(
        self, agent: CareAgentSnapshot, spec: HandoffSpec, *, log_action: str, at: datetime
    ) -> OpenedHandoff:
        if self._state(agent.patient_id) is not ControlState.AUTO:
            existing = self._open(agent.patient_id) or next(
                (r for r in reversed(self.requests) if r.patient_id == agent.patient_id), None
            )
            if existing is None:
                raise InvalidTransitionError("conversation is not in AUTO and has no handoff request")
            return OpenedHandoff(existing, created=False)
        request = HandoffRequestSnapshot(
            id=uuid4(),
            patient_id=agent.patient_id,
            care_agent_id=agent.id,
            reason=spec.reason,
            summary=spec.summary,
            depth=spec.depth,
            confidence=spec.confidence,
            required_skill=spec.required_skill,
            urgency=spec.urgency,
            created_at=at,
        )
        self.requests.append(request)
        self.care.states[agent.patient_id] = ControlState.HANDOFF_ROUTING
        self.controls[agent.patient_id] = ControlSnapshot(ControlState.HANDOFF_ROUTING, since=at)
        self._log(agent, log_action, spec.depth, at)
        return OpenedHandoff(request, created=True)

    async def accept(
        self, patient_id: UUID, staff_id: UUID, *, log_action: str, at: datetime
    ) -> HandoffRequestSnapshot:
        agent = self._agent(patient_id)
        request = self._open(patient_id)
        if self._state(patient_id) is not ControlState.HANDOFF_ROUTING or request is None:
            raise InvalidTransitionError(f"cannot accept from {self._state(patient_id).value}")
        accepted = replace(request, accepted_by=staff_id, outcome="accepted")
        self._replace(accepted)
        self.care.states[patient_id] = ControlState.STAFF
        self.controls[patient_id] = ControlSnapshot(ControlState.STAFF, since=at, staff_owner=staff_id)
        self._log(agent, log_action, request.depth, at)
        return accepted

    async def record_decline(
        self, patient_id: UUID, staff_id: UUID, *, log_action: str, at: datetime
    ) -> HandoffRequestSnapshot:
        agent = self._agent(patient_id)
        request = self._open(patient_id)
        if self._state(patient_id) is not ControlState.HANDOFF_ROUTING or request is None:
            raise InvalidTransitionError(f"cannot decline from {self._state(patient_id).value}")
        self._log(agent, log_action, request.depth, at)
        return request

    async def release(
        self, patient_id: UUID, staff_id: UUID, spec: ReleaseSpec, *, log_action: str, at: datetime
    ) -> ControlSnapshot:
        agent = self._agent(patient_id)
        if self._state(patient_id) is not ControlState.STAFF:
            raise InvalidTransitionError(f"cannot release from {self._state(patient_id).value}")
        self.care.states[patient_id] = ControlState.AUTO
        snapshot = ControlSnapshot(ControlState.AUTO, since=at, release_note=spec.release_note)
        self.controls[patient_id] = snapshot
        if spec.memory_fact is not None:
            self.memory.append((agent.id, spec.memory_fact, "staff"))
        self._log(agent, log_action, None, at)
        if spec.override is not None:
            self.override_log.append((agent.id, spec.override))
            until = spec.override.until.isoformat() if spec.override.until else None
            self.care.agents[agent.id] = replace(
                agent, autonomy_override={"level": level_code(spec.override.level), "until": until}
            )
            self._log(agent, f"autonomy:override_set:level{spec.override.level}", None, at)
        return snapshot

    async def set_auto_release_after(
        self, patient_id: UUID, after: timedelta | None, *, log_action: str, at: datetime
    ) -> None:
        agent = self._agent(patient_id)
        current = self.controls.get(patient_id, ControlSnapshot(self._state(patient_id)))
        self.controls[patient_id] = replace(current, auto_release_after=after)
        self._log(agent, log_action, None, at)


class FakeSuggestions:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.items: list[tuple[UUID, str, str, ControlState]] = []

    async def create_suggestion(
        self, agent: CareAgentSnapshot, patient_ref: str, text: str, state: ControlState
    ) -> str | None:
        self.items.append((agent.id, patient_ref, text, state))
        return str(uuid4()) if self.ok else None


class FakeDepthLlm:
    """The "model" of the depth classifier: counts calls, returns a fixed answer (or None, or raises)."""

    def __init__(self, answer: DepthLlmOutput | None = None, *, fail: bool = False) -> None:
        self.answer = answer
        self.fail = fail
        self.calls: list[str] = []

    async def classify(self, masked_text: str, *, instruction: str) -> DepthLlmOutput | None:
        self.calls.append(masked_text)
        if self.fail:
            raise RuntimeError("model unavailable")
        return self.answer


class StaticTexts:
    """``MessageTextSource`` that returns the same texts for every event."""

    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)

    async def patient_texts(self, agent: CareAgentSnapshot, event: CareEvent) -> Sequence[str]:
        return self.texts


class StaticHandoffConfig:
    """``HandoffConfigSource`` with a fixed config; ``reads`` counts how often it was read."""

    def __init__(self, config: HandoffConfig | None = None) -> None:
        self.config = config or HandoffConfig()
        self.reads = 0

    async def get(self, clinic_id: UUID) -> HandoffSettings:
        self.reads += 1
        return HandoffSettings("instruction (fixture)", self.config)


# ------------------------------------------------------------------------------------------ M4
@dataclass
class TaskRow:
    id: UUID
    parent_id: UUID | None
    care_agent_id: UUID
    agent_id: str
    status: str = TaskStatus.RUNNING.value
    input: JsonObject = field(default_factory=dict[str, Any])
    result: TaskResult | None = None
    tokens: int = 0
    cost: Decimal = Decimal(0)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    deadline_at: datetime | None = None
    error: str | None = None


class InMemoryTaskStore:
    """``TaskStore`` over a list, with the same depth rule as ``SqlTaskStore``."""

    def __init__(self) -> None:
        self.rows: dict[UUID, TaskRow] = {}

    async def create_root(self, care_agent_id: UUID, *, started_at: datetime, deadline_at: datetime) -> UUID:
        row = TaskRow(
            uuid4(), None, care_agent_id, "care-turn", started_at=started_at, deadline_at=deadline_at
        )
        self.rows[row.id] = row
        return row.id

    async def create_child(
        self,
        parent_id: UUID,
        *,
        agent_id: str,
        input: JsonObject,
        started_at: datetime,
        deadline_at: datetime,
    ) -> UUID:
        parent = self.rows[parent_id]
        if parent.parent_id is not None:
            raise DepthError("a delegation cannot delegate (depth 1)")
        row = TaskRow(
            uuid4(), parent.id, parent.care_agent_id, agent_id, input=input, started_at=started_at,
            deadline_at=deadline_at,
        )  # fmt: skip
        self.rows[row.id] = row
        return row.id

    async def finish(
        self,
        task_id: UUID,
        *,
        status: TaskStatus,
        result: TaskResult | None,
        tokens: int,
        cost: Decimal,
        finished_at: datetime,
        error: str | None = None,
    ) -> None:
        row = self.rows[task_id]
        row.status, row.result, row.tokens, row.cost = status.value, result, tokens, cost
        row.finished_at, row.error = finished_at, error

    def depth(self, task_id: UUID) -> int:
        depth, parent = 0, self.rows[task_id].parent_id
        while parent is not None:
            depth, parent = depth + 1, self.rows[parent].parent_id
        return depth

    def children(self) -> list[TaskRow]:
        return [r for r in self.rows.values() if r.parent_id is not None]


class FakeSlots:
    """``SlotSearch``: the same slots for every query; counts calls."""

    def __init__(self, slots: Sequence[FreeSlot] = ()) -> None:
        self.slots = list(slots)
        self.queries: list[SlotQuery] = []

    async def search(self, query: SlotQuery) -> Sequence[FreeSlot]:
        self.queries.append(query)
        return self.slots


class FakeKnowledge:
    """``KnowledgeAccess``: hits by exact question; everything else is empty."""

    def __init__(self, hits: Mapping[str, Sequence[KbHit]] | None = None) -> None:
        self.hits = dict(hits or {})
        self.searches: list[tuple[str, bool]] = []
        self.ingested: list[str] = []

    async def search(self, question: str, *, only_approved: bool, limit: int = 5) -> list[KbHit]:
        self.searches.append((question, only_approved))
        return list(self.hits.get(question, []))

    async def ingest_text(self, name: str, text: str) -> KbSourceBrief:
        self.ingested.append(name)
        return KbSourceBrief("src-fake", name, "cho_xu_ly", False)

    async def list_sources(self) -> list[KbSourceBrief]:
        return [KbSourceBrief("src-fake", "Hướng dẫn mẫu", "san_sang", True)]


class FakeConfirmPolicy:
    def __init__(self, *, l1: bool = False) -> None:
        self.l1 = l1

    async def l1_applies(self, care_agent_id: UUID, now: datetime) -> bool:
        return self.l1


class FakeActions:
    """The one method of ``AgentFacingClinicActions`` the Scheduler calls; records the proposals."""

    def __init__(self) -> None:
        self.proposals: list[Any] = []

    async def propose_appointment(self, ctx: object, request: Any) -> Any:
        self.proposals.append(request)
        return SimpleNamespace(id=uuid4())


@dataclass
class DelegationRig:
    """A ``DelegationService`` over in-memory fakes, with one care turn ready to delegate from."""

    service: DelegationService
    scope: CareTurnScope
    tasks: InMemoryTaskStore
    store: InMemoryCareStore
    clock: FakeClock
    slots: FakeSlots
    knowledge: FakeKnowledge
    actions: FakeActions
    toolkit: SpecialistToolkit


def make_rig(
    *,
    models: Mapping[str, ChatModel] | None = None,
    slots: Sequence[FreeSlot] = (),
    hits: Mapping[str, Sequence[KbHit]] | None = None,
    checklist: ReviewChecklist | None = None,
    l1_confirm: bool = False,
    kill_switch: KillSwitchState | None = None,
    mode: TurnMode = TurnMode.INTERACTIVE,
    token_ceiling: int | None = None,
    max_specialists: int | None = None,
    max_tool_steps: int | None = None,
    deadline: timedelta | None = None,
    contexts: Mapping[str, JsonObject] | None = None,
    classify_depth: Callable[[str], Any] | None = None,
) -> DelegationRig:
    """``models`` maps a specialist id to the scripted model that plays it (the Reviewer has no model)."""
    clock = FakeClock(vn(2026, 10, 3, 10, 0))
    store = InMemoryCareStore()
    agent = store.add_patient("P900")
    tasks = InMemoryTaskStore()
    fake_slots, fake_knowledge, actions = FakeSlots(slots), FakeKnowledge(hits), FakeActions()
    toolkit = SpecialistToolkit(
        slots=fake_slots,
        actions=cast("AgentFacingClinicActions", actions),
        knowledge=fake_knowledge,
        confirm_policy=FakeConfirmPolicy(l1=l1_confirm),
        clock=clock,
    )
    runners: dict[str, Any] = {
        spec_id: LlmSpecialistRunner(model) for spec_id, model in (models or {}).items()
    }
    runners[REVIEWER_ID] = ChecklistRunner(StaticChecklist(checklist or ReviewChecklist()), classify_depth)
    budget_args: dict[str, Any] = {"mode": mode, "clock": clock, "deadline": deadline}
    for key, value in (
        ("token_ceiling", token_ceiling),
        ("max_specialists", max_specialists),
        ("max_tool_steps", max_tool_steps),
    ):
        if value is not None:
            budget_args[key] = value
    scope = CareTurnScope(
        care_agent=agent,
        patient_ref="P900",
        budget=TurnBudget(**budget_args),
        turn_key="turn-fake-1",
        contexts=dict(contexts or {}),
    )
    switches = kill_switch or KillSwitchState()
    service = DelegationService(
        specs={spec.agent_id: spec for spec in all_specs()},
        runners=runners,
        toolkit=toolkit,
        tasks=tasks,
        store=store,
        kill_switch=lambda: switches,
        clock=clock,
    )
    return DelegationRig(service, scope, tasks, store, clock, fake_slots, fake_knowledge, actions, toolkit)

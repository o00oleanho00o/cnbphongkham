"""In-memory fakes of the M2c ports for tests (not imported by production code). Companion of
``pema.care.testing``; everything is synthetic (the on-call number is a placeholder flagged ``is_fixture``).

Nothing here sleeps: the SLA scheduler only remembers the checks and a test fires them by hand, with the
``FakeClock`` of ``pema.care.testing``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pema.care.control import CareControl
from pema.care.depth import DepthClassifier
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_skill import HandoffSkill
from pema.care.handoff_types import Depth, DepthLlmOutput, HandoffAction, HandoffDecision, Urgency
from pema.care.loop import CareEventBus, CareTurnRunner, CareTurnWorker, TurnOutcome
from pema.care.models import ControlState
from pema.care.oncall import OnCallDirectory
from pema.care.patient_notices import PatientNotices
from pema.care.ports import (
    AutonomyPolicy,
    CareAgentSnapshot,
    ChannelTarget,
    HandoffRequestSnapshot,
    OpenedHandoff,
    PatientContext,
)
from pema.care.priority import CarePriorityQueue
from pema.care.reminders import ReminderService
from pema.care.routing import RoutingService
from pema.care.routing_types import (
    Candidate,
    CandidateStatus,
    DeclineRecord,
    DueReminder,
    HandoffNotice,
    NewPausedReminder,
    OnCallInfo,
    OnCallRow,
    Ownership,
    PausedReminder,
    ReminderStatus,
    RoutingConfig,
    SlaCheck,
    StaffInfo,
    candidates_from_json,
)
from pema.care.testing import (
    ActionRow,
    FakeChannel,
    FakeClock,
    FakeContextLoader,
    FakeDepthLlm,
    FakeGuard,
    FakeHarness,
    FakeReview,
    FakeScheduler,
    FakeSuggestions,
    FixedWindow,
    InMemoryCareStore,
    InMemoryControlStore,
    StaticHandoffConfig,
    StaticTexts,
    vn,
)
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType, Role

WEEKDAYS_8_17: dict[str, list[list[str]]] = {
    day: [["08:00", "17:00"]] for day in ("mon", "tue", "wed", "thu", "fri")
}


class InMemoryRoutingStore:
    """``RoutingStore`` over the requests of an ``InMemoryControlStore`` (same list, same audit log)."""

    def __init__(self, controls: InMemoryControlStore) -> None:
        self.controls = controls
        self.saves = 0

    async def get_request(self, request_id: UUID) -> HandoffRequestSnapshot | None:
        return next((r for r in self.controls.requests if r.id == request_id), None)

    async def list_unresolved_requests(self, *, limit: int) -> Sequence[HandoffRequestSnapshot]:
        return [r for r in self.controls.requests if r.outcome is None][:limit]

    async def save_routing(
        self,
        request_id: UUID,
        *,
        expected_idx: int,
        candidates: Sequence[Mapping[str, object]],
        current_idx: int,
        notified_at: datetime | None,
        outcome: str | None,
        log_action: str,
        at: datetime,
    ) -> HandoffRequestSnapshot | None:
        request = await self.get_request(request_id)
        if request is None or request.outcome is not None or request.current_idx != expected_idx:
            return None
        saved = replace(
            request,
            candidates=tuple(dict(c) for c in candidates),
            current_idx=current_idx,
            current_notified_at=notified_at,
            outcome=outcome,
        )
        self.controls.replace_request(saved)
        self.controls.care.actions.append(
            ActionRow(saved.care_agent_id, log_action, "paused", saved.depth, at)
        )
        self.saves += 1
        return saved

    async def record_action(
        self, care_agent_id: UUID, *, action_type: str, disposition: str, depth: str | None, at: datetime
    ) -> None:
        await self.controls.record_action(
            care_agent_id, action_type=action_type, disposition=disposition, depth=depth, at=at
        )

    async def declines_since(self, since: datetime, *, limit: int) -> Sequence[DeclineRecord]:
        records: list[DeclineRecord] = []
        for request in self.controls.requests:
            for candidate in candidates_from_json(request.candidates):
                if (
                    candidate.status is CandidateStatus.DECLINED
                    and candidate.declined_at is not None
                    and candidate.declined_at >= since
                ):
                    records.append(
                        DeclineRecord(
                            request.id,
                            candidate.user_id,
                            request.required_skill,
                            request.depth,
                            candidate.decline_reason,
                            candidate.declined_at,
                        )
                    )
        return records[:limit]


class InMemoryRoutingDirectory:
    def __init__(self) -> None:
        self.staff: dict[UUID, StaffInfo] = {}
        self.owners: dict[UUID, Ownership] = {}
        self.list_calls = 0

    def add_staff(
        self,
        role: str = "cs_staff",
        *,
        skills: Sequence[str] = (),
        shift: Mapping[str, object] | None = None,
        capacity: int = 5,
        load: int = 0,
    ) -> UUID:
        user_id = uuid4()
        self.staff[user_id] = StaffInfo(
            user_id=user_id,
            role=role,
            skills=tuple(skills),
            shift=dict(shift) if shift is not None else dict(WEEKDAYS_8_17),
            capacity=capacity,
            load=load,
        )
        return user_id

    def own(self, patient_id: UUID, *, cs_owner: UUID | None = None, doctor: UUID | None = None) -> None:
        self.owners[patient_id] = Ownership(cs_owner=cs_owner, doctor=doctor)

    async def list_staff(self, clinic_id: UUID) -> Sequence[StaffInfo]:
        self.list_calls += 1
        return list(self.staff.values())

    async def ownership(self, patient_id: UUID) -> Ownership:
        return self.owners.get(patient_id, Ownership())


class InMemoryOnCallSource:
    """Rows of the on-call table. Tests change them to prove a change applies on the next read."""

    def __init__(self, *, number: str | None = "0000000001") -> None:
        self.rows: list[OnCallRow] = []
        self.reads = 0
        if number is not None:
            self.set_number(number)

    def set_number(self, number: str, *, valid_from: datetime | None = None) -> OnCallRow:
        """A new active row that replaces the older ones (the dashboard edit)."""
        self.rows = [replace(r, active=False) for r in self.rows]
        row = OnCallRow(
            id=uuid4(),
            zalo_number=number,
            owner="Trực (mẫu)",
            valid_from=valid_from or datetime(2026, 1, 1, tzinfo=UTC),
            is_fixture=True,
        )
        self.rows.append(row)
        return row

    async def active_contacts(self, clinic_id: UUID) -> Sequence[OnCallRow]:
        self.reads += 1
        return [r for r in self.rows if r.active]


class StaticRoutingConfig:
    def __init__(self, config: RoutingConfig | None = None) -> None:
        self.config = config or RoutingConfig()
        self.reads = 0

    async def get(self, clinic_id: UUID) -> RoutingConfig:
        self.reads += 1
        return self.config


class FakeStaffNotify:
    """Records what staff and the on-call contact were told; ``fail`` makes staff delivery fail."""

    def __init__(self, *, fail: bool = False, fail_on_call: bool = False) -> None:
        self.fail = fail
        self.fail_on_call = fail_on_call
        self.staff: list[tuple[UUID, HandoffNotice]] = []
        self.on_call: list[tuple[OnCallInfo, HandoffNotice]] = []

    async def notify_staff(self, user_id: UUID, notice: HandoffNotice) -> bool:
        self.staff.append((user_id, notice))
        return not self.fail

    async def notify_on_call(self, contact: OnCallInfo, notice: HandoffNotice) -> bool:
        self.on_call.append((contact, notice))
        return not self.fail_on_call


class FakeSlaScheduler:
    """S stand-in: remembers the checks; a test fires them by hand (no clock, no sleep)."""

    def __init__(self) -> None:
        self.checks: list[SlaCheck] = []

    async def schedule_check(self, check: SlaCheck) -> None:
        self.checks.append(check)

    @property
    def last(self) -> SlaCheck:
        return self.checks[-1]


class InMemoryReminderStore:
    def __init__(self) -> None:
        self.rows: list[PausedReminder] = []

    async def add(self, reminder: NewPausedReminder) -> bool:
        if any(
            r.care_agent_id == reminder.care_agent_id and r.dedupe_key == reminder.dedupe_key
            for r in self.rows
        ):
            return False
        self.rows.append(
            PausedReminder(
                id=uuid4(),
                care_agent_id=reminder.care_agent_id,
                patient_id=reminder.patient_id,
                patient_ref=reminder.patient_ref,
                kind=reminder.kind,
                rule=reminder.rule,
                due_at=reminder.due_at,
                dedupe_key=reminder.dedupe_key,
                prepared_text=reminder.prepared_text,
                owner_user_id=reminder.owner_user_id,
                status=ReminderStatus.PAUSED,
                payload=reminder.payload,
                paused_at=reminder.paused_at,
            )
        )
        return True

    async def list_paused(self, care_agent_id: UUID) -> Sequence[PausedReminder]:
        return sorted(
            (r for r in self.rows if r.care_agent_id == care_agent_id and r.status is ReminderStatus.PAUSED),
            key=lambda r: r.due_at,
        )

    async def list_for_owner(self, owner_user_id: UUID, *, limit: int) -> Sequence[PausedReminder]:
        found = [
            r for r in self.rows if r.owner_user_id == owner_user_id and r.status is ReminderStatus.PAUSED
        ]
        return sorted(found, key=lambda r: r.due_at)[:limit]

    async def resolve(self, reminder_id: UUID, status: ReminderStatus, resolution: str, at: datetime) -> bool:
        for position, row in enumerate(self.rows):
            if row.id == reminder_id and row.status is ReminderStatus.PAUSED:
                self.rows[position] = replace(row, status=status, resolution=resolution, resolved_at=at)
                return True
        return False

    def by_status(self, status: ReminderStatus) -> list[PausedReminder]:
        return [r for r in self.rows if r.status is status]


class FakeDueReminders:
    """``DueReminderSource``: reminders already queued for a patient; ``held`` remembers what must wait."""

    def __init__(self, *items: DueReminder) -> None:
        self.items = list(items)
        self.held: list[str] = []

    async def due_for(self, patient_id: UUID, now: datetime) -> Sequence[DueReminder]:
        return list(self.items)

    async def hold(self, patient_id: UUID, dedupe_keys: Sequence[str]) -> None:
        self.held.extend(dedupe_keys)


class RecordingPublisher:
    """``EventPublisher`` that keeps the events (``ok=False`` models a patient without a care agent)."""

    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok
        self.events: list[CareEvent] = []

    async def publish(self, event: CareEvent) -> bool:
        self.events.append(event)
        return self.ok


# ------------------------------------------------------------------------------------------- the rig
MONDAY_10 = vn(2026, 10, 5, 10, 0)
"""A Monday, 10:00 clinic time: inside the default send window and inside the shift of the fake staff."""
MONDAY_22 = vn(2026, 10, 5, 22, 0)
"""Outside the send window."""
REF = "P900"
RED_FLAG_TEXT = "em bị chảy máu nhiều ở chỗ tiêm"
PLAIN_TEXT = "kem này dùng buổi tối được không ạ"


@dataclass
class RoutingRig:
    """A care loop with the whole of package M wired to in-memory fakes (no database, no clock, no sleep)."""

    care: InMemoryCareStore
    controls: InMemoryControlStore
    routing_store: InMemoryRoutingStore
    directory: InMemoryRoutingDirectory
    oncall_source: InMemoryOnCallSource
    routing_config: StaticRoutingConfig
    notifier: FakeStaffNotify
    sla: FakeSlaScheduler
    clock: FakeClock
    harness: FakeHarness
    channel: FakeChannel
    llm: FakeDepthLlm
    texts: StaticTexts
    oncall: OnCallDirectory
    service: RoutingService
    control: CareControl
    reminders: ReminderService
    reminder_store: InMemoryReminderStore
    due: FakeDueReminders
    runner: CareTurnRunner
    queue: CarePriorityQueue
    bus: CareEventBus
    agent: CareAgentSnapshot
    window: FixedWindow

    @property
    def state(self) -> ControlState:
        return self.care.states.get(self.agent.patient_id, ControlState.AUTO)

    def actions(self) -> list[str]:
        return [row.action_type for row in self.care.actions]

    @property
    def request(self) -> HandoffRequestSnapshot:
        return self.controls.requests[-1]

    def chain(self) -> list[Candidate]:
        return candidates_from_json(self.request.candidates)

    async def message(self, text: str = PLAIN_TEXT) -> TurnOutcome:
        """A patient message goes through the whole turn (skill ``handoff`` included)."""
        self.texts.texts = [text]
        return await self.runner.run_turn(
            self.agent.id,
            CareEvent(
                kind=EventKind.PATIENT_MESSAGE,
                initiator=Initiator.PATIENT,
                patient_ref=REF,
                occurred_at=self.clock.now,
            ),
        )

    async def open_round(
        self,
        depth: Depth = Depth.D4,
        urgency: Urgency = Urgency.URGENT,
        required_skill: str | None = None,
    ) -> OpenedHandoff:
        """Open a round directly (``CareControl.request_handoff``), like the skill would."""
        context = PatientContext(
            REF, self.agent.patient_id, channel=ChannelTarget("acct-fake", "thread-fake"), facts={"vip": True}
        )
        decision = HandoffDecision(
            action=HandoffAction.HANDOFF,
            reason="depth_at_or_above_threshold",
            depth=depth,
            confidence=0.8,
            required_skill=required_skill or ("medical" if depth.rank >= Depth.D4.rank else "general"),
            urgency=urgency,
            signals=("depth_at_or_above_threshold",),
        )
        event = CareEvent(
            kind=EventKind.PATIENT_MESSAGE,
            initiator=Initiator.PATIENT,
            patient_ref=REF,
            occurred_at=self.clock.now,
        )
        return await self.control.request_handoff(self.agent, event, context, decision, self.clock.now)

    async def drain(self) -> int:
        return await CareTurnWorker(self.queue, self.runner).run_until_idle()


def staff_context(user: UUID, role: Role = Role.CS_STAFF) -> ActionContext:
    return ActionContext(
        clinic_id=UUID(int=1), actor_type=ActorType.USER, actor_user_id=user, actor_role=role
    )


def make_routing_rig(
    *,
    now: datetime = MONDAY_10,
    depth: Depth = Depth.D2,
    with_on_call: bool = True,
    autonomy: AutonomyPolicy | None = None,
    routing_config: RoutingConfig | None = None,
    reminders_due: Sequence[DueReminder] = (),
    oncall_ttl: float = 0.0,
    notifier: FakeStaffNotify | None = None,
) -> RoutingRig:
    care = InMemoryCareStore()
    agent = care.add_patient(REF)
    controls = InMemoryControlStore(care)
    routing_store = InMemoryRoutingStore(controls)
    directory = InMemoryRoutingDirectory()
    oncall_source = InMemoryOnCallSource(number="0000000001" if with_on_call else None)
    routing_cfg = StaticRoutingConfig(routing_config)
    notifier = notifier or FakeStaffNotify()
    sla = FakeSlaScheduler()
    clock = FakeClock(now)
    harness = FakeHarness()
    channel = FakeChannel()
    llm = FakeDepthLlm(DepthLlmOutput(depth=depth, confidence=0.9))
    texts = StaticTexts(PLAIN_TEXT)
    handoff_cfg = StaticHandoffConfig()
    window = FixedWindow()
    oncall = OnCallDirectory(
        oncall_source, routing_store, cache_ttl_seconds=oncall_ttl, monotonic=lambda: clock.now.timestamp()
    )
    service = RoutingService(
        store=routing_store,
        directory=directory,
        oncall=oncall,
        config_source=routing_cfg,
        notifier=notifier,
        sla=sla,
        window=window,
        clock=clock,
    )
    queue = CarePriorityQueue()
    bus = CareEventBus(care, queue)
    reminder_store = InMemoryReminderStore()
    due = FakeDueReminders(*reminders_due)
    reminders = ReminderService(
        store=reminder_store,
        config_source=routing_cfg,
        directory=directory,
        controls=controls,
        recorder=routing_store,
        publisher=bus,
        clock=clock,
        due_source=due,
    )
    control = CareControl(
        store=controls,
        config_source=handoff_cfg,
        channel=channel,
        clock=clock,
        routing=service,
        routing_start=service,
        notices=PatientNotices(config_source=routing_cfg, window=window, oncall=oncall),
        reminders=reminders,
    )
    skill = HandoffSkill(
        classifier=DepthClassifier(llm),
        config_source=handoff_cfg,
        texts=texts,
        clock=clock,
        window=window,
    )
    runner = CareTurnRunner(
        store=care,
        context_loader=FakeContextLoader(),
        harness=harness,
        channel=channel,
        scheduler=FakeScheduler(),
        review=FakeReview(),
        window=window,
        guard=FakeGuard(),
        clock=clock,
        handoff=skill,
        autonomy=autonomy,
        requester=control,
        suggestions=FakeSuggestions(),
        reminders=reminders,
        cap_per_day=3,
    )
    return RoutingRig(
        care=care,
        controls=controls,
        routing_store=routing_store,
        directory=directory,
        oncall_source=oncall_source,
        routing_config=routing_cfg,
        notifier=notifier,
        sla=sla,
        clock=clock,
        harness=harness,
        channel=channel,
        llm=llm,
        texts=texts,
        oncall=oncall,
        service=service,
        control=control,
        reminders=reminders,
        reminder_store=reminder_store,
        due=due,
        runner=runner,
        queue=queue,
        bus=bus,
        agent=agent,
        window=window,
    )

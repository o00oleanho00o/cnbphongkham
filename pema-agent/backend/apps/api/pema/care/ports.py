"""Ports of package M: thin ``Protocol`` s for interfaces that belong to other packages.

New module (not a port). A package M step codes against these and never reimplements the other package.

M1
* ``PatientCreatedHook``: B1's ``create_patient`` action (``pema.clinic.actions.patients``) has no extension
  point yet, so the pairing of a new patient with its care agent is a hook that the action's caller (or the
  action itself, once it takes a hook) invokes inside the SAME session right after the patient row is flushed.
  ``pema.care.pairing.CareAgentPairing`` is the implementation.

M2a (the turn loop, ``pema.care.loop``)
* ``Harness``: D1's shared pipeline entry point (the ``HarnessProcessor`` of PLAN-M). D1 has no entry point
  that takes a care event yet (``AgentEngine.run_turn`` takes a channel batch), so the loop codes against
  this one-method port; the adapter that builds the ``AgentTurnRequest`` with the care-agent persona belongs
  to the wiring package.
* ``PatientContextLoader``: loads the PII-masked, minimal context of a patient through ``actions/`` (B1).
* ``ChannelSend``: package C1/C2. The care loop never calls a Zalo client directly.
* ``Scheduler``: S. Queues a send for the start of the next send window (adapter over ``SchedulerPort``).
* ``ReviewSink``: creates the ``review_item`` that holds a draft for a person (autonomy L0, no channel).
* ``HandoffDecider``: M2b's skill ``handoff`` (``pema.care.handoff_skill.HandoffSkill``); ``AlwaysAnswer`` is
  the stand-in of a wiring that has not got it.
* ``AutonomyPolicy``: M3. Until it exists ``L0Autonomy`` stands in: nothing is sent without approval.
* ``SendWindowProvider``: the clinic's send window (``pema.care.window.ChannelPolicySendWindow``).
* ``PatientDirectory``: pseudonym patient code -> care agent id (``pema.care.store.SqlCareStore``).
* ``CareStore``: the rows the loop reads and writes in ``agent.*`` (``pema.care.store.SqlCareStore``).
* ``TickRuleSource``: the rules of the daily tick that need no LLM (missed milestone, stale pending work).

S's ``ProactiveSendGuard`` (``pema_contracts.scheduler``) is used as it is for the per-patient daily cap.

M2b (control state machine and the skill ``handoff``)
* ``ControlStore``: the rows of the state machine (``conversation_control``, ``handoff_requests``, the staff
  release note in ``care_memory``, ``autonomy_override``) and the audit line of each transition, written in
  the SAME transaction (``pema.care.control_store.SqlControlStore``).
* ``HandoffRequester``: what the loop calls when the skill says ``handoff``
  (``pema.care.control.CareControl``).
* ``HandoffConfigSource``: the skill row ``agent.skills`` ``handoff`` (instruction + ``classifier_config``).
* ``MessageTextSource``: the text of what the patient just wrote. A ``CareEvent`` carries ids only, the
  text is in the history store of the channel pipeline (C1/C2, D1); this port is read-only and the depth
  classifier
  runs the red-flag rules on it before anything else.
* ``DepthLlm``: the schema-constrained model call of the classifier (D2-D4 only; a red flag never reaches it).
* ``SuggestionSink``: a ``review_item`` of kind ``suggestion`` for staff while the conversation is not in
  AUTO. ``pema_contracts.review.ReviewKind`` has no such kind yet (open item for B1/A), so the port is all
  there is; nothing it receives is ever sent to a patient.
* ``RoutingAdvance``: M2c. Called after a decline; until it exists the request simply stays open.

M2c (staff routing, SLA, on-call, reminder pause and reconcile)
* ``RoutingStart``: called by ``CareControl`` right after a routing round is opened; builds the chain and
  asks the first candidate (``pema.care.routing.RoutingService``, which is also the ``RoutingAdvance``).
* ``RoutingStore``: the routing columns of ``agent.handoff_requests`` (``candidates``, ``current_idx``,
  ``outcome``) with a compare-and-set on ``current_idx``, so a decline and an SLA expiry that race advance the
  chain once (``pema.care.routing_store.SqlRoutingStore``).
* ``RoutingDirectory``: staff profiles with their load, and the owners of a patient (the views
  ``clinic_agent.staff_profile`` and ``patient_ownership``).
* ``OnCallSource``: the rows of ``clinic_agent.on_call_contact`` (``pema.care.oncall.OnCallDirectory`` picks
  the current one on every call).
* ``RoutingConfigSource``: the row ``agent.skills`` ``routing`` (SLA minutes, templates, reminder rules).
* ``StaffNotify``: push + in-app notification of a staff member, and the message to the on-call contact. B1/E
  have no such interface yet, so this is all there is; nothing it receives goes to a patient.
* ``SlaScheduler``: S. Schedules "look at this request again at T" (a job, never a sleep).
* ``PatientNoticeComposer``: the text of the ONE message the patient gets when a round opens outside clinic
  hours (``pema.care.patient_notices.PatientNotices``); ``None`` keeps the holding message of M2b.
* ``ReminderStore`` / ``DueReminderSource`` / ``EventPublisher``: the ``agent.paused_reminders`` rows, the
  reminders that are already queued for a patient (S, B2) and the way back into the loop
  (``CareEventBus``).
* ``ReminderPauser`` (the loop) and ``ReminderHooks`` (``CareControl``):
  ``pema.care.reminders.ReminderService``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.events import CareEvent
from pema.care.handoff_types import DepthLlmOutput, HandoffAction, HandoffConfig, HandoffDecision
from pema.care.models import ControlState
from pema.care.routing_types import (
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
)
from pema.care.window import SendWindow
from pema_contracts.common import JsonObject


@runtime_checkable
class PatientCreatedHook(Protocol):
    """Called once per new patient, in the unit of work that created it (idempotent: a repeat is harmless)."""

    async def on_patient_created(self, session: AsyncSession, patient_id: UUID) -> None: ...


# ------------------------------------------------------------------------------------------ data
@dataclass(frozen=True)
class CareAgentSnapshot:
    """What the loop needs of ``agent.care_agents`` (a detached copy: the loop never holds a session)."""

    id: UUID
    clinic_id: UUID
    patient_id: UUID
    profile: str
    paused: bool = False
    autonomy_levels: Mapping[str, object] = field(default_factory=dict[str, object])
    autonomy_override: Mapping[str, object] | None = None


@dataclass(frozen=True)
class ChannelTarget:
    """Where a message to the patient goes: a verified identity on a running account."""

    account_id: str
    thread_id: str


@dataclass(frozen=True)
class PatientContext:
    """PII-masked minimal context of one patient (``actions/``): only a code and structured facts."""

    patient_ref: str
    patient_id: UUID
    facts: JsonObject = field(default_factory=dict[str, Any])
    channel: ChannelTarget | None = None
    """``None``: no verified identity on a running account. The agent can only draft for staff to send."""
    marketing_opt_out: bool = False


@dataclass(frozen=True)
class HarnessRequest:
    care_agent_id: UUID
    profile: str
    persona: str
    event: CareEvent
    context: PatientContext


@dataclass(frozen=True)
class HarnessDecision:
    """What the shared pipeline decided for this event. ``text`` is ``None`` when there is nothing to say."""

    text: str | None
    action_type: str = "reply"
    depth: str | None = None
    marketing: bool = False


@dataclass(frozen=True)
class SendOutcome:
    ok: bool
    error_code: str | None = None


@dataclass(frozen=True)
class DeferredSend:
    care_agent_id: UUID
    patient_id: UUID
    target: ChannelTarget
    text: str
    run_at: datetime
    dedupe_key: str


@dataclass(frozen=True)
class HandoffVerdict:
    action: HandoffAction
    reason: str = ""
    decision: HandoffDecision | None = None
    """The full structured output of the skill (M2b); ``None`` for a stand-in that has none."""


@dataclass(frozen=True)
class TickFinding:
    """One thing the rules of the daily tick found about a patient."""

    care_agent_id: UUID
    patient_ref: str
    kind: str
    needs_draft: bool
    payload: JsonObject = field(default_factory=dict[str, Any])


# ------------------------------------------------------------------------------- data (M2b)
@dataclass(frozen=True)
class ControlSnapshot:
    state: ControlState
    since: datetime | None = None
    staff_owner: UUID | None = None
    release_note: str | None = None
    auto_release_after: timedelta | None = None


@dataclass(frozen=True)
class HandoffSpec:
    """What a new routing round is opened with (``depth``/``urgency`` as the table stores them)."""

    reason: str
    summary: str
    """PII-masked summary of the context for the staff who is asked."""
    depth: str
    confidence: float
    required_skill: str | None
    urgency: str


@dataclass(frozen=True)
class HandoffRequestSnapshot:
    id: UUID
    patient_id: UUID
    care_agent_id: UUID
    reason: str
    summary: str
    depth: str
    confidence: float
    required_skill: str | None
    urgency: str
    candidates: tuple[object, ...] = ()
    current_idx: int = 0
    accepted_by: UUID | None = None
    outcome: str | None = None
    created_at: datetime | None = None
    clinic_id: UUID | None = None
    current_notified_at: datetime | None = None


@dataclass(frozen=True)
class OpenedHandoff:
    request: HandoffRequestSnapshot
    created: bool
    """``False``: a round was already open (or the conversation was not in AUTO) and nothing was changed."""


@dataclass(frozen=True)
class AutonomyOverride:
    """``agent.care_agents.autonomy_override``: ``{level, until}``.

    ``until`` ``None``: until changed. ``level`` is the number 0..2; the column stores ``"L0"``..``"L2"``."""

    level: int
    until: datetime | None = None


@dataclass(frozen=True)
class ReleaseSpec:
    memory_fact: str | None = None
    """PII-masked release note, stored in ``care_memory`` with source ``staff``."""
    release_note: str | None = None
    override: AutonomyOverride | None = None


@dataclass(frozen=True)
class HandoffSettings:
    """The row of the skill ``handoff``: its instruction text and its ``classifier_config``."""

    instruction: str
    config: HandoffConfig


# ----------------------------------------------------------------------------------------- ports
class Harness(Protocol):
    async def process(self, request: HarnessRequest) -> HarnessDecision: ...


class PatientContextLoader(Protocol):
    async def load(self, agent: CareAgentSnapshot, event: CareEvent) -> PatientContext: ...


class ChannelSend(Protocol):
    async def send(self, target: ChannelTarget, text: str, *, proactive: bool) -> SendOutcome: ...


class Scheduler(Protocol):
    async def defer_send(self, request: DeferredSend) -> None: ...


class ReviewSink(Protocol):
    async def create_draft(
        self, agent: CareAgentSnapshot, patient_ref: str, text: str, reason: str
    ) -> str | None:
        """The id of the new review item, or ``None`` when it could not be created."""
        ...


class HandoffDecider(Protocol):
    async def decide(
        self, agent: CareAgentSnapshot, event: CareEvent, context: PatientContext
    ) -> HandoffVerdict: ...


class AutonomyPolicy(Protocol):
    async def may_auto_send(
        self, agent: CareAgentSnapshot, decision: HarnessDecision, now: datetime
    ) -> bool: ...


class SendWindowProvider(Protocol):
    async def get(self, clinic_id: UUID) -> SendWindow: ...


class PatientDirectory(Protocol):
    async def care_agent_id_for(self, patient_ref: str) -> UUID | None: ...


class CareStore(Protocol):
    async def get_care_agent(self, care_agent_id: UUID) -> CareAgentSnapshot | None: ...

    async def get_control_state(self, patient_id: UUID) -> ControlState:
        """``AUTO`` when the patient has no control row yet."""
        ...

    async def list_active_care_agents(self, *, after: UUID | None, limit: int) -> Sequence[CareAgentSnapshot]:
        """Not paused, ordered by id, keyset pagination."""
        ...

    async def record_action(
        self,
        care_agent_id: UUID,
        *,
        action_type: str,
        disposition: str,
        depth: str | None,
        at: datetime,
    ) -> None: ...

    async def touch_last_tick(self, care_agent_ids: Sequence[UUID], at: datetime) -> None: ...


class ControlStore(Protocol):
    """Every method is one unit of work: the state change AND its ``actions_log`` line (``log_action``)."""

    async def get_control(self, patient_id: UUID) -> ControlSnapshot: ...

    async def agent_for_patient(self, patient_id: UUID) -> CareAgentSnapshot | None: ...

    async def record_action(
        self,
        care_agent_id: UUID,
        *,
        action_type: str,
        disposition: str,
        depth: str | None,
        at: datetime,
    ) -> None:
        """A line of ``actions_log`` that is not part of a transition (the holding message)."""
        ...

    async def get_open_request(self, patient_id: UUID) -> HandoffRequestSnapshot | None: ...

    async def open_handoff(
        self, agent: CareAgentSnapshot, spec: HandoffSpec, *, log_action: str, at: datetime
    ) -> OpenedHandoff:
        """``AUTO -> HANDOFF_ROUTING`` and the new request, atomically. Not in AUTO: nothing changes and the
        open request comes back with ``created=False`` (two events racing open ONE round)."""
        ...

    async def accept(
        self, patient_id: UUID, staff_id: UUID, *, log_action: str, at: datetime
    ) -> HandoffRequestSnapshot:
        """``HANDOFF_ROUTING -> STAFF``; ``InvalidTransitionError`` in any other state."""
        ...

    async def record_decline(
        self, patient_id: UUID, staff_id: UUID, *, log_action: str, at: datetime
    ) -> HandoffRequestSnapshot:
        """Only audited here; the state stays ``HANDOFF_ROUTING``. ``InvalidTransitionError`` otherwise."""
        ...

    async def release(
        self, patient_id: UUID, staff_id: UUID, spec: ReleaseSpec, *, log_action: str, at: datetime
    ) -> ControlSnapshot:
        """``STAFF -> AUTO``, release note into ``care_memory``, optional ``autonomy_override``, together.
        ``InvalidTransitionError`` in any other state."""
        ...

    async def set_auto_release_after(
        self, patient_id: UUID, after: timedelta | None, *, log_action: str, at: datetime
    ) -> None: ...


class HandoffRequester(Protocol):
    async def request_handoff(
        self,
        agent: CareAgentSnapshot,
        event: CareEvent,
        context: PatientContext,
        decision: HandoffDecision,
        now: datetime,
    ) -> OpenedHandoff: ...


class HandoffConfigSource(Protocol):
    async def get(self, clinic_id: UUID) -> HandoffSettings:
        """Read on EVERY turn (a change of the matrix applies at once). Defaults when the row is missing."""
        ...


class MessageTextSource(Protocol):
    async def patient_texts(self, agent: CareAgentSnapshot, event: CareEvent) -> Sequence[str]:
        """The texts of the patient's messages that woke the agent (empty for any other event)."""
        ...


class DepthLlm(Protocol):
    async def classify(self, masked_text: str, *, instruction: str) -> DepthLlmOutput | None:
        """``masked_text`` has been through the PII mask. ``None``: no usable answer (error, invalid JSON)."""
        ...


class SuggestionSink(Protocol):
    async def create_suggestion(
        self, agent: CareAgentSnapshot, patient_ref: str, text: str, state: ControlState
    ) -> str | None:
        """A suggestion for the staff who handle the patient; NEVER sent. ``None``: could not be created."""
        ...


class RoutingAdvance(Protocol):
    async def on_declined(
        self, request: HandoffRequestSnapshot, staff_id: UUID, reason: str, suggest_user_id: UUID | None
    ) -> None: ...


class RoutingStart(Protocol):
    async def on_opened(self, request: HandoffRequestSnapshot, now: datetime) -> None:
        """Build the chain of candidates and ask the first one."""
        ...


class RoutingStore(Protocol):
    async def get_request(self, request_id: UUID) -> HandoffRequestSnapshot | None: ...

    async def list_unresolved_requests(self, *, limit: int) -> Sequence[HandoffRequestSnapshot]:
        """Requests with ``outcome`` NULL (waiting for a candidate), oldest first."""
        ...

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
        """Compare-and-set: only while the request is open (``outcome`` NULL) and ``current_idx`` still is
        ``expected_idx``; ``None`` otherwise (somebody else moved it). The change and its ``actions_log`` line
        are one unit of work."""
        ...

    async def record_action(
        self,
        care_agent_id: UUID,
        *,
        action_type: str,
        disposition: str,
        depth: str | None,
        at: datetime,
    ) -> None: ...

    async def declines_since(self, since: datetime, *, limit: int) -> Sequence[DeclineRecord]: ...


class RoutingDirectory(Protocol):
    async def list_staff(self, clinic_id: UUID) -> Sequence[StaffInfo]:
        """Every staff profile with the number of conversations the person handles (one query)."""
        ...

    async def ownership(self, patient_id: UUID) -> Ownership: ...


class OnCallSource(Protocol):
    async def active_contacts(self, clinic_id: UUID) -> Sequence[OnCallRow]:
        """Read from the database on every call."""
        ...


class RoutingConfigSource(Protocol):
    async def get(self, clinic_id: UUID) -> RoutingConfig:
        """Read on EVERY use (a change applies at once). Defaults when the row is missing."""
        ...


class StaffNotify(Protocol):
    async def notify_staff(self, user_id: UUID, notice: HandoffNotice) -> bool:
        """Push and in-app. ``False``: could not be delivered."""
        ...

    async def notify_on_call(self, contact: OnCallInfo, notice: HandoffNotice) -> bool: ...


class SlaScheduler(Protocol):
    async def schedule_check(self, check: SlaCheck) -> None: ...


class PatientNoticeComposer(Protocol):
    async def compose(self, agent: CareAgentSnapshot, decision: HandoffDecision, now: datetime) -> str | None:
        """The text of the one message of this round, or ``None`` for the default holding message."""
        ...


class ReminderStore(Protocol):
    async def add(self, reminder: NewPausedReminder) -> bool:
        """``False`` when ``(care_agent_id, dedupe_key)`` already exists (a repeat changes nothing)."""
        ...

    async def list_paused(self, care_agent_id: UUID) -> Sequence[PausedReminder]: ...

    async def list_for_owner(self, owner_user_id: UUID, *, limit: int) -> Sequence[PausedReminder]:
        """Paused reminders shown on the timeline of the owning staff member."""
        ...

    async def resolve(self, reminder_id: UUID, status: ReminderStatus, resolution: str, at: datetime) -> bool:
        """Only while the reminder is ``paused``; ``False`` when it already was resolved."""
        ...


class DueReminderSource(Protocol):
    async def due_for(self, patient_id: UUID, now: datetime) -> Sequence[DueReminder]: ...

    async def hold(self, patient_id: UUID, dedupe_keys: Sequence[str]) -> None:
        """Tell S / B2 not to fire these again (a repeat would only be paused a second time)."""
        ...


class EventPublisher(Protocol):
    async def publish(self, event: CareEvent) -> bool: ...


class ReminderPauser(Protocol):
    async def pause_event(self, agent: CareAgentSnapshot, event: CareEvent, now: datetime) -> bool:
        """``True`` when ``event`` is a reminder and was recorded as paused."""
        ...


class ReminderHooks(Protocol):
    async def pause_for(self, agent: CareAgentSnapshot, now: datetime) -> int: ...

    async def reconcile_on_release(self, agent: CareAgentSnapshot, now: datetime) -> None: ...


class TickRuleSource(Protocol):
    async def findings(self, agents: Sequence[CareAgentSnapshot], now: datetime) -> Sequence[TickFinding]:
        """Batch API (one query per batch, never one per patient)."""
        ...


# ------------------------------------------------------------------------------------ stand-ins
class AlwaysAnswer:
    """``HandoffDecider`` until M2b's skill ``handoff`` exists."""

    async def decide(
        self, agent: CareAgentSnapshot, event: CareEvent, context: PatientContext
    ) -> HandoffVerdict:
        return HandoffVerdict(HandoffAction.ANSWER)


class L0Autonomy:
    """``AutonomyPolicy`` until M3 exists: everything is a draft for a person (PLAN-M section 4, level L0)."""

    async def may_auto_send(self, agent: CareAgentSnapshot, decision: HarnessDecision, now: datetime) -> bool:
        return False

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
* ``HandoffDecider``: M2b's skill ``handoff``; until it exists ``AlwaysAnswer`` stands in.
* ``AutonomyPolicy``: M3. Until it exists ``L0Autonomy`` stands in: nothing is sent without approval.
* ``SendWindowProvider``: the clinic's send window (``pema.care.window.ChannelPolicySendWindow``).
* ``PatientDirectory``: pseudonym patient code -> care agent id (``pema.care.store.SqlCareStore``).
* ``CareStore``: the rows the loop reads and writes in ``agent.*`` (``pema.care.store.SqlCareStore``).
* ``TickRuleSource``: the rules of the daily tick that need no LLM (missed milestone, stale pending work).

S's ``ProactiveSendGuard`` (``pema_contracts.scheduler``) is used as it is for the per-patient daily cap.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from pema.care.events import CareEvent
from pema.care.models import ControlState
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


class HandoffAction(StrEnum):
    ANSWER = "answer"
    HANDOFF = "handoff"


@dataclass(frozen=True)
class HandoffVerdict:
    action: HandoffAction
    reason: str = ""


@dataclass(frozen=True)
class TickFinding:
    """One thing the rules of the daily tick found about a patient."""

    care_agent_id: UUID
    patient_ref: str
    kind: str
    needs_draft: bool
    payload: JsonObject = field(default_factory=dict[str, Any])


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

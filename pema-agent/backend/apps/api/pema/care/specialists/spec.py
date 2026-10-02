"""A specialist agent as configuration (PLAN-AI01-M section 9, recipe M4 "config factories").

New module (not a port). ``SpecialistSpec`` is the data of one specialist: id, persona, TOOL ALLOWLIST and
policy profile. ``to_agent_profile`` turns it into the D1 ``AgentProfile`` record stored in ``agent.agents``.

Allowlist vs the stored record. ``agent.agents`` stores a DENY list (``disabled_tools``): the capability of an
agent is "every known tool except these" (so a tool added later is on for an old agent). For a specialist that
is the wrong default, so the record is built as ``ALL_KNOWN_TOOL_KEYS - allowlist`` AND the resolver
(``toolkit.SpecialistToolkit``) intersects the allowlist of the spec with the record, so a tool added to the
catalogue tomorrow never reaches a specialist.

Depth 1 is enforced here, as data: ``delegate`` is never in an allowlist (``SpecialistSpec`` refuses to be
built with it) and is always in the deny list of the record.

Profiles. ``agent.agents.policy_profile`` only knows ``staff_assistant`` and ``patient_channel``. The plan
gives
Scheduler and Knowledge ``staff_assistant``; the Reviewer is "read only", which is not a profile: it is
``staff_assistant`` with an EMPTY allowlist (no tool at all, ``read_only=True``). Whatever the record says,
the
turn runs under the strictest profile of the chain (``inherited_profile_key``), which toward a patient is
``patient_channel``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from uuid import UUID

from pema.care.budget import MAX_TOOL_STEPS
from pema.care.task_result import TaskResult
from pema_contracts.agents import AgentProfile
from pema_contracts.common import JsonObject
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.tools import BUILTIN_TOOL_KEYS, CLINIC_TOOL_KEYS, AgentTool

DELEGATE_TOOL = "delegate"
SUBMIT_RESULT_TOOL = "submit_result"
"""The schema-constrained final answer of a specialist (not a catalogue tool: it exists only inside a
specialist run and is built by the runner)."""

SCHEDULER_ID = "care-scheduler"
KNOWLEDGE_ID = "care-knowledge"
REVIEWER_ID = "care-reviewer"
SPECIALIST_IDS: tuple[str, ...] = (SCHEDULER_ID, KNOWLEDGE_ID, REVIEWER_ID)

TOOL_SEARCH_SLOTS = "appointment.search_slots"
TOOL_BOOK = "appointment.book"
TOOL_KB_SEARCH = "kb_search"
TOOL_KB_INGEST = "kb_ingest"
TOOL_KB_LIST = "kb_list"
SPECIALIST_ONLY_TOOL_KEYS: tuple[str, ...] = (TOOL_SEARCH_SLOTS, TOOL_KB_INGEST, TOOL_KB_LIST)

ALL_KNOWN_TOOL_KEYS: tuple[str, ...] = tuple(
    dict.fromkeys([*BUILTIN_TOOL_KEYS, *CLINIC_TOOL_KEYS, *SPECIALIST_ONLY_TOOL_KEYS, DELEGATE_TOOL])
)
"""Every key the deny list of a specialist record is computed against."""


class SpecialistConfigError(ValueError):
    """A specialist was configured against the rules (``delegate`` in an allowlist, unknown tool key)."""


@dataclass(frozen=True)
class SpecialistSpec:
    agent_id: str
    name: str
    icon: str
    persona: str
    allowed_tools: frozenset[str]
    policy_profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT
    read_only: bool = False
    max_steps: int = MAX_TOOL_STEPS

    def __post_init__(self) -> None:
        if DELEGATE_TOOL in self.allowed_tools:
            raise SpecialistConfigError(
                f"{self.agent_id}: a specialist never gets '{DELEGATE_TOOL}' (depth 1)"
            )
        unknown = self.allowed_tools - set(ALL_KNOWN_TOOL_KEYS)
        if unknown:
            raise SpecialistConfigError(f"{self.agent_id}: unknown tool keys {sorted(unknown)}")
        if self.read_only and self.allowed_tools:
            raise SpecialistConfigError(f"{self.agent_id}: a read-only specialist has no tool")

    def disabled_tools(self) -> list[str]:
        """The deny list of the stored record: everything known that is not allowlisted (always has "
        "``delegate``)."""
        return sorted(set(ALL_KNOWN_TOOL_KEYS) - self.allowed_tools)

    def to_agent_profile(self, clinic_id: UUID) -> AgentProfile:
        return AgentProfile(
            id=self.agent_id,
            clinic_id=clinic_id,
            icon=self.icon,
            name=self.name,
            persona=self.persona,
            max_steps=self.max_steps,
            disabled_tools=self.disabled_tools(),
            policy_profile=self.policy_profile,
        )


def inherited_profile_key(*keys: PolicyProfileKey) -> PolicyProfileKey:
    """The strictest of the given profiles (``patient_channel`` beats ``staff_assistant``): PLAN-M "
    "section 11, rule 1."""
    if PolicyProfileKey.PATIENT_CHANNEL in keys or not keys:
        return PolicyProfileKey.PATIENT_CHANNEL
    return PolicyProfileKey.STAFF_ASSISTANT


def profile_of_turn(care_profile: str, specialists: Iterable[SpecialistSpec]) -> PolicyProfileKey:
    """The profile a delegated run uses: the strictest of the care agent and the specialists it calls.

    ``care_profile`` is the column of ``agent.care_agents`` (default and fail-safe: ``patient_channel``); an
    unreadable value counts as ``patient_channel``. Toward a patient the care agent is ALWAYS
    ``patient_channel`` (the column cannot say otherwise), so in practice the result is ``patient_channel``.
    """
    try:
        care = PolicyProfileKey(care_profile)
    except ValueError:
        care = PolicyProfileKey.PATIENT_CHANNEL
    return inherited_profile_key(care, *(s.policy_profile for s in specialists))


# ---------------------------------------------------------------------------------------- a run
@dataclass
class RunState:
    """What the tools of one specialist run collect, so the result can be checked against facts and not
    against what the model wrote (the citations of the Knowledge agent, the drafts of the Scheduler)."""

    citations: dict[str, str] = field(default_factory=dict[str, str])
    """source_id -> title of every knowledge hit the run really received."""
    slots: set[str] = field(default_factory=set[str])
    """UTC ISO ``starts_at`` of every free slot ``appointment.search_slots`` really returned."""
    artifacts: list[JsonObject] = field(default_factory=list[JsonObject])
    """Structured outcomes the tools produced (a drafted appointment)."""


@dataclass(frozen=True)
class SpecialistCall:
    """Everything the runner needs for ONE specialist run (no PII: ``task`` and ``context`` are masked)."""

    spec: SpecialistSpec
    task: str
    context: JsonObject
    tools: Mapping[str, AgentTool]
    state: RunState
    max_steps: int
    token_budget: int
    seconds_left: float


@dataclass(frozen=True)
class SpecialistRun:
    """What a runner reports. ``result`` is ``None`` when the run ended without a final answer."""

    result: TaskResult | None
    tokens: int = 0
    steps: int = 0
    stopped_by_steps: bool = False
    stopped_by_tokens: bool = False

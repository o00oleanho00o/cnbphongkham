"""In-memory doubles for the policy hooks (tests and evals only; never imported by production code).

``FakeClinicActions`` implements ``AgentFacingClinicActions`` with the one behaviour the policy relies on:
``create_review_item`` is idempotent on ``job_id``. ``FakePolicyGateway`` mimics the SQL functions of
revision ``p0001_identity_link`` (candidate link, ambiguous phone, one-time code, five failures an hour)
so the flow can be tested without Postgres; ``tests/policy/test_identity_sql.py`` runs the real ones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pema.policy.gateway import (
    ApprovedTemplate,
    LinkOutcome,
    LinkResult,
    PatientPolicyFlags,
)
from pema.policy.hooks import ClinicPolicyHooks
from pema.policy.identity import MAX_FAILED_LINK_ATTEMPTS_PER_HOUR
from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentCreate, AppointmentOut
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.clinic_actions import (
    AgentAppointmentView,
    CareContext,
    IdentityLink,
    IdentityLinkStatus,
    InboxRef,
)
from pema_contracts.common import now_vn
from pema_contracts.conversations import MessageStatus
from pema_contracts.policy import DEFAULT_PROFILES, PolicyContext, PolicyProfileKey
from pema_contracts.review import ReviewItemCreate, ReviewItemOut, ReviewStatus
from pema_contracts.testing import FAKE_CLINIC_ID


class FakeClinicActions:
    """Records review items; ``links`` maps (channel, external_user_id) to an ``IdentityLink``."""

    def __init__(self) -> None:
        self.review_items: list[ReviewItemCreate] = []
        self._by_job: dict[str, ReviewItemOut] = {}
        self.links: dict[tuple[ChannelKind, str], IdentityLink] = {}
        self.fail_create_review_item = False
        self.fail_resolve_identity = False

    async def get_care_context(self, ctx: ActionContext, patient_ref: str) -> CareContext | None:
        return None

    async def list_upcoming_appointments(
        self, ctx: ActionContext, patient_ref: str, limit: int = 5
    ) -> list[AgentAppointmentView]:
        return []

    async def book_appointment(self, ctx: ActionContext, request: AppointmentCreate) -> AppointmentOut:
        raise NotImplementedError

    async def create_review_item(self, ctx: ActionContext, request: ReviewItemCreate) -> ReviewItemOut:
        if self.fail_create_review_item:
            raise RuntimeError("review item store unavailable")
        existing = self._by_job.get(request.job_id)
        if existing is not None:
            return existing
        self.review_items.append(request)
        risk = request.risk_level
        out = ReviewItemOut(
            id=uuid4(),
            kind=request.kind,
            origin=request.origin,
            status=ReviewStatus.PENDING,
            conversation_id=None,
            patient_id=None,
            patient_code=request.patient_ref,
            draft_text=request.draft_text,
            payload=request.payload,
            sources=request.sources,
            risk_level=risk,
            red_flags=request.red_flags,
            requires_doctor=risk.value == "red_flag",
            job_id=request.job_id,
            created_at=now_vn(),
            version=1,
        )
        self._by_job[request.job_id] = out
        return out

    async def resolve_identity(
        self, ctx: ActionContext, channel: ChannelKind, external_user_id: str
    ) -> IdentityLink:
        if self.fail_resolve_identity:
            raise RuntimeError("identity store unavailable")
        return self.links.get(
            (channel, external_user_id),
            IdentityLink(
                channel=channel, external_user_id=external_user_id, status=IdentityLinkStatus.UNLINKED
            ),
        )

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        raise NotImplementedError

    async def record_outbound_message(
        self,
        ctx: ActionContext,
        *,
        conversation_id: UUID,
        text: str,
        status: MessageStatus,
        proactive: bool = False,
        review_item_id: UUID | None = None,
        error_code: str | None = None,
    ) -> InboxRef:
        raise NotImplementedError


@dataclass
class FakePolicyGateway:
    patients: dict[UUID, PatientPolicyFlags] = field(default_factory=dict[UUID, PatientPolicyFlags])
    templates: dict[str, ApprovedTemplate] = field(default_factory=dict[str, ApprovedTemplate])
    phone_index: dict[str, list[UUID]] = field(default_factory=dict[str, list[UUID]])
    """phone hash -> patients having that phone."""
    codes: dict[str, UUID] = field(default_factory=dict[str, UUID])
    """code hash -> patient the code was issued for (unused, unexpired)."""
    expired_codes: set[str] = field(default_factory=set[str])
    failures: dict[tuple[ChannelKind, str], int] = field(default_factory=dict[tuple[ChannelKind, str], int])
    pending: dict[tuple[ChannelKind, str], UUID] = field(default_factory=dict[tuple[ChannelKind, str], UUID])
    verified: dict[tuple[ChannelKind, str], UUID] = field(default_factory=dict[tuple[ChannelKind, str], UUID])
    calls: list[str] = field(default_factory=list[str])
    fail_template_lookup: bool = False

    def add_patient(self, flags: PatientPolicyFlags) -> None:
        self.patients[flags.patient_id] = flags

    async def patient_flags(self, clinic_id: UUID, patient_id: UUID) -> PatientPolicyFlags | None:
        return self.patients.get(patient_id)

    async def approved_template(self, clinic_id: UUID, template_key: str) -> ApprovedTemplate | None:
        if self.fail_template_lookup:
            raise RuntimeError("database unavailable")
        return self.templates.get(template_key)

    def _fail(self, key: tuple[ChannelKind, str], outcome: LinkOutcome) -> LinkResult:
        self.failures[key] = self.failures.get(key, 0) + 1
        return LinkResult(outcome)

    def _limited(self, key: tuple[ChannelKind, str]) -> bool:
        return self.failures.get(key, 0) >= MAX_FAILED_LINK_ATTEMPTS_PER_HOUR

    def _code_of(self, patient_id: UUID) -> str | None:
        flags = self.patients.get(patient_id)
        return None if flags is None else flags.code

    async def link_by_phone_hash(
        self, clinic_id: UUID, channel: ChannelKind, external_user_id: str, phone_hash: str
    ) -> LinkResult:
        self.calls.append("phone")
        key = (channel, external_user_id)
        if self._limited(key):
            return LinkResult(LinkOutcome.RATE_LIMITED)
        if key in self.verified:
            return LinkResult(
                LinkOutcome.ALREADY_VERIFIED, self.verified[key], self._code_of(self.verified[key])
            )
        matches = self.phone_index.get(phone_hash, [])
        if not matches:
            return self._fail(key, LinkOutcome.NO_MATCH)
        if len(matches) > 1:
            return self._fail(key, LinkOutcome.AMBIGUOUS)
        self.pending[key] = matches[0]
        return LinkResult(LinkOutcome.CANDIDATE_CREATED, matches[0], self._code_of(matches[0]))

    async def redeem_link_code(
        self, clinic_id: UUID, channel: ChannelKind, external_user_id: str, code_hash: str
    ) -> LinkResult:
        self.calls.append("code")
        key = (channel, external_user_id)
        if self._limited(key):
            return LinkResult(LinkOutcome.RATE_LIMITED)
        if code_hash in self.expired_codes:
            return self._fail(key, LinkOutcome.EXPIRED_CODE)
        patient_id = self.codes.pop(code_hash, None)
        if patient_id is None:
            return self._fail(key, LinkOutcome.INVALID_CODE)
        self.verified[key] = patient_id
        self.pending.pop(key, None)
        return LinkResult(LinkOutcome.VERIFIED, patient_id, self._code_of(patient_id))


FAKE_PATIENT_ID = UUID("00000000-0000-4000-8000-0000000000a1")
"""Synthetic patient 'P025' used across the policy tests."""


def make_policy_context(
    profile_key: PolicyProfileKey = PolicyProfileKey.PATIENT_CHANNEL,
    *,
    thread_id: str = "thread-1",
    account_id: str = "acc-1",
    isolated: bool = False,
    patient_id: UUID | None = None,
    identity_verified: bool = False,
) -> PolicyContext:
    """A ``PolicyContext`` of the given profile."""
    return PolicyContext(
        clinic_id=FAKE_CLINIC_ID,
        account_id=account_id,
        agent_id="agent-test",
        channel=ChannelKind.ZALO_BOT,
        thread_id=thread_id,
        profile=DEFAULT_PROFILES[profile_key],
        isolated=isolated,
        patient_id=patient_id,
        identity_verified=identity_verified,
    )


def make_hooks(
    *,
    gateway: FakePolicyGateway | None = None,
    escalate: bool = True,
    mask_when_optional: bool = False,
) -> tuple[ClinicPolicyHooks, FakeClinicActions, FakePolicyGateway]:
    """Real hooks over fakes: ``(hooks, actions, gateway)``."""
    actions = FakeClinicActions()
    gw = gateway if gateway is not None else FakePolicyGateway()
    hooks = ClinicPolicyHooks(
        actions=actions, gateway=gw, escalate=escalate, mask_when_optional=mask_when_optional
    )
    return hooks, actions, gw

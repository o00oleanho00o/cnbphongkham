"""The ONLY surface through which the agent side reaches clinic data (PLAN-AI01 principles 3 and 4).

``pema.agent``, ``pema.conversation``, ``pema.scheduler``, ``pema.policy``, ``pema.channels`` and the
workers may import ``pema.clinic.actions`` and nothing else of ``pema.clinic`` (enforced by
import-linter). In the database the ``agent_worker`` role cannot read any ``clinic.*`` table: it reads
views and calls SECURITY DEFINER functions of schema ``clinic_agent``, which these actions wrap.

Package B1 implements ``AgentFacingClinicActions`` in ``pema.clinic.actions.agent_facing``. Every
other package codes against this Protocol and tests with a fake.

Data minimisation: ``CareContext`` carries no phone, no national id, no address, no free clinical
text and no photo. ``display_name`` is present only for a VERIFIED identity and is replaced by the
patient code by the PII mask before any model call in ``patient_channel``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field

from pema_contracts.actions import ActionContext
from pema_contracts.appointments import AppointmentCreate, AppointmentOut
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.conversations import MessageStatus
from pema_contracts.review import ReviewItemCreate, ReviewItemOut


class FollowupMilestone(StrEnum):
    """Post-treatment milestones of the CRM rules d1, d3, d7."""

    D1 = "d1"
    D3 = "d3"
    D7 = "d7"


class IdentityLinkStatus(StrEnum):
    UNLINKED = "unlinked"
    PENDING = "pending"
    """Candidate link exists; a staff member has not confirmed it."""
    VERIFIED = "verified"
    REJECTED = "rejected"


class IdentityLink(ApiModel):
    """``zalo_uid`` (channel external user id) <-> patient record."""

    channel: ChannelKind
    external_user_id: str
    status: IdentityLinkStatus
    patient_id: UUID | None = None
    patient_code: str | None = None
    verified_at: VnDatetime | None = None


class CareContext(ApiModel):
    """The least context the agent needs about a patient. Source: views of schema ``clinic_agent``."""

    patient_code: str = Field(description="Pseudonym such as 'P025'.")
    identity_verified: bool
    display_name: str | None = Field(default=None, description="Only when identity_verified.")
    lifecycle_stage: Literal["new", "returning", "treating", "dormant", "reactivated"] | None = None
    days_since_last_visit: int | None = None
    last_protocol_id: str | None = Field(default=None, description="A code such as 'laser-co2', not text.")
    days_since_last_session: int | None = None
    remaining_sessions: int | None = None
    days_to_next_appointment: int | None = None
    followup_milestone: FollowupMilestone | None = None
    marketing_opt_out: bool = False
    consent_messaging: bool = False


class AgentAppointmentView(ApiModel):
    id: UUID
    starts_at: VnDatetime
    duration_min: int
    status: str
    doctor_id: UUID | None = None


class InboxRef(ApiModel):
    conversation_id: UUID
    message_id: UUID | None = None
    patient_id: UUID | None = None
    duplicate: bool = Field(default=False, description="update_id already recorded; nothing new was written.")


class AgentFacingClinicActions(Protocol):
    """Every method audits its mutations (actor_type='agent') and filters by ``ctx.clinic_id``."""

    async def get_care_context(self, ctx: ActionContext, patient_ref: str) -> CareContext | None:
        """Tool ``patient.get_care_context``. ``None`` when the code is unknown in this clinic."""
        ...

    async def list_upcoming_appointments(
        self, ctx: ActionContext, patient_ref: str, limit: int = 5
    ) -> list[AgentAppointmentView]: ...

    async def book_appointment(self, ctx: ActionContext, request: AppointmentCreate) -> AppointmentOut:
        """Tool ``appointment.book``. Goes through the same schedule validator as the UI. In
        ``patient_channel`` the result is a PROPOSAL that a human confirms (open item for B1)."""
        ...

    async def create_review_item(self, ctx: ActionContext, request: ReviewItemCreate) -> ReviewItemOut:
        """Tool ``review_item.create``. Idempotent on ``request.job_id``."""
        ...

    async def resolve_identity(
        self, ctx: ActionContext, channel: ChannelKind, external_user_id: str
    ) -> IdentityLink: ...

    async def record_inbound_message(self, ctx: ActionContext, message: InboundMessage) -> InboxRef:
        """Inbox of record (``clinic.conversation`` / ``clinic.message``). Idempotent on ``update_id``."""
        ...

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
    ) -> InboxRef: ...

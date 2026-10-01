"""Review queue DTOs (table ``clinic.review_item``).

In the ``patient_channel`` profile everything the agent would send to a patient lands here first
(``OutboundMode.REVIEW``). A human approves, edits or rejects; only then does the system send. Red-flag
items carry ``requires_doctor=True`` and are never auto-resolved.

The agent creates items through ``AgentFacingClinicActions.create_review_item`` (a SECURITY DEFINER
function for the ``agent_worker`` role); staff decide through the REST routes. Both end in the same
action in ``pema.clinic.actions`` (PLAN-AI01 principle 3).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, VnDatetime


class ReviewKind(StrEnum):
    REPLY_DRAFT = "reply_draft"
    """Answer to a patient message."""
    FOLLOWUP_DRAFT = "followup_draft"
    """Message from a scheduled job or a CRM rule that needs a human before sending."""
    TRIAGE_ALERT = "triage_alert"
    """Red flag found before any LLM call; goes straight to a doctor."""
    MEDIA_FLAG = "media_flag"
    """The patient sent an image/file; the agent does not process it, a person takes over."""
    IDENTITY_CHECK = "identity_check"
    """A zalo_uid is not yet linked to a verified patient; staff confirm or reject the link."""


class ReviewOrigin(StrEnum):
    AGENT_TURN = "agent_turn"
    SCHEDULED_AGENT = "scheduled_agent"
    CRM_RULE = "crm_rule"
    POLICY = "policy"
    """Raised by a policy hook (red flag, media, identity), not by the model."""


class ReviewStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    """Approved as-is or after edit; the send is queued or done."""
    REJECTED = "rejected"
    ESCALATED = "escalated"
    EXPIRED = "expired"


class RiskLevel(StrEnum):
    NORMAL = "normal"
    ATTENTION = "attention"
    RED_FLAG = "red_flag"


class SourceCitation(ApiModel):
    """A knowledge-base passage the draft relies on. AI drafts must carry at least one when the
    answer states a clinic fact."""

    source_id: str
    title: str
    snippet: str = Field(max_length=500)
    score: float | None = None


class ReviewItemOut(ApiModel):
    id: UUID
    kind: ReviewKind
    origin: ReviewOrigin
    status: ReviewStatus
    conversation_id: UUID | None
    patient_id: UUID | None
    patient_code: str | None
    draft_text: str | None
    final_text: str | None = None
    payload: dict[str, Any] | None = None
    sources: list[SourceCitation] = Field(default_factory=list[SourceCitation])
    risk_level: RiskLevel
    red_flags: list[str] = Field(default_factory=list[str])
    requires_doctor: bool
    job_id: str | None = Field(default=None, description="Scheduled job or agent turn that produced it.")
    model: str | None = None
    prompt_version: str | None = None
    created_at: VnDatetime
    decided_at: VnDatetime | None = None
    decided_by: UUID | None = None
    decision_note: str | None = None
    version: int


class ReviewItemCreate(ApiModel):
    """Posted by the agent worker. ``job_id`` is the idempotency key: a second post for the same
    ``job_id`` returns the first item."""

    job_id: str
    clinic_id: UUID
    patient_ref: str | None = Field(default=None, description="Patient code, never a name or phone.")
    conversation_ref: str | None = Field(default=None, description="clinic.conversation id as string.")
    kind: ReviewKind
    origin: ReviewOrigin = ReviewOrigin.AGENT_TURN
    draft_text: str | None = Field(default=None, max_length=4000)
    payload: dict[str, Any] | None = None
    sources: list[SourceCitation] = Field(default_factory=list[SourceCitation])
    risk_level: RiskLevel = RiskLevel.NORMAL
    red_flags: list[str] = Field(default_factory=list[str])
    model: str | None = None
    prompt_version: str | None = None


class ReviewApprove(ApiModel):
    version: int
    final_text: str | None = Field(
        default=None, max_length=2000, description="Edited text; omitted = send the draft unchanged."
    )
    note: str | None = Field(default=None, max_length=1000)
    send: bool = Field(default=True, description="False approves the content without sending it.")


class ReviewReject(ApiModel):
    version: int
    reason: str = Field(min_length=1, max_length=1000)


class ReviewEscalate(ApiModel):
    version: int
    note: str | None = Field(default=None, max_length=1000)

"""Conversation and message DTOs (tables ``clinic.conversation`` / ``clinic.message``).

Message bodies are PII-bearing clinical-adjacent text: they are stored only in ``clinic.*`` and
returned only to authorised staff. In ``patient_channel`` the agent never sees ``MessageOut.body``; it
sees text that already went through the PII mask of ``pema.policy.pii``.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import Field

from pema_contracts.channel import ChannelKind
from pema_contracts.common import ApiModel, VnDatetime


class ConversationStatus(StrEnum):
    OPEN = "open"
    PENDING_REVIEW = "pending_review"
    """An AI draft or an alert waits in the review queue."""
    HANDOFF = "handoff"
    """Escalated to a doctor (red flag or explicit request)."""
    CLOSED = "closed"


class MessageDirection(StrEnum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class SenderType(StrEnum):
    PATIENT = "patient"
    STAFF = "staff"
    AI_DRAFT = "ai_draft"
    """Draft written by the agent; becomes ``STAFF`` once a human approves and sends it."""
    SYSTEM = "system"
    """Self-approved rule message (simple appointment reminder)."""


class MessageStatus(StrEnum):
    RECEIVED = "received"
    DRAFT = "draft"
    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    REJECTED = "rejected"
    """Blocked by a channel guard (cap, kill switch, window, not friend)."""


class ConversationSummary(ApiModel):
    id: UUID
    channel: ChannelKind
    patient_id: UUID | None
    patient_code: str | None
    patient_display_name: str | None
    status: ConversationStatus
    assigned_user_id: UUID | None = None
    last_message_at: VnDatetime | None = None
    last_message_preview: str | None = Field(default=None, max_length=120)
    unread_count: int = 0
    has_pending_review: bool = False
    version: int


class ConversationOut(ConversationSummary):
    external_ref: str = Field(description="Opaque channel conversation id; staff-only.")
    created_at: VnDatetime


class MessageOut(ApiModel):
    id: UUID
    conversation_id: UUID
    direction: MessageDirection
    sender_type: SenderType
    sender_user_id: UUID | None = None
    body: str | None
    status: MessageStatus
    proactive: bool = False
    review_item_id: UUID | None = None
    error_code: str | None = None
    created_at: VnDatetime
    sent_at: VnDatetime | None = None


class MessageCreate(ApiModel):
    """Staff sends a manual reply (or sends an approved draft via the review endpoints)."""

    text: str = Field(min_length=1, max_length=2000)
    proactive: bool = False


class ConversationUpdate(ApiModel):
    version: int
    status: ConversationStatus | None = None
    assigned_user_id: UUID | None = None


class WebhookAck(ApiModel):
    """Body returned to the channel for webhook calls (always 200 once authenticated)."""

    ok: bool = True
    duplicate: bool = False

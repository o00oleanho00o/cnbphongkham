"""Builders of the ``ReviewItemCreate`` requests the policy opens (and that callers open for held text).

New module. Everything the ``patient_channel`` profile does not let through, or must show a person,
becomes a ``review_item`` (``clinic.review_item``), created through
``AgentFacingClinicActions.create_review_item`` (idempotent on ``job_id``, audited as actor ``agent``):

===============  ==============  ============================================  ===================
situation        ``kind``        who opens it                                  stays pending until
===============  ==============  ============================================  ===================
red flag         triage_alert    ``before_llm`` hook (this package)            a DOCTOR decides
patient image    media_flag      ``before_llm`` hook (this package)            staff take over
unverified id    identity_check  ``before_llm`` hook (this package)            staff confirm link
turn reply       reply_draft     the caller of ``on_outbound`` (C2)            staff approve + send
scheduled text   followup_draft  the caller of ``on_outbound`` (S)             staff approve + send
===============  ==============  ============================================  ===================

``job_id`` is the idempotency key, so every id below is derived from stable ids (account, thread,
message ids), never from the clock: a retried turn finds the first item instead of opening a second one.

Review payloads carry ids and codes only. The patient's words are already in the Inbox
(``clinic.message``); a review item must not duplicate them, so a triage alert never carries the message.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.policy import OutboundOrigin, PolicyContext
from pema_contracts.review import (
    ReviewItemCreate,
    ReviewKind,
    ReviewOrigin,
    RiskLevel,
    SourceCitation,
)

RED_FLAG_HOLDING_DRAFT = (
    "Dạ phòng khám đã nhận được thông tin của mình và đang chuyển cho bác sĩ xem ngay. "
    "Nhân viên sẽ liên hệ lại với mình sớm nhất."
)
"""Draft shown to the staff member who handles a triage alert. FICTIONAL wording: the clinic's doctor
rewrites it (it is a draft like every other outbound text and is sent only after a human approves)."""

MEDIA_FLAG_HOLDING_DRAFT = (
    "Dạ em đã nhận được hình/tệp của mình. Nhân viên phòng khám sẽ xem và phản hồi lại cho mình ạ."
)

MAX_DRAFT_CHARS = 4000
"""``ReviewItemCreate.draft_text`` limit."""


def _digest(parts: Sequence[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def batch_message_ids(batch: Sequence[InboundMessage]) -> list[str]:
    return [m.msg_id for m in batch if not m.is_self]


def red_flag_job_id(ctx: PolicyContext, batch: Sequence[InboundMessage]) -> str:
    """Idempotency key of the triage alert of this batch. Public so a caller that must open the alert
    itself (the policy hook failed) uses the SAME key and cannot create a duplicate."""
    return f"policy:red_flag:{ctx.account_id}:{ctx.thread_id}:{_digest(batch_message_ids(batch))}"


def media_flag_job_id(ctx: PolicyContext, batch: Sequence[InboundMessage]) -> str:
    return f"policy:media:{ctx.account_id}:{ctx.thread_id}:{_digest(batch_message_ids(batch))}"


def identity_check_job_id(ctx: PolicyContext, external_user_id: str, patient_code: str) -> str:
    return f"policy:identity:{ctx.account_id}:{_digest([ctx.thread_id, external_user_id, patient_code])}"


def _batch_payload(ctx: PolicyContext, batch: Sequence[InboundMessage], trigger: str) -> dict[str, object]:
    return {
        "trigger": trigger,
        "channel": ctx.channel.value,
        "account_id": ctx.account_id,
        "thread_id": ctx.thread_id,
        "msg_ids": batch_message_ids(batch),
    }


def build_red_flag_item(
    ctx: PolicyContext,
    batch: Sequence[InboundMessage],
    red_flags: Sequence[str],
    *,
    patient_code: str | None = None,
) -> ReviewItemCreate:
    return ReviewItemCreate(
        job_id=red_flag_job_id(ctx, batch),
        clinic_id=ctx.clinic_id,
        patient_ref=patient_code,
        kind=ReviewKind.TRIAGE_ALERT,
        origin=ReviewOrigin.POLICY,
        draft_text=RED_FLAG_HOLDING_DRAFT,
        payload=_batch_payload(ctx, batch, "red_flag"),
        risk_level=RiskLevel.RED_FLAG,
        red_flags=list(red_flags),
    )


def build_media_flag_item(
    ctx: PolicyContext, batch: Sequence[InboundMessage], *, patient_code: str | None = None
) -> ReviewItemCreate:
    kinds = sorted({m.kind.value for m in batch if not m.is_self})
    payload = _batch_payload(ctx, batch, "inbound_media")
    payload["kinds"] = kinds
    return ReviewItemCreate(
        job_id=media_flag_job_id(ctx, batch),
        clinic_id=ctx.clinic_id,
        patient_ref=patient_code,
        kind=ReviewKind.MEDIA_FLAG,
        origin=ReviewOrigin.POLICY,
        draft_text=MEDIA_FLAG_HOLDING_DRAFT,
        payload=payload,
        risk_level=RiskLevel.ATTENTION,
    )


def build_identity_check_item(
    ctx: PolicyContext, *, channel: ChannelKind, external_user_id: str, patient_code: str, method: str
) -> ReviewItemCreate:
    return ReviewItemCreate(
        job_id=identity_check_job_id(ctx, external_user_id, patient_code),
        clinic_id=ctx.clinic_id,
        patient_ref=patient_code,
        kind=ReviewKind.IDENTITY_CHECK,
        origin=ReviewOrigin.POLICY,
        payload={
            "trigger": "identity_link_candidate",
            "method": method,
            "channel": channel.value,
            "account_id": ctx.account_id,
            "thread_id": ctx.thread_id,
            "external_user_id": external_user_id,
            "candidate_patient_code": patient_code,
        },
        risk_level=RiskLevel.ATTENTION,
    )


_OUTBOUND_KIND: dict[OutboundOrigin, tuple[ReviewKind, ReviewOrigin]] = {
    OutboundOrigin.TURN_REPLY: (ReviewKind.REPLY_DRAFT, ReviewOrigin.AGENT_TURN),
    OutboundOrigin.TOOL_SEND: (ReviewKind.REPLY_DRAFT, ReviewOrigin.AGENT_TURN),
    OutboundOrigin.SCHEDULED_MESSAGE: (ReviewKind.FOLLOWUP_DRAFT, ReviewOrigin.CRM_RULE),
    OutboundOrigin.SCHEDULED_AGENT: (ReviewKind.FOLLOWUP_DRAFT, ReviewOrigin.SCHEDULED_AGENT),
}


def build_outbound_review_item(
    ctx: PolicyContext,
    text: str,
    origin: OutboundOrigin,
    *,
    job_id: str,
    patient_code: str | None = None,
    conversation_ref: str | None = None,
    sources: Sequence[SourceCitation] = (),
    risk_level: RiskLevel = RiskLevel.NORMAL,
    model: str | None = None,
    prompt_version: str | None = None,
) -> ReviewItemCreate:
    """For a caller that received ``HOLD_FOR_REVIEW`` from ``on_outbound``.

    ``job_id`` must be stable for the turn or job (the turn id, the scheduled job id + its run slot), so
    a retry does not queue the same text twice. Text over 4000 characters is cut and flagged in the
    payload; the 2000-character send limit of a channel is the sender's concern, not the reviewer's.
    """
    kind, review_origin = _OUTBOUND_KIND[origin]
    payload: dict[str, object] = {
        "channel": ctx.channel.value,
        "account_id": ctx.account_id,
        "thread_id": ctx.thread_id,
        "origin": origin.value,
    }
    draft = text
    if len(draft) > MAX_DRAFT_CHARS:
        draft = draft[:MAX_DRAFT_CHARS]
        payload["truncated"] = True
    return ReviewItemCreate(
        job_id=job_id,
        clinic_id=ctx.clinic_id,
        patient_ref=patient_code,
        conversation_ref=conversation_ref,
        kind=kind,
        origin=review_origin,
        draft_text=draft,
        payload=payload,
        sources=list(sources),
        risk_level=risk_level,
        model=model,
        prompt_version=prompt_version,
    )

"""MIRROR of the review item builders of package P (``pema.policy.review``).

New module, temporary. The turn pipeline opens a ``review_item`` in two places: for a text the policy HELD
(``on_outbound`` -> ``HOLD_FOR_REVIEW``; the hook only decides, the CALLER opens the item) and, as a safety
net, for a hand-off whose escalation the ``before_llm`` hook reported as failed. Package P owns the builders
and the idempotency keys; they are copied here, line for line where it matters (the ``job_id`` functions),
because ``pema.channels`` cannot import ``pema.policy`` while the packages live in separate worktrees. The
``job_id`` equality is what makes a second call harmless: ``create_review_item`` is idempotent on it, so an
item opened by the hook and again here is still ONE item.

Package G replaces this module by ``from pema.policy.review import ...``; ``test_policy_review_mirror``
compares the two as soon as both exist (``importorskip``).
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from pema_contracts.channel import InboundMessage
from pema_contracts.policy import OutboundOrigin, PolicyContext
from pema_contracts.review import ReviewItemCreate, ReviewKind, ReviewOrigin, RiskLevel, SourceCitation

RED_FLAG_HOLDING_DRAFT = (
    "Dạ phòng khám đã nhận được thông tin của mình và đang chuyển cho bác sĩ xem ngay. "
    "Nhân viên sẽ liên hệ lại với mình sớm nhất."
)

MEDIA_FLAG_HOLDING_DRAFT = (
    "Dạ em đã nhận được hình/tệp của mình. Nhân viên phòng khám sẽ xem và phản hồi lại cho mình ạ."
)

MAX_DRAFT_CHARS = 4000

_OUTBOUND_KIND: dict[OutboundOrigin, tuple[ReviewKind, ReviewOrigin]] = {
    OutboundOrigin.TURN_REPLY: (ReviewKind.REPLY_DRAFT, ReviewOrigin.AGENT_TURN),
    OutboundOrigin.TOOL_SEND: (ReviewKind.REPLY_DRAFT, ReviewOrigin.AGENT_TURN),
    OutboundOrigin.SCHEDULED_MESSAGE: (ReviewKind.FOLLOWUP_DRAFT, ReviewOrigin.CRM_RULE),
    OutboundOrigin.SCHEDULED_AGENT: (ReviewKind.FOLLOWUP_DRAFT, ReviewOrigin.SCHEDULED_AGENT),
}


def _digest(parts: Sequence[str]) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def batch_message_ids(batch: Sequence[InboundMessage]) -> list[str]:
    return [m.msg_id for m in batch if not m.is_self]


def red_flag_job_id(ctx: PolicyContext, batch: Sequence[InboundMessage]) -> str:
    return f"policy:red_flag:{ctx.account_id}:{ctx.thread_id}:{_digest(batch_message_ids(batch))}"


def media_flag_job_id(ctx: PolicyContext, batch: Sequence[InboundMessage]) -> str:
    return f"policy:media:{ctx.account_id}:{ctx.thread_id}:{_digest(batch_message_ids(batch))}"


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
    conversation_ref: str | None = None,
) -> ReviewItemCreate:
    return ReviewItemCreate(
        job_id=red_flag_job_id(ctx, batch),
        clinic_id=ctx.clinic_id,
        patient_ref=patient_code,
        conversation_ref=conversation_ref,
        kind=ReviewKind.TRIAGE_ALERT,
        origin=ReviewOrigin.POLICY,
        draft_text=RED_FLAG_HOLDING_DRAFT,
        payload=_batch_payload(ctx, batch, "red_flag"),
        risk_level=RiskLevel.RED_FLAG,
        red_flags=list(red_flags),
    )


def build_media_flag_item(
    ctx: PolicyContext,
    batch: Sequence[InboundMessage],
    *,
    patient_code: str | None = None,
    conversation_ref: str | None = None,
) -> ReviewItemCreate:
    kinds = sorted({m.kind.value for m in batch if not m.is_self})
    payload = _batch_payload(ctx, batch, "inbound_media")
    payload["kinds"] = kinds
    return ReviewItemCreate(
        job_id=media_flag_job_id(ctx, batch),
        clinic_id=ctx.clinic_id,
        patient_ref=patient_code,
        conversation_ref=conversation_ref,
        kind=ReviewKind.MEDIA_FLAG,
        origin=ReviewOrigin.POLICY,
        draft_text=MEDIA_FLAG_HOLDING_DRAFT,
        payload=payload,
        risk_level=RiskLevel.ATTENTION,
    )


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
    """For a caller that received ``HOLD_FOR_REVIEW`` from ``on_outbound``. ``job_id`` must be stable for the
    turn or job so a retry does not queue the same text twice."""
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

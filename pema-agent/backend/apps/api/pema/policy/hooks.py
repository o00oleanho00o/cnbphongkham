"""``PolicyHooks`` implementation for both profiles (PLAN-AI01 section 5).

New module. One class, ``ClinicPolicyHooks``, implements the eight hook points of
``pema_contracts.policy.PolicyHooks``. It behaves by the FLAGS of ``ctx.profile`` (the data in
``DEFAULT_PROFILES``), so:

* ``staff_assistant`` (every flag off): each hook returns what ``PermissivePolicyHooks`` returns. The
  original zalo-agent behaviour is untouched; there is a test per hook that says so.
* ``patient_channel``: what the table of section 5 says, implemented below.

Where each rule of the table lives
----------------------------------
=========================================  =============================================================
rule (``patient_channel``)                 hook
=========================================  =============================================================
red flag -> doctor BEFORE the model        ``before_llm``: ``HAND_OFF`` + a ``triage_alert`` review item
patient image/file -> Inbox flag, human    ``before_llm``: ``HAND_OFF`` + a ``media_flag`` review item
PII masked before the model                ``before_llm`` (mask) and ``after_llm`` (restore names only)
zalo_uid <-> record before naming anything ``before_llm`` (code / phone flow) and ``verify_identity``
every outbound text -> review, then send   ``on_outbound``: ``HOLD_FOR_REVIEW``
scheduled agent job only drafts            ``check_job``: ``DOWNGRADE_TO_DRAFT``
scheduled message only from a template     ``check_job``: ``DENY`` unless an approved template
marketingOptOut blocks marketing           ``check_job``: ``DENY``; birthday is never auto-sent: ``DENY``
image/video/document/web/MCP tools off     ``filter_tool_keys``
save_memory off for patient content        ``filter_tool_keys`` (tool hidden) and ``allow_memory_write``
daily proactive cap per patient+account    ``proactive_cap``: the scope key
=========================================  =============================================================

Failure policy: when the policy cannot decide (database down, action failed) it fails CLOSED. A red-flag
hand-off stays a hand-off even if the review item could not be created (``reason`` says so, the caller
retries with ``review.red_flag_job_id``); a job whose template cannot be checked is denied.

What this class does NOT do, because it is another package's call site: opening the review item for a
held outbound text (``on_outbound`` only decides; the caller uses ``review.build_outbound_review_item``),
and masking the HISTORY and tool results the model sees (``mask_text`` is public for D1/D2/D4).

Logging: ids, codes and counts only; never message text, names, phone numbers or hashes.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from uuid import UUID

from pema.policy.gateway import LinkOutcome, PolicyGateway
from pema.policy.identity import IdentityLinker
from pema.policy.pii import KnownName, MaskVault
from pema.policy.redflags import detect_red_flags_in_batch
from pema.policy.review import (
    build_identity_check_item,
    build_media_flag_item,
    build_red_flag_item,
)
from pema.policy.text_normalize import fold_text, to_nfc
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.channel import ChannelKind, InboundKind, InboundMessage
from pema_contracts.clinic_actions import AgentFacingClinicActions, IdentityLinkStatus
from pema_contracts.policy import (
    BeforeLlmAction,
    BeforeLlmDecision,
    IdentityStatus,
    InboundMediaAction,
    JobAction,
    JobDecision,
    MemorySource,
    MemoryWritePolicy,
    OutboundAction,
    OutboundDecision,
    OutboundMode,
    OutboundOrigin,
    PiiMaskMode,
    PolicyContext,
    PolicyProfileKey,
    ProactiveCap,
    ProactiveCapScope,
    ScheduledJobPolicy,
)
from pema_contracts.review import ReviewItemCreate
from pema_contracts.roles import ActorType
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind

log = create_logger("policy")

MEDIA_KINDS_TO_FLAG: frozenset[InboundKind] = frozenset(
    {InboundKind.IMAGE, InboundKind.FILE, InboundKind.VOICE}
)
"""Inbound kinds that cannot be read by the text-only agent and go to a person. A voice note is included
on purpose: it may say "tôi khó thở" and would otherwise bypass the red-flag check. Stickers do not."""

SAVE_MEMORY_TOOL_KEY = "save_memory"
MCP_TOOL_PREFIX = "mcp__"
_BIRTHDAY = re.compile(r"birthday|sinh[\s_.\-]*nhat")

REASON_RED_FLAG = "red_flag"
REASON_RED_FLAG_ESCALATION_FAILED = "red_flag_escalation_failed"
REASON_MEDIA = "inbound_media"
REASON_MEDIA_FLAG_FAILED = "inbound_media_flag_failed"


def _action_context(ctx: PolicyContext) -> ActionContext:
    return ActionContext(
        clinic_id=ctx.clinic_id,
        actor_type=ActorType.AGENT,
        source=ActionSource.AGENT,
        request_id=ctx.request_id,
    )


class ClinicPolicyHooks:
    """The real ``PolicyHooks``. Inject ``actions`` (B1) and ``gateway`` (``SqlPolicyGateway`` or a fake)."""

    def __init__(
        self,
        *,
        actions: AgentFacingClinicActions,
        gateway: PolicyGateway,
        vault: MaskVault | None = None,
        escalate: bool = True,
        mask_when_optional: bool = False,
    ) -> None:
        self._actions = actions
        self._gateway = gateway
        self.vault = vault if vault is not None else MaskVault()
        self._escalate = escalate
        self._mask_when_optional = mask_when_optional
        self._linker = IdentityLinker(gateway)

    # ----------------------------------------------------------------------------- helpers
    def _masking_on(self, ctx: PolicyContext) -> bool:
        mode = ctx.profile.pii_mask
        return mode is PiiMaskMode.REQUIRED or (mode is PiiMaskMode.OPTIONAL and self._mask_when_optional)

    @staticmethod
    def _mask_key(ctx: PolicyContext) -> str:
        return f"{ctx.clinic_id}:{ctx.account_id}:{ctx.thread_id}"

    async def _patient_code(self, ctx: PolicyContext) -> str | None:
        """The code of the VERIFIED patient of this turn (review items name a patient by code only)."""
        if not (ctx.identity_verified and ctx.patient_id is not None):
            return None
        try:
            flags = await self._gateway.patient_flags(ctx.clinic_id, ctx.patient_id)
        except Exception as exc:
            log.warning("patient lookup failed", err=exc, account_id=ctx.account_id)
            return None
        return None if flags is None else flags.code

    async def _open_item(self, ctx: PolicyContext, request: ReviewItemCreate, what: str) -> bool:
        try:
            await self._actions.create_review_item(_action_context(ctx), request)
        except Exception as exc:
            log.error(
                "review item failed", err=exc, what=what, account_id=ctx.account_id, thread_id=ctx.thread_id
            )
            return False
        return True

    # ------------------------------------------------------------------------------ before_llm
    async def before_llm(self, ctx: PolicyContext, batch: Sequence[InboundMessage]) -> BeforeLlmDecision:
        profile = ctx.profile
        inbound = [m for m in batch if not m.is_self]
        patient_code: str | None = None

        flags: list[str] = []
        if profile.red_flag_check:
            found = detect_red_flags_in_batch(m.text for m in inbound)
            flags = list(found.flags)

        media_present = profile.inbound_media is InboundMediaAction.FLAG_AND_HAND_OFF and any(
            m.kind in MEDIA_KINDS_TO_FLAG or m.images for m in inbound
        )

        if flags or media_present:
            patient_code = await self._patient_code(ctx)

        if flags:
            ok = True
            if self._escalate:
                ok = await self._open_item(
                    ctx, build_red_flag_item(ctx, inbound, flags, patient_code=patient_code), "red_flag"
                )
            if media_present and self._escalate:
                await self._open_item(
                    ctx, build_media_flag_item(ctx, inbound, patient_code=patient_code), "media"
                )
            log.warning(
                "red flag handed off",
                account_id=ctx.account_id,
                thread_id=ctx.thread_id,
                flags=",".join(flags),
                messages=len(inbound),
                escalated=ok,
            )
            return BeforeLlmDecision(
                action=BeforeLlmAction.HAND_OFF,
                red_flags=flags,
                reason=REASON_RED_FLAG if ok else REASON_RED_FLAG_ESCALATION_FAILED,
            )

        if media_present:
            ok = True
            if self._escalate:
                ok = await self._open_item(
                    ctx, build_media_flag_item(ctx, inbound, patient_code=patient_code), "media"
                )
            log.info(
                "inbound media handed off", account_id=ctx.account_id, thread_id=ctx.thread_id, escalated=ok
            )
            return BeforeLlmDecision(
                action=BeforeLlmAction.HAND_OFF, reason=REASON_MEDIA if ok else REASON_MEDIA_FLAG_FAILED
            )

        if profile.require_identity_verification and not ctx.identity_verified:
            await self._try_identity_link(ctx, inbound)

        return await self._masked_decision(ctx, inbound)

    async def _masked_decision(
        self, ctx: PolicyContext, inbound: Sequence[InboundMessage]
    ) -> BeforeLlmDecision:
        if not self._masking_on(ctx):
            return BeforeLlmDecision()
        token, session = self.vault.session_for(self._mask_key(ctx))
        for message in inbound:
            if message.sender_name.strip():
                session.add_known_name(KnownName(message.sender_name))
        if ctx.identity_verified and ctx.patient_id is not None:
            try:
                flags = await self._gateway.patient_flags(ctx.clinic_id, ctx.patient_id)
            except Exception as exc:
                log.warning("patient lookup failed", err=exc, account_id=ctx.account_id)
                flags = None
            if flags is not None:
                session.add_known_name(KnownName(flags.full_name, flags.code))
        masked: dict[str, str] = {}
        for message in inbound:
            if not message.text:
                continue
            result = session.mask(message.text)
            if result.changed:
                masked[message.msg_id] = result.text
        return BeforeLlmDecision(masked_text_by_msg_id=masked, mask_token=token)

    async def _try_identity_link(self, ctx: PolicyContext, inbound: Sequence[InboundMessage]) -> None:
        senders = {m.sender_id for m in inbound if m.sender_id}
        if len(senders) != 1:
            return
        external_user_id = next(iter(senders))
        try:
            attempt = await self._linker.attempt(
                ctx.clinic_id, ctx.channel, external_user_id, [m.text for m in inbound if m.text]
            )
        except Exception as exc:
            log.warning("identity link failed", err=exc, account_id=ctx.account_id)
            return
        if attempt is None:
            return
        log.info(
            "identity link attempt",
            account_id=ctx.account_id,
            thread_id=ctx.thread_id,
            method=attempt.method,
            outcome=attempt.outcome.value,
        )
        if attempt.outcome is LinkOutcome.CANDIDATE_CREATED and attempt.patient_code:
            await self._open_item(
                ctx,
                build_identity_check_item(
                    ctx,
                    channel=ctx.channel,
                    external_user_id=external_user_id,
                    patient_code=attempt.patient_code,
                    method=attempt.method,
                ),
                "identity_check",
            )

    def mask_text(self, ctx: PolicyContext, text: str) -> str:
        """Mask a text with the SAME placeholders as the turn (history lines, tool results, a prompt field).

        D1/D2/D4 call this for everything they put in front of the model besides the batch. A no-op when
        the profile does not mask."""
        if not self._masking_on(ctx):
            return text
        _, session = self.vault.session_for(self._mask_key(ctx))
        return session.mask(text).text

    # ------------------------------------------------------------------------------ after_llm
    async def after_llm(self, ctx: PolicyContext, text: str, mask_token: str | None) -> str:
        if not self._masking_on(ctx):
            return text
        session = self.vault.get(mask_token)
        if session is None:
            _, session = self.vault.session_for(self._mask_key(ctx))
        return session.restore(text)

    # ------------------------------------------------------------------------ filter_tool_keys
    async def filter_tool_keys(self, ctx: PolicyContext, keys: frozenset[str]) -> frozenset[str]:
        profile = ctx.profile
        blocked: set[str] = set(profile.disabled_tool_keys)
        if profile.memory_write is MemoryWritePolicy.STAFF_ONLY:
            blocked.add(SAVE_MEMORY_TOOL_KEY)
        if profile.key is PolicyProfileKey.PATIENT_CHANNEL:
            blocked.update(k for k in keys if k.startswith(MCP_TOOL_PREFIX))
        return frozenset(k for k in keys if k not in blocked)

    # ----------------------------------------------------------------------- allow_memory_write
    async def allow_memory_write(self, ctx: PolicyContext, source: MemorySource) -> bool:
        if ctx.profile.memory_write is MemoryWritePolicy.ALLOW:
            return True
        return source is MemorySource.STAFF

    # ---------------------------------------------------------------------------- on_outbound
    async def on_outbound(
        self, ctx: PolicyContext, text: str, *, proactive: bool, origin: OutboundOrigin
    ) -> OutboundDecision:
        if ctx.profile.outbound_mode is OutboundMode.DIRECT:
            return OutboundDecision()
        if not text.strip():
            return OutboundDecision(action=OutboundAction.DROP, reason="empty_text")
        return OutboundDecision(action=OutboundAction.HOLD_FOR_REVIEW, reason="review_required")

    # ------------------------------------------------------------------------------ check_job
    async def check_job(self, ctx: PolicyContext, job: CreateScheduledJobInput) -> JobDecision:
        profile = ctx.profile
        if profile.scheduled_jobs is ScheduledJobPolicy.ANY:
            return JobDecision()

        template_key = job.payload.strip() if job.kind is JobKind.MESSAGE else ""
        if not profile.birthday_auto_send and self._is_birthday(job, template_key):
            return JobDecision(action=JobAction.DENY, reason="birthday_never_auto_sent")

        if job.kind is JobKind.AGENT:
            return JobDecision(action=JobAction.DOWNGRADE_TO_DRAFT, reason="agent_job_drafts_only")

        try:
            template = await self._gateway.approved_template(job.clinic_id, template_key)
        except Exception as exc:
            log.error("template lookup failed", err=exc, account_id=job.account_id)
            return JobDecision(action=JobAction.DENY, reason="policy_unavailable")
        if template is None:
            return JobDecision(action=JobAction.DENY, reason="template_not_approved")

        if template.marketing and profile.marketing_opt_out_blocks_marketing:
            return await self._check_marketing(ctx, job)
        return JobDecision()

    async def _check_marketing(self, ctx: PolicyContext, job: CreateScheduledJobInput) -> JobDecision:
        patient_id: UUID | None = job.patient_id or ctx.patient_id
        if patient_id is None:
            return JobDecision(action=JobAction.DENY, reason="marketing_patient_unknown")
        try:
            flags = await self._gateway.patient_flags(job.clinic_id, patient_id)
        except Exception as exc:
            log.error("patient lookup failed", err=exc, account_id=job.account_id)
            return JobDecision(action=JobAction.DENY, reason="policy_unavailable")
        if flags is None:
            return JobDecision(action=JobAction.DENY, reason="marketing_patient_unknown")
        if flags.marketing_opt_out:
            return JobDecision(action=JobAction.DENY, reason="marketing_opt_out")
        return JobDecision()

    @staticmethod
    def _is_birthday(job: CreateScheduledJobInput, template_key: str) -> bool:
        haystack = fold_text(to_nfc(" ".join([job.name, job.dedupe_key or "", template_key])))
        return _BIRTHDAY.search(haystack) is not None

    # -------------------------------------------------------------------------- proactive_cap
    async def proactive_cap(self, ctx: PolicyContext, default_max_per_day: int | None) -> ProactiveCap:
        scope = ctx.profile.proactive_cap_scope
        if scope is ProactiveCapScope.PATIENT_ACCOUNT:
            if ctx.patient_id is not None:
                key = f"patient:{ctx.patient_id}:{ctx.account_id}"
            else:
                # no verified patient yet: the cap still exists, per conversation
                key = f"thread:{ctx.account_id}:{ctx.thread_id}"
        else:
            key = f"{ctx.account_id}:{ctx.thread_id}"
        return ProactiveCap(scope_key=key, max_per_day=default_max_per_day)

    # ----------------------------------------------------------------------- verify_identity
    async def verify_identity(
        self, ctx: PolicyContext, channel: ChannelKind, external_user_id: str
    ) -> IdentityStatus:
        if not ctx.profile.require_identity_verification:
            return IdentityStatus(verified=True)
        try:
            link = await self._actions.resolve_identity(_action_context(ctx), channel, external_user_id)
        except Exception as exc:
            log.error("identity lookup failed", err=exc, account_id=ctx.account_id)
            return IdentityStatus(verified=False)
        if link.status is IdentityLinkStatus.VERIFIED and link.patient_id is not None:
            return IdentityStatus(verified=True, patient_id=link.patient_id)
        return IdentityStatus(
            verified=False, needs_staff_confirmation=link.status is IdentityLinkStatus.PENDING
        )

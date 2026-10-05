"""Policy profiles and the hook points package P attaches to.

PLAN-AI01 section 5: clinic safety is a *policy profile* (``staff_assistant`` | ``patient_channel``)
bound to each account and agent, never a deletion of ported zalo-agent features. This module holds:

* ``PolicyProfile``: the data of the table in section 5 (``DEFAULT_PROFILES``);
* ``PolicyHooks``: the eight hook points the agent loop (D1), the scheduler (S), the channel
  pipeline (C1/C2), the tool registry (D4) and the memory tool (D2) call. They depend on this
  protocol only. Package P implements it in ``pema.policy`` (profiles, red flags, PII mask,
  identity verification);
* ``PermissivePolicyHooks``: the ``staff_assistant`` behaviour (everything passes). It is the
  default injected into every engine so D1, S, C1, C2 can be developed and tested before P lands.

Which profile applies: ``effective_profile_key(account, agent)``. The RESTRICTIVE one wins: if the
account or its agent is ``patient_channel`` the turn runs under ``patient_channel``. The default of
both is ``patient_channel`` (fail safe).

Hook call sites (normative, so P can attach without editing D1/S):

====================  =================================================  ==========================
hook                  called by                                          where
====================  =================================================  ==========================
``before_llm``        agent loop, once per turn before the first model   ``pema.agent.agent_loop``
                      call, and again for messages injected mid-turn
``after_llm``         agent loop, on the final text of a turn            ``pema.agent.agent_loop``
``filter_tool_keys``  tool registry, every turn                          ``pema.agent.tools``
``allow_memory_write`` ``save_memory`` tool                              ``pema.agent.tools``
``on_outbound``       channel reply delivery AND scheduler delivery      ``pema.channels`` and
                      (every text that would leave the system)           ``pema.scheduler``
``check_job``         scheduler ``create_job`` and ``run_scheduled_job``  ``pema.scheduler``
``proactive_cap``     proactive send guard                               ``pema.scheduler``
``verify_identity``   before the agent may name a patient, an            ``pema.agent`` /
                      appointment or a medicine                          ``pema.policy``
====================  =================================================  ==========================
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import ConfigDict, Field

from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.common import ApiModel
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind


class PolicyProfileKey(StrEnum):
    STAFF_ASSISTANT = "staff_assistant"
    """Same behaviour as the original zalo-agent."""
    PATIENT_CHANNEL = "patient_channel"
    """Text-only patient care: review before send, red flags to a doctor, PII masked."""


class OutboundMode(StrEnum):
    DIRECT = "direct"
    """Send straight to the patient/user."""
    REVIEW = "review"
    """Every outbound text becomes a ``review_item``; a human approves, then it is sent."""


class ScheduledJobPolicy(StrEnum):
    ANY = "any"
    """Both ``message`` and ``agent`` jobs run as in zalo-agent."""
    MESSAGE_FROM_TEMPLATE_ONLY = "message_from_template_only"
    """Only ``kind: message`` from an approved template; an ``agent`` job may only draft."""


class MemoryWritePolicy(StrEnum):
    ALLOW = "allow"
    STAFF_ONLY = "staff_only"
    """``save_memory`` is off for content that came from a patient; only doctor/CSKH write."""


class InboundMediaAction(StrEnum):
    PASS = "pass"  # noqa: S105 - an action name, not a password
    FLAG_AND_HAND_OFF = "flag_and_hand_off"
    """Patient sent an image/file: flag the Inbox, hand the conversation to a person."""


class PiiMaskMode(StrEnum):
    OFF = "off"
    OPTIONAL = "optional"
    REQUIRED = "required"


class ProactiveCapScope(StrEnum):
    ACCOUNT_THREAD = "account_thread"
    """zalo-agent behaviour: per (account, thread, day)."""
    PATIENT_ACCOUNT = "patient_account"
    """Per (patient, account, day), plus ``marketingOptOut`` and no automatic birthday message."""


MEDIA_AND_WEB_TOOL_KEYS: frozenset[str] = frozenset(
    {
        "send_file",
        "create_word_document",
        "create_excel_file",
        "create_image",
        "tai_video",
        "read_image",
        "web_search",
        "web_fetch",
    }
)
"""The image / video / document / web tools turned off by ``patient_channel`` (PLAN-AI01 section 5)."""


class PolicyProfile(ApiModel):
    """One column of the table in PLAN-AI01 section 5, as data."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: PolicyProfileKey
    outbound_mode: OutboundMode
    scheduled_jobs: ScheduledJobPolicy
    memory_write: MemoryWritePolicy
    disabled_tool_keys: frozenset[str] = Field(default_factory=frozenset[str])
    inbound_media: InboundMediaAction
    red_flag_check: bool = Field(
        description="Run the red-flag detector (bleeding, fever, pus, dyspnoea; with and without "
        "diacritics) before any LLM call and hand off to a doctor on a hit."
    )
    pii_mask: PiiMaskMode
    proactive_cap_scope: ProactiveCapScope
    marketing_opt_out_blocks_marketing: bool
    birthday_auto_send: bool = Field(description="False: a birthday is a staff task, never auto-sent.")
    require_identity_verification: bool = Field(
        description="zalo_uid must be linked to a verified patient record before the agent may name "
        "the patient, an appointment or a medicine."
    )


STAFF_ASSISTANT_PROFILE = PolicyProfile(
    key=PolicyProfileKey.STAFF_ASSISTANT,
    outbound_mode=OutboundMode.DIRECT,
    scheduled_jobs=ScheduledJobPolicy.ANY,
    memory_write=MemoryWritePolicy.ALLOW,
    disabled_tool_keys=frozenset(),
    inbound_media=InboundMediaAction.PASS,
    red_flag_check=False,
    pii_mask=PiiMaskMode.OPTIONAL,
    proactive_cap_scope=ProactiveCapScope.ACCOUNT_THREAD,
    marketing_opt_out_blocks_marketing=False,
    birthday_auto_send=True,
    require_identity_verification=False,
)

PATIENT_CHANNEL_PROFILE = PolicyProfile(
    key=PolicyProfileKey.PATIENT_CHANNEL,
    outbound_mode=OutboundMode.REVIEW,
    scheduled_jobs=ScheduledJobPolicy.MESSAGE_FROM_TEMPLATE_ONLY,
    memory_write=MemoryWritePolicy.STAFF_ONLY,
    disabled_tool_keys=MEDIA_AND_WEB_TOOL_KEYS,
    inbound_media=InboundMediaAction.FLAG_AND_HAND_OFF,
    red_flag_check=True,
    pii_mask=PiiMaskMode.REQUIRED,
    proactive_cap_scope=ProactiveCapScope.PATIENT_ACCOUNT,
    marketing_opt_out_blocks_marketing=True,
    birthday_auto_send=False,
    require_identity_verification=True,
)

DEFAULT_PROFILES: dict[PolicyProfileKey, PolicyProfile] = {
    PolicyProfileKey.STAFF_ASSISTANT: STAFF_ASSISTANT_PROFILE,
    PolicyProfileKey.PATIENT_CHANNEL: PATIENT_CHANNEL_PROFILE,
}


def effective_profile_key(
    account_profile: PolicyProfileKey, agent_profile: PolicyProfileKey
) -> PolicyProfileKey:
    """The restrictive profile wins. Used wherever an account and its agent are combined."""
    if PolicyProfileKey.PATIENT_CHANNEL in (account_profile, agent_profile):
        return PolicyProfileKey.PATIENT_CHANNEL
    return PolicyProfileKey.STAFF_ASSISTANT


@dataclass(frozen=True)
class PolicyContext:
    """Everything a hook may need. Built once per turn / job by the caller."""

    clinic_id: UUID
    account_id: str
    agent_id: str
    channel: ChannelKind
    thread_id: str
    profile: PolicyProfile
    isolated: bool = False
    """True for scheduler-run turns (no history, no memory, no user present)."""
    patient_id: UUID | None = None
    identity_verified: bool = False
    request_id: str | None = None


class MemorySource(StrEnum):
    PATIENT_MESSAGE = "patient_message"
    STAFF = "staff"
    WEB_CONTENT = "web_content"


class BeforeLlmAction(StrEnum):
    CONTINUE = "continue"
    HAND_OFF = "hand_off"
    """Stop: do not call the model. The caller opens a triage ``review_item`` for a doctor."""


class BeforeLlmDecision(ApiModel):
    action: BeforeLlmAction = BeforeLlmAction.CONTINUE
    masked_text_by_msg_id: dict[str, str] = Field(
        default_factory=dict,
        description="msg_id -> text to show the model instead of the original (PII masked). "
        "Missing id = unchanged.",
    )
    mask_token: str | None = Field(
        default=None, description="Opaque handle ``after_llm`` uses to restore names in the reply."
    )
    red_flags: list[str] = Field(default_factory=list[str])
    reason: str | None = Field(default=None, description="Short code, no message text, no PII.")


class OutboundAction(StrEnum):
    SEND = "send"
    HOLD_FOR_REVIEW = "hold_for_review"
    DROP = "drop"


class OutboundOrigin(StrEnum):
    TURN_REPLY = "turn_reply"
    SCHEDULED_MESSAGE = "scheduled_message"
    SCHEDULED_AGENT = "scheduled_agent"
    TOOL_SEND = "tool_send"


class OutboundDecision(ApiModel):
    action: OutboundAction = OutboundAction.SEND
    reason: str | None = None


class JobAction(StrEnum):
    ALLOW = "allow"
    DOWNGRADE_TO_DRAFT = "downgrade_to_draft"
    """An ``agent`` job runs but only drafts: its output becomes a review item."""
    DENY = "deny"


class JobDecision(ApiModel):
    action: JobAction = JobAction.ALLOW
    reason: str | None = None


class ProactiveCap(ApiModel):
    scope_key: str = Field(description="Key of ``agent.proactive_send_counters``.")
    max_per_day: int | None = Field(default=None, ge=0, description="None = no cap beyond the channel's.")


class IdentityStatus(ApiModel):
    verified: bool
    patient_id: UUID | None = None
    needs_staff_confirmation: bool = False
    """A candidate link exists but no staff member confirmed it yet (admin.policy permission)."""


class PolicyHooks(Protocol):
    """The eight hook points. All async so P can read the DB; implementations must be fast."""

    async def before_llm(self, ctx: PolicyContext, batch: Sequence[InboundMessage]) -> BeforeLlmDecision: ...

    async def after_llm(self, ctx: PolicyContext, text: str, mask_token: str | None) -> str: ...

    async def filter_tool_keys(self, ctx: PolicyContext, keys: frozenset[str]) -> frozenset[str]: ...

    async def allow_memory_write(self, ctx: PolicyContext, source: MemorySource) -> bool: ...

    async def on_outbound(
        self, ctx: PolicyContext, text: str, *, proactive: bool, origin: OutboundOrigin
    ) -> OutboundDecision: ...

    async def check_job(self, ctx: PolicyContext, job: CreateScheduledJobInput) -> JobDecision: ...

    async def proactive_cap(self, ctx: PolicyContext, default_max_per_day: int | None) -> ProactiveCap: ...

    async def verify_identity(
        self, ctx: PolicyContext, channel: ChannelKind, external_user_id: str
    ) -> IdentityStatus: ...


class PermissivePolicyHooks:
    """``staff_assistant`` behaviour: nothing is blocked, held, masked or rewritten.

    Default injected into every engine. It is also the correct implementation for a profile whose
    ``PolicyProfile`` flags are all off, so engines MUST still consult ``ctx.profile`` and only call
    P's real hooks when the profile asks for it; the permissive hooks never have to.
    """

    async def before_llm(self, ctx: PolicyContext, batch: Sequence[InboundMessage]) -> BeforeLlmDecision:
        return BeforeLlmDecision()

    async def after_llm(self, ctx: PolicyContext, text: str, mask_token: str | None) -> str:
        return text

    async def filter_tool_keys(self, ctx: PolicyContext, keys: frozenset[str]) -> frozenset[str]:
        return keys

    async def allow_memory_write(self, ctx: PolicyContext, source: MemorySource) -> bool:
        return True

    async def on_outbound(
        self, ctx: PolicyContext, text: str, *, proactive: bool, origin: OutboundOrigin
    ) -> OutboundDecision:
        return OutboundDecision()

    async def check_job(self, ctx: PolicyContext, job: CreateScheduledJobInput) -> JobDecision:
        return JobDecision()

    async def proactive_cap(self, ctx: PolicyContext, default_max_per_day: int | None) -> ProactiveCap:
        return ProactiveCap(scope_key=f"{ctx.account_id}:{ctx.thread_id}", max_per_day=default_max_per_day)

    async def verify_identity(
        self, ctx: PolicyContext, channel: ChannelKind, external_user_id: str
    ) -> IdentityStatus:
        return IdentityStatus(verified=True)


def job_kind_allowed(profile: PolicyProfile, kind: JobKind) -> bool:
    """Pure helper both S and P use: may this profile run a job of ``kind`` unmodified?"""
    if profile.scheduled_jobs is ScheduledJobPolicy.ANY:
        return True
    return kind is JobKind.MESSAGE

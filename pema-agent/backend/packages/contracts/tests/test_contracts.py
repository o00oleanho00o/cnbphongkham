from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import BaseModel, ValidationError

from pema_contracts.agent_turn import AgentTurnRequest, TurnQueue
from pema_contracts.agents import AccountConfig, AgentProfile, LlmProviderKind
from pema_contracts.channel import (
    ZALO_PERSONAL_DEFAULT_DAILY_CAP,
    ChannelCapabilities,
    ChannelKind,
    ChannelPort,
    InboundKind,
    InboundMessage,
    MediaChannel,
    ReactionChannel,
    SendStatus,
    ThreadKind,
    TypingChannel,
)
from pema_contracts.common import VN_TZ, ApiModel, VnDatetime, now_vn
from pema_contracts.errors import ERROR_HTTP_STATUS, DomainError, ErrorCode
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    MEDIA_AND_WEB_TOOL_KEYS,
    PATIENT_CHANNEL_PROFILE,
    STAFF_ASSISTANT_PROFILE,
    BeforeLlmAction,
    JobAction,
    OutboundAction,
    OutboundMode,
    OutboundOrigin,
    PermissivePolicyHooks,
    PolicyContext,
    PolicyHooks,
    PolicyProfileKey,
    ProactiveCapScope,
    effective_profile_key,
    job_kind_allowed,
)
from pema_contracts.roles import STAFF_ROLES, Role
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    EverySchedule,
    JobKind,
    OnceSchedule,
    ScheduledJob,
    ScheduleKind,
    thread_kind_of,
)
from pema_contracts.testing import (
    FakeChannel,
    FakeTextGenerator,
    InMemoryAccountStore,
    InMemoryAgentStore,
    InMemoryThreadLock,
    InMemoryTurnQueue,
    fake_account_config,
    fake_agent_profile,
    make_inbound,
    new_turn_job,
)
from pema_contracts.tools import BUILTIN_TOOL_KEYS, CLINIC_TOOL_KEYS
from pema_contracts.turn_errors import (
    AgentTurnError,
    GuardBlockReason,
    PromptLeakReason,
    ProviderErrorKind,
    ProviderErrorReason,
    failed_turn_step,
)


class _Stamp(BaseModel):
    at: VnDatetime


def test_roles_are_the_six_fixed_ones() -> None:
    assert {r.value for r in Role} == {"owner", "manager", "doctor", "cs_staff", "reception", "patient"}
    assert Role.PATIENT not in STAFF_ROLES


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValidationError):
        _Stamp(at=datetime(2026, 9, 20, 9, 0, 0))


def test_datetime_is_normalised_to_plus_seven_and_serialised_with_offset() -> None:
    stamp = _Stamp(at=datetime(2026, 9, 20, 2, 0, 0, tzinfo=UTC))
    assert stamp.at.utcoffset() == timedelta(hours=7)
    assert json.loads(stamp.model_dump_json())["at"] == "2026-09-20T09:00:00+07:00"
    other_zone = _Stamp(at=datetime(2026, 9, 20, 9, 0, 0, tzinfo=timezone(timedelta(hours=9))))
    assert other_zone.model_dump(mode="json")["at"] == "2026-09-20T07:00:00+07:00"


def test_every_error_code_has_an_http_status() -> None:
    assert set(ERROR_HTTP_STATUS) == set(ErrorCode)
    assert ERROR_HTTP_STATUS[ErrorCode.NOT_IMPLEMENTED] == 501
    assert ERROR_HTTP_STATUS[ErrorCode.POLICY_DENIED] == 403


def test_domain_error_maps_to_envelope() -> None:
    err = DomainError(ErrorCode.CHANNEL_DAILY_CAP_REACHED, "Đã hết hạn mức tin chủ động hôm nay.")
    body = err.to_response("req-1")
    assert err.http_status == 429
    assert body.error.code is ErrorCode.CHANNEL_DAILY_CAP_REACHED
    assert body.error.request_id == "req-1"


def test_dtos_reject_unknown_fields() -> None:
    class Probe(ApiModel):
        name: str

    with pytest.raises(ValidationError):
        Probe.model_validate({"name": "x", "surprise": 1})


# ------------------------------------------------------------------ ChannelPort


def test_personal_zalo_capabilities_describe_proactive_limits() -> None:
    caps = ChannelCapabilities(
        channel=ChannelKind.ZALO_PERSONAL,
        can_send_proactive=True,
        daily_cap=ZALO_PERSONAL_DEFAULT_DAILY_CAP,
        requires_friend=True,
        min_gap_seconds=20,
        max_gap_seconds=90,
        send_window_start="08:00",
        send_window_end="18:00",
        supports_send_image=True,
        supports_send_file=True,
    )
    assert ZALO_PERSONAL_DEFAULT_DAILY_CAP == 10
    assert caps.can_send_proactive
    assert caps.requires_friend
    assert caps.daily_cap == 10


def test_bot_capabilities_carry_blocked_tools_and_no_formatting() -> None:
    caps = ChannelCapabilities(
        channel=ChannelKind.ZALO_BOT,
        can_send_proactive=True,
        supports_formatting=False,
        blocked_tools={"send_file": "Bot API has no file method"},
    )
    assert caps.daily_cap is None
    assert not caps.supports_formatting
    assert "send_file" in caps.blocked_tools


async def test_fake_channel_satisfies_the_port_and_records_parts() -> None:
    channel = FakeChannel(caps=ChannelCapabilities(channel=ChannelKind.ZALO_BOT, can_send_proactive=False))
    assert isinstance(channel, ChannelPort)
    assert not isinstance(channel, TypingChannel | MediaChannel | ReactionChannel)
    parsed = channel.parse_inbound({"text": "xin chào"})
    assert parsed is not None
    assert parsed.text == "xin chào"
    assert channel.parse_inbound({"event": "follow"}) is None
    assert channel.verify_webhook({"x-secret": "ok"}, b"{}")
    assert not channel.verify_webhook({"x-secret": "wrong"}, b"{}")
    result = await channel.send_text("t1", "chào bạn", proactive=True)
    assert result.status is SendStatus.SENT
    assert [(p.thread_id, p.text, p.proactive) for p in channel.sent] == [("t1", "chào bạn", True)]


def test_inbound_message_defaults_and_serialisation() -> None:
    msg = make_inbound("hi", kind=InboundKind.TEXT, thread_kind=ThreadKind.GROUP, is_group=True)
    data = json.loads(msg.model_dump_json())
    assert data["sent_at"].endswith("+07:00")
    assert InboundMessage.model_validate(data) == msg


def test_thread_kind_follows_zca_thread_type() -> None:
    assert thread_kind_of(0) is ThreadKind.USER
    assert thread_kind_of(1) is ThreadKind.GROUP
    assert thread_kind_of(-1) is ThreadKind.USER


# ------------------------------------------------------------------ scheduler


def test_scheduler_models_round_trip() -> None:
    spec = CreateScheduledJobInput(
        clinic_id=uuid4(),
        account_id="acc-1",
        thread_id="t1",
        thread_type=0,
        name="Nhac lich D+1",
        kind=JobKind.MESSAGE,
        payload="template:d1",
        schedule=OnceSchedule(run_at_utc="2026-09-21T01:00:00.000Z"),
        created_by="crm_rule",
        dedupe_key="d1:P025:evt-7",
    )
    again = CreateScheduledJobInput.model_validate(json.loads(spec.model_dump_json()))
    assert again.schedule.kind is ScheduleKind.ONCE
    every = CreateScheduledJobInput.model_validate(
        {**json.loads(spec.model_dump_json()), "schedule": {"kind": "every", "minutes": 60}}
    )
    assert isinstance(every.schedule, EverySchedule)
    job = ScheduledJob(
        id="a1b2c3",
        clinic_id=spec.clinic_id,
        account_id="acc-1",
        thread_id="t1",
        thread_type=0,
        name="x",
        kind=JobKind.AGENT,
        payload="p",
        schedule_kind=ScheduleKind.CRON,
        cron_expr="0 8 * * *",
    )
    assert job.delivery_attempts == 0
    assert job.max_runs is None


# ------------------------------------------------------------------ policy


def test_default_profiles_match_the_table_of_plan_section_5() -> None:
    assert set(DEFAULT_PROFILES) == set(PolicyProfileKey)
    staff, patient = STAFF_ASSISTANT_PROFILE, PATIENT_CHANNEL_PROFILE
    assert staff.outbound_mode is OutboundMode.DIRECT
    assert patient.outbound_mode is OutboundMode.REVIEW
    assert patient.red_flag_check
    assert not staff.red_flag_check
    assert patient.require_identity_verification
    assert not staff.require_identity_verification
    assert patient.proactive_cap_scope is ProactiveCapScope.PATIENT_ACCOUNT
    assert not patient.birthday_auto_send
    assert patient.marketing_opt_out_blocks_marketing
    assert patient.disabled_tool_keys == MEDIA_AND_WEB_TOOL_KEYS
    assert staff.disabled_tool_keys == frozenset()
    assert set(BUILTIN_TOOL_KEYS) >= MEDIA_AND_WEB_TOOL_KEYS


def test_restrictive_profile_wins() -> None:
    s, p = PolicyProfileKey.STAFF_ASSISTANT, PolicyProfileKey.PATIENT_CHANNEL
    assert effective_profile_key(s, s) is s
    assert effective_profile_key(s, p) is p
    assert effective_profile_key(p, s) is p


def test_patient_channel_only_runs_template_messages_unmodified() -> None:
    assert job_kind_allowed(PATIENT_CHANNEL_PROFILE, JobKind.MESSAGE)
    assert not job_kind_allowed(PATIENT_CHANNEL_PROFILE, JobKind.AGENT)
    assert job_kind_allowed(STAFF_ASSISTANT_PROFILE, JobKind.AGENT)


def test_profiles_and_accounts_default_to_the_safe_profile() -> None:
    account = AccountConfig(
        id="bot-1", clinic_id=uuid4(), label="Bot", channel=ChannelKind.ZALO_BOT, agent_id="default"
    )
    agent = AgentProfile(
        id="default", clinic_id=uuid4(), name="Default", model_provider=LlmProviderKind.GOOGLE
    )
    assert account.policy_profile is PolicyProfileKey.PATIENT_CHANNEL
    assert agent.policy_profile is PolicyProfileKey.PATIENT_CHANNEL
    assert not account.has_bot_token


async def test_permissive_hooks_pass_everything_and_satisfy_the_protocol() -> None:
    hooks: PolicyHooks = PermissivePolicyHooks()
    ctx = PolicyContext(
        clinic_id=uuid4(),
        account_id="acc-1",
        agent_id="default",
        channel=ChannelKind.ZALO_BOT,
        thread_id="t1",
        profile=STAFF_ASSISTANT_PROFILE,
    )
    batch = [make_inbound("chảy máu nhiều")]
    assert (await hooks.before_llm(ctx, batch)).action is BeforeLlmAction.CONTINUE
    assert await hooks.after_llm(ctx, "ok", None) == "ok"
    assert await hooks.filter_tool_keys(ctx, frozenset({"send_file"})) == frozenset({"send_file"})
    decision = await hooks.on_outbound(ctx, "hello", proactive=False, origin=OutboundOrigin.TURN_REPLY)
    assert decision.action is OutboundAction.SEND
    job = CreateScheduledJobInput(
        clinic_id=ctx.clinic_id,
        account_id="acc-1",
        thread_id="t1",
        thread_type=0,
        name="n",
        kind=JobKind.AGENT,
        payload="p",
        schedule=EverySchedule(minutes=60),
        created_by="t",
    )
    assert (await hooks.check_job(ctx, job)).action is JobAction.ALLOW
    cap = await hooks.proactive_cap(ctx, 60)
    assert (cap.scope_key, cap.max_per_day) == ("acc-1:t1", 60)
    assert (await hooks.verify_identity(ctx, ChannelKind.ZALO_BOT, "uid")).verified


# ------------------------------------------------------------------ agent turn, queue, lock, fakes


def test_agent_turn_request_needs_at_least_one_message() -> None:
    with pytest.raises(ValidationError):
        AgentTurnRequest(clinic_id=uuid4(), account_id="a", batch=[])
    request = AgentTurnRequest(clinic_id=uuid4(), account_id="a", batch=[make_inbound()])
    assert not request.isolated


async def test_in_memory_queue_retries_with_incremented_attempt() -> None:
    queue: TurnQueue = InMemoryTurnQueue()
    job = new_turn_job()
    await queue.enqueue(job)
    claimed = await queue.claim(0)
    assert claimed is not None
    await queue.nack(claimed.job_id, retry=True)
    retried = await queue.claim(0)
    assert retried is not None
    assert retried.attempt == 2
    await queue.ack(retried.job_id)
    assert await queue.claim(0) is None


async def test_in_memory_thread_lock_rejects_overlapping_turns() -> None:
    lock = InMemoryThreadLock()
    async with lock.hold("acc", "t1"):
        with pytest.raises(RuntimeError):
            async with lock.hold("acc", "t1"):
                pass
        async with lock.hold("acc", "t2"):
            pass
    async with lock.hold("acc", "t1"):
        pass


async def test_fake_text_generator_records_prompts() -> None:
    generator = FakeTextGenerator(reply=lambda p: p.upper())
    out = await generator.generate_text("tom tat")
    assert out.text == "TOM TAT"
    assert generator.prompts == ["tom tat"]


def test_tool_key_vocabulary() -> None:
    assert len(BUILTIN_TOOL_KEYS) == 15
    assert len(set(BUILTIN_TOOL_KEYS)) == 15
    assert not set(BUILTIN_TOOL_KEYS) & set(CLINIC_TOOL_KEYS)


def test_now_vn_is_plus_seven() -> None:
    assert now_vn().utcoffset() == VN_TZ.utcoffset(None)


def test_fake_profiles_default_to_staff_assistant_and_disable_nothing() -> None:
    agent = fake_agent_profile()
    account = fake_account_config(disabled_tools=["send_file"])
    assert agent.policy_profile is PolicyProfileKey.STAFF_ASSISTANT
    assert agent.disabled_tools == []
    assert account.disabled_tools == ["send_file"]
    assert (
        effective_profile_key(account.policy_profile, agent.policy_profile)
        is PolicyProfileKey.STAFF_ASSISTANT
    )


def test_failed_turn_step_has_a_machine_readable_finish_reason() -> None:
    provider = failed_turn_step(ProviderErrorReason(error_kind="auth", message="401 from router"))
    assert provider.step_number == 0
    assert provider.finish_reason == "error:auth"
    assert "401 from router" in provider.text
    guard = failed_turn_step(GuardBlockReason(code="same_tool", message="5 identical calls"), attempt=2)
    assert guard.finish_reason == "blocked:same_tool"
    assert guard.attempt == 2
    leak = failed_turn_step(PromptLeakReason())
    assert leak.finish_reason == "blocked:prompt-leak"
    assert "KHÔNG gửi cho người dùng" in leak.text


def test_agent_turn_error_carries_the_classified_kind() -> None:
    err = AgentTurnError(ProviderErrorKind.CONFIG, "no API key", turn_id=7)
    assert err.kind is ProviderErrorKind.CONFIG
    assert err.kind.value == "cau_hinh"
    assert err.turn_id == 7
    assert "no API key" in str(err)
    assert {k.value for k in ProviderErrorKind} == {
        "cau_hinh", "rate_limit", "context_overflow", "auth", "transient", "unknown"
    }  # fmt: skip


async def test_in_memory_account_and_agent_stores_behave_like_the_ports() -> None:
    accounts = InMemoryAccountStore(fake_account_config(id="bot-1"))
    agents = InMemoryAgentStore()
    clinic = fake_account_config().clinic_id
    account = await accounts.get_account(clinic, "bot-1")
    assert account is not None
    assert (await agents.get_agent_for_account(clinic, account)).is_default
    await accounts.set_bot_token(clinic, "bot-1", "123456:synthetic")
    assert await accounts.get_bot_token(clinic, "bot-1") == "123456:synthetic"
    updated = await accounts.update_account(clinic, "bot-1", {"enabled": False})
    assert updated is not None
    assert not updated.enabled
    assert await accounts.list_all_enabled_accounts() == []
    assert await accounts.delete_account(clinic, "bot-1")
    assert await accounts.get_account(clinic, "bot-1") is None

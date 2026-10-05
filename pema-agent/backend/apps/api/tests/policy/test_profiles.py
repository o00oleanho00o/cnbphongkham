"""Profiles as data and the PolicyContext builder (new module)."""

from __future__ import annotations

from pema.policy.profiles import build_policy_context, get_profile, profiles_out, resolve_profile
from pema_contracts.channel import ChannelKind
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    MEDIA_AND_WEB_TOOL_KEYS,
    InboundMediaAction,
    MemoryWritePolicy,
    OutboundMode,
    PiiMaskMode,
    PolicyProfileKey,
    ProactiveCapScope,
    ScheduledJobPolicy,
)
from pema_contracts.testing import FAKE_CLINIC_ID, fake_account_config, fake_agent_profile

S = PolicyProfileKey.STAFF_ASSISTANT
P = PolicyProfileKey.PATIENT_CHANNEL


def test_patient_channel_matches_the_table_of_plan_section_5() -> None:
    """hồ sơ patient_channel khớp bảng mục 5 của PLAN-AI01"""
    p = get_profile(P)
    assert p.outbound_mode is OutboundMode.REVIEW
    assert p.scheduled_jobs is ScheduledJobPolicy.MESSAGE_FROM_TEMPLATE_ONLY
    assert p.memory_write is MemoryWritePolicy.STAFF_ONLY
    assert p.disabled_tool_keys == MEDIA_AND_WEB_TOOL_KEYS
    assert p.inbound_media is InboundMediaAction.FLAG_AND_HAND_OFF
    assert p.red_flag_check is True
    assert p.pii_mask is PiiMaskMode.REQUIRED
    assert p.proactive_cap_scope is ProactiveCapScope.PATIENT_ACCOUNT
    assert p.marketing_opt_out_blocks_marketing is True
    assert p.birthday_auto_send is False
    assert p.require_identity_verification is True


def test_staff_assistant_keeps_the_original_behaviour() -> None:
    """hồ sơ staff_assistant giữ hành vi gốc của zalo-agent"""
    s = get_profile(S)
    assert s.outbound_mode is OutboundMode.DIRECT
    assert s.scheduled_jobs is ScheduledJobPolicy.ANY
    assert s.memory_write is MemoryWritePolicy.ALLOW
    assert not s.disabled_tool_keys
    assert s.red_flag_check is False
    assert s.require_identity_verification is False
    assert s.birthday_auto_send is True


def test_the_restrictive_profile_wins() -> None:
    """tài khoản hoặc agent là patient_channel thì lượt chạy theo patient_channel"""
    assert resolve_profile(S, S).key is S
    assert resolve_profile(P, S).key is P
    assert resolve_profile(S, P).key is P
    assert resolve_profile(P, P).key is P


def test_build_policy_context_takes_the_profile_from_account_and_agent() -> None:
    """PolicyContext lấy hồ sơ từ tài khoản + agent, kênh từ tài khoản"""
    account = fake_account_config(policy_profile=S, channel=ChannelKind.ZALO_PERSONAL)
    agent = fake_agent_profile(policy_profile=P)
    ctx = build_policy_context(clinic_id=FAKE_CLINIC_ID, account=account, agent=agent, thread_id="t-9")
    assert ctx.profile.key is P
    assert ctx.channel is ChannelKind.ZALO_PERSONAL
    assert (ctx.account_id, ctx.agent_id, ctx.thread_id) == (account.id, agent.id, "t-9")
    assert ctx.identity_verified is False
    assert ctx.patient_id is None


def test_profiles_out_lists_both_profiles_staff_first() -> None:
    """danh sách hồ sơ cho màn quản trị: staff_assistant trước"""
    out = profiles_out()
    assert [p.key for p in out.profiles] == [S, P]
    assert out.profiles[1] == DEFAULT_PROFILES[P]

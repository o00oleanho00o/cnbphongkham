"""``ClinicPolicyHooks`` under ``staff_assistant``: the zalo-agent behaviour, untouched (new module).

For every hook the real implementation must answer exactly what ``PermissivePolicyHooks`` answers, even for
input that would trigger every rule of ``patient_channel`` (a red-flag text, an image, a birthday job).
Fictional data only.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from pema.policy.testing import FakePolicyGateway, make_hooks, make_policy_context
from pema.policy.turn_guard import run_guarded_turn
from pema_contracts.channel import ChannelKind, InboundKind
from pema_contracts.policy import (
    BeforeLlmAction,
    JobAction,
    MemorySource,
    OutboundAction,
    OutboundOrigin,
    PermissivePolicyHooks,
    PolicyHooks,
    PolicyProfileKey,
)
from pema_contracts.scheduler import CreateScheduledJobInput, JobKind, OnceSchedule
from pema_contracts.testing import FAKE_CLINIC_ID, FakeTextGenerator, make_inbound

S = PolicyProfileKey.STAFF_ASSISTANT
CTX = make_policy_context(S)
REFERENCE: PolicyHooks = PermissivePolicyHooks()


def _job(**patch: object) -> CreateScheduledJobInput:
    data: dict[str, object] = {
        "clinic_id": FAKE_CLINIC_ID,
        "account_id": "acc-1",
        "thread_id": "thread-1",
        "thread_type": 0,
        "name": "Chúc mừng sinh nhật",
        "kind": JobKind.AGENT,
        "payload": "Chúc mừng sinh nhật khách",
        "schedule": OnceSchedule(run_at_utc="2026-09-21T02:00:00Z"),
        "created_by": "staff",
        "dedupe_key": "birthday:P1",
        **patch,
    }
    return CreateScheduledJobInput.model_validate(data)


async def test_before_llm_ignores_red_flags_and_media_and_masks_nothing() -> None:
    """staff_assistant: không cờ đỏ, không chuyển người vì ảnh, không che PII"""
    hooks, actions, _ = make_hooks()
    batch = [
        make_inbound("em khó thở, sdt 0901234567", msg_id="a"),
        make_inbound("", kind=InboundKind.IMAGE, msg_id="b"),
    ]
    decision = await hooks.before_llm(CTX, batch)
    assert decision == await REFERENCE.before_llm(CTX, batch)
    assert decision.action is BeforeLlmAction.CONTINUE
    assert not actions.review_items


async def test_the_model_is_called_with_the_original_text() -> None:
    """staff_assistant: mô hình nhận nguyên văn tin nhắn"""
    hooks, _, _ = make_hooks()
    generator = FakeTextGenerator(reply=lambda _p: "ok")

    async def generate(prompt: str) -> str:
        return (await generator.generate_text(prompt)).text

    turn = await run_guarded_turn(hooks, CTX, [make_inbound("em chảy máu, sdt 0901234567")], generate)
    assert generator.prompts == ["em chảy máu, sdt 0901234567"]
    assert turn.handed_off is False
    assert turn.outbound is not None
    assert turn.outbound.action is OutboundAction.SEND


async def test_after_llm_returns_the_text_unchanged() -> None:
    """staff_assistant: after_llm không đổi chữ nào, kể cả mã giữ chỗ"""
    hooks, _, _ = make_hooks()
    text = "gọi [SDT_1] cho [KH_P025]"
    assert await hooks.after_llm(CTX, text, None) == text == await REFERENCE.after_llm(CTX, text, None)


async def test_all_tools_stay_available() -> None:
    """staff_assistant giữ nguyên mọi tool, kể cả save_memory, web và MCP"""
    hooks, _, _ = make_hooks()
    keys = frozenset({"save_memory", "web_fetch", "send_file", "create_image", "mcp__x__y", "kb_search"})
    assert await hooks.filter_tool_keys(CTX, keys) == keys == await REFERENCE.filter_tool_keys(CTX, keys)


@pytest.mark.parametrize("source", list(MemorySource))
async def test_memory_writes_are_allowed(source: MemorySource) -> None:
    """staff_assistant cho save_memory với mọi nguồn"""
    hooks, _, _ = make_hooks()
    assert await hooks.allow_memory_write(CTX, source) is True


@pytest.mark.parametrize("origin", list(OutboundOrigin))
async def test_outbound_is_sent_directly(origin: OutboundOrigin) -> None:
    """staff_assistant gửi thẳng, kể cả tin theo lịch"""
    hooks, _, _ = make_hooks()
    decision = await hooks.on_outbound(CTX, "Chào chị", proactive=True, origin=origin)
    assert decision == await REFERENCE.on_outbound(CTX, "Chào chị", proactive=True, origin=origin)
    assert decision.action is OutboundAction.SEND


async def test_every_job_is_allowed_even_a_birthday_agent_job() -> None:
    """staff_assistant cho mọi job, kể cả job agent sinh nhật (hành vi gốc)"""
    hooks, _, _ = make_hooks(gateway=FakePolicyGateway())
    job = _job()
    decision = await hooks.check_job(CTX, job)
    assert decision == await REFERENCE.check_job(CTX, job)
    assert decision.action is JobAction.ALLOW


async def test_proactive_cap_is_per_account_and_thread_as_in_zalo_agent() -> None:
    """staff_assistant: trần theo (account, thread) như zalo-agent"""
    hooks, _, _ = make_hooks()
    ctx = make_policy_context(S, patient_id=uuid4())
    cap = await hooks.proactive_cap(ctx, 10)
    assert cap == await REFERENCE.proactive_cap(ctx, 10)
    assert cap.scope_key == "acc-1:thread-1"


async def test_identity_needs_no_verification() -> None:
    """staff_assistant: không cần xác minh danh tính"""
    hooks, actions, _ = make_hooks()
    status = await hooks.verify_identity(CTX, ChannelKind.ZALO_BOT, "anyone")
    assert status.verified is True
    assert not actions.review_items


async def test_optional_masking_is_off_unless_enabled() -> None:
    """che PII ở staff_assistant là tùy chọn: mặc định tắt, bật bằng cờ"""
    off, _, _ = make_hooks()
    on, _, _ = make_hooks(mask_when_optional=True)
    message = make_inbound("sdt 0901234567", msg_id="m1")
    assert (await off.before_llm(CTX, [message])).masked_text_by_msg_id == {}
    masked = await on.before_llm(CTX, [message])
    assert masked.masked_text_by_msg_id == {"m1": "sdt [SDT_1]"}
    assert masked.action is BeforeLlmAction.CONTINUE

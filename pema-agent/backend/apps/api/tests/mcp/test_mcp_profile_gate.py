"""New in Pema (no original): the policy-profile gate of the MCP tools. ``patient_channel`` is OFF by default,
``staff_assistant`` keeps the behaviour of zalo-agent, and package P can narrow or widen it with one constant."""

from __future__ import annotations

from pema.mcp.mcp_profile_gate import (
    MCP_ALLOWED_PROFILES,
    MCP_TOOL_KEY_PREFIX,
    filter_mcp_tool_keys,
    is_mcp_tool_key,
    mcp_allowed_for_profile,
)
from pema.mcp.mcp_tool_definition import mcp_tool_name
from pema_contracts.policy import PolicyProfileKey

KEYS = frozenset({"save_memory", "kb_search", "mcp__notion__tra_cuu", "mcp__x__y"})


def test_mcp_profile_gate_patient_channel_is_off_by_default_and_staff_assistant_is_on() -> None:
    """mặc định patient_channel TẮT MCP, staff_assistant giữ như bản gốc"""
    assert mcp_allowed_for_profile(PolicyProfileKey.STAFF_ASSISTANT) is True
    assert mcp_allowed_for_profile(PolicyProfileKey.PATIENT_CHANNEL) is False
    assert {PolicyProfileKey.STAFF_ASSISTANT} == MCP_ALLOWED_PROFILES


def test_mcp_profile_gate_filter_drops_every_mcp_key_for_patient_channel_and_nothing_else() -> None:
    """lọc khóa tool: patient_channel mất mọi khóa mcp__ và chỉ chúng"""
    assert filter_mcp_tool_keys(PolicyProfileKey.PATIENT_CHANNEL, KEYS) == {"save_memory", "kb_search"}
    assert filter_mcp_tool_keys(PolicyProfileKey.STAFF_ASSISTANT, KEYS) == KEYS


def test_mcp_profile_gate_the_allowed_set_can_be_widened_or_narrowed_by_the_caller() -> None:
    """P có thể siết hoặc nới bằng tham số"""
    both = {PolicyProfileKey.STAFF_ASSISTANT, PolicyProfileKey.PATIENT_CHANNEL}
    assert mcp_allowed_for_profile(PolicyProfileKey.PATIENT_CHANNEL, both) is True
    assert mcp_allowed_for_profile(PolicyProfileKey.STAFF_ASSISTANT, set()) is False
    assert filter_mcp_tool_keys(PolicyProfileKey.STAFF_ASSISTANT, KEYS, set()) == {"save_memory", "kb_search"}


def test_mcp_profile_gate_every_generated_tool_key_is_recognised_as_an_mcp_key() -> None:
    """mọi khóa do mcp_tool_name sinh ra đều nhận ra được bằng tiền tố (kể cả khi bị băm)"""
    for server, tool in (("Notion", "tra_cuu"), ("Tra cứu", "tool_a"), ("", "x" * 100), ("a b", "tra cứu")):
        key = mcp_tool_name(server, tool, "srv-id")
        assert key.startswith(MCP_TOOL_KEY_PREFIX)
        assert is_mcp_tool_key(key)
    assert not is_mcp_tool_key("kb_search")

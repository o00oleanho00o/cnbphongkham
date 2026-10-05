# ported from: src/mcp/mcp-agent-binding.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Every test runs on the in-memory store AND on Postgres (fixture ``bundle``). The Postgres schema has real foreign
keys, so the servers and agents a test binds are created first (the original bound ids that did not exist).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.policy import PolicyProfileKey

if TYPE_CHECKING:
    from tests.mcp.conftest import StoreBundle


async def _servers(bundle: StoreBundle, *names: str) -> list[str]:
    return [
        (await bundle.servers.create_server(bundle.clinic_id, name=n, url="https://x/mcp")).id for n in names
    ]


async def test_mcp_agent_binding_an_unbound_agent_gets_nothing_default_deny(bundle: StoreBundle) -> None:
    """agent chưa gán -> RỖNG (default-deny)"""
    await bundle.add_agent("ag1")
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "ag1") == []
    policy = await bundle.bindings.policy_for_agent(bundle.clinic_id, "ag1")
    assert policy.bound_server_ids == []
    assert policy.default_deny is True


async def test_mcp_agent_binding_default_deny_holds_even_when_servers_exist(bundle: StoreBundle) -> None:
    """default-deny giữ kể cả khi CÓ server tồn tại"""
    s1, _s2 = await _servers(bundle, "a", "b")
    await bundle.add_agent("agent-khac")
    await bundle.add_agent("agent-chua-gan")
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "agent-khac", [s1])
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "agent-chua-gan") == []
    assert (await bundle.bindings.policy_for_agent(bundle.clinic_id, "agent-chua-gan")).bound_server_ids == []


async def test_mcp_agent_binding_set_servers_for_agent_replaces_not_accumulates(bundle: StoreBundle) -> None:
    """datServerChoAgent THAY THẾ, không cộng dồn"""
    s1, s2, s3 = await _servers(bundle, "a", "b", "c")
    await bundle.add_agent("ag1")
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", [s1, s2])
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", [s3])
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "ag1") == [s3]


async def test_mcp_agent_binding_clear_for_agent_wipes_one_agent(bundle: StoreBundle) -> None:
    """xoaGanServerCuaAgent dọn sạch một agent"""
    (s1,) = await _servers(bundle, "a")
    await bundle.add_agent("ag1")
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", [s1])
    await bundle.bindings.clear_for_agent(bundle.clinic_id, "ag1")
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "ag1") == []


# ------------------------------------------- additions of the Python port (not in the original test file)


async def test_mcp_agent_binding_patient_channel_agent_has_an_empty_effective_policy(
    bundle: StoreBundle,
) -> None:
    """agent hồ sơ patient_channel: chính sách hiệu lực RỖNG dù đã gán (mặc định tắt MCP)"""
    (s1,) = await _servers(bundle, "a")
    await bundle.add_agent("patient-agent", PolicyProfileKey.PATIENT_CHANNEL)
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "patient-agent", [s1])
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "patient-agent") == [s1]
    policy = await bundle.bindings.policy_for_agent(bundle.clinic_id, "patient-agent")
    assert policy.bound_server_ids == []


async def test_mcp_agent_binding_staff_assistant_agent_sees_its_bound_servers(bundle: StoreBundle) -> None:
    """agent staff_assistant thấy các server đã gán"""
    s1, s2 = await _servers(bundle, "a", "b")
    await bundle.add_agent("ag1")
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", [s2, s1])
    policy = await bundle.bindings.policy_for_agent(bundle.clinic_id, "ag1")
    assert policy.bound_server_ids == sorted([s1, s2])
    assert policy.clinic_id == bundle.clinic_id
    assert policy.agent_id == "ag1"


async def test_mcp_agent_binding_an_unknown_agent_has_an_empty_policy(bundle: StoreBundle) -> None:
    """agent không tồn tại -> chính sách rỗng (đóng)"""
    assert (await bundle.bindings.policy_for_agent(bundle.clinic_id, "ma-ma")).bound_server_ids == []


async def test_mcp_agent_binding_binding_unknown_ids_is_not_found(bundle: StoreBundle) -> None:
    """gán agent/server không tồn tại -> NOT_FOUND (khóa ngoại), không có dòng mồ côi"""
    await bundle.add_agent("ag1")
    with pytest.raises(DomainError) as unknown_server:
        await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", ["khong-co"])
    assert unknown_server.value.code is ErrorCode.NOT_FOUND
    (s1,) = await _servers(bundle, "a")
    with pytest.raises(DomainError) as unknown_agent:
        await bundle.bindings.set_agents_for_server(bundle.clinic_id, s1, ["khong-co"])
    assert unknown_agent.value.code is ErrorCode.NOT_FOUND
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "ag1") == []


async def test_mcp_agent_binding_duplicates_are_filtered(bundle: StoreBundle) -> None:
    """lọc trùng qua Set phòng id lặp"""
    (s1,) = await _servers(bundle, "a")
    await bundle.add_agent("ag1")
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", [s1, s1, s1])
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "ag1") == [s1]


async def test_mcp_agent_binding_reverse_direction_and_counts(bundle: StoreBundle) -> None:
    """chiều ngược: agentsOfServer, setAgentsForServer, đếm agent theo server (server không có agent vắng mặt)"""
    s1, s2 = await _servers(bundle, "a", "b")
    await bundle.add_agent("ag1")
    await bundle.add_agent("ag2")
    await bundle.bindings.set_agents_for_server(bundle.clinic_id, s1, ["ag2", "ag1"])
    assert await bundle.bindings.agents_of_server(bundle.clinic_id, s1) == ["ag1", "ag2"]
    counts = await bundle.bindings.count_agents_by_server(bundle.clinic_id)
    assert counts == {s1: 2}
    assert s2 not in counts
    await bundle.bindings.set_agents_for_server(bundle.clinic_id, s1, [])
    assert await bundle.bindings.agents_of_server(bundle.clinic_id, s1) == []


async def test_mcp_agent_binding_a_write_refreshes_the_in_memory_cache(bundle: StoreBundle) -> None:
    """ghi gán -> bản sao trong RAM (cửa 1) cập nhật ngay"""
    (s1,) = await _servers(bundle, "a")
    await bundle.add_agent("ag1")
    assert bundle.cache.is_bound(bundle.clinic_id, "ag1", s1) is False
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", [s1])
    assert bundle.cache.is_bound(bundle.clinic_id, "ag1", s1) is True
    assert bundle.cache.servers_of_agent("ag1") == [(bundle.clinic_id, s1)]
    await bundle.bindings.clear_for_agent(bundle.clinic_id, "ag1")
    assert bundle.cache.is_bound(bundle.clinic_id, "ag1", s1) is False

# ported from: src/server/routes/tool-routes.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

API ``GET /admin/tools``: focused on ``kb_search.available`` because it is the ONLY tool that gates by AGENT (every
other tool used to gate on global infrastructure, independent of ``agentId``). The route takes an optional
``agent_id``, see ``_build_scope`` in ``admin_tools.py`` for the full reason.

Forced deviations: Hono ``app.request`` + dashboard login become ``httpx.AsyncClient`` over the FastAPI app with the
services overridden (``InMemoryAccountStore`` / ``InMemoryAgentStore`` of ``pema_contracts.testing``, a fake
``KbAvailability``); ``400`` for an unknown id is ``422 validation_failed`` (the shared vocabulary); the channel
kind of the account comes from a ``ChannelCapabilitiesProvider`` (C1/C2 own the real capabilities); plus the new
``blocked_by_policy`` flag of the policy profile.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest

from pema.agent.tools.testing import (
    FakeKbAvailability,
    bot_capabilities,
    make_tool_deps,
    personal_capabilities,
)
from pema.agent.tools.tool_registry import DefaultToolRegistry
from pema.api.routers.admin_tools import (
    ToolsAdminServices,
    get_tools_admin_services,
    install_tools_admin_services,
)
from pema.bootstrap import create_app
from pema.config.runtime_settings_kv import reset_runtime_settings_kv
from pema_contracts.channel import ChannelCapabilities, ChannelKind
from pema_contracts.common import JsonObject
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    InMemoryAccountStore,
    InMemoryAgentStore,
    fake_account_config,
    fake_agent_profile,
)


class _Channels:
    def capabilities_for(self, kind: ChannelKind) -> ChannelCapabilities:
        return bot_capabilities() if kind is ChannelKind.ZALO_BOT else personal_capabilities()


class _Env:
    def __init__(self) -> None:
        self.kb = FakeKbAvailability()
        self.accounts = InMemoryAccountStore()
        self.agents = InMemoryAgentStore()
        deps = make_tool_deps(kb_availability=self.kb)
        self.services = ToolsAdminServices(
            registry=DefaultToolRegistry(deps),
            accounts=self.accounts,
            agents=self.agents,
            channels=_Channels(),
            clinic_id=lambda: FAKE_CLINIC_ID,
        )


@pytest.fixture
async def env() -> AsyncIterator[tuple[_Env, httpx.AsyncClient]]:
    reset_runtime_settings_kv()
    state = _Env()
    app = create_app()
    app.dependency_overrides[get_tools_admin_services] = lambda: state.services
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield state, client
    install_tools_admin_services(None)
    reset_runtime_settings_kv()


async def _items(client: httpx.AsyncClient, query: str = "") -> tuple[int, list[JsonObject]]:
    res = await client.get(f"/api/v1/admin/tools{query}")
    return res.status_code, (res.json() if res.status_code == 200 else [])


def _tool(items: list[JsonObject], key: str) -> JsonObject:
    found = next((t for t in items if t["key"] == key), None)
    assert found is not None, f"{key} phải có mặt trong catalog (route trả CẢ tool chưa available)"
    return found


# ------------------------------------------------------------- kb_search.available by agent_id


async def test_get_admin_tools_kb_search_available_by_agent_id_agent_with_a_source_is_usable(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """agentId của agent ĐÃ gán nguồn -> available: true"""
    state, client = env
    await state.agents.create_agent(
        FAKE_CLINIC_ID, agent_id="agent-co-nguon", name="Agent có nguồn", icon="x", persona=""
    )
    state.kb.agents.add("agent-co-nguon")
    _status, items = await _items(client, "?agent_id=agent-co-nguon")
    assert _tool(items, "kb_search")["usable"] is True


async def test_get_admin_tools_kb_search_available_by_agent_id_agent_without_a_source_is_not_usable(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """agentId của agent CHƯA gán nguồn -> available: false"""
    state, client = env
    await state.agents.create_agent(
        FAKE_CLINIC_ID, agent_id="agent-chua-gan", name="Agent chưa gán", icon="x", persona=""
    )
    state.kb.agents.add("agent-khac")  # a source exists in the store, but NOT assigned to this agent
    _status, items = await _items(client, "?agent_id=agent-chua-gan")
    assert _tool(items, "kb_search")["usable"] is False


async def test_get_admin_tools_kb_search_available_by_agent_id_no_agent_id_and_an_empty_store_is_not_usable(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """không truyền agentId, kho RỖNG -> available: false"""
    _state, client = env
    _status, items = await _items(client)
    assert _tool(items, "kb_search")["usable"] is False


async def test_get_admin_tools_kb_search_available_by_agent_id_no_agent_id_but_the_store_has_a_source_is_usable(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """không truyền agentId, kho CÓ nguồn (bất kể gán cho ai) -> available: true"""
    state, client = env
    state.kb.has_any = True
    _status, items = await _items(client)
    assert _tool(items, "kb_search")["usable"] is True


async def test_get_admin_tools_kb_search_available_by_agent_id_an_unknown_agent_is_a_client_error_not_500(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """agentId trỏ vào agent KHÔNG TỒN TẠI -> lỗi khách (422 validation_failed), không phải 500 hay rơi về ca không-agent"""
    _state, client = env
    status, _ = await _items(client, "?agent_id=khong-ton-tai")
    assert status == 422


# ------------------------------------------------------------- channel of the account


async def test_get_admin_tools_account_channel_bot_account_tools_needing_the_personal_api_are_not_usable(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """account BOT: tool cần zca-js hiện KHÔNG dùng được, kèm lý do của Zalo

    Without this road the Tools page of a Bot account would still show every tool and "Send file" green, while the
    model running on that account never receives it: the dashboard says one thing, the model gets another.
    """
    state, client = env
    state.accounts.accounts[(FAKE_CLINIC_ID, "acc-bot")] = fake_account_config(
        id="acc-bot", channel=ChannelKind.ZALO_BOT
    )
    _status, items = await _items(client, "?account_id=acc-bot")
    send_file = _tool(items, "send_file")
    assert send_file["usable"] is False, "send_file vẫn hiện dùng được trên tài khoản bot"
    assert "Zalo Bot API" in str(send_file["hint"])


async def test_get_admin_tools_account_channel_personal_account_the_same_tools_stay_usable(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """account CÁ NHÂN: đúng những tool đó vẫn dùng được"""
    state, client = env
    state.accounts.accounts[(FAKE_CLINIC_ID, "acc-ca-nhan")] = fake_account_config(
        id="acc-ca-nhan", channel=ChannelKind.ZALO_PERSONAL
    )
    _status, items = await _items(client, "?account_id=acc-ca-nhan")
    assert _tool(items, "send_file")["usable"] is True


async def test_get_admin_tools_account_channel_no_account_id_falls_back_to_the_personal_channel_without_breaking(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """KHÔNG truyền accountId thì rơi về kênh cá nhân, không vỡ"""
    _state, client = env
    status, items = await _items(client)
    assert status == 200
    assert _tool(items, "send_file")["usable"] is True


async def test_get_admin_tools_account_channel_an_unknown_account_is_an_error_not_a_silent_personal_fallback(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """accountId không tồn tại thì lỗi khách, KHÔNG im lặng rơi về kênh cá nhân

    An earlier version fell back to "personal" on the argument that a wrong account should not kill the whole Tools
    page. But the ``agent_id`` branch next to it errors for exactly the opposite argument, and that one wins: silently
    turning a wrong id into "personal channel" makes the page show every tool as "usable" for a BOT account that was
    just deleted. A trap for the next debugging session.
    """
    _state, client = env
    status, _ = await _items(client, "?account_id=khong-ton-tai")
    assert status == 422


# ------------------------------------------------------------- policy profile (new)


async def test_get_admin_tools_policy_profile_patient_channel_flags_media_and_web_tools_as_blocked_by_policy(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """hồ sơ patient_channel: tool ảnh/video/tài liệu/web hiện blocked_by_policy và không dùng được (ca bổ sung)"""
    state, client = env
    state.accounts.accounts[(FAKE_CLINIC_ID, "acc-bn")] = fake_account_config(
        id="acc-bn", channel=ChannelKind.ZALO_PERSONAL, policy_profile=PolicyProfileKey.PATIENT_CHANNEL
    )
    state.agents.agents[(FAKE_CLINIC_ID, "agent-test")] = fake_agent_profile()
    _status, items = await _items(client, "?account_id=acc-bn&agent_id=agent-test")
    web = _tool(items, "web_search")
    assert web["blocked_by_policy"] is True
    assert web["usable"] is False
    assert _tool(items, "get_datetime")["blocked_by_policy"] is False
    assert _tool(items, "get_datetime")["usable"] is True


async def test_get_admin_tools_reports_the_disabled_flags_of_the_account_and_the_agent(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """cờ disabled_for_account / disabled_for_agent phản ánh danh sách tắt (ca bổ sung)"""
    state, client = env
    state.accounts.accounts[(FAKE_CLINIC_ID, "acc-1")] = fake_account_config(
        id="acc-1", disabled_tools=["send_file"]
    )
    state.agents.agents[(FAKE_CLINIC_ID, "ag-1")] = fake_agent_profile(
        id="ag-1", disabled_tools=["web_fetch"]
    )
    _status, items = await _items(client, "?account_id=acc-1&agent_id=ag-1")
    assert _tool(items, "send_file")["disabled_for_account"] is True
    assert _tool(items, "send_file")["disabled_for_agent"] is False
    assert _tool(items, "web_fetch")["disabled_for_agent"] is True


# ------------------------------------------------------------- source chains


async def test_web_search_chain_patch_brave_without_a_key_is_refused_and_the_key_is_never_returned(
    env: tuple[_Env, httpx.AsyncClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    """chọn Brave khi chưa có key bị từ chối; key nhập vào KHÔNG BAO GIỜ trả về plaintext"""
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "00" * 32)
    _state, client = env
    steps_brave = {"steps": [{"id": "brave", "label": "Brave Search", "enabled": True}]}
    res = await client.patch("/api/v1/admin/tools/web_search", json=steps_brave)
    assert res.status_code == 422

    res = await client.patch(
        "/api/v1/admin/tools/web_search", json={**steps_brave, "brave_api_key": "BSA-bi-mat-123"}
    )
    assert res.status_code == 200
    assert "BSA-bi-mat-123" not in res.text, "key thật lọt ra response là lỗi bảo mật"
    body = res.json()
    assert body["brave_api_key_set"] is True
    assert body["steps"][0]["enabled"] is True


async def test_web_search_chain_the_last_step_duckduckgo_cannot_be_switched_off(
    env: tuple[_Env, httpx.AsyncClient],
) -> None:
    """bậc cuối của chuỗi (DuckDuckGo) không tắt được - tool không bao giờ rơi vào 'chưa cấu hình'"""
    _state, client = env
    res = await client.patch(
        "/api/v1/admin/tools/web_search",
        json={"steps": [{"id": "duckduckgo", "label": "DuckDuckGo", "enabled": False}]},
    )
    assert res.status_code == 422


async def test_web_fetch_chain_patch_toggles_the_jina_fallback(env: tuple[_Env, httpx.AsyncClient]) -> None:
    """PATCH web_fetch bật/tắt bậc 2 (Jina); bậc tự tải luôn bật"""
    _state, client = env
    res = await client.patch("/api/v1/admin/tools/web_fetch", json={"fallback_enabled": True})
    assert res.status_code == 200
    assert res.json()["fallback_enabled"] is True
    res = await client.get("/api/v1/admin/tools/web_fetch")
    assert [s["enabled"] for s in res.json()["steps"]] == [True, True]
    res = await client.patch("/api/v1/admin/tools/web_fetch", json={"fallback_enabled": False})
    assert res.json()["steps"][1]["enabled"] is False


def test_the_tools_admin_services_default_is_not_implemented_until_installed() -> None:
    """chưa lắp services thì route trả 501 chứ không sập (ca bổ sung)"""
    install_tools_admin_services(None)
    with pytest.raises(Exception) as info:  # noqa: PT011 - DomainError(NOT_IMPLEMENTED)
        get_tools_admin_services()
    assert "triển khai" in str(info.value)


_ = UUID

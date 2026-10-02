# ported from: src/mcp/mcp-manager.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original injected a fake connect function (``datKetNoiServerChoTest``) and a SQLite file; here every test builds
a ``Rig``: a fresh manager over ``InMemoryMcpStore`` with a ``FakeConnector``, a private tool provider (no global
state) and a binding cache the store keeps in step. The Postgres stores are covered in ``test_mcp_server_store`` and
``test_mcp_agent_binding``.

Bindings in this port are cached in memory for the synchronous schema door: ``bind`` goes through the store, which
refreshes the cache, so a binding made after a connect is visible to ``tools_for_agent`` at once, as in the original.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest

from pema.agent.tools.tool_failure_result import la_ket_qua_loi as is_tool_failure_result
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.mcp.mcp_agent_binding import McpBindingCache
from pema.mcp.mcp_manager import DefaultMcpManager
from pema.mcp.mcp_tool_provider import SwitchableMcpToolProvider
from pema.mcp.mcp_types import McpServerStatus
from pema.mcp.testing import FakeConnector, InMemoryMcpStore, remote_tools
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi
from pema_contracts.channel import ChannelKind
from pema_contracts.installation import reset_installation_clinic_id, set_installation_clinic_id
from pema_contracts.policy import DEFAULT_PROFILES, PolicyContext, PolicyProfileKey
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    InMemoryAgentStore,
    fake_account_config,
    fake_agent_profile,
    make_inbound,
)
from pema_contracts.tools import ToolContext

OTHER_CLINIC = UUID("00000000-0000-4000-8000-000000000002")


@dataclass
class Rig:
    manager: DefaultMcpManager
    store: InMemoryMcpStore
    connector: FakeConnector
    provider: SwitchableMcpToolProvider
    agents: InMemoryAgentStore

    def add_agent(
        self,
        agent_id: str,
        *,
        clinic_id: UUID = FAKE_CLINIC_ID,
        profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
    ) -> None:
        self.agents.agents[(clinic_id, agent_id)] = fake_agent_profile(
            id=agent_id, clinic_id=clinic_id, policy_profile=profile
        )

    async def server(self, name: str = "svr", url: str = "https://x/mcp", **kwargs: object) -> str:
        created = await self.store.create_server(FAKE_CLINIC_ID, name=name, url=url, **kwargs)  # type: ignore[arg-type]
        return created.id

    async def bind(self, agent_id: str, *server_ids: str, clinic_id: UUID = FAKE_CLINIC_ID) -> None:
        if (clinic_id, agent_id) not in self.agents.agents:
            self.add_agent(agent_id, clinic_id=clinic_id)
        await self.store.set_servers_for_agent(clinic_id, agent_id, list(server_ids))

    async def status(self, server_id: str, clinic_id: UUID = FAKE_CLINIC_ID) -> McpServerStatus:
        found = await self.store.get_server(clinic_id, server_id)
        assert found is not None
        return found.status

    def keys(self, agent_id: str) -> list[str]:
        return [spec.key for spec in self.manager.tools_for_agent(agent_id)]


def make_rig(*tool_names: str, fail_urls_containing: str | None = None) -> Rig:
    agents = InMemoryAgentStore()
    cache = McpBindingCache()
    store = InMemoryMcpStore(agent_store=agents, binding_cache=cache)
    connector = FakeConnector(
        tools=remote_tools(*(tool_names or ("tra_cuu",))), fail_urls_containing=fail_urls_containing
    )
    provider = SwitchableMcpToolProvider()
    rig = Rig(manager=None, store=store, connector=connector, provider=provider, agents=agents)  # type: ignore[arg-type]

    rig.manager = DefaultMcpManager(
        server_store=store,
        binding_store=store,
        bindings=cache,
        connect=connector,
        provider=provider,
    )
    return rig


@pytest.fixture(autouse=True)
def _reset_tuning() -> Iterator[None]:
    reset_tuning_provider()
    set_installation_clinic_id(FAKE_CLINIC_ID)
    yield
    reset_installation_clinic_id()


def _ctx(agent_id: str, clinic_id: UUID = FAKE_CLINIC_ID) -> ToolContext:
    message = make_inbound()
    return ToolContext(
        clinic_id=clinic_id,
        account=fake_account_config(),
        agent=fake_agent_profile(id=agent_id),
        channel=None,
        message=message,
        batch=[message],
        policy=PolicyContext(
            clinic_id=clinic_id,
            account_id="acc-1",
            agent_id=agent_id,
            channel=ChannelKind.ZALO_BOT,
            thread_id="thread-1",
            profile=DEFAULT_PROFILES[PolicyProfileKey.STAFF_ASSISTANT],
        ),
    )


async def _status_is(
    rig: Rig, server_id: str, expected: McpServerStatus, clinic_id: UUID = FAKE_CLINIC_ID
) -> None:
    async def reached() -> bool:
        return await rig.status(server_id, clinic_id) is expected

    await doi_cho_den_khi(reached, WaitOptions(mo_ta=f"trạng thái {expected.value}"))


async def test_mcp_manager_connect_then_tools_only_for_the_bound_agent() -> None:
    """nối rồi mcpToolDefinitions chỉ cho agent được gán"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    await rig.bind("a1", server_id)
    rig.add_agent("a2")
    assert rig.keys("a1") == ["mcp__svr__tra_cuu"]
    assert rig.keys("a2") == []
    assert await rig.status(server_id) is McpServerStatus.CONNECTED


async def test_mcp_manager_disabled_server_is_not_loaded_and_stays_cho_ket_noi() -> None:
    """server enabled:false -> ketNoiLaiServer KHÔNG nạp tool, trạng thái cho_ket_noi"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("tat", enabled=False)
    await rig.bind("a1", server_id)
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    assert rig.keys("a1") == []
    assert await rig.status(server_id) is McpServerStatus.CONNECTING
    assert rig.connector.configs == []


async def test_mcp_manager_connected_server_then_disabled_then_reconnect_disconnects_and_does_not_reconnect() -> (
    None
):
    """server đang nối -> capNhatServer tắt -> ketNoiLaiServer -> NGẮT, không tự nối lại"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.bind("a1", server_id)
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    assert len(rig.keys("a1")) == 1, "phải nối được trước khi tắt"
    await rig.store.update_server(FAKE_CLINIC_ID, server_id, enabled=False)
    await rig.manager.reconnect_server(
        FAKE_CLINIC_ID, server_id
    )  # mirrors the PATCH route: changed -> call again
    assert rig.keys("a1") == [], "PATCH tắt không được ngắt-rồi-nối-lại"
    assert await rig.status(server_id) is McpServerStatus.CONNECTING
    assert len(rig.connector.connections) == 1
    assert rig.connector.connections[0].closed is True


async def test_mcp_manager_drift_against_the_baseline_goes_to_can_duyet_lai_and_loads_no_tool() -> None:
    """drift so mốc -> can_duyet_lai, KHÔNG nạp tool"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)  # first time: save the baseline and load
    await rig.bind("a1", server_id)
    rig.connector.tools = remote_tools("tra_cuu", "ghi_file")  # the server changes
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    assert await rig.status(server_id) is McpServerStatus.NEEDS_REAPPROVAL
    assert rig.keys("a1") == []  # not loaded on drift
    assert rig.connector.connections[-1].closed is True
    found = await rig.store.get_server(FAKE_CLINIC_ID, server_id)
    assert found is not None
    assert found.error == "Bộ tool đổi (thêm 1, đổi 0, bỏ 0)"


async def test_mcp_manager_a_broken_server_does_not_block_another() -> None:
    """một server hỏng không chặn server khác"""
    rig = make_rig("t", fail_urls_containing="hong")
    ok = await rig.server("ok", url="https://ok/mcp")
    broken = await rig.server("hong", url="https://hong/mcp")
    await rig.bind("a1", ok, broken)
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, ok)
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, broken)
    assert len(rig.keys("a1")) == 1  # only the first loaded
    assert await rig.status(broken) is McpServerStatus.ERROR


async def test_mcp_manager_reapprove_drift_sets_the_new_baseline_and_connects() -> None:
    """duyetLaiDrift đặt mốc mới + da_ket_noi"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    rig.connector.tools = remote_tools("tra_cuu", "ghi_file")
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)  # -> can_duyet_lai
    await rig.manager.reapprove_drift(FAKE_CLINIC_ID, server_id)  # approve the new set
    await rig.bind("a1", server_id)
    assert await rig.status(server_id) is McpServerStatus.CONNECTED
    assert len(rig.keys("a1")) == 2
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)  # the new baseline holds: no drift again
    assert await rig.status(server_id) is McpServerStatus.CONNECTED


async def test_mcp_manager_list_tools_hanging_past_the_timeout_closes_the_handle_sets_loi_and_loads_nothing() -> (
    None
):
    """tools() treo quá timeout -> đóng handle, đặt loi, KHÔNG nạp, không treo test

    MCP_CONNECT_TIMEOUT_MS has a minimum of 1000 in the tuning specs: fast enough for one test, and the lowest
    value ``get_tuning`` still accepts (a lower one falls back to the default of 15000 and would hang the test)."""
    install_tuning_provider(StaticTuningProvider({"MCP_CONNECT_TIMEOUT_MS": 1000}))
    rig = make_rig("tra_cuu")
    rig.connector.connection_kwargs = {"hang_on_list_tools": True}
    server_id = await rig.server("treo", url="https://treo/mcp")
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    assert await rig.status(server_id) is McpServerStatus.ERROR
    statuses = await rig.manager.runtime_status(FAKE_CLINIC_ID)
    assert next(s for s in statuses if s.server_id == server_id).tool_count == 0
    assert rig.connector.connections[0].closed is True, (
        "handle rò rỉ - list_tools timeout phải đóng client trước khi báo loi"
    )


async def test_mcp_manager_start_with_mcp_enabled_false_is_a_noop_and_connects_no_server() -> None:
    """startMcpManager() với MCP_ENABLED=false -> noop, không nối server nào"""
    install_tuning_provider(StaticTuningProvider({"MCP_ENABLED": False}))
    rig = make_rig("tra_cuu")
    server_id = await rig.server("khong-duoc-noi")
    await rig.manager.start()
    await asyncio.sleep(0)
    await rig.manager.stop()  # callable and does not raise
    assert rig.connector.configs == []
    assert await rig.status(server_id) is McpServerStatus.CONNECTING
    assert rig.provider.tools_for_agent("a1") == []


async def test_mcp_manager_mcp_enabled_false_at_read_time_empties_the_tools_even_when_connected() -> None:
    """MCP_ENABLED=false LÚC ĐỌC (không chỉ lúc boot) -> mcpToolDefinitions rỗng dù đã nối"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.bind("a1", server_id)
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    assert len(rig.keys("a1")) == 1, "phải nối được trước khi tắt công tắc"
    install_tuning_provider(StaticTuningProvider({"MCP_ENABLED": False}))
    assert rig.keys("a1") == [], "kill-switch phải chặn NGAY, không cần restart"


async def test_mcp_manager_start_enabled_connects_the_servers_and_returns_a_stop_that_can_be_called() -> None:
    """startMcpManager() (bật) trả hàm stop gọi được"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.bind("a1", server_id)
    await rig.manager.start()
    await _status_is(rig, server_id, McpServerStatus.CONNECTED)
    assert [s.key for s in rig.provider.tools_for_agent("a1")] == [
        "mcp__svr__tra_cuu"
    ]  # registered as the source
    await rig.manager.stop()
    assert rig.connector.connections[0].closed is True
    assert rig.provider.tools_for_agent("a1") == []


async def test_mcp_manager_two_concurrent_reapprove_calls_on_the_same_id_open_one_connection() -> None:
    """duyetLaiDrift gọi đồng thời 2 lần cùng id không mở 2 kết nối"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)  # first connect so a handle is open
    opened_before = len(rig.connector.connections)
    # Both calls start before any microtask runs: the double click on "Re-approve" of the dashboard.
    await asyncio.gather(
        rig.manager.reapprove_drift(FAKE_CLINIC_ID, server_id),
        rig.manager.reapprove_drift(FAKE_CLINIC_ID, server_id),
    )
    assert len(rig.connector.connections) - opened_before == 1, (
        "chốt dangNap phải chặn lượt gọi đồng thời thứ 2, không mở 2 handle"
    )
    assert await rig.status(server_id) is McpServerStatus.CONNECTED


# ------------------------------------------- additions of the Python port (not in the original test file)


async def test_mcp_manager_first_connect_saves_the_baseline_and_the_snapshot_and_passes_the_headers() -> None:
    """lần nối đầu lưu mốc + snapshot; header giải mã được truyền cho kết nối"""
    rig = make_rig("tra_cuu", "ghi_chu")
    server_id = await rig.server("svr", headers={"Authorization": "Bearer synthetic"})
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    assert await rig.store.get_fingerprint(FAKE_CLINIC_ID, server_id) != ""
    found = await rig.store.get_server(FAKE_CLINIC_ID, server_id)
    assert found is not None
    assert [t.name for t in found.tools_snapshot] == ["tra_cuu", "ghi_chu"]
    assert rig.connector.configs[0].headers == {"Authorization": "Bearer synthetic"}
    assert "synthetic" not in repr(rig.connector.configs[0])


async def test_mcp_manager_a_tool_runs_end_to_end_through_the_connection_wrapped_as_untrusted() -> None:
    """tool chạy xuyên suốt: manager -> spec -> build -> execute -> kết nối giả, kết quả bọc không tin cậy"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.bind("a1", server_id)
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    (spec,) = rig.manager.tools_for_agent("a1")
    result = await spec.build(_ctx("a1")).execute({"q": "abc"})
    assert isinstance(result, str)
    assert "<noi_dung_ngoai_" in result
    assert rig.connector.connections[0].calls == [("tra_cuu", {"q": "abc"})]


async def test_mcp_manager_a_grant_revoked_in_the_database_blocks_execution_even_with_a_stale_cache() -> None:
    """gỡ quyền trong DB giữa lượt: cache RAM còn cũ nhưng cửa 2 hỏi DB nên chặn"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.bind("a1", server_id)
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    (spec,) = rig.manager.tools_for_agent("a1")
    tool = spec.build(_ctx("a1"))
    rig.store.simulate_all_bindings_revoked_by_another_process()  # this process's cache is stale
    assert len(rig.keys("a1")) == 1
    result = await tool.execute({"q": "x"})
    assert is_tool_failure_result(result)
    assert "không còn được cấp" in str(result)
    assert rig.connector.connections[0].calls == []


async def test_mcp_manager_tools_for_agent_never_raises() -> None:
    """tools_for_agent không bao giờ ném (hợp đồng McpToolProvider)"""

    class ExplodingCache(McpBindingCache):
        def servers_of_agent(self, agent_id: str) -> list[tuple[UUID, str]]:
            raise RuntimeError("boom")

    rig = make_rig("tra_cuu")
    store = rig.store

    manager = DefaultMcpManager(
        server_store=store,
        binding_store=store,
        bindings=ExplodingCache(),
        connect=rig.connector,
        provider=SwitchableMcpToolProvider(),
    )
    assert manager.tools_for_agent("a1") == []


async def test_mcp_manager_health_sync_retries_a_loi_server_but_never_a_can_duyet_lai_one() -> None:
    """health: server loi được nối lại; server can_duyet_lai KHÔNG tự nối lại, chờ người duyệt"""
    rig = make_rig("tra_cuu")
    failing = await rig.server("loi", url="https://hong/mcp")
    drifted = await rig.server("drift", url="https://ok/mcp")
    await rig.store.set_status(FAKE_CLINIC_ID, failing, McpServerStatus.ERROR, "chết")
    await rig.store.set_status(FAKE_CLINIC_ID, drifted, McpServerStatus.NEEDS_REAPPROVAL, "đổi")
    await rig.manager.sync_once()
    await _status_is(rig, failing, McpServerStatus.CONNECTED)
    assert await rig.status(drifted) is McpServerStatus.NEEDS_REAPPROVAL
    assert all("ok/mcp" not in c.url for c in rig.connector.configs)


async def test_mcp_manager_health_sync_follows_changes_made_by_another_process() -> None:
    """health: theo kịp thay đổi do tiến trình khác (API) ghi vào DB: tắt, đổi url, xóa, tạo mới"""
    rig = make_rig("tra_cuu")
    keep = await rig.server("keep", url="https://a/mcp")
    to_disable = await rig.server("tat", url="https://b/mcp")
    to_change = await rig.server("doi", url="https://c/mcp")
    to_delete = await rig.server("xoa", url="https://d/mcp")
    for server_id in (keep, to_disable, to_change, to_delete):
        await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    assert len(rig.manager.connected_server_ids(FAKE_CLINIC_ID)) == 4
    await rig.store.update_server(FAKE_CLINIC_ID, to_disable, enabled=False)
    await rig.store.update_server(FAKE_CLINIC_ID, to_change, url="https://c2/mcp")
    await rig.store.delete_server(FAKE_CLINIC_ID, to_delete)
    fresh = await rig.server("moi", url="https://e/mcp")  # created by the API process: cho_ket_noi
    await rig.manager.sync_once()
    await _status_is(rig, fresh, McpServerStatus.CONNECTED)
    await doi_cho_den_khi(lambda: any(c.url == "https://c2/mcp" for c in rig.connector.configs))
    connected = rig.manager.connected_server_ids(FAKE_CLINIC_ID)
    assert to_disable not in connected
    assert to_delete not in connected
    assert {keep, fresh} <= connected
    assert to_change in connected  # reconnected with the new url


async def test_mcp_manager_health_sync_refreshes_the_bindings_of_each_clinic() -> None:
    """health: nạp lại bản sao gán trong RAM (kịp thay đổi của tiến trình khác)"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")
    await rig.manager.reconnect_server(FAKE_CLINIC_ID, server_id)
    rig.add_agent("a1")
    rig.store.simulate_binding_written_by_another_process(FAKE_CLINIC_ID, "a1", server_id)
    assert rig.keys("a1") == []
    await rig.manager.sync_once()
    assert len(rig.keys("a1")) == 1


async def test_mcp_manager_boot_survives_a_failing_store() -> None:
    """boot: lỗi đọc DB không làm sập tiến trình, chỉ ghi log"""
    rig = make_rig("tra_cuu")
    server_id = await rig.server("svr")

    async def broken(clinic_id: UUID) -> list:  # type: ignore[type-arg]
        raise ConnectionError("db down")

    rig.store.list_servers = broken  # type: ignore[method-assign]
    await rig.manager.boot()
    assert await rig.status(server_id) is not McpServerStatus.CONNECTED

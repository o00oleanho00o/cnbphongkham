# ported from: src/mcp/mcp-agent-binding-cleanup.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original called ``deleteAgent`` of ``agent-store.ts`` (D2) and checked the bindings were gone, because there
were no foreign keys and the store had to clean up by hand. Postgres has ``ON DELETE CASCADE``, so the test
deletes the agent ROW (what D2's ``delete_agent`` ends up doing) and checks the same invariant. In memory the
agent store is a different object, so only the explicit cleanup path (``clear_for_agent``) applies there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from tests.mcp.conftest import StoreBundle


async def test_mcp_agent_binding_cleanup_deleting_an_agent_also_removes_its_mcp_bindings(
    bundle: StoreBundle,
) -> None:
    """deleteAgent xóa luôn agent_mcp_servers của nó"""
    server = await bundle.servers.create_server(bundle.clinic_id, name="a", url="https://x/mcp")
    await bundle.add_agent("ban-hang")
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ban-hang", [server.id])
    if bundle.admin is None:
        await bundle.bindings.clear_for_agent(bundle.clinic_id, "ban-hang")
    else:
        with bundle.admin.begin() as conn:
            deleted = conn.execute(
                text("DELETE FROM agent.agents WHERE clinic_id = :c AND id = 'ban-hang'"),
                {"c": bundle.clinic_id},
            )
        assert deleted.rowcount == 1
    assert await bundle.bindings.servers_of_agent(bundle.clinic_id, "ban-hang") == []
    assert await bundle.bindings.agents_of_server(bundle.clinic_id, server.id) == []


async def test_mcp_agent_binding_cleanup_clear_for_agent_leaves_other_agents_alone(
    bundle: StoreBundle,
) -> None:
    """dọn gán của một agent không đụng agent khác"""
    server = await bundle.servers.create_server(bundle.clinic_id, name="a", url="https://x/mcp")
    await bundle.add_agent("ag1")
    await bundle.add_agent("ag2")
    await bundle.bindings.set_agents_for_server(bundle.clinic_id, server.id, ["ag1", "ag2"])
    await bundle.bindings.clear_for_agent(bundle.clinic_id, "ag1")
    assert await bundle.bindings.agents_of_server(bundle.clinic_id, server.id) == ["ag2"]

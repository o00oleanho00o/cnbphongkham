# ported from: src/mcp/mcp-server-store.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Every test runs on the in-memory store AND on Postgres (fixture ``bundle``); the ones about the stored form of
the headers need the real table and run on Postgres only.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from pema.mcp.mcp_types import McpServerStatus, McpToolInfo

if TYPE_CHECKING:
    from tests.mcp.conftest import StoreBundle


async def test_mcp_server_store_create_then_read_back_headers_decrypt_to_the_same_value(
    bundle: StoreBundle,
) -> None:
    """tạo rồi đọc lại, header giải mã khớp"""
    server = await bundle.servers.create_server(
        bundle.clinic_id, name="Notion", url="https://x/mcp", headers={"Authorization": "Bearer k"}
    )
    internal = await bundle.servers.get_internal(bundle.clinic_id, server.id)
    assert internal is not None
    assert internal.headers["Authorization"] == "Bearer k"
    assert internal.server.status is McpServerStatus.CONNECTING


async def test_mcp_server_store_headers_are_stored_encrypted_not_plaintext(bundle: StoreBundle) -> None:
    """header lưu ở dạng mã hóa, KHÔNG plaintext"""
    if bundle.admin is None:
        pytest.skip("the stored form only exists in Postgres")
    server = await bundle.servers.create_server(
        bundle.clinic_id, name="a", url="https://x/mcp", headers={"Authorization": "Bearer secret123"}
    )
    with bundle.admin.connect() as conn:
        stored = conn.execute(
            text("SELECT headers_enc FROM agent.mcp_servers WHERE clinic_id = :c AND id = :i"),
            {"c": bundle.clinic_id, "i": server.id},
        ).scalar_one()
    assert stored != ""
    assert "secret123" not in stored, "header bị lưu plaintext"


async def test_mcp_server_store_list_servers_does_not_expose_headers(bundle: StoreBundle) -> None:
    """danhSachServer KHÔNG lộ headers"""
    await bundle.servers.create_server(
        bundle.clinic_id, name="a", url="https://x/mcp", headers={"Authorization": "Bearer k"}
    )
    listed = await bundle.servers.list_servers(bundle.clinic_id)
    assert not hasattr(listed[0], "headers")
    assert "headers" not in listed[0].model_dump()
    assert listed[0].has_headers is True
    assert "Bearer k" not in listed[0].model_dump_json()


async def test_mcp_server_store_update_server_headers_none_keeps_the_old_headers(bundle: StoreBundle) -> None:
    """capNhatServer headers===undefined thì GIỮ nguyên"""
    server = await bundle.servers.create_server(
        bundle.clinic_id, name="a", url="https://x/mcp", headers={"Authorization": "Bearer k"}
    )
    assert await bundle.servers.update_server(bundle.clinic_id, server.id, name="b") is True
    internal = await bundle.servers.get_internal(bundle.clinic_id, server.id)
    assert internal is not None
    assert internal.headers["Authorization"] == "Bearer k"
    assert internal.server.name == "b"


async def test_mcp_server_store_clear_headers_removes_them_for_good(bundle: StoreBundle) -> None:
    """xoaHeaders xóa hẳn header"""
    server = await bundle.servers.create_server(
        bundle.clinic_id, name="a", url="https://x/mcp", headers={"Authorization": "Bearer k"}
    )
    assert await bundle.servers.clear_headers(bundle.clinic_id, server.id) is True
    internal = await bundle.servers.get_internal(bundle.clinic_id, server.id)
    assert internal is not None
    assert internal.headers == {}
    assert internal.server.has_headers is False


async def test_mcp_server_store_delete_server_also_removes_its_binding_rows(bundle: StoreBundle) -> None:
    """xoaServer dọn luôn dòng gán trong agent_mcp_servers"""
    server = await bundle.servers.create_server(bundle.clinic_id, name="a", url="https://x/mcp")
    await bundle.add_agent("ag1")
    await bundle.bindings.set_servers_for_agent(bundle.clinic_id, "ag1", [server.id])
    assert await bundle.servers.delete_server(bundle.clinic_id, server.id) is True
    assert await bundle.bindings.agents_of_server(bundle.clinic_id, server.id) == []


# ------------------------------------------- additions of the Python port (not in the original test file)


async def test_mcp_server_store_id_is_16_hex_chars_not_a_slug_of_the_name(bundle: StoreBundle) -> None:
    """id sinh ngẫu nhiên 16 ký tự hex, không phải slug của tên"""
    first = await bundle.servers.create_server(bundle.clinic_id, name="Notion", url="https://x/mcp")
    second = await bundle.servers.create_server(bundle.clinic_id, name="Notion", url="https://x/mcp")
    assert len(first.id) == 16
    int(first.id, 16)
    assert first.id != second.id


async def test_mcp_server_store_unknown_server_answers_false_or_none(bundle: StoreBundle) -> None:
    """server không tồn tại: update/xóa trả False, đọc trả None"""
    assert await bundle.servers.get_server(bundle.clinic_id, "khong-co") is None
    assert await bundle.servers.get_internal(bundle.clinic_id, "khong-co") is None
    assert await bundle.servers.update_server(bundle.clinic_id, "khong-co", name="x") is False
    assert await bundle.servers.clear_headers(bundle.clinic_id, "khong-co") is False
    assert await bundle.servers.delete_server(bundle.clinic_id, "khong-co") is False


async def test_mcp_server_store_status_snapshot_and_fingerprint_round_trip(bundle: StoreBundle) -> None:
    """đặt trạng thái, lưu snapshot + mốc rồi đọc lại"""
    server = await bundle.servers.create_server(bundle.clinic_id, name="a", url="https://x/mcp")
    assert await bundle.servers.get_fingerprint(bundle.clinic_id, server.id) == ""
    await bundle.servers.set_status(bundle.clinic_id, server.id, McpServerStatus.ERROR, "chết")
    await bundle.servers.save_snapshot_fingerprint(
        bundle.clinic_id, server.id, [McpToolInfo(name="t", description="d")], '{"t":"h"}'
    )
    read = await bundle.servers.get_server(bundle.clinic_id, server.id)
    assert read is not None
    assert read.status is McpServerStatus.ERROR
    assert read.error == "chết"
    assert read.tools_snapshot == [McpToolInfo(name="t", description="d")]
    assert await bundle.servers.get_fingerprint(bundle.clinic_id, server.id) == '{"t":"h"}'


async def test_mcp_server_store_a_clinic_never_sees_the_servers_of_another(bundle: StoreBundle) -> None:
    """phòng khám khác không thấy server của phòng khám này"""
    server = await bundle.servers.create_server(bundle.clinic_id, name="a", url="https://x/mcp")
    other = uuid.uuid4()
    if bundle.admin is not None:
        with bundle.admin.begin() as conn:
            conn.execute(
                text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, 'Other')"),
                {"id": other, "slug": f"o-{other.hex[:12]}"},
            )
    assert await bundle.servers.list_servers(other) == []
    assert await bundle.servers.get_server(other, server.id) is None
    assert await bundle.servers.delete_server(other, server.id) is False
    assert await bundle.servers.get_server(bundle.clinic_id, server.id) is not None


async def test_mcp_server_store_a_headers_blob_that_cannot_be_decrypted_falls_back_to_empty(
    bundle: StoreBundle,
) -> None:
    """giải mã hỏng (key đổi, dữ liệu hư) -> rơi về rỗng thay vì chết cả tiến trình"""
    if bundle.admin is None:
        pytest.skip("the stored form only exists in Postgres")
    server = await bundle.servers.create_server(
        bundle.clinic_id, name="a", url="https://x/mcp", headers={"Authorization": "Bearer k"}
    )
    with bundle.admin.begin() as conn:
        conn.execute(
            text("UPDATE agent.mcp_servers SET headers_enc = 'not-a-valid-blob' WHERE id = :i"),
            {"i": server.id},
        )
    internal = await bundle.servers.get_internal(bundle.clinic_id, server.id)
    assert internal is not None
    assert internal.headers == {}


async def test_mcp_server_store_headers_are_not_printed_by_repr(bundle: StoreBundle) -> None:
    """repr của bản nội bộ không in header (traceback/log không lộ token)"""
    server = await bundle.servers.create_server(
        bundle.clinic_id, name="a", url="https://x/mcp", headers={"Authorization": "Bearer top-secret-value"}
    )
    internal = await bundle.servers.get_internal(bundle.clinic_id, server.id)
    assert internal is not None
    assert "top-secret-value" not in repr(internal)

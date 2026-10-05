# ported from: src/mcp/mcp-schema.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Adapted to Postgres (``PORT-MAP``: "table/default-deny test, adapted to Postgres"): the tables come from the
alembic history of package A, so this checks that the migration still has what ``pema.mcp.mcp_schema`` declares.
Needs ``PEMA_TEST_DATABASE_URL`` (fixture ``pg_admin`` skips otherwise).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from pema.core.testing import ensure_test_clinic, truncate_installation_data
from pema.mcp.mcp_schema import STATUS_VALUES, agent_mcp_servers, mcp_servers

pytestmark = pytest.mark.db


@pytest.fixture
def clinic(pg_admin: Engine) -> uuid.UUID:
    with pg_admin.begin() as conn:
        clinic_id = ensure_test_clinic(conn)
        truncate_installation_data(conn)
        conn.execute(
            text("INSERT INTO agent.agents (clinic_id, id, name) VALUES (:c, 'ag', 'Agent')"),
            {"c": clinic_id},
        )
    return clinic_id


def _columns(engine: Engine, table: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'agent' AND table_name = :t"
            ),
            {"t": table},
        )
        return {r[0] for r in rows}


def test_mcp_schema_mcp_servers_table_has_all_the_columns(pg_admin: Engine) -> None:
    """tạo bảng mcp_servers đủ cột"""
    columns = _columns(pg_admin, "mcp_servers")
    for name in (
        "clinic_id",
        "id",
        "name",
        "url",
        "headers_enc",
        "enabled",
        "status",
        "error",
        "tools_snapshot",
        "fingerprint",
    ):
        assert name in columns, f"thiếu cột {name}"


def test_mcp_schema_agent_mcp_servers_table_has_a_composite_key(pg_admin: Engine) -> None:
    """tạo bảng agent_mcp_servers (khóa ghép)"""
    assert _columns(pg_admin, "agent_mcp_servers") == {"clinic_id", "agent_id", "server_id"}


def test_mcp_schema_status_accepts_only_the_four_valid_values(pg_admin: Engine, clinic: uuid.UUID) -> None:
    """trang_thai chỉ nhận 4 giá trị hợp lệ (CHECK chặn giá trị lạ)"""
    insert = text(
        "INSERT INTO agent.mcp_servers (clinic_id, id, name, url, status) VALUES (:c, :i, 'test', 'http://x', :s)"
    )
    for index, status in enumerate(STATUS_VALUES):
        with pg_admin.begin() as conn:
            conn.execute(insert, {"c": clinic, "i": f"ok-{index}", "s": status})
    with pytest.raises(IntegrityError), pg_admin.begin() as conn:
        conn.execute(insert, {"c": clinic, "i": "test-check-invalid", "s": "gia_tri_bay"})


def test_mcp_schema_agent_mcp_servers_rejects_a_duplicate_composite_key(
    pg_admin: Engine, clinic: uuid.UUID
) -> None:
    """agent_mcp_servers chặn chèn trùng khóa ghép (agent_id, server_id)"""
    with pg_admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent.mcp_servers (clinic_id, id, name, url) VALUES (:c, 'server-b', 'b', 'http://x')"
            ),
            {"c": clinic},
        )
        conn.execute(
            text(
                "INSERT INTO agent.agent_mcp_servers (clinic_id, agent_id, server_id) VALUES (:c, 'ag', 'server-b')"
            ),
            {"c": clinic},
        )
    with pytest.raises(IntegrityError), pg_admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent.agent_mcp_servers (clinic_id, agent_id, server_id) VALUES (:c, 'ag', 'server-b')"
            ),
            {"c": clinic},
        )


# ------------------------------------------- additions of the Python port (not in the original test file)


def test_mcp_schema_the_sqlalchemy_declaration_matches_the_migration(pg_admin: Engine) -> None:
    """khai báo SQLAlchemy của mcp_schema khớp bảng do migration 0002 tạo"""
    assert {c.name for c in mcp_servers.c} == _columns(pg_admin, "mcp_servers")
    assert {c.name for c in agent_mcp_servers.c} == _columns(pg_admin, "agent_mcp_servers")


def test_mcp_schema_both_tables_carry_no_row_level_security_single_tenant(pg_admin: Engine) -> None:
    """một bản cài đặt là một phòng khám: cả hai bảng không còn RLS (migration st_0009_single_tenant)"""
    with pg_admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'agent' AND c.relname IN ('mcp_servers', 'agent_mcp_servers')"
            )
        ).all()
    assert {(r[0], r[1]) for r in rows} == {("mcp_servers", False), ("agent_mcp_servers", False)}


def test_mcp_schema_deleting_an_agent_or_a_server_cascades_to_the_bindings(
    pg_admin: Engine, clinic: uuid.UUID
) -> None:
    """xóa agent hoặc server -> dòng gán biến mất (khóa ngoại ON DELETE CASCADE)"""
    with pg_admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent.mcp_servers (clinic_id, id, name, url) VALUES (:c, 's1', 'a', 'http://x')"
            ),
            {"c": clinic},
        )
        conn.execute(
            text(
                "INSERT INTO agent.agent_mcp_servers (clinic_id, agent_id, server_id) VALUES (:c, 'ag', 's1')"
            ),
            {"c": clinic},
        )
        conn.execute(text("DELETE FROM agent.mcp_servers WHERE clinic_id = :c AND id = 's1'"), {"c": clinic})
        remaining = conn.execute(
            text("SELECT count(*) FROM agent.agent_mcp_servers WHERE clinic_id = :c"), {"c": clinic}
        ).scalar_one()
    assert remaining == 0

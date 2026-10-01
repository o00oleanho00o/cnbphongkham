# ported from: src/mcp/mcp-schema.ts
"""MCP client schema: external servers and the binding of servers to agents (default-deny).

Forced deviation (SQLite -> Postgres): the original created the tables from ``taoBangMcp(db)`` at boot. Here
the DDL is in ``alembic/versions/0002_agent_schema.py`` (package A), so this module only DECLARES the two
tables for SQLAlchemy Core. What the migration changes, all in favour of the original's intent:

* ``clinic_id`` on both tables and in every key; RLS (``clinic_id = ctx.current_clinic_id()``);
* REAL foreign keys. The original said "NO FOREIGN KEY: ``database.ts`` does not enable
  ``PRAGMA foreign_keys``, so ``REFERENCES`` is an empty promise, every delete path must clean both tables
  explicitly in one transaction". Postgres enforces them with ``ON DELETE CASCADE`` (deleting an agent or a
  server removes its bindings), and the store still deletes the bindings explicitly in the same transaction,
  like the original;
* ``id`` of ``mcp_servers`` is ``secrets.token_hex(8)`` (``randomBytes(8).toString("hex")``), not a slug of
  the name, so a NEW server with the name of a deleted one can never "resurrect" old binding rows;
* ``tools_snapshot`` is ``jsonb`` (a JSON list of ``{name, description}``), ``headers_enc`` replaces
  ``headers_ma_hoa`` and ``status``/``error`` replace ``trang_thai``/``loi``. The status values keep the
  original Vietnamese strings.
"""

from __future__ import annotations

from sqlalchemy import Boolean, Column, DateTime, MetaData, Table, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB

AGENT_SCHEMA = "agent"

STATUS_VALUES: tuple[str, ...] = ("cho_ket_noi", "da_ket_noi", "loi", "can_duyet_lai")
"""The four values the ``status`` CHECK constraint accepts (``McpServerStatus``)."""

metadata = MetaData(schema=AGENT_SCHEMA)

mcp_servers = Table(
    "mcp_servers",
    metadata,
    Column("clinic_id", Uuid(as_uuid=True), primary_key=True),
    Column("id", Text, primary_key=True),
    Column("name", Text, nullable=False),
    Column("url", Text, nullable=False),
    Column("headers_enc", Text, nullable=False, server_default=""),
    Column("enabled", Boolean, nullable=False, server_default="true"),
    Column("status", Text, nullable=False, server_default="cho_ket_noi"),
    Column("error", Text, nullable=False, server_default=""),
    Column("tools_snapshot", JSONB, nullable=False, server_default="[]"),
    Column("fingerprint", Text, nullable=False, server_default=""),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

agent_mcp_servers = Table(
    "agent_mcp_servers",
    metadata,
    Column("clinic_id", Uuid(as_uuid=True), primary_key=True),
    Column("agent_id", Text, primary_key=True),
    Column("server_id", Text, primary_key=True),
)

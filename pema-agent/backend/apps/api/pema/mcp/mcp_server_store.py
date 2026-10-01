# ported from: src/mcp/mcp-server-store.ts
"""CRUD of external MCP servers plus encryption of the authentication headers. Schema in ``mcp_schema``.

Forced deviations (SQLite -> Postgres, sync -> async, one tenant -> clinics):

* module-level functions with prepared statements become ``PgMcpServerStore``: SQLAlchemy Core over
  ``ClinicDatabase``; every method takes ``clinic_id`` and runs in ``db.session(clinic_id)`` so RLS applies.
  ``McpServerStore`` is the Protocol the manager and the admin routes depend on (``InMemoryMcpStore`` in
  ``pema.mcp.testing`` is the second implementation);
* names: ``taoServer`` is ``create_server``, ``layServerNoiBo`` is ``get_internal``, ``danhSachServer`` is
  ``list_servers``, ``capNhatServer`` is ``update_server``, ``xoaHeaders`` is ``clear_headers``, ``xoaServer``
  is ``delete_server``, ``datTrangThaiServer`` is ``set_status``, ``luuSnapshotFingerprint`` is
  ``save_snapshot_fingerprint``, ``layFingerprint`` is ``get_fingerprint``. Two additions the multi-process
  deployment needs: ``get_server`` (one public row, for the routes) and ``list_internal`` (every server of a
  clinic WITH headers, one query, for the health sync);
* ``id`` is ``secrets.token_hex(8)`` like ``randomBytes(8).toString("hex")``.

Kept from the original: headers are stored encrypted and never leave through ``McpServer``/``list_servers``
(only the ``has_headers`` flag); ``headers=None`` on update KEEPS the old headers ("empty box = keep the old
key"); clearing is a separate path (``clear_headers``); a decrypt failure (key rotated, corrupt data) falls
back to empty headers instead of killing the process.
"""

from __future__ import annotations

import json
import secrets
from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, cast
from uuid import UUID

from sqlalchemy import delete, insert, select, update

from pema.config.secret_cipher import decrypt_secret, encrypt_secret
from pema.core.db import ClinicDatabase
from pema.mcp.mcp_schema import agent_mcp_servers, mcp_servers
from pema.mcp.mcp_types import McpServer, McpServerInternal, McpServerStatus, McpToolInfo


class McpServerStore(Protocol):
    async def create_server(
        self,
        clinic_id: UUID,
        *,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> McpServer: ...

    async def get_server(self, clinic_id: UUID, server_id: str) -> McpServer | None:
        """Public row (no headers) or ``None``."""
        ...

    async def get_internal(self, clinic_id: UUID, server_id: str) -> McpServerInternal | None:
        """WITH decrypted headers: only the manager that connects may call this."""
        ...

    async def list_servers(self, clinic_id: UUID) -> list[McpServer]:
        """NO headers: safe to hand to the dashboard API."""
        ...

    async def list_internal(self, clinic_id: UUID) -> list[McpServerInternal]: ...

    async def update_server(
        self,
        clinic_id: UUID,
        server_id: str,
        *,
        name: str | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> bool:
        """``headers is None`` KEEPS the old headers. Returns False when the server does not exist."""
        ...

    async def clear_headers(self, clinic_id: UUID, server_id: str) -> bool: ...

    async def delete_server(self, clinic_id: UUID, server_id: str) -> bool:
        """Also removes the bindings of the server, in the same transaction."""
        ...

    async def set_status(
        self, clinic_id: UUID, server_id: str, status: McpServerStatus, error: str = ""
    ) -> None: ...

    async def save_snapshot_fingerprint(
        self, clinic_id: UUID, server_id: str, snapshot: list[McpToolInfo], fingerprint_json: str
    ) -> None: ...

    async def get_fingerprint(self, clinic_id: UUID, server_id: str) -> str:
        """Empty when the server never connected successfully / has no drift baseline yet."""
        ...


def encrypt_headers(headers: dict[str, str] | None) -> str:
    """JSON then AES-GCM; an empty or missing mapping is stored as the empty string (``has_headers``
    False)."""
    if not headers:
        return ""
    return encrypt_secret(json.dumps(headers))


def decrypt_headers(encrypted: str) -> dict[str, str]:
    """Decrypt failure (key changed, corrupt data) falls back to empty instead of killing the process."""
    if not encrypted:
        return {}
    try:
        parsed = cast(object, json.loads(decrypt_secret(encrypted)))
    except Exception:  # key rotated, bad base64, bad JSON: never fatal
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(k): str(v) for k, v in cast(dict[object, object], parsed).items()}


def _read_snapshot(raw: object) -> list[McpToolInfo]:
    if not isinstance(raw, list):
        return []
    tools: list[McpToolInfo] = []
    for item in cast(list[object], raw):
        if isinstance(item, dict):
            entry = cast(dict[str, object], item)
            tools.append(
                McpToolInfo(name=str(entry.get("name", "")), description=str(entry.get("description", "")))
            )
    return tools


def _map_row(data: Mapping[Any, object]) -> McpServer:
    return McpServer(
        id=str(data["id"]),
        name=str(data["name"]),
        url=str(data["url"]),
        enabled=bool(data["enabled"]),
        status=McpServerStatus(str(data["status"])),
        error=str(data["error"]),
        tools_snapshot=_read_snapshot(data["tools_snapshot"]),
        has_headers=str(data["headers_enc"]) != "",
        created_at=cast(datetime, data["created_at"]),  # aware timestamptz, validated by VnDatetime
        updated_at=cast(datetime, data["updated_at"]),
    )


def _map_internal(clinic_id: UUID, data: Mapping[Any, object]) -> McpServerInternal:
    return McpServerInternal(
        clinic_id=clinic_id,
        server=_map_row(data),
        headers=decrypt_headers(str(data["headers_enc"])),
    )


class PgMcpServerStore:
    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def create_server(
        self,
        clinic_id: UUID,
        *,
        name: str,
        url: str,
        headers: dict[str, str] | None = None,
        enabled: bool = True,
    ) -> McpServer:
        server_id = secrets.token_hex(8)
        async with self._db.session(clinic_id) as session:
            row = (
                (
                    await session.execute(
                        insert(mcp_servers)
                        .values(
                            clinic_id=clinic_id,
                            id=server_id,
                            name=name,
                            url=url,
                            headers_enc=encrypt_headers(headers),
                            enabled=enabled,
                        )
                        .returning(*mcp_servers.c)
                    )
                )
                .mappings()
                .one()
            )
        # The row was just written with the id just generated: the read cannot miss.
        return _map_row(row)

    async def get_server(self, clinic_id: UUID, server_id: str) -> McpServer | None:
        async with self._db.session(clinic_id) as session:
            row = (
                (await session.execute(select(mcp_servers).where(mcp_servers.c.id == server_id)))
                .mappings()
                .one_or_none()
            )
        return _map_row(row) if row is not None else None

    async def get_internal(self, clinic_id: UUID, server_id: str) -> McpServerInternal | None:
        async with self._db.session(clinic_id) as session:
            row = (
                (await session.execute(select(mcp_servers).where(mcp_servers.c.id == server_id)))
                .mappings()
                .one_or_none()
            )
        return _map_internal(clinic_id, row) if row is not None else None

    async def list_servers(self, clinic_id: UUID) -> list[McpServer]:
        async with self._db.session(clinic_id) as session:
            rows = (
                (
                    await session.execute(
                        select(mcp_servers).order_by(mcp_servers.c.created_at, mcp_servers.c.id)
                    )
                )
                .mappings()
                .all()
            )
        return [_map_row(r) for r in rows]

    async def list_internal(self, clinic_id: UUID) -> list[McpServerInternal]:
        async with self._db.session(clinic_id) as session:
            rows = (
                (
                    await session.execute(
                        select(mcp_servers).order_by(mcp_servers.c.created_at, mcp_servers.c.id)
                    )
                )
                .mappings()
                .all()
            )
        return [_map_internal(clinic_id, r) for r in rows]

    async def update_server(
        self,
        clinic_id: UUID,
        server_id: str,
        *,
        name: str | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        enabled: bool | None = None,
    ) -> bool:
        values: dict[str, object] = {}
        if name is not None:
            values["name"] = name
        if url is not None:
            values["url"] = url
        if enabled is not None:
            values["enabled"] = enabled
        if headers is not None:
            values["headers_enc"] = encrypt_headers(headers)
        async with self._db.session(clinic_id) as session:
            if not values:
                found = await session.execute(select(mcp_servers.c.id).where(mcp_servers.c.id == server_id))
                return found.first() is not None
            result = await session.execute(
                update(mcp_servers)
                .where(mcp_servers.c.id == server_id)
                .values(**values)
                .returning(mcp_servers.c.id)
            )
            return result.first() is not None

    async def clear_headers(self, clinic_id: UUID, server_id: str) -> bool:
        async with self._db.session(clinic_id) as session:
            result = await session.execute(
                update(mcp_servers)
                .where(mcp_servers.c.id == server_id)
                .values(headers_enc="")
                .returning(mcp_servers.c.id)
            )
            return result.first() is not None

    async def delete_server(self, clinic_id: UUID, server_id: str) -> bool:
        """There is a real foreign key with ON DELETE CASCADE, but the bindings are still deleted explicitly
        in the SAME transaction, like the original ("clean both tables in one transaction")."""
        async with self._db.session(clinic_id) as session:
            await session.execute(delete(agent_mcp_servers).where(agent_mcp_servers.c.server_id == server_id))
            result = await session.execute(
                delete(mcp_servers).where(mcp_servers.c.id == server_id).returning(mcp_servers.c.id)
            )
            return result.first() is not None

    async def set_status(
        self, clinic_id: UUID, server_id: str, status: McpServerStatus, error: str = ""
    ) -> None:
        async with self._db.session(clinic_id) as session:
            await session.execute(
                update(mcp_servers)
                .where(mcp_servers.c.id == server_id)
                .values(status=status.value, error=error)
            )

    async def save_snapshot_fingerprint(
        self, clinic_id: UUID, server_id: str, snapshot: list[McpToolInfo], fingerprint_json: str
    ) -> None:
        async with self._db.session(clinic_id) as session:
            await session.execute(
                update(mcp_servers)
                .where(mcp_servers.c.id == server_id)
                .values(
                    tools_snapshot=[t.model_dump(mode="json") for t in snapshot],
                    fingerprint=fingerprint_json,
                )
            )

    async def get_fingerprint(self, clinic_id: UUID, server_id: str) -> str:
        async with self._db.session(clinic_id) as session:
            value = (
                await session.execute(select(mcp_servers.c.fingerprint).where(mcp_servers.c.id == server_id))
            ).scalar_one_or_none()
        return value or ""

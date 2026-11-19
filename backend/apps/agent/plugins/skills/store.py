"""Where the items and their versions are kept: Postgres (the plugin's own ``sk_`` tables, scoped by tenant
and agent) or process memory (tests, an agent run without a database).

Every save writes a new version with the whole item, in the same transaction; going back to an older version
is a save of its text, so the history only grows."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import Text

from .models import Item, Version


class NameTakenError(ValueError):
    """Another item of the same kind has this name."""


class ItemStore(Protocol):
    async def list(self, *, kind: str | None = None, status: str | None = None) -> list[Item]: ...

    async def get(self, item_id: str) -> Item | None: ...

    async def save(self, item: Item, *, by: str, reason: str = "") -> Item:
        """Creates the item (its ``id`` is new) or replaces it; returns it with its new version. Raises
        ``NameTakenError`` when another item of the kind has the name."""
        ...

    async def versions(self, item_id: str) -> list[Version]: ...


class InMemoryItemStore:
    def __init__(self, clock: Callable[[], datetime] | None = None) -> None:
        self._items: dict[str, Item] = {}
        self._versions: dict[str, list[Version]] = {}
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list(self, *, kind: str | None = None, status: str | None = None) -> list[Item]:
        found = [
            replace(i)
            for i in self._items.values()
            if (kind is None or i.kind == kind) and (status is None or i.status == status)
        ]
        return sorted(found, key=lambda i: (i.kind, i.name))

    async def get(self, item_id: str) -> Item | None:
        found = self._items.get(item_id)
        return None if found is None else replace(found)

    async def save(self, item: Item, *, by: str, reason: str = "") -> Item:
        if any(o.id != item.id and o.kind == item.kind and o.name == item.name for o in self._items.values()):
            raise NameTakenError(f"there is a {item.kind} named {item.name!r} already")
        now = self._clock()
        old = self._items.get(item.id)
        saved = replace(
            item,
            version=1 if old is None else old.version + 1,
            updated_by=by,
            created_at=item.created_at or (old.created_at if old else now),
            updated_at=now,
        )
        self._items[saved.id] = saved
        self._versions.setdefault(saved.id, []).append(
            Version(saved.id, saved.version, saved.snapshot(), by, reason, now)
        )
        return replace(saved)

    async def versions(self, item_id: str) -> list[Version]:
        return sorted(self._versions.get(item_id, []), key=lambda v: v.version, reverse=True)


_LIST = text(
    "SELECT id, kind, name, description, body, status, origin, scopes, meta, usage, version, updated_by, "
    "created_at, updated_at FROM agent_rt.sk_item WHERE tenant_id = :tenant_id AND agent = :agent "
    "AND (CAST(:kind AS text) IS NULL OR kind = :kind) "
    "AND (CAST(:status AS text) IS NULL OR status = :status) ORDER BY kind, name"
)
_GET = text(
    "SELECT id, kind, name, description, body, status, origin, scopes, meta, usage, version, updated_by, "
    "created_at, updated_at FROM agent_rt.sk_item "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND id = :id"
)
_TAKEN = text(
    "SELECT 1 FROM agent_rt.sk_item WHERE tenant_id = :tenant_id AND agent = :agent AND kind = :kind "
    "AND name = :name AND id <> :id"
)
_UPSERT = text(
    "INSERT INTO agent_rt.sk_item (tenant_id, agent, id, kind, name, description, body, status, origin, "
    "scopes, meta, usage, updated_by) "
    "VALUES (:tenant_id, :agent, :id, :kind, :name, :description, :body, :status, :origin, :scopes, "
    "CAST(:meta AS jsonb), CAST(:usage AS jsonb), :by) "
    "ON CONFLICT (tenant_id, agent, id) DO UPDATE SET kind = EXCLUDED.kind, name = EXCLUDED.name, "
    "description = EXCLUDED.description, body = EXCLUDED.body, status = EXCLUDED.status, "
    "scopes = EXCLUDED.scopes, meta = EXCLUDED.meta, updated_by = EXCLUDED.updated_by, "
    "version = agent_rt.sk_item.version + 1, updated_at = now() "
    "RETURNING version, created_at, updated_at"
).bindparams(bindparam("scopes", type_=ARRAY(Text)))
_ADD_VERSION = text(
    "INSERT INTO agent_rt.sk_item_version (tenant_id, agent, item_id, version, snapshot, changed_by, reason) "
    "VALUES (:tenant_id, :agent, :id, :version, CAST(:snapshot AS jsonb), :by, :reason)"
)
_VERSIONS = text(
    "SELECT item_id, version, snapshot, changed_by, reason, created_at FROM agent_rt.sk_item_version "
    "WHERE tenant_id = :tenant_id AND agent = :agent AND item_id = :id ORDER BY version DESC"
)


class PostgresItemStore:
    def __init__(self, engine: AsyncEngine, *, tenant_id: str, agent: str) -> None:
        self._engine = engine
        self._scope = {"tenant_id": tenant_id, "agent": agent}

    async def list(self, *, kind: str | None = None, status: str | None = None) -> list[Item]:
        params = {**self._scope, "kind": kind, "status": status}
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_LIST, params)).mappings().all()
        return [_item(row) for row in rows]

    async def get(self, item_id: str) -> Item | None:
        async with self._engine.connect() as conn:
            row = (await conn.execute(_GET, {**self._scope, "id": item_id})).mappings().one_or_none()
        return None if row is None else _item(row)

    async def save(self, item: Item, *, by: str, reason: str = "") -> Item:
        params = {
            **self._scope,
            "id": item.id,
            "kind": item.kind,
            "name": item.name,
            "description": item.description,
            "body": item.body,
            "status": item.status,
            "origin": item.origin,
            "scopes": list(item.scopes),
            "meta": json.dumps(item.meta, ensure_ascii=False),
            "usage": json.dumps(item.usage, ensure_ascii=False),
            "by": by,
        }
        async with self._engine.begin() as conn:
            if (await conn.execute(_TAKEN, params)).first() is not None:
                raise NameTakenError(f"there is a {item.kind} named {item.name!r} already")
            row = (await conn.execute(_UPSERT, params)).mappings().one()
            saved = replace(
                item,
                version=row["version"],
                updated_by=by,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            version = {
                **self._scope,
                "id": saved.id,
                "version": saved.version,
                "snapshot": json.dumps(saved.snapshot(), ensure_ascii=False),
                "by": by,
                "reason": reason,
            }
            await conn.execute(_ADD_VERSION, version)
        return saved

    async def versions(self, item_id: str) -> list[Version]:
        async with self._engine.connect() as conn:
            rows = (await conn.execute(_VERSIONS, {**self._scope, "id": item_id})).mappings().all()
        return [
            Version(
                row["item_id"],
                row["version"],
                _mapping(row["snapshot"]),
                row["changed_by"],
                row["reason"],
                row["created_at"],
            )
            for row in rows
        ]


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def _item(row: Any) -> Item:
    return Item(
        id=row["id"],
        kind=row["kind"],
        name=row["name"],
        description=row["description"],
        body=row["body"],
        status=row["status"],
        origin=row["origin"],
        scopes=list(row["scopes"]),
        meta=_mapping(row["meta"]),
        usage=_mapping(row["usage"]),
        version=row["version"],
        updated_by=row["updated_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )

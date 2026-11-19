"""What the skills plugin keeps: items (a skill, a set of rules or a persona text) with the scopes they are
bound to, and the versions each change leaves behind."""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final, Literal

Kind = Literal["skill", "rules", "persona"]
Status = Literal["draft", "active", "archived"]
Origin = Literal["admin", "plugin", "agent"]

KINDS: Final = ("skill", "rules", "persona")
STATUSES: Final = ("draft", "active", "archived")


def new_id() -> str:
    return f"itm-{secrets.token_hex(6)}"


@dataclass(slots=True)
class Item:
    id: str
    kind: Kind
    name: str
    description: str
    """One line: for a skill when to use it (it is in the index), for rules and persona what they are."""
    body: str
    status: Status = "active"
    origin: Origin = "admin"
    scopes: list[str] = field(default_factory=list[str])
    """``agent``, ``plugin:<name>`` or ``channel:<name>``; none means the whole agent."""
    meta: dict[str, Any] = field(default_factory=dict[str, Any])
    usage: dict[str, Any] = field(default_factory=dict[str, Any])
    version: int = 1
    updated_by: str = ""
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def snapshot(self) -> dict[str, Any]:
        """What a version keeps: everything a person can change."""
        return {
            "kind": self.kind,
            "name": self.name,
            "description": self.description,
            "body": self.body,
            "status": self.status,
            "scopes": list(self.scopes),
            "meta": dict(self.meta),
        }

    def shown(self) -> dict[str, Any]:
        return {
            "id": self.id,
            **self.snapshot(),
            "origin": self.origin,
            "usage": dict(self.usage),
            "version": self.version,
            "updated_by": self.updated_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


@dataclass(frozen=True, slots=True)
class Version:
    item_id: str
    version: int
    snapshot: dict[str, Any]
    changed_by: str
    reason: str
    created_at: datetime

    def shown(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "snapshot": self.snapshot,
            "changed_by": self.changed_by,
            "reason": self.reason,
            "created_at": self.created_at.isoformat(),
        }

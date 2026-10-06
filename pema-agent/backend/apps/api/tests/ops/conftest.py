"""Fixtures of the package-O tests. The database fixtures live in ``pema.api.clinic_testing`` (shared with
``tests/clinic``); the helpers below arrange raw state as the superuser (never used by the code under test)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import (
    admin,
    app,
    client_factory,
    db,
    demo_clock,
    jwt_env,
    pg_url,
    worker_db,
    world,
)
from pema.clinic.actions.seed_demo import SeedResult
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType, Role

__all__ = [
    "add_account",
    "admin",
    "app",
    "client_factory",
    "db",
    "demo_clock",
    "jwt_env",
    "pg_url",
    "set_channel",
    "staff_ctx",
    "worker_db",
    "world",
]

AddAccount = Callable[..., str]


@pytest.fixture
def add_account(admin: Engine, world: SeedResult) -> AddAccount:
    """``add_account("long", channel="zalo_personal", purpose="customer", ...)`` inserts a channel account (and the
    default agent it needs) and returns its id. Extra keyword arguments are column values."""

    def make(
        account_id: str, *, channel: str = "zalo_personal", purpose: str = "customer", **columns: Any
    ) -> str:
        with admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO agent.agents (clinic_id, id, name, is_default) "
                    "VALUES (:c, 'default', 'Trợ lý mặc định (mẫu)', true) ON CONFLICT DO NOTHING"
                ),
                {"c": world.clinic_id},
            )
            values: dict[str, Any] = {
                "clinic_id": world.clinic_id,
                "id": account_id,
                "label": columns.pop("label", f"Danh tính {account_id}"),
                "channel": channel,
                "agent_id": "default",
                "purpose": purpose,
                **columns,
            }
            names = ", ".join(values)
            marks = ", ".join(f":{name}" for name in values)
            conn.execute(text(f"INSERT INTO agent.accounts ({names}) VALUES ({marks})"), values)  # noqa: S608  - test keys
        return account_id

    return make


StaffCtx = Callable[[str], ActionContext]
SetChannel = Callable[..., None]

_ROLES: dict[str, Role] = {
    "owner": Role.OWNER,
    "manager": Role.MANAGER,
    "doctor.mai": Role.DOCTOR,
    "doctor.an": Role.DOCTOR,
    "cs.maianh": Role.CS_STAFF,
    "cs.thu": Role.CS_STAFF,
    "reception.lan": Role.RECEPTION,
    "accountant.hoa": Role.ACCOUNTANT,
}


@pytest.fixture
def staff_ctx(world: SeedResult) -> StaffCtx:
    """``staff_ctx("manager")``: the action context of a seeded user (the role follows the seed)."""

    def make(key: str) -> ActionContext:
        return ActionContext(
            clinic_id=world.clinic_id,
            actor_type=ActorType.USER,
            actor_user_id=world.users[key],
            actor_role=_ROLES[key],
        )

    return make


@pytest.fixture
def set_channel(admin: Engine, world: SeedResult) -> SetChannel:
    """``set_channel("zalo_personal", gap_min=3, gap_max=9, daily_cap=50)``: the one row per channel."""

    def make(channel: str, *, gap_min: int = 0, gap_max: int = 0, daily_cap: int | None = None) -> None:
        with admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.channel_setting (clinic_id, channel, enabled, min_gap_seconds, "
                    "max_gap_seconds, daily_cap) VALUES (:c, :ch, true, :lo, :hi, :cap) "
                    "ON CONFLICT (clinic_id, channel) DO UPDATE SET min_gap_seconds = :lo, "
                    "max_gap_seconds = :hi, daily_cap = :cap"
                ),
                {"c": world.clinic_id, "ch": channel, "lo": gap_min, "hi": gap_max, "cap": daily_cap},
            )

    return make

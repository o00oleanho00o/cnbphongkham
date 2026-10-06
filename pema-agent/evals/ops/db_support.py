"""Helpers for the DB-backed parts of the ops eval (load run, race suite, security tests). New module.

Plain functions over the throwaway Postgres: arranging raw state goes through the superuser engine (never used
by the code under test), the code under test runs as the ``be_app`` role through ``ClinicDatabase``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import record_inbound
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType, Role

EXTRA_OPERATOR = "cs.extra"
OPERATOR_KEYS = ("owner", "manager", "cs.maianh", "cs.thu", EXTRA_OPERATOR)
"""The five operators of the load run: no doctor, because a doctor only sees the conversations of patients in
their own scope and an unlinked customer's thread is a 404 for them (SEC-63 a); the fifth is a CS user that
``ensure_operators`` adds to the seed."""
NON_OPERATOR_KEYS = ("reception.lan", "accountant.hoa")

ROLES: dict[str, Role] = {
    "owner": Role.OWNER,
    "manager": Role.MANAGER,
    "doctor.mai": Role.DOCTOR,
    "doctor.an": Role.DOCTOR,
    "cs.maianh": Role.CS_STAFF,
    "cs.thu": Role.CS_STAFF,
    "reception.lan": Role.RECEPTION,
    "accountant.hoa": Role.ACCOUNTANT,
    EXTRA_OPERATOR: Role.CS_STAFF,
}

DEFAULT_IDENTITY = "long"


def staff_context(world: SeedResult, key: str, *, idempotency_key: str | None = None) -> ActionContext:
    """The action context of a seeded user (the role follows the seed)."""
    return ActionContext(
        clinic_id=world.clinic_id,
        actor_type=ActorType.USER,
        actor_user_id=world.users[key],
        actor_role=ROLES[key],
        idempotency_key=idempotency_key,
    )


def insert_account(
    admin: Engine,
    world: SeedResult,
    account_id: str,
    *,
    channel: str = "zalo_personal",
    purpose: str = "customer",
    **columns: Any,
) -> str:
    """Insert a channel account (and the default agent it needs); extra keywords are column values."""
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
        conn.execute(text(f"INSERT INTO agent.accounts ({names}) VALUES ({marks})"), values)  # noqa: S608  - eval keys
    return account_id


async def new_threads(
    db: ClinicDatabase,
    admin: Engine,
    world: SeedResult,
    count: int,
    *,
    account: str | None = DEFAULT_IDENTITY,
) -> list[UUID]:
    """``count`` conversations of distinct synthetic customers, each with one inbound message, tied to
    ``account`` (the O1 column; the inbound path of the tests writes the old bot account)."""
    ids: list[UUID] = []
    for _ in range(count):
        ref = await record_inbound(
            db, world, uid=f"stranger-{uuid4().hex[:10]}", text="Em muốn hỏi về lịch hẹn (tin mẫu)"
        )
        ids.append(ref.conversation_id)
    if account is not None and ids:
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE clinic.conversation SET account_id = :a WHERE id = ANY(:ids)"),
                {"a": account, "ids": ids},
            )
    return ids


def ensure_operators(admin: Engine, world: SeedResult) -> None:
    """Add the fifth operator (a CS user, synthetic) to the seed once; ``world.users`` then knows it."""
    if EXTRA_OPERATOR in world.users:
        return
    user_id = uuid4()
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.user_account (id, clinic_id, email, display_name, role, active) "
                "VALUES (:id, :c, 'cs.extra@example.test', 'CSKH Thêm (mẫu)', 'cs_staff', true)"
            ),
            {"id": user_id, "c": world.clinic_id},
        )
    world.users[EXTRA_OPERATOR] = user_id

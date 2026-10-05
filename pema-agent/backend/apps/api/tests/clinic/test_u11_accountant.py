# new tests (package U, step U11; the old web's `accountant` account: "Đối soát & thu ngân")
"""The seventh role. The pure half checks the permission matrix in both directions (allow and deny), the
exclusion from ``ASSIGNABLE_ROLES`` and that nobody but the doctor and the owner approves an order. The HTTP half
(needs ``PEMA_TEST_DATABASE_URL``, skipped otherwise) walks an accountant through the finance month, the cashier and
the routes it must not reach, and checks the audit row of a close."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from pema.api.clinic_testing import API_INI, BE_PASSWORD, WORKER_PASSWORD, ClientFactory
from pema.clinic.actions import catalog
from pema.clinic.actions.seed_demo import DEMO_DAY, SeedResult
from pema.clinic.domain.orders import parse_catalog_rows
from pema.clinic.rbac import ASSIGNABLE_ROLES, ROLE_PERMISSIONS, has_permission, require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import STAFF_ROLES, ActorType, Permission, Role

P = Permission
ACCOUNTANT = ROLE_PERMISSIONS[Role.ACCOUNTANT]
CATALOG_JSON = Path(__file__).resolve().parents[6] / "prototype" / "shared" / "product-catalog.json"
F = "/api/v1/finance"
ORDERS = "/api/v1/orders"
MONTH = f"{DEMO_DAY.year:04d}-{DEMO_DAY.month:02d}"
LAST_MONTH = "2026-08"
KEY = "accountant.hoa"


def _ctx(role: Role) -> ActionContext:
    return ActionContext(clinic_id=uuid4(), actor_type=ActorType.USER, actor_user_id=uuid4(), actor_role=role)


# ----------------------------------------------------------------------------------------------- the matrix
def test_the_accountant_is_a_staff_role_and_the_seventh_role() -> None:
    assert Role.ACCOUNTANT in STAFF_ROLES
    assert Role.ACCOUNTANT.value == "accountant"
    assert len(Role) == 7


@pytest.mark.parametrize(
    "permission",
    [
        P.FINANCE_READ,
        P.FINANCE_WRITE,
        P.FINANCE_PERIOD_CLOSE,
        P.FINANCE_COLLECT,
        P.ORDER_READ,
        P.ORDER_WRITE,
        P.PATIENT_READ,
        P.CONSENT_READ,
        P.KB_READ,
    ],
)
def test_the_accountant_holds_the_billing_side(permission: Permission) -> None:
    assert permission in ACCOUNTANT
    require(_ctx(Role.ACCOUNTANT), permission)


@pytest.mark.parametrize(
    "permission",
    [
        P.ORDER_APPROVE,  # safety: the doctor signs an order, a prescription is a clinical act
        P.SESSION_WRITE,
        P.SESSION_READ,
        P.MEDIA_WRITE,
        P.MEDIA_READ,
        P.PATIENT_READ_360,
        P.PATIENT_WRITE,
        P.CONSENT_WRITE,
        P.APPOINTMENT_READ,
        P.APPOINTMENT_WRITE,
        P.REVIEW_DECIDE_CLINICAL,
        P.CRM_TASK_READ,
        P.CRM_TASK_RESOLVE,
        P.CONVERSATION_READ,
        P.CONVERSATION_REPLY,
        P.FINANCE_READ_OWN,
        P.FINANCE_NOTIFICATIONS,
        P.ADMIN_USERS,
        P.ADMIN_USERS_READ,
        P.ADMIN_RULES,
        P.ADMIN_ACCOUNTS,
        P.AGENT_SUBMIT,
    ],
)
def test_the_accountant_is_denied_everything_clinical_crm_and_admin(permission: Permission) -> None:
    assert permission not in ACCOUNTANT
    assert not has_permission(_ctx(Role.ACCOUNTANT), permission)
    with pytest.raises(DomainError) as caught:
        require(_ctx(Role.ACCOUNTANT), permission)
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert caught.value.http_status == 403


def test_only_the_doctor_and_the_owner_hold_order_approve() -> None:
    holders = {role for role, perms in ROLE_PERMISSIONS.items() if P.ORDER_APPROVE in perms}
    assert holders == {Role.DOCTOR, Role.OWNER}


def test_the_period_close_belongs_to_the_accountant_with_owner_and_manager_as_override() -> None:
    holders = {role for role, perms in ROLE_PERMISSIONS.items() if P.FINANCE_PERIOD_CLOSE in perms}
    assert holders == {Role.ACCOUNTANT, Role.OWNER, Role.MANAGER}


def test_the_accountant_is_not_assignable() -> None:
    """No Inbox, no CRM queue: an item handed to the accountant would sit unseen."""
    assert frozenset({Role.OWNER, Role.MANAGER, Role.DOCTOR, Role.CS_STAFF}) == ASSIGNABLE_ROLES
    assert Role.ACCOUNTANT not in ASSIGNABLE_ROLES


# ---------------------------------------------------------------------------------------------------- HTTP
@pytest.mark.db
async def test_me_lists_the_accountant_permissions(client_factory: ClientFactory, world: SeedResult) -> None:
    accountant = await client_factory(KEY)
    me = (await accountant.get("/api/v1/me")).json()
    assert me["user"]["role"] == "accountant"
    assert set(me["permissions"]) == {permission.value for permission in ACCOUNTANT}


@pytest.mark.db
async def test_the_accountant_cannot_reach_inbox_crm_staff_or_the_owners_notifications(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    accountant = await client_factory(KEY)
    for path in (
        "/api/v1/conversations",
        "/api/v1/crm/tasks",
        "/api/v1/admin/users",
        f"{F}/notifications",
        "/api/v1/appointments",
    ):
        assert (await accountant.get(path)).status_code == 403, path
    assert (await accountant.post("/api/v1/admin/users", json={})).status_code in {403, 422}
    assert (await accountant.get(f"{F}/overview", params={"month": MONTH})).status_code == 200


def _entry_body(world: SeedResult, service_id: str, day: str) -> dict[str, Any]:
    return {
        "patient_id": str(world.patients["P025"]),
        "service_id": service_id,
        "entry_date": day,
        "list_vnd": 2_500_000,
        "discount_vnd": 100_000,
        "note": "Đã hoàn tất (mẫu)",
        "people": [
            {"doctor_id": str(world.users["owner"]), "share_bp": 7000, "rate_bp": 1500},
            {"doctor_id": str(world.users["doctor.mai"]), "share_bp": 3000, "rate_bp": 500},
        ],
    }


@pytest.mark.db
async def test_the_accountant_collects_and_closes_a_month_and_the_audit_names_it(
    client_factory: ClientFactory, db: ClinicDatabase, world: SeedResult
) -> None:
    accountant = await client_factory(KEY)
    services = (await accountant.get("/api/v1/services")).json()
    service = next(s["id"] for s in services if s["code"] == "laser-co2")
    created = await accountant.post(f"{F}/entries", json=_entry_body(world, service, "2026-08-10"))
    assert created.status_code == 201, created.text
    entry = created.json()

    receipt = {"id": "u11-receipt-0001", "invoice_id": entry["invoice_id"], "amount_vnd": 500_000}
    collected = await accountant.post(f"{F}/payments", json={**receipt, "method": "cash"})
    assert collected.status_code == 201, collected.text  # finance.collect

    assert (await accountant.post(f"{F}/entries/{entry['id']}/approve")).status_code == 200
    closed = await accountant.post(f"{F}/periods/{LAST_MONTH}/close")
    assert closed.status_code == 200, closed.text  # finance_period.close
    assert closed.json()["status"] == "closed"

    async with db.session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT actor_role, actor_user_id, entity_id FROM clinic.audit_log "
                    "WHERE action = 'finance.period.close' AND entity_id = :month"
                ),
                {"month": LAST_MONTH},
            )
        ).one()
    assert row.actor_role == "accountant"
    assert row.actor_user_id == world.users[KEY]


@pytest.mark.db
async def test_owner_and_manager_may_close_and_everyone_else_may_not(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    for key in ("reception.lan", "doctor.mai", "cs.maianh"):
        client = await client_factory(key)
        assert (await client.post(f"{F}/periods/{LAST_MONTH}/close")).status_code == 403, key
    # the override: owner and manager reach the action (the month has no data, so the answer is 409 or 422)
    for key in ("owner", "manager"):
        client = await client_factory(key)
        assert (await client.post(f"{F}/periods/{LAST_MONTH}/close")).status_code != 403, key


@pytest.mark.db
async def test_the_accountant_raises_a_draft_order_but_cannot_approve_it(
    client_factory: ClientFactory, db: ClinicDatabase, world: SeedResult
) -> None:
    if not CATALOG_JSON.exists():
        pytest.skip("prototype catalog not in this checkout")
    system = ActionContext(
        clinic_id=world.clinic_id,
        actor_type=ActorType.SYSTEM,
        source=ActionSource.SYSTEM,
        request_id="test-u11-catalog",
    )
    rows = parse_catalog_rows(json.loads(CATALOG_JSON.read_text(encoding="utf-8")))
    await catalog.import_catalog(db, system, rows, source_name="product-catalog.json")
    accountant = await client_factory(KEY)
    code = "H002"
    draft = {
        "patient_id": str(world.patients["P025"]),
        "diagnosis": "Nám · tăng sắc tố (mẫu)",
        "items": [{"product_code": code, "quantity": 1, "usage": "Bôi lớp mỏng, sáng và tối (mẫu)"}],
    }
    created = await accountant.post(ORDERS, json=draft)
    assert created.status_code == 201, created.text
    order = created.json()
    refused = await accountant.post(f"{ORDERS}/{order['id']}/approve", json={"version": order["version"]})
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "forbidden"
    assert "order.approve" in refused.text


@pytest.mark.db
def test_a_downgrade_through_the_role_migration_keeps_an_existing_accountant(
    pg_url: str, world: SeedResult
) -> None:
    """Narrowing the role CHECKs would fail (and lose or change data) while an accountant exists, so the
    downgrade keeps them wide: the account, its role and the audit trail survive a round trip."""
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = pg_url
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    config = Config(str(API_INI))
    engine = create_engine(pg_url)
    query = text("SELECT role FROM clinic.user_account WHERE id = :id")
    try:
        with engine.connect() as conn:
            assert conn.execute(query, {"id": world.users[KEY]}).scalar() == "accountant"
        command.downgrade(config, "u6_0010_finance")
        with engine.connect() as conn:
            assert conn.execute(query, {"id": world.users[KEY]}).scalar() == "accountant"
        command.upgrade(config, "heads")
        with engine.connect() as conn:
            assert conn.execute(query, {"id": world.users[KEY]}).scalar() == "accountant"
    finally:
        engine.dispose()

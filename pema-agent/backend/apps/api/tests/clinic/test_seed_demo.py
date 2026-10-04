# ruff: noqa: PT018
"""The demo seed: synthetic, idempotent, complete."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ACCOUNT_PASSWORD
from pema.clinic.actions.seed_demo import CASES, USERS, SeedResult, seed_demo
from pema.core.db import ClinicDatabase
from pema_contracts.roles import Role

pytestmark = pytest.mark.db


async def test_the_seed_is_idempotent_and_returns_stable_ids(db: ClinicDatabase, world_a: SeedResult) -> None:
    again = await seed_demo(db, password=ACCOUNT_PASSWORD, slug="clinic-a")
    assert again.created is False
    assert again.clinic_id == world_a.clinic_id
    assert again.users == world_a.users
    assert again.patients == world_a.patients
    assert again.conversation_id == world_a.conversation_id


async def test_the_seed_creates_every_role_the_cases_and_the_inbox(
    world_a: SeedResult, admin: Engine
) -> None:
    assert {role for _, _, role in USERS} >= {
        Role.OWNER,
        Role.MANAGER,
        Role.DOCTOR,
        Role.CS_STAFF,
        Role.RECEPTION,
    }
    with admin.connect() as conn:
        roles = {
            r[0]
            for r in conn.execute(
                text("SELECT role FROM clinic.user_account WHERE clinic_id = :c"), {"c": world_a.clinic_id}
            )
        }
        codes = {
            r[0]
            for r in conn.execute(
                text("SELECT code FROM clinic.patient WHERE clinic_id = :c"), {"c": world_a.clinic_id}
            )
        }
        pending = conn.execute(
            text("SELECT count(*) FROM clinic.review_item WHERE clinic_id = :c AND status = 'pending'"),
            {"c": world_a.clinic_id},
        ).scalar_one()
        approved = conn.execute(
            text(
                "SELECT count(*) FROM clinic.message_template WHERE clinic_id = :c AND active AND approved_at IS NOT NULL"
            ),
            {"c": world_a.clinic_id},
        ).scalar_one()
    assert {"owner", "manager", "doctor", "cs_staff", "reception"} <= roles
    assert {code for code, *_ in CASES} <= codes
    assert pending >= 2
    assert approved >= 1


async def test_everything_in_the_seed_is_visibly_synthetic(world_a: SeedResult, admin: Engine) -> None:
    """Dữ liệu hư cấu: không số điện thoại thật, không địa chỉ thật, không email thật"""
    with admin.connect() as conn:
        phones = [
            r[0]
            for r in conn.execute(
                text("SELECT phone FROM clinic.patient WHERE clinic_id = :c AND phone IS NOT NULL"),
                {"c": world_a.clinic_id},
            )
        ]
        emails = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT email FROM clinic.user_account WHERE clinic_id = :c AND email LIKE '%@example.test'"
                ),
                {"c": world_a.clinic_id},
            )
        ]
        names = [
            r[0]
            for r in conn.execute(
                text(
                    "SELECT full_name FROM clinic.patient WHERE clinic_id = :c AND code LIKE 'P0%' AND code IN ('P025','P026','P027','P028','P029','P030','P031','P032')"
                ),
                {"c": world_a.clinic_id},
            )
        ]
    assert phones and all(p.startswith("0000000") for p in phones if p.startswith("0")), phones
    assert len(emails) >= len(USERS)
    assert all("mẫu" in n for n in names)


async def test_the_seed_never_stores_the_clear_password(world_a: SeedResult, admin: Engine) -> None:
    with admin.connect() as conn:
        hashes = [
            r[0]
            for r in conn.execute(
                text("SELECT password_hash FROM clinic.user_account WHERE clinic_id = :c"),
                {"c": world_a.clinic_id},
            )
        ]
    assert hashes
    assert all(h is None or (ACCOUNT_PASSWORD not in h and h.startswith("$argon2id$")) for h in hashes)

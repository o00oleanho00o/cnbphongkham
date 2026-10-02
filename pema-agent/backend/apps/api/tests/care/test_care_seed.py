"""Dev seed of package M (step M1). New tests (no zalo-agent original). Needs ``PEMA_TEST_DATABASE_URL``."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text

from pema.care.seed import FIXTURE_ON_CALL_NUMBER, seed_care_dev
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db


def _count(admin: Engine, sql: str) -> int:
    with admin.connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


async def test_the_seed_adds_three_staff_one_fixture_on_call_number_and_two_paired_patients(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    result = await seed_care_dev(db, users=world.users, patients=world.patients)
    assert len(result.staff_profiles) == 3
    assert set(result.care_agents) == {"P025", "P026"}
    assert _count(admin, "SELECT count(*) FROM clinic.staff_profiles") == 3
    assert _count(admin, "SELECT count(DISTINCT skills) FROM clinic.staff_profiles") == 3  # different skills
    assert _count(admin, "SELECT count(*) FROM agent.care_agents") == 2
    assert _count(admin, "SELECT count(*) FROM clinic.patient_ownership") == 2
    with admin.connect() as conn:
        on_call = conn.execute(
            text("SELECT zalo_number, is_fixture, active FROM clinic.on_call_contacts")
        ).all()
    assert [(r.zalo_number, r.is_fixture, r.active) for r in on_call] == [
        (FIXTURE_ON_CALL_NUMBER, True, True)
    ]


async def test_the_seed_is_idempotent(db: ClinicDatabase, world: SeedResult, admin: Engine) -> None:
    first = await seed_care_dev(db, users=world.users, patients=world.patients)
    second = await seed_care_dev(db, users=world.users, patients=world.patients)
    assert first == second
    assert _count(admin, "SELECT count(*) FROM clinic.staff_profiles") == 3
    assert _count(admin, "SELECT count(*) FROM clinic.on_call_contacts") == 1
    assert _count(admin, "SELECT count(*) FROM agent.care_agents") == 2
    assert _count(admin, "SELECT count(*) FROM clinic.patient_ownership") == 2


async def test_every_seeded_number_is_a_flagged_fixture(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await seed_care_dev(db, users=world.users, patients=world.patients)
    assert _count(admin, "SELECT count(*) FROM clinic.on_call_contacts WHERE NOT is_fixture") == 0

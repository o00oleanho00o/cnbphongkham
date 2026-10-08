"""One installation is ONE clinic (single tenant): replaces the RLS isolation tests of the multi-clinic version.

The database holds exactly one clinic row, the worker role reaches clinic data only through the
``clinic_agent`` views, and an id that does not exist answers 404 through the API.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase, get_installation_clinic_id

pytestmark = pytest.mark.db


async def test_the_database_holds_exactly_one_clinic_and_a_second_one_is_refused(
    world: SeedResult, admin: Engine
) -> None:
    with admin.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM clinic.clinic")).scalar_one() == 1
        assert conn.execute(text("SELECT id FROM clinic.clinic")).scalar_one() == world.clinic_id
    with pytest.raises(DBAPIError), admin.begin() as conn:
        conn.execute(
            text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:i, 'second', 'Second')"), {"i": uuid4()}
        )


async def test_the_installation_id_is_the_id_of_the_seeded_clinic(
    db: ClinicDatabase, world: SeedResult
) -> None:
    assert await get_installation_clinic_id(db) == world.clinic_id


async def test_the_worker_role_reads_clinic_data_only_through_the_views(
    worker_db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    with admin.connect() as conn:
        patients = conn.execute(text("SELECT count(*) FROM clinic.patient")).scalar_one()
    async with worker_db.session() as session:
        assert await session.scalar(text("SELECT count(*) FROM clinic_agent.patient_ref")) == patients
    with pytest.raises(DBAPIError):
        async with worker_db.session() as session:
            await session.execute(text("SELECT count(*) FROM clinic.patient"))


async def test_ids_that_do_not_exist_answer_404_through_the_api(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory("owner")
    unknown = uuid4()
    for path in (
        f"/patients/{unknown}",
        f"/patients/{unknown}/360",
        f"/patients/{unknown}/consents",
        f"/conversations/{unknown}",
        f"/conversations/{unknown}/messages",
    ):
        response = await owner.get(f"/api/v1{path}")
        assert response.status_code == 404, path
        assert response.json()["error"]["code"] == "not_found"
    approve = await owner.post(f"/api/v1/review-items/{unknown}/approve", json={"version": 1})
    assert approve.status_code == 404

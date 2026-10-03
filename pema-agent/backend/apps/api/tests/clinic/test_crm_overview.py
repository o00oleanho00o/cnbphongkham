# ported from: prototype/shared/crm-automation.js (profile, metrics.segments) and crm-ui.js (segment, protocol)
"""Customer groups and the read-only rule list of the CRM workspace (package U, step U7).

The eight demo cases of ``seed_demo`` (the CRM01 stories P025..P032) fix every expected number: all eight have a
completed session, so nobody is ``new``; P027 and P029 are at risk; P030 and P031 are dormant.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions.seed_demo import SeedResult
from pema_contracts.crm import RuleKey

pytestmark = pytest.mark.db

OWNER, MANAGER, DOCTOR, CS, RECEPTION = "owner", "manager", "doctor.mai", "cs.maianh", "reception.lan"


def counts(body: dict[str, Any]) -> dict[str, int]:
    return {str(s["key"]): int(s["count"]) for s in body["segments"]}


async def test_the_groups_count_the_eight_demo_cases(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    cs = await client_factory(CS)
    response = await cs.get("/api/v1/crm/segments")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_patients"] == 8
    assert counts(body) == {
        "new": 0,
        "returning": 3,
        "treating": 3,
        "dormant": 2,
        "reactivated": 0,
        "at_risk": 2,
    }
    assert body["marketing_opt_out"] == 1


async def test_a_group_lists_its_patients_most_overdue_first(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    cs = await client_factory(CS)
    page = (await cs.get("/api/v1/crm/segments/at_risk/patients")).json()
    assert page["total"] == 2
    assert [p["patient_code"] for p in page["items"]] == ["P027", "P029"]
    first = page["items"][0]
    assert first["overdue_days"] == 14
    assert first["risk_level"] == "high"
    assert first["marketing_opt_out"] is False
    assert first["version"] >= 1
    assert first["full_name"].startswith("Bệnh nhân mẫu")
    assert first["cs_owner_name"] is not None


async def test_the_dormant_group_shows_who_opted_out_of_marketing(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    cs = await client_factory(CS)
    items = (await cs.get("/api/v1/crm/segments/dormant/patients")).json()["items"]
    assert {p["patient_code"]: p["marketing_opt_out"] for p in items} == {"P030": True, "P031": False}
    assert all(p["lifecycle_stage"] == "dormant" for p in items)


async def test_a_group_pages_with_limit_and_offset(client_factory: ClientFactory, world: SeedResult) -> None:
    cs = await client_factory(CS)
    page = (await cs.get("/api/v1/crm/segments/treating/patients", params={"limit": 2, "offset": 2})).json()
    assert page["total"] == 3
    assert len(page["items"]) == 1
    assert (page["limit"], page["offset"]) == (2, 2)


async def test_an_unknown_group_is_refused(client_factory: ClientFactory, world: SeedResult) -> None:
    cs = await client_factory(CS)
    assert (await cs.get("/api/v1/crm/segments/vip/patients")).status_code == 422


async def test_a_doctor_sees_the_groups_of_their_own_patients_only(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = (await (await client_factory(OWNER)).get("/api/v1/crm/segments")).json()
    doctor = (await (await client_factory(DOCTOR)).get("/api/v1/crm/segments")).json()
    assert 0 < doctor["total_patients"] < owner["total_patients"]


async def test_reception_has_no_crm_groups_or_rules(client_factory: ClientFactory, world: SeedResult) -> None:
    reception = await client_factory(RECEPTION)
    assert (await reception.get("/api/v1/crm/segments")).status_code == 403
    assert (await reception.get("/api/v1/crm/segments/dormant/patients")).status_code == 403
    assert (await reception.get("/api/v1/crm/rules")).status_code == 403


async def test_the_opt_out_switch_moves_a_patient_into_the_count_and_is_audited(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    cs = await client_factory(CS)
    row = next(
        p
        for p in (await cs.get("/api/v1/crm/segments/returning/patients")).json()["items"]
        if p["patient_code"] == "P028"
    )
    switched = await cs.patch(
        f"/api/v1/patients/{row['patient_id']}", json={"version": row["version"], "marketing_opt_out": True}
    )
    assert switched.status_code == 200, switched.text
    assert (await cs.get("/api/v1/crm/segments")).json()["marketing_opt_out"] == 2
    with admin.begin() as conn:
        details = conn.execute(
            text("SELECT details FROM clinic.audit_log WHERE action = 'patient.update' AND entity_id = :id"),
            {"id": row["patient_id"]},
        ).scalar_one()
    assert "marketing_opt_out" in details["changed_fields"]


async def test_staff_read_the_ten_rules_in_protocol_order(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    cs = await client_factory(CS)
    response = await cs.get("/api/v1/crm/rules")
    assert response.status_code == 200, response.text
    rules = response.json()
    assert [r["rule_key"] for r in rules] == [
        "d1",
        "d3",
        "d7",
        "due",
        "overdue",
        "no_show",
        "abandoned",
        "dormant90",
        "dormant180",
        "birthday",
    ]
    assert {r["rule_key"] for r in rules} == {k.value for k in RuleKey} - {"manual"}
    birthday = rules[-1]
    assert birthday["send_mode"] == "staff_task"
    assert all(r["delay_days"] >= 0 and r["suggested_action"] for r in rules)


async def test_a_rule_is_read_only_through_the_crm_route(
    client_factory: ClientFactory, world: SeedResult
) -> None:
    owner = await client_factory(OWNER)
    assert (await owner.patch("/api/v1/crm/rules", json={})).status_code == 405
    assert (await owner.put("/api/v1/crm/rules", json={})).status_code == 405

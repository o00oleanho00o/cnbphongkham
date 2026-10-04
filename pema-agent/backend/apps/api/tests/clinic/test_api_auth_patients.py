"""Auth endpoints, patients, Patient 360 and consent through the real HTTP API on a real Postgres."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ACCOUNT_PASSWORD, ClientFactory
from pema.clinic.actions.seed_demo import SeedResult

pytestmark = pytest.mark.db

B1_GUARDED_GETS = [
    "/api/v1/me",
    "/api/v1/permissions",
    "/api/v1/patients",
    "/api/v1/appointments",
    "/api/v1/crm/tasks",
    "/api/v1/crm/activities",
    "/api/v1/conversations",
    "/api/v1/review-items",
    "/api/v1/admin/logs/audit",
    "/api/v1/admin/templates",
]


# ---------------------------------------------------------------- auth


async def test_login_sets_an_httponly_cookie_and_me_lists_the_permissions_of_the_role(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    client = await client_factory("clinic-a", "reception.lan")
    cookie = client.cookies.jar
    names = [c.name for c in cookie]
    assert names == ["pema_session"]
    me = (await client.get("/api/v1/me")).json()
    assert me["user"]["role"] == "reception"
    assert "appointment.write" in me["permissions"]
    assert "patient.read_360" not in me["permissions"]
    permissions = (await client.get("/api/v1/permissions")).json()
    assert permissions["role"] == "reception"


async def test_the_session_cookie_is_httponly_and_samesite_lax(app: Any, world_a: SeedResult) -> None:
    import httpx

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.post(
            "/api/v1/auth/login",
            json={"clinic_slug": "clinic-a", "email": "owner@example.test", "password": ACCOUNT_PASSWORD},
        )
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header
    assert "pema_session=" in header
    assert ACCOUNT_PASSWORD not in response.text


@pytest.mark.parametrize("path", B1_GUARDED_GETS)
async def test_every_guarded_route_answers_401_without_a_session(app: Any, path: str) -> None:
    import httpx

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        response = await http.get(path)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_wrong_password_and_unknown_clinic_are_401_and_give_the_same_message(
    app: Any, world_a: SeedResult
) -> None:
    import httpx

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        wrong = await http.post(
            "/api/v1/auth/login",
            json={"clinic_slug": "clinic-a", "email": "owner@example.test", "password": "wrong-password"},
        )
        unknown = await http.post(
            "/api/v1/auth/login",
            json={"clinic_slug": "nope", "email": "owner@example.test", "password": "wrong-password"},
        )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


async def test_logout_clears_the_cookie_and_the_old_session_is_dead(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    client = await client_factory("clinic-a", "cs.thu")
    token = client.cookies["pema_session"]
    assert (await client.post("/api/v1/auth/logout")).status_code == 204
    client.cookies.set("pema_session", token)  # a stolen copy of the cookie
    assert (await client.get("/api/v1/me")).status_code == 401


async def test_refresh_extends_the_session_and_reissues_the_cookie(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    client = await client_factory("clinic-a", "cs.maianh")
    response = await client.post("/api/v1/auth/refresh")
    assert response.status_code == 200
    assert (await client.get("/api/v1/me")).status_code == 200


async def test_a_patient_role_account_cannot_sign_in_to_the_staff_dashboard(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    from pema.clinic.rbac import passwords

    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.user_account (clinic_id, email, display_name, role, password_hash) "
                "VALUES (:c, 'patient.app@example.test', 'Bệnh nhân (mẫu)', 'patient', :h) "
                "ON CONFLICT DO NOTHING"
            ),
            {
                "c": world_a.clinic_id,
                "h": passwords.hash_password(ACCOUNT_PASSWORD, time_cost=1, memory_cost=1024),
            },
        )
    with pytest.raises(AssertionError):
        await client_factory("clinic-a", "patient.app")


async def test_a_user_of_one_clinic_cannot_sign_in_to_another(
    client_factory: ClientFactory, world_a: SeedResult, world_b: SeedResult
) -> None:
    # same e-mail exists in both clinics with its own account; each logs into its own clinic only
    a = await client_factory("clinic-a", "owner")
    b = await client_factory("clinic-b", "owner")
    me_a = (await a.get("/api/v1/me")).json()["user"]
    me_b = (await b.get("/api/v1/me")).json()["user"]
    assert me_a["clinic_id"] != me_b["clinic_id"]
    assert me_a["id"] != me_b["id"]


# ---------------------------------------------------------------- patients


async def test_create_get_update_and_search_a_patient(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    reception = await client_factory("clinic-a", "reception.lan")
    created = await reception.post(
        "/api/v1/patients",
        json={"full_name": "Bệnh nhân thử nghiệm", "phone": "0000000999", "gender": "female"},
    )
    assert created.status_code == 201, created.text
    patient = created.json()
    assert patient["code"].startswith("P")
    assert patient["version"] == 1

    got = (await reception.get(f"/api/v1/patients/{patient['id']}")).json()
    assert got["full_name"] == "Bệnh nhân thử nghiệm"

    updated = await reception.patch(
        f"/api/v1/patients/{patient['id']}",
        json={"version": 1, "phone": "0000000998", "marketing_opt_out": True},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["marketing_opt_out"] is True

    stale = await reception.patch(
        f"/api/v1/patients/{patient['id']}", json={"version": 1, "phone": "0000000001"}
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"

    found = (await reception.get("/api/v1/patients", params={"q": "thử nghiệm"})).json()
    assert [p["id"] for p in found["items"]] == [patient["id"]]
    by_code = (await reception.get("/api/v1/patients", params={"q": patient["code"].lower()})).json()
    assert patient["id"] in [p["id"] for p in by_code["items"]]


async def test_search_escapes_like_wildcards(client_factory: ClientFactory, world_a: SeedResult) -> None:
    owner = await client_factory("clinic-a", "owner")
    everything = (await owner.get("/api/v1/patients", params={"q": "%"})).json()
    assert everything["total"] == 0


async def test_patient_codes_are_unique_and_a_duplicate_explicit_code_is_refused(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    reception = await client_factory("clinic-a", "reception.lan")
    first = (await reception.post("/api/v1/patients", json={"full_name": "A mẫu"})).json()
    second = (await reception.post("/api/v1/patients", json={"full_name": "B mẫu"})).json()
    assert first["code"] != second["code"]
    duplicate = await reception.post("/api/v1/patients", json={"full_name": "C mẫu", "code": first["code"]})
    assert duplicate.status_code == 422


async def test_assignees_must_be_active_staff_of_the_right_role(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    reception = await client_factory("clinic-a", "reception.lan")
    cs_id = world_a.users["cs.thu"]
    bad = await reception.post("/api/v1/patients", json={"full_name": "D mẫu", "doctor_id": str(cs_id)})
    assert bad.status_code == 422
    ok = await reception.post(
        "/api/v1/patients", json={"full_name": "E mẫu", "doctor_id": str(world_a.users["doctor.an"])}
    )
    assert ok.status_code == 201
    assert ok.json()["doctor_name"].startswith("BS. An")


async def test_a_doctor_only_opens_own_or_scheduled_patients(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    mai = await client_factory("clinic-a", "doctor.mai")
    mine = (await mai.get("/api/v1/patients", params={"limit": 200})).json()
    codes = {p["code"] for p in mine["items"]}
    # seeded: even indexes belong to Mai (P025, P027, P029, P031); P026 has an appointment with BS. An only
    assert {"P025", "P027", "P029", "P031"} <= codes
    assert "P030" not in codes
    foreign = world_a.patients["P030"]
    assert (await mai.get(f"/api/v1/patients/{foreign}")).status_code == 403
    assert (await mai.get(f"/api/v1/patients/{foreign}/360")).status_code == 403
    assert (await mai.get(f"/api/v1/patients/{world_a.patients['P025']}")).status_code == 200


async def test_patient_360_joins_context_and_stays_traceable_to_the_source_records(
    client_factory: ClientFactory, world_a: SeedResult, admin: Engine
) -> None:
    cs = await client_factory("clinic-a", "cs.maianh")
    with admin.begin() as conn:  # other tests book P027; the overdue case needs it without a future visit
        conn.execute(
            text(
                "UPDATE clinic.appointment SET status = 'cancelled' WHERE patient_id = :p AND status IN ('booked', 'confirmed', 'arrived', 'in_progress')"
            ),
            {"p": world_a.patients["P027"]},
        )
    body = (await cs.get(f"/api/v1/patients/{world_a.patients['P027']}/360")).json()
    assert body["patient"]["code"] == "P027"
    assert body["profile"]["lifecycle_stage"] == "returning"
    assert body["profile"]["overdue_days"] == 14  # CRM01 case 03: expected 14 days before 2026-09-20
    assert body["profile"]["risk_level"] == "high"
    assert body["plans"][0]["service_code"] == "skin-care"
    assert any(task["rule_key"] == "overdue" for task in body["open_tasks"])
    assert body["timeline"], "the timeline must not be empty"
    assert all(event["source_id"] for event in body["timeline"])
    # message text is not copied into the timeline
    assert "Em thấy da" not in str(body["timeline"])

    p025 = (await cs.get(f"/api/v1/patients/{world_a.patients['P025']}/360")).json()
    assert p025["conversations"], "P025 has an Inbox conversation"
    seeded = next(c for c in p025["conversations"] if c["id"] == str(world_a.conversation_id))
    assert seeded["has_pending_review"] is True
    assert {c["kind"] for c in p025["consents"]} == {"messaging"}


async def test_reception_has_no_patient_360(client_factory: ClientFactory, world_a: SeedResult) -> None:
    reception = await client_factory("clinic-a", "reception.lan")
    response = await reception.get(f"/api/v1/patients/{world_a.patients['P025']}/360")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


# ---------------------------------------------------------------- consent


async def test_consent_history_is_append_only_and_revoking_marketing_opts_the_patient_out(
    client_factory: ClientFactory, world_a: SeedResult
) -> None:
    reception = await client_factory("clinic-a", "reception.lan")
    patient = (await reception.post("/api/v1/patients", json={"full_name": "Đồng ý mẫu"})).json()
    base = f"/api/v1/patients/{patient['id']}/consents"
    granted = await reception.post(base, json={"kind": "marketing", "granted": True, "source": "form"})
    assert granted.status_code == 201
    assert granted.json()["granted_at"] is not None
    assert (await reception.get(f"/api/v1/patients/{patient['id']}")).json()["marketing_opt_out"] is False

    revoked = await reception.post(base, json={"kind": "marketing", "granted": False})
    assert revoked.json()["revoked_at"] is not None
    rows = (await reception.get(base)).json()
    assert len(rows) == 2
    assert rows[0]["granted"] is False, "newest first"
    assert (await reception.get(f"/api/v1/patients/{patient['id']}")).json()["marketing_opt_out"] is True

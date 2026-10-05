# ruff: noqa: PT018, N806
"""Every mutation writes an audit row in its own transaction, the log is append-only and carries no PII."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from pema.api.clinic_testing import (
    ACCOUNT_PASSWORD,
    ClientFactory,
    add_staff_account,
    fresh_start,
    record_inbound,
    sign_in,
)
from pema.clinic import audit
from pema.clinic.actions import FakeOutboundDelivery
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.models import Patient
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.roles import ActorType

pytestmark = pytest.mark.db

B1_TAGS = {
    "auth",
    "patients",
    "appointments",
    "crm",
    "conversations",
    "review-items",
    "admin-templates",
    "admin-users",
}

# operation id of every mutating B1 route -> the audit action it must write
MUTATIONS: dict[str, str] = {
    "auth_login": "auth.login",
    "auth_refresh": "auth.refresh",
    "auth_logout": "auth.logout",
    "auth_change_password": "auth.change_password",
    "admin_users_create_user": "user.create",
    "admin_users_update_user": "user.update",
    "admin_users_reset_user_password": "auth.reset_password",
    "patients_create_patient": "patient.create",
    "patients_update_patient": "patient.update",
    "patients_record_consent": "consent.record",
    "appointments_create_appointment": "appointment.create",
    "appointments_update_appointment": "appointment.update",
    "appointments_check_in_appointment": "appointment.check_in",
    "appointments_start_appointment": "appointment.start",
    "appointments_complete_appointment": "appointment.complete",
    "appointments_cancel_appointment": "appointment.cancel",
    "appointments_miss_appointment": "appointment.miss",
    "crm_resolve_task": "crm_task.resolve",
    "crm_create_activity": "crm_activity.create",
    "conversations_update_conversation": "conversation.update",
    "conversations_mark_conversation_read": "conversation.mark_read",
    "conversations_send_message": "message.send",
    "review_items_approve_review_item": "review_item.approve",
    "review_items_reject_review_item": "review_item.reject",
    "review_items_escalate_review_item": "review_item.escalate",
    "admin_templates_create_template": "message_template.create",
    "admin_templates_update_template": "message_template.update",
    "admin_templates_approve_template": "message_template.approve",
}


# Presence heartbeats (ST-R) change nothing in the database: they live in Redis for 30 seconds, and one audit row
# every 15 seconds per open conversation would only bury the log. Not mutations of clinic data.
EPHEMERAL: frozenset[str] = frozenset({"conversations_touch_presence", "conversations_leave_presence"})


def test_the_table_covers_every_mutating_route_of_the_clinic_api(app: FastAPI) -> None:
    """A new POST/PATCH/PUT/DELETE route without an audit expectation fails here."""
    mutating = {
        operation["operationId"]
        for item in app.openapi()["paths"].values()
        for method, operation in item.items()
        if method in {"post", "patch", "put", "delete"} and set(operation["tags"]) & B1_TAGS
    }
    assert mutating - EPHEMERAL == set(MUTATIONS)


async def _audit_actions(admin: Engine, request_id: str) -> set[str]:
    with admin.connect() as conn:
        rows = conn.execute(
            text("SELECT action FROM clinic.audit_log WHERE request_id = :r"), {"r": request_id}
        )
        return {row[0] for row in rows}


async def test_every_mutating_call_leaves_an_audit_row_tagged_with_its_request_id(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine, app: FastAPI
) -> None:
    app.state.outbound_delivery = FakeOutboundDelivery()
    seen: dict[str, str] = {}

    async def call(op: str, client: httpx.AsyncClient, method: str, url: str, **kw: object) -> httpx.Response:
        request_id = f"audit-{uuid4().hex}"
        headers = {"X-Request-Id": request_id, **dict(kw.pop("headers", {}))}  # type: ignore[call-overload]
        response = await client.request(method, f"/api/v1{url}", headers=headers, **kw)  # type: ignore[arg-type]
        assert response.status_code < 400, f"{op}: {response.status_code} {response.text}"
        wanted = MUTATIONS[op]
        assert wanted in await _audit_actions(admin, request_id), f"{op} wrote no '{wanted}' audit row"
        seen[op] = wanted
        return response

    reception = await client_factory("reception.lan")
    cs = await client_factory("cs.maianh")
    mai = await client_factory("doctor.mai")
    manager = await client_factory("manager")
    P027, P029 = (str(world.patients[c]) for c in ("P027", "P029"))

    # auth: login is audited under the id sent with the login request itself
    request_id = f"audit-{uuid4().hex}"
    login = await reception.post(
        "/api/v1/auth/login",
        headers={"X-Request-Id": request_id},
        json={"email": "reception.lan@example.test", "password": ACCOUNT_PASSWORD},
    )
    assert login.status_code == 200
    assert "auth.login" in await _audit_actions(admin, request_id)
    seen["auth_login"] = "auth.login"
    await call("auth_refresh", reception, "POST", "/auth/refresh")

    patient = (
        await call(
            "patients_create_patient", reception, "POST", "/patients", json={"full_name": "Kiểm toán mẫu"}
        )
    ).json()
    await call(
        "patients_update_patient",
        reception,
        "PATCH",
        f"/patients/{patient['id']}",
        json={"version": 1, "phone": "0000000123"},
    )
    await call(
        "patients_record_consent",
        reception,
        "POST",
        f"/patients/{patient['id']}/consents",
        json={"kind": "media", "granted": True},
    )

    doctor = str(world.users["doctor.mai"])
    appts: list[dict[str, Any]] = []
    for _ in range(3):
        created = await call(
            "appointments_create_appointment",
            reception,
            "POST",
            "/appointments",
            json={"patient_id": P027, "doctor_id": doctor, "starts_at": fresh_start()},
        )
        appts.append(created.json())
    await call(
        "appointments_update_appointment",
        reception,
        "PATCH",
        f"/appointments/{appts[0]['id']}",
        json={"version": 1, "note": "n"},
    )
    await call(
        "appointments_check_in_appointment",
        reception,
        "POST",
        f"/appointments/{appts[0]['id']}/check-in",
        json={"version": 2},
    )
    await call(
        "appointments_start_appointment",
        reception,
        "POST",
        f"/appointments/{appts[0]['id']}/start",
        json={"version": 3},
    )
    await call(
        "appointments_complete_appointment",
        reception,
        "POST",
        f"/appointments/{appts[0]['id']}/complete",
        json={"version": 4},
    )
    await call(
        "appointments_cancel_appointment",
        reception,
        "POST",
        f"/appointments/{appts[1]['id']}/cancel",
        json={"version": 1, "reason": "đổi ý"},
    )
    await call(
        "appointments_miss_appointment",
        reception,
        "POST",
        f"/appointments/{appts[2]['id']}/miss",
        json={"version": 1},
    )

    task_id = str(uuid4())
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.crm_task (id, clinic_id, task_key, patient_id, rule_key, reason, due_at, suggested_action) "
                "VALUES (:i, :c, :k, :p, 'd1', 'r', now(), 'a')"
            ),
            {"i": task_id, "c": world.clinic_id, "k": f"audit:{task_id}", "p": world.patients["P029"]},
        )
    await call(
        "crm_resolve_task",
        cs,
        "POST",
        f"/crm/tasks/{task_id}/resolve",
        json={
            "version": 1,
            "outcome": "no_need",
            "channel": "call",
            "note": "ghi chú",
            "owner_user_id": str(world.users["cs.maianh"]),
        },
    )
    await call(
        "crm_create_activity",
        cs,
        "POST",
        "/crm/activities",
        json={"patient_id": P029, "channel": "internal_note", "note": "n"},
    )

    ref = await record_inbound(db, world)
    conv = f"/conversations/{ref.conversation_id}"
    await call("conversations_mark_conversation_read", cs, "POST", f"{conv}/read")
    await call("conversations_send_message", cs, "POST", f"{conv}/messages", json={"text": "Chào bạn."})
    version = (await cs.get(f"/api/v1{conv}")).json()["version"]
    await call(
        "conversations_update_conversation",
        cs,
        "PATCH",
        conv,
        json={"version": version, "assigned_user_id": str(world.users["cs.thu"])},
    )

    from pema.clinic.actions import ClinicAgentFacingActions
    from pema_contracts.review import ReviewItemCreate, ReviewItemOut, ReviewKind

    agent = ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.AGENT)
    items: list[ReviewItemOut] = []
    for n in range(3):
        items.append(
            await ClinicAgentFacingActions(db).create_review_item(
                agent,
                ReviewItemCreate(
                    job_id=f"audit-job-{uuid4().hex}",
                    clinic_id=world.clinic_id,
                    patient_ref="P025",
                    conversation_ref=str(ref.conversation_id),
                    kind=ReviewKind.REPLY_DRAFT,
                    draft_text=f"Bản nháp {n}",
                ),
            )
        )
    await call(
        "review_items_approve_review_item",
        cs,
        "POST",
        f"/review-items/{items[0].id}/approve",
        json={"version": 1},
    )
    await call(
        "review_items_reject_review_item",
        cs,
        "POST",
        f"/review-items/{items[1].id}/reject",
        json={"version": 1, "reason": "sai"},
    )
    await call(
        "review_items_escalate_review_item",
        cs,
        "POST",
        f"/review-items/{items[2].id}/escalate",
        json={"version": 1},
    )

    template = (
        await call(
            "admin_templates_create_template",
            manager,
            "POST",
            "/admin/templates",
            json={"template_key": f"audit_{uuid4().hex[:8]}", "title": "t", "body": "b"},
        )
    ).json()
    await call(
        "admin_templates_update_template",
        manager,
        "PATCH",
        f"/admin/templates/{template['id']}",
        json={"version": 1, "title": "t2"},
    )
    await call(
        "admin_templates_approve_template",
        mai,
        "POST",
        f"/admin/templates/{template['id']}/approve",
        json={"version": 2},
    )

    # a throw-away account: changing the password of a seeded one would break every later test
    changer = await sign_in(app, await add_staff_account(db, world))
    await call(
        "auth_change_password",
        changer,
        "POST",
        "/auth/password",
        json={"current_password": ACCOUNT_PASSWORD, "new_password": "a-brand-new-password-1"},
    )
    await changer.aclose()

    # the owner resets the password of another throw-away account (never the seeded ones)
    victim_email = await add_staff_account(db, world)
    with admin.connect() as conn:
        victim_id = conn.execute(
            text("SELECT id FROM clinic.user_account WHERE email = :e"), {"e": victim_email}
        ).scalar_one()
    owner = await client_factory("owner")
    await call(
        "admin_users_reset_user_password",
        owner,
        "POST",
        f"/admin/users/{victim_id}/password",
        json={"new_password": "owner-chosen-password-1"},
    )
    # the owner creates an account, then edits it (role + lock); both are audited
    created = await call(
        "admin_users_create_user",
        owner,
        "POST",
        "/admin/users",
        json={
            "display_name": "Nhân viên kiểm toán (mẫu)",
            "email": f"audit.{uuid4().hex[:8]}@example.test",
            "role": "cs_staff",
            "password": "owner-chosen-password-1",
        },
    )
    await call(
        "admin_users_update_user",
        owner,
        "PATCH",
        f"/admin/users/{created.json()['id']}",
        json={"version": created.json()["version"], "role": "reception", "active": False},
    )
    await call("auth_logout", reception, "POST", "/auth/logout")
    assert seen.keys() == MUTATIONS.keys(), f"not exercised: {set(MUTATIONS) - set(seen)}"


async def test_an_audit_row_records_who_did_it_and_never_pii(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    reception = await client_factory("reception.lan")
    request_id = f"audit-{uuid4().hex}"
    secret_name, secret_phone = "Tên Riêng Kiểm Thử", "0000000777"
    created = await reception.post(
        "/api/v1/patients",
        headers={"X-Request-Id": request_id},
        json={"full_name": secret_name, "phone": secret_phone},
    )
    assert created.status_code == 201
    with admin.connect() as conn:
        row = conn.execute(
            text(
                "SELECT actor_type, actor_user_id, actor_role, entity_type, entity_id, details::text FROM clinic.audit_log WHERE request_id = :r"
            ),
            {"r": request_id},
        ).one()
        everything = " ".join(
            str(v)
            for r in conn.execute(
                text("SELECT details::text, entity_id FROM clinic.audit_log WHERE clinic_id = :c"),
                {"c": world.clinic_id},
            )
            for v in r
        )
    assert row.actor_type == "user"
    assert row.actor_user_id == world.users["reception.lan"]
    assert row.actor_role == "reception"
    assert row.entity_type == "patient"
    assert secret_name not in everything and secret_phone not in everything
    assert "Bệnh nhân mẫu" not in everything and "Em thấy da" not in everything


async def test_the_audit_log_is_append_only_even_for_the_application_role(
    db: ClinicDatabase, world: SeedResult
) -> None:
    async with db.session() as session:
        assert (await session.scalar(text("SELECT count(*) FROM clinic.audit_log"))) > 0
    for statement in (
        "UPDATE clinic.audit_log SET action = 'x'",
        "DELETE FROM clinic.audit_log",
        "TRUNCATE clinic.audit_log",
    ):
        with pytest.raises(DBAPIError):
            async with db.session() as session:
                await session.execute(text(statement))


async def test_the_guard_refuses_to_commit_a_clinic_change_without_an_audit_row(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    code = f"G{uuid4().hex[:6]}"
    with pytest.raises(audit.AuditMissingError):
        async with db.session() as session:
            session.add(Patient(clinic_id=world.clinic_id, code=code, full_name="Không audit (mẫu)"))
    with admin.connect() as conn:
        found = conn.execute(
            text("SELECT count(*) FROM clinic.patient WHERE code = :c"), {"c": code}
        ).scalar_one()
    assert found == 0, "the refused transaction must have rolled back"
    ctx = ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.SYSTEM)
    async with db.session() as session:
        session.add(Patient(clinic_id=world.clinic_id, code=code, full_name="Có audit (mẫu)"))
        await session.flush()
        await audit.record(session, ctx, "test.patient_create", "patient", code)
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM clinic.patient WHERE code = :c"), {"c": code}
            ).scalar_one()
            == 1
        )


async def test_a_read_only_transaction_needs_no_audit_row(db: ClinicDatabase, world: SeedResult) -> None:
    async with db.session() as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1


def test_audit_details_with_pii_keys_are_refused() -> None:
    import asyncio

    ctx = ActionContext(clinic_id=uuid4(), actor_type=ActorType.SYSTEM)

    class Dummy:
        def add(self, _row: object) -> None:  # pragma: no cover - never reached
            raise AssertionError

    for key in ("full_name", "phone", "text", "body", "email", "note"):
        with pytest.raises(ValueError, match="PII"):
            asyncio.run(audit.record(Dummy(), ctx, "x", "y", None, {key: "value"}))  # type: ignore[arg-type]

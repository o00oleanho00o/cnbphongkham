"""Every write that accepts an assignee runs the same check, and leaves an audit row (package ST-S).

New tests (no zalo-agent original). Needs ``PEMA_TEST_DATABASE_URL``. The three places that take a "Phụ trách":
a conversation (``PATCH /conversations/{id}``), a CRM task (``POST /crm/tasks/{id}/resolve``) and a patient
(``PATCH /patients/{id}``: treating doctor and CSKH owner). The target must be a user of this installation, ACTIVE
and of an assignable role; since ST-S a staff member may hand work to a colleague, and the audit row says who
gave it to whom (ids only).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import ClientFactory, record_inbound
from pema.clinic.actions import assignees
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.rbac import ASSIGNABLE_ROLES
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

REFUSED = "Người được giao không hợp lệ."
COLLEAGUES = ["owner", "manager", "doctor.an", "cs.thu"]


def _audit(admin: Engine, action: str, entity_id: str) -> list[dict[str, Any]]:
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_type, actor_user_id, actor_role, entity_type, details "
                "FROM clinic.audit_log WHERE action = :a AND entity_id = :e ORDER BY id"
            ),
            {"a": action, "e": entity_id},
        ).all()
    return [
        {
            "actor_type": row.actor_type,
            "actor_user_id": row.actor_user_id,
            "actor_role": row.actor_role,
            "entity_type": row.entity_type,
            "details": row.details,
        }
        for row in rows
    ]


def _lock(admin: Engine, user_id: object) -> None:
    with admin.begin() as conn:
        conn.execute(text("UPDATE clinic.user_account SET active = false WHERE id = :u"), {"u": user_id})


def _patient_role_user(admin: Engine, world: SeedResult) -> str:
    user_id = uuid4()
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.user_account (id, clinic_id, email, display_name, role, active) "
                "VALUES (:i, :c, :e, 'Tài khoản bệnh nhân (mẫu)', 'patient', true)"
            ),
            {"i": user_id, "c": world.clinic_id, "e": f"patient.{user_id.hex[:8]}@example.test"},
        )
    return str(user_id)


def _new_task(admin: Engine, world: SeedResult) -> str:
    task_id = uuid4()
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.crm_task (id, clinic_id, task_key, patient_id, rule_key, reason, priority, "
                "owner_user_id, due_at, suggested_action) VALUES (:id, :c, :k, :p, 'd1', 'lý do mẫu', 'normal', "
                ":o, '2026-09-20T09:00:00+07:00', 'hành động mẫu')"
            ),
            {
                "id": task_id,
                "c": world.clinic_id,
                "k": f"st-s:{task_id}",
                "p": world.patients["P032"],
                "o": world.users["cs.maianh"],
            },
        )
    return str(task_id)


def _resolve_body(owner: object, **extra: object) -> dict[str, object]:
    body: dict[str, object] = {
        "version": 1,
        "outcome": "no_need",
        "channel": "call",
        "note": "Đã gọi, bệnh nhân chưa có nhu cầu (ghi chú mẫu)",
        "owner_user_id": str(owner),
    }
    body.update(extra)
    return body


def test_the_assignable_roles_follow_the_permission_matrix() -> None:
    """vai trò được giao việc = vai trò giữ quyền trả lời hội thoại hoặc xử lý việc CSKH"""
    assert {Role.OWNER, Role.MANAGER, Role.DOCTOR, Role.CS_STAFF} == ASSIGNABLE_ROLES
    assert Role.RECEPTION not in ASSIGNABLE_ROLES
    assert Role.PATIENT not in ASSIGNABLE_ROLES


# ------------------------------------------------------------------------------------------ conversations


async def _conversation(db: ClinicDatabase, world: SeedResult, cs: httpx.AsyncClient) -> tuple[str, int]:
    ref = await record_inbound(db, world)
    url = f"/api/v1/conversations/{ref.conversation_id}"
    return url, (await cs.get(url)).json()["version"]


@pytest.mark.parametrize("target", COLLEAGUES)
async def test_a_conversation_can_be_handed_to_a_colleague_and_the_hand_over_is_audited(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine, target: str
) -> None:
    """giao hội thoại cho đồng nghiệp: được, và audit ghi ai giao cho ai (chỉ id)"""
    cs = await client_factory("cs.maianh")
    url, version = await _conversation(db, world, cs)
    conversation_id = url.rsplit("/", 1)[1]

    response = await cs.patch(url, json={"version": version, "assigned_user_id": str(world.users[target])})

    assert response.status_code == 200, response.text
    assert response.json()["assigned_user_id"] == str(world.users[target])
    rows = _audit(admin, "conversation.update", conversation_id)
    assert len(rows) == 1
    audit = rows[0]
    assert audit["actor_user_id"] == world.users["cs.maianh"]
    assert audit["actor_role"] == "cs_staff"
    assert audit["entity_type"] == "conversation"
    assert audit["details"]["assignee_from"] is None
    assert audit["details"]["assignee_to"] == str(world.users[target])
    assert audit["details"]["changed_fields"] == ["assigned_user_id"]
    dumped = json.dumps(audit["details"], ensure_ascii=False)
    assert "(mẫu)" not in dumped
    assert "@example.test" not in dumped


async def test_handing_a_conversation_on_records_the_previous_assignee(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine
) -> None:
    """giao tiếp cho người khác thì audit giữ cả người giao trước đó; bỏ giao (null) cũng được ghi"""
    cs = await client_factory("cs.maianh")
    url, version = await _conversation(db, world, cs)
    conversation_id = url.rsplit("/", 1)[1]
    first = await cs.patch(url, json={"version": version, "assigned_user_id": str(world.users["cs.maianh"])})
    thu = await client_factory("cs.thu")
    second = await thu.patch(
        url, json={"version": first.json()["version"], "assigned_user_id": str(world.users["doctor.mai"])}
    )
    third = await thu.patch(url, json={"version": second.json()["version"], "assigned_user_id": None})

    assert third.status_code == 200
    assert third.json()["assigned_user_id"] is None
    rows = _audit(admin, "conversation.update", conversation_id)
    assert [(r["details"].get("assignee_from"), r["details"].get("assignee_to")) for r in rows] == [
        (None, str(world.users["cs.maianh"])),
        (str(world.users["cs.maianh"]), str(world.users["doctor.mai"])),
        (str(world.users["doctor.mai"]), None),
    ]
    assert rows[1]["actor_user_id"] == world.users["cs.thu"]


async def test_a_conversation_refuses_an_unknown_locked_or_non_assignable_assignee_with_one_answer(
    client_factory: ClientFactory, world: SeedResult, db: ClinicDatabase, admin: Engine
) -> None:
    """người lạ, tài khoản khóa, lễ tân, vai trò bệnh nhân: cùng một câu trả lời 422, không đổi gì"""
    cs = await client_factory("cs.maianh")
    url, version = await _conversation(db, world, cs)
    conversation_id = url.rsplit("/", 1)[1]
    _lock(admin, world.users["cs.thu"])
    targets = {
        "unknown": str(uuid4()),
        "locked": str(world.users["cs.thu"]),
        "reception": str(world.users["reception.lan"]),
        "patient role": _patient_role_user(admin, world),
    }

    answers: set[str] = set()
    for label, target in targets.items():
        response = await cs.patch(url, json={"version": version, "assigned_user_id": target})
        assert response.status_code == 422, label
        error = response.json()["error"]
        assert error["code"] == "validation_failed", label
        answers.add(error["message"])

    assert answers == {REFUSED}, "the answer must not tell which accounts exist or which are locked"
    assert (await cs.get(url)).json()["assigned_user_id"] is None
    assert _audit(admin, "conversation.update", conversation_id) == []


# ------------------------------------------------------------------------------------------------- tasks


@pytest.mark.parametrize("target", ["owner", "manager", "doctor.an", "cs.thu"])
async def test_a_task_can_be_handed_to_a_colleague_and_the_hand_over_is_audited(
    client_factory: ClientFactory, world: SeedResult, admin: Engine, target: str
) -> None:
    """giao việc CSKH cho đồng nghiệp: được, audit ghi người cũ và người mới (chỉ id)"""
    cs = await client_factory("cs.maianh")
    task_id = _new_task(admin, world)

    response = await cs.post(f"/api/v1/crm/tasks/{task_id}/resolve", json=_resolve_body(world.users[target]))

    assert response.status_code == 200, response.text
    assert response.json()["owner_user_id"] == str(world.users[target])
    audit = _audit(admin, "crm_task.resolve", task_id)[0]
    assert audit["actor_user_id"] == world.users["cs.maianh"]
    assert audit["details"]["owner_from"] == str(world.users["cs.maianh"])
    assert audit["details"]["owner_to"] == str(world.users[target])
    assert "(mẫu)" not in json.dumps(audit["details"], ensure_ascii=False)


async def test_a_task_refuses_an_unknown_locked_or_non_assignable_owner_and_records_nothing(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    """người phụ trách không hợp lệ: 422 cùng một câu, không tạo hoạt động, không đóng việc"""
    cs = await client_factory("cs.maianh")
    task_id = _new_task(admin, world)
    _lock(admin, world.users["cs.thu"])
    targets = [
        uuid4(),
        world.users["cs.thu"],
        world.users["reception.lan"],
        _patient_role_user(admin, world),
    ]

    messages: set[str] = set()
    for target in targets:
        response = await cs.post(f"/api/v1/crm/tasks/{task_id}/resolve", json=_resolve_body(target))
        assert response.status_code == 422, response.text
        messages.add(response.json()["error"]["message"])

    assert len(messages) == 1
    task = (await cs.get(f"/api/v1/crm/tasks/{task_id}")).json()
    assert task["status"] == "open"
    assert task["owner_user_id"] == str(world.users["cs.maianh"])
    activities = (await cs.get("/api/v1/crm/activities", params={"task_id": task_id})).json()
    assert activities["total"] == 0
    assert _audit(admin, "crm_task.resolve", task_id) == []


# --------------------------------------------------------------------------------------------- patients


async def test_a_patient_owner_must_be_active_assignable_and_of_the_right_slot(
    client_factory: ClientFactory, world: SeedResult, admin: Engine
) -> None:
    """bác sĩ phụ trách phải là bác sĩ/chủ, CSKH phụ trách phải là CSKH/quản lý/chủ; khóa hay lễ tân thì 422"""
    reception = await client_factory("reception.lan")
    created = await reception.post(
        "/api/v1/patients",
        json={"full_name": "Bệnh nhân thử giao việc (mẫu)", "phone": "0000000777", "gender": "female"},
    )
    patient = created.json()
    url = f"/api/v1/patients/{patient['id']}"
    _lock(admin, world.users["cs.thu"])

    for body in (
        {"cs_owner_id": str(world.users["doctor.mai"])},  # a doctor is not a CSKH owner
        {"cs_owner_id": str(world.users["cs.thu"])},  # locked
        {"cs_owner_id": str(world.users["reception.lan"])},  # not assignable
        {"doctor_id": str(world.users["cs.maianh"])},  # a CSKH member is not a treating doctor
        {"doctor_id": str(uuid4())},  # unknown
    ):
        refused = await reception.patch(url, json={"version": 1, **body})
        assert refused.status_code == 422, body
        assert refused.json()["error"]["code"] == "validation_failed"

    ok = await reception.patch(
        url,
        json={
            "version": 1,
            "cs_owner_id": str(world.users["manager"]),
            "doctor_id": str(world.users["doctor.an"]),
        },
    )
    assert ok.status_code == 200, ok.text
    audit = _audit(admin, "patient.update", patient["id"])[0]
    assert audit["actor_user_id"] == world.users["reception.lan"]
    assert audit["details"]["cs_owner_id_from"] is None
    assert audit["details"]["cs_owner_id_to"] == str(world.users["manager"])
    assert audit["details"]["doctor_id_to"] == str(world.users["doctor.an"])
    assert "(mẫu)" not in json.dumps(audit["details"], ensure_ascii=False)


# --------------------------------------------------------------------------------------- the shared check


async def test_the_shared_check_can_narrow_the_roles_but_never_widen_them(
    db: ClinicDatabase, world: SeedResult
) -> None:
    """tham số roles chỉ thu hẹp: liệt kê reception cũng không làm lễ tân được giao việc"""
    ctx = ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.SYSTEM)
    async with db.session() as session:
        doctor = await assignees.load_assignable_user(
            session, ctx, world.users["doctor.mai"], roles=["doctor", "reception"]
        )
        assert doctor.role == "doctor"
        with pytest.raises(DomainError) as widened:
            await assignees.load_assignable_user(
                session, ctx, world.users["reception.lan"], roles=["reception", "cs_staff"]
            )
        assert widened.value.code is ErrorCode.VALIDATION_FAILED
        with pytest.raises(DomainError):
            await assignees.load_assignable_user(session, ctx, world.users["cs.thu"], roles=["doctor"])

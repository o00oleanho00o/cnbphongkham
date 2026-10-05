"""RBAC per role at the HTTP boundary (deny by default), following the matrix of ARCH-PB01.

For every endpoint the table says WHICH roles hold the permission. A role outside that set must get 403 and
every role inside it must NOT get 403 (the request may still end 404/422/409: the fake ids and bodies are
only there to get past the permission check). The patient role has no staff session at all; it is tested at
the action layer below.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from uuid import uuid4

import pytest

from pema.api.clinic_testing import ClientFactory
from pema.clinic import actions
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.dashboard import DashboardRange
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

OWNER, MANAGER, DOCTOR, CS, RECEPTION = "owner", "manager", "doctor.mai", "cs.maianh", "reception.lan"
ALL = frozenset({OWNER, MANAGER, DOCTOR, CS, RECEPTION})
FAKE = "00000000-0000-4000-8000-000000000001"


@dataclass(frozen=True)
class Endpoint:
    name: str
    method: str
    path: str
    allowed: frozenset[str]
    body: Callable[[SeedResult], dict[str, object]] | None = None


def _none(_: SeedResult) -> dict[str, object]:
    return {}


ENDPOINTS: tuple[Endpoint, ...] = (
    Endpoint("me", "GET", "/me", ALL),
    Endpoint("permissions", "GET", "/permissions", ALL),
    # every staff role changes its OWN password; the wrong current password here ends in 401, never 403
    Endpoint(
        "change_own_password",
        "POST",
        "/auth/password",
        ALL,
        lambda w: {"current_password": "not-the-password", "new_password": "another-password-1"},
    ),
    # resetting ANOTHER user's password is the owner's alone (admin.users); the fake id is a 404 for the owner
    Endpoint(
        "reset_user_password",
        "POST",
        f"/admin/users/{FAKE}/password",
        frozenset({OWNER}),
        lambda w: {"new_password": "another-password-1"},
    ),
    # staff accounts (H4): reading the list is owner + manager (admin.users.read); every change is the owner's
    Endpoint("list_users", "GET", "/admin/users", frozenset({OWNER, MANAGER})),
    Endpoint(
        "create_user",
        "POST",
        "/admin/users",
        frozenset({OWNER}),
        # role "patient" and a short password: the owner gets past the permission check and ends in a 422
        lambda w: {"display_name": "x", "email": "rbac@example.test", "role": "patient", "password": "short"},
    ),
    Endpoint(
        "update_user",
        "PATCH",
        f"/admin/users/{FAKE}",
        frozenset({OWNER}),
        lambda w: {"version": 1, "display_name": "x"},
    ),
    Endpoint("list_patients", "GET", "/patients", ALL),
    Endpoint(
        "create_patient",
        "POST",
        "/patients",
        frozenset({OWNER, MANAGER, CS, RECEPTION}),
        lambda w: {"full_name": "Bệnh nhân RBAC mẫu"},
    ),
    Endpoint("patient_360", "GET", "/patients/{P025}/360", frozenset({OWNER, MANAGER, DOCTOR, CS})),
    Endpoint("list_consents", "GET", "/patients/{P025}/consents", ALL),
    Endpoint(
        "record_consent",
        "POST",
        "/patients/{P025}/consents",
        ALL,
        lambda w: {"kind": "media", "granted": True},
    ),
    Endpoint("list_appointments", "GET", "/appointments", ALL),
    Endpoint(
        "create_appointment",
        "POST",
        "/appointments",
        frozenset({OWNER, MANAGER, DOCTOR, RECEPTION}),
        lambda w: {
            "patient_id": str(w.patients["P032"]),
            "doctor_id": str(w.users["doctor.mai"]),
            "starts_at": "2026-09-19T10:00:00+07:00",  # past: passes the permission, then 422
        },
    ),
    Endpoint("appointment_schedule", "GET", "/appointments/schedule?day=2026-09-20", ALL),
    Endpoint(
        "appointment_free_slot",
        "GET",
        f"/appointments/free-slot?patient_id={FAKE}&day=2026-09-20",
        frozenset({OWNER, MANAGER, DOCTOR, RECEPTION, CS}),
    ),
    Endpoint("dashboard_kpis", "GET", "/dashboard/kpis", ALL),
    Endpoint(
        "confirm",
        "POST",
        f"/appointments/{FAKE}/confirm",
        frozenset({OWNER, MANAGER, DOCTOR, RECEPTION}),
        lambda w: {"version": 1},
    ),
    Endpoint(
        "check_in",
        "POST",
        f"/appointments/{FAKE}/check-in",
        frozenset({OWNER, MANAGER, DOCTOR, RECEPTION}),
        lambda w: {"version": 1},
    ),
    Endpoint(
        "cancel",
        "POST",
        f"/appointments/{FAKE}/cancel",
        frozenset({OWNER, MANAGER, DOCTOR, RECEPTION}),
        lambda w: {"version": 1, "reason": "x"},
    ),
    Endpoint("list_tasks", "GET", "/crm/tasks", frozenset({OWNER, MANAGER, DOCTOR, CS})),
    Endpoint(
        "resolve_task",
        "POST",
        f"/crm/tasks/{FAKE}/resolve",
        frozenset({OWNER, MANAGER, DOCTOR, CS}),
        lambda w: {
            "version": 1,
            "outcome": "no_need",
            "channel": "call",
            "note": "x",
            "owner_user_id": str(w.users["cs.maianh"]),
        },
    ),
    Endpoint("list_activities", "GET", "/crm/activities", frozenset({OWNER, MANAGER, DOCTOR, CS})),
    Endpoint(
        "create_activity",
        "POST",
        "/crm/activities",
        frozenset({OWNER, MANAGER, DOCTOR, CS}),
        lambda w: {
            "patient_id": str(w.patients["P025"]),
            "channel": "internal_note",
            "note": "ghi chú RBAC mẫu",
        },
    ),
    Endpoint("get_segments", "GET", "/crm/segments", frozenset({OWNER, MANAGER, DOCTOR, CS})),
    Endpoint(
        "list_segment_patients",
        "GET",
        "/crm/segments/dormant/patients",
        frozenset({OWNER, MANAGER, DOCTOR, CS}),
    ),
    Endpoint("list_crm_rules", "GET", "/crm/rules", frozenset({OWNER, MANAGER, DOCTOR, CS})),
    Endpoint("list_guide_articles", "GET", "/guide/articles", ALL),
    Endpoint("get_guide_article", "GET", "/guide/articles/none", ALL),
    Endpoint("ask_the_guide", "POST", "/guide/ask", ALL, lambda w: {"question": "lịch"}),
    Endpoint(
        "set_guide_tags",
        "PUT",
        f"/guide/articles/{FAKE}/tags",
        frozenset({OWNER, MANAGER, DOCTOR}),
        lambda w: {"tags": ["guide"]},
    ),
    Endpoint("list_conversations", "GET", "/conversations", frozenset({OWNER, MANAGER, DOCTOR, CS})),
    Endpoint(
        "send_message",
        "POST",
        f"/conversations/{FAKE}/messages",
        frozenset({OWNER, MANAGER, DOCTOR, CS}),
        lambda w: {"text": "x"},
    ),
    Endpoint("list_review_items", "GET", "/review-items", frozenset({OWNER, MANAGER, DOCTOR, CS})),
    Endpoint(
        "approve_review_item",
        "POST",
        f"/review-items/{FAKE}/approve",
        frozenset({OWNER, MANAGER, DOCTOR, CS}),
        lambda w: {"version": 1},
    ),
    Endpoint(
        "reject_review_item",
        "POST",
        f"/review-items/{FAKE}/reject",
        frozenset({OWNER, MANAGER, DOCTOR, CS}),
        lambda w: {"version": 1, "reason": "x"},
    ),
    Endpoint(
        "escalate_review_item",
        "POST",
        f"/review-items/{FAKE}/escalate",
        frozenset({OWNER, MANAGER, DOCTOR, CS}),
        lambda w: {"version": 1},
    ),
    Endpoint("audit_log", "GET", "/admin/logs/audit", frozenset({OWNER, MANAGER})),
    Endpoint("list_templates", "GET", "/admin/templates", frozenset({OWNER, MANAGER, DOCTOR})),
    Endpoint(
        "create_template",
        "POST",
        "/admin/templates",
        frozenset({OWNER, MANAGER}),
        lambda w: {"template_key": f"rbac_{uuid4().hex[:8]}", "title": "t", "body": "b"},
    ),
    Endpoint(
        "update_template",
        "PATCH",
        f"/admin/templates/{FAKE}",
        frozenset({OWNER, MANAGER}),
        lambda w: {"version": 1, "title": "t"},
    ),
    Endpoint(
        "approve_template",
        "POST",
        f"/admin/templates/{FAKE}/approve",
        frozenset({OWNER, DOCTOR}),
        lambda w: {"version": 1},
    ),
)


@pytest.mark.parametrize("endpoint", ENDPOINTS, ids=lambda e: e.name)
async def test_each_role_gets_403_exactly_when_the_matrix_denies_it(
    endpoint: Endpoint, client_factory: ClientFactory, world: SeedResult
) -> None:
    path = endpoint.path
    for code, patient_id in world.patients.items():
        path = path.replace("{" + code + "}", str(patient_id))
    body = (endpoint.body or _none)(world)
    for role in sorted(ALL):
        client = await client_factory(role)
        response = await client.request(
            endpoint.method, f"/api/v1{path}", json=body if endpoint.body else None
        )
        denied = role not in endpoint.allowed
        assert (response.status_code == 403) is denied, (
            f"{role} {endpoint.method} {endpoint.path}: got {response.status_code}, "
            f"expected {'403' if denied else 'anything but 403'}"
        )
        if denied:
            assert response.json()["error"]["code"] == "forbidden"


async def test_the_patient_role_is_denied_every_clinic_action(db: ClinicDatabase, world: SeedResult) -> None:
    """Người bệnh: không có quyền nào của nhân viên (chưa có liên kết phiên bệnh nhân với hồ sơ)"""
    ctx = ActionContext(
        clinic_id=world.clinic_id, actor_type=ActorType.USER, actor_user_id=uuid4(), actor_role=Role.PATIENT
    )
    calls = [
        actions.patients.list_patients(db, ctx),
        actions.patient_360.get_patient_360(db, ctx, world.patients["P025"]),
        actions.appointments.list_appointments(db, ctx),
        actions.appointments.list_schedule(db, ctx, day=date(2026, 9, 20)),
        actions.dashboard.kpis(db, ctx, range_=DashboardRange.TODAY),
        actions.crm_tasks.list_tasks(db, ctx),
        actions.conversations.list_conversations(db, ctx),
        actions.review_items.list_review_items(db, ctx),
        actions.templates.list_templates(db, ctx),
        actions.audit_logs.list_audit_logs(db, ctx),
    ]
    for call in calls:
        with pytest.raises(DomainError) as caught:
            await call
        assert caught.value.code is ErrorCode.FORBIDDEN


async def test_an_agent_actor_cannot_use_the_staff_actions(db: ClinicDatabase, world: SeedResult) -> None:
    ctx = ActionContext(clinic_id=world.clinic_id, actor_type=ActorType.AGENT)
    with pytest.raises(DomainError) as caught:
        await actions.patients.list_patients(db, ctx)
    assert caught.value.code is ErrorCode.FORBIDDEN

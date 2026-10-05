"""``/api/v1/care/**``: the supervision routes of the care agent (package M, step M5).

New tests (no zalo-agent original). Needs ``PEMA_TEST_DATABASE_URL`` for the signed-in users. The service behind
the routes is a hand-written stand-in (``StubCare``); what is under test is the HTTP face: who may call which route
(deny by default), what the routes say while no service is installed, that a change publishes the live events with
the patient id and nothing else, and that the live stream of a role carries the care events only when the role may
read them.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI

from pema.api import live_access
from pema.api.clinic_testing import ClientFactory
from pema.api.dashboard_auth import AuthenticatedUser
from pema.api.routers import care as care_router
from pema_contracts.actions import ActionContext
from pema_contracts.care import (
    AutonomyMatrixOut,
    CareAlertListOut,
    CareApprovalIn,
    CareAutonomyOut,
    CareControlOut,
    CareControlState,
    CareDepth,
    CareLevel,
    CareMatrixIn,
    CareMatrixOut,
    CareTimingIn,
    CareTimingOut,
    HandoffDeclineIn,
    HandoffListOut,
    HandoffMatrixOut,
    HandoffResultOut,
    OnCallContactIn,
    OnCallContactOut,
    OnCallListOut,
    PatientCareTimelineOut,
    ReleaseIn,
    ReleasePreviewOut,
    ReleaseResultOut,
    StaffCareProfileIn,
    StaffCareProfileListOut,
    StaffCareProfileOut,
    TellAgentIn,
    TellAgentOut,
)
from pema_contracts.live import LiveEventType
from pema_contracts.roles import Role

pytestmark = pytest.mark.db

PATIENT = UUID("00000000-0000-4000-8002-000000000002")
NOW = datetime(2026, 10, 2, 9, 0, tzinfo=UTC)

STAFF_BODY = {"reason": "Đang bận ca khác", "suggest_user_id": None}
RELEASE_BODY = {"note": "Khách ổn", "level": None, "days": None}
TELL_BODY = {"instruction": "Gọi khách bằng chị"}
TIMING_BODY = {
    "sla_urgent_minutes": 5,
    "sla_normal_minutes": 30,
    "max_candidates": 5,
    "oncall_direct_from_depth": "D3",
    "version": 1,
}
APPROVAL_BODY = {"approved": True, "version": 1}
SHIFT: dict[str, list[object]] = {day: [] for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
STAFF_PROFILE_BODY = {"skills": ["laser"], "shift": SHIFT, "capacity": 4, "languages": ["vi"], "version": 1}
ON_CALL_BODY = {"zalo_number": "0000000001", "owner": "Trực mẫu", "active": True}
HANDOFF_MATRIX = {
    "confidence_threshold": 0.6,
    "unverified_max_depth": "D1",
    "post_procedure_window_hours": 48,
    "repeat_question_threshold": 2,
    "rows": [{"signal": "default", "from_depth": "D4"}],
}
AUTONOMY_MATRIX = {
    "confidence_threshold": 0.85,
    "appointment_confirm_l1": False,
    "rules": [{"action_type": "faq_kb_answer", "hard_human": False, "n_to_l2": 10, "d3_enabled": False}],
}
MATRIX_BODY = {"handoff": HANDOFF_MATRIX, "autonomy": AUTONOMY_MATRIX, "version": 1}


class StubCare:
    """Answers every route with a fixed, valid value and remembers who asked."""

    def __init__(self) -> None:
        self.callers: list[ActionContext] = []

    def _seen(self, ctx: ActionContext) -> None:
        self.callers.append(ctx)

    def _matrix(self, ctx: ActionContext) -> CareMatrixOut:
        self._seen(ctx)
        return CareMatrixOut(
            pending_doctor_approval=True,
            can_edit=True,
            can_approve=True,
            handoff=HandoffMatrixOut.model_validate(HANDOFF_MATRIX),
            autonomy=AutonomyMatrixOut.model_validate(AUTONOMY_MATRIX),
            version=1,
        )

    async def list_handoffs(self, ctx: ActionContext, scope: str) -> HandoffListOut:
        self._seen(ctx)
        return HandoffListOut(items=[])

    async def accept_handoff(self, ctx: ActionContext, patient_id: UUID) -> HandoffResultOut:
        self._seen(ctx)
        return HandoffResultOut(patient_id=patient_id, state=CareControlState.STAFF, outcome="accepted")

    async def decline_handoff(
        self, ctx: ActionContext, patient_id: UUID, body: HandoffDeclineIn
    ) -> HandoffResultOut:
        self._seen(ctx)
        return HandoffResultOut(patient_id=patient_id, state=CareControlState.HANDOFF_ROUTING)

    async def timeline(self, ctx: ActionContext, patient_id: UUID) -> PatientCareTimelineOut:
        self._seen(ctx)
        return PatientCareTimelineOut(
            patient_id=patient_id,
            patient_name="Bệnh nhân mẫu",
            control=CareControlOut(state=CareControlState.AUTO, since=NOW),
            autonomy=CareAutonomyOut(effective_level=CareLevel.L0, base_level=CareLevel.L0, paused=False),
            pending_drafts=[],
            paused_reminders=[],
            entries=[],
            memory=[],
            can_release=False,
            can_tell_agent=True,
            release_levels=[],
            max_override_days=30,
        )

    async def preview_release(
        self, ctx: ActionContext, patient_id: UUID, body: ReleaseIn
    ) -> ReleasePreviewOut:
        self._seen(ctx)
        return ReleasePreviewOut(allowed=True, consequence="Agent tiếp tục.")

    async def release(self, ctx: ActionContext, patient_id: UUID, body: ReleaseIn) -> ReleaseResultOut:
        self._seen(ctx)
        return ReleaseResultOut(patient_id=patient_id, state=CareControlState.AUTO)

    async def tell_agent(self, ctx: ActionContext, patient_id: UUID, body: TellAgentIn) -> TellAgentOut:
        self._seen(ctx)
        return TellAgentOut(memory_id=uuid4())

    async def list_staff_profiles(self, ctx: ActionContext) -> StaffCareProfileListOut:
        self._seen(ctx)
        return StaffCareProfileListOut(items=[], known_skills=["laser"])

    async def update_staff_profile(
        self, ctx: ActionContext, user_id: UUID, body: StaffCareProfileIn
    ) -> StaffCareProfileOut:
        self._seen(ctx)
        return StaffCareProfileOut(
            user_id=user_id,
            name="Nhân viên mẫu",
            role="cs_staff",
            skills=body.skills,
            shift=body.shift,
            capacity=body.capacity,
            languages=body.languages,
            load=0,
            version=body.version + 1,
        )

    async def list_on_call(self, ctx: ActionContext) -> OnCallListOut:
        self._seen(ctx)
        return OnCallListOut(items=[], chain_ends_with_on_call=False)

    def _contact(self, body: OnCallContactIn, contact_id: UUID) -> OnCallContactOut:
        return OnCallContactOut(
            id=contact_id,
            zalo_number=body.zalo_number,
            owner=body.owner,
            valid_from=NOW,
            active=body.active,
            is_fixture=True,
            version=1,
        )

    async def create_on_call(self, ctx: ActionContext, body: OnCallContactIn) -> OnCallContactOut:
        self._seen(ctx)
        return self._contact(body, uuid4())

    async def update_on_call(
        self, ctx: ActionContext, contact_id: UUID, body: OnCallContactIn
    ) -> OnCallContactOut:
        self._seen(ctx)
        return self._contact(body, contact_id)

    async def get_matrix(self, ctx: ActionContext) -> CareMatrixOut:
        return self._matrix(ctx)

    async def save_matrix(self, ctx: ActionContext, body: CareMatrixIn) -> CareMatrixOut:
        return self._matrix(ctx)

    async def approve_matrix(self, ctx: ActionContext, body: CareApprovalIn) -> CareMatrixOut:
        return self._matrix(ctx)

    def _timing(self, ctx: ActionContext) -> CareTimingOut:
        self._seen(ctx)
        return CareTimingOut(
            sla_urgent_minutes=5,
            sla_normal_minutes=30,
            max_candidates=5,
            oncall_direct_from_depth=CareDepth.D3,
            time_zone="Asia/Ho_Chi_Minh",
            pending_doctor_approval=True,
            can_edit=True,
            version=1,
        )

    async def get_timing(self, ctx: ActionContext) -> CareTimingOut:
        return self._timing(ctx)

    async def save_timing(self, ctx: ActionContext, body: CareTimingIn) -> CareTimingOut:
        return self._timing(ctx)

    async def list_alerts(self, ctx: ActionContext) -> CareAlertListOut:
        self._seen(ctx)
        return CareAlertListOut(items=[])


# Each route once: (method, path, body). The same table drives the role matrix and the 503 test.
ROUTES: dict[str, tuple[str, str, object | None]] = {
    "handoffs": ("GET", "/api/v1/care/handoffs", None),
    "accept": ("POST", f"/api/v1/care/handoffs/{PATIENT}/accept", None),
    "decline": ("POST", f"/api/v1/care/handoffs/{PATIENT}/decline", STAFF_BODY),
    "timeline": ("GET", f"/api/v1/care/patients/{PATIENT}/timeline", None),
    "preview": ("POST", f"/api/v1/care/patients/{PATIENT}/release/preview", RELEASE_BODY),
    "release": ("POST", f"/api/v1/care/patients/{PATIENT}/release", RELEASE_BODY),
    "tell": ("POST", f"/api/v1/care/patients/{PATIENT}/tell-agent", TELL_BODY),
    "staff-list": ("GET", "/api/v1/care/admin/staff", None),
    "staff-save": ("PUT", f"/api/v1/care/admin/staff/{PATIENT}", STAFF_PROFILE_BODY),
    "on-call-list": ("GET", "/api/v1/care/admin/on-call", None),
    "on-call-add": ("POST", "/api/v1/care/admin/on-call", ON_CALL_BODY),
    "on-call-save": ("PUT", f"/api/v1/care/admin/on-call/{PATIENT}", ON_CALL_BODY),
    "matrix-get": ("GET", "/api/v1/care/admin/matrix", None),
    "matrix-save": ("PUT", "/api/v1/care/admin/matrix", MATRIX_BODY),
    "matrix-approve": ("POST", "/api/v1/care/admin/matrix/approval", APPROVAL_BODY),
    "timing-get": ("GET", "/api/v1/care/admin/timing", None),
    "timing-save": ("PUT", "/api/v1/care/admin/timing", TIMING_BODY),
    "alerts": ("GET", "/api/v1/care/admin/alerts", None),
}

STAFF_ROUTES = {"handoffs", "accept", "decline", "timeline", "preview", "release", "tell"}
ADMIN_ROUTES = {
    "staff-list",
    "staff-save",
    "on-call-list",
    "on-call-add",
    "on-call-save",
    "timing-get",
    "timing-save",
    "alerts",
}
MATRIX_ROUTES = {"matrix-get", "matrix-save"}
APPROVE_ROUTES = {"matrix-approve"}
assert set(ROUTES) == STAFF_ROUTES | ADMIN_ROUTES | MATRIX_ROUTES | APPROVE_ROUTES

# Which user key of the seed holds which part, as the matrix of ``pema.clinic.rbac.matrix`` grants it.
ALLOWED: dict[str, set[str]] = {
    "owner": STAFF_ROUTES | ADMIN_ROUTES | MATRIX_ROUTES | APPROVE_ROUTES,
    "manager": STAFF_ROUTES | ADMIN_ROUTES | MATRIX_ROUTES | APPROVE_ROUTES,
    "doctor.mai": STAFF_ROUTES | MATRIX_ROUTES | APPROVE_ROUTES,
    "cs.maianh": STAFF_ROUTES,
    "reception.lan": set(),
}


async def call(client: httpx.AsyncClient, name: str) -> httpx.Response:
    method, path, body = ROUTES[name]
    return await client.request(method, path, json=body)


@pytest.fixture
def care(app: FastAPI) -> StubCare:
    stub = StubCare()
    app.state.care = stub
    return stub


@pytest.fixture
def announced(monkeypatch: pytest.MonkeyPatch) -> list[tuple[LiveEventType, UUID | None]]:
    seen: list[tuple[LiveEventType, UUID | None]] = []

    def record(event_type: LiveEventType, entity_id: UUID | None = None) -> None:
        seen.append((event_type, entity_id))

    monkeypatch.setattr(care_router, "emit_live", record)
    return seen


# ------------------------------------------------------------------------------------------ who may call
@pytest.mark.parametrize("user_key", list(ALLOWED))
async def test_each_role_reaches_exactly_the_routes_its_permissions_allow(
    user_key: str, client_factory: ClientFactory, care: StubCare, world: object
) -> None:
    client = await client_factory(user_key)
    outcome = {name: (await call(client, name)).status_code for name in ROUTES}
    wrong = {
        name: status
        for name, status in outcome.items()
        if (status == 200) != (name in ALLOWED[user_key]) or (status not in (200, 403))
    }
    assert wrong == {}


async def test_an_anonymous_caller_is_refused_everywhere(app: FastAPI, care: StubCare) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as anonymous:
        statuses = {name: (await call(anonymous, name)).status_code for name in ROUTES}
    assert set(statuses.values()) == {401}


async def test_a_refused_call_never_reaches_the_service(
    client_factory: ClientFactory, care: StubCare, world: object
) -> None:
    client = await client_factory("cs.maianh")
    response = await call(client, "matrix-get")
    assert response.status_code == 403
    assert care.callers == []


async def test_the_service_gets_the_caller_as_the_actor(
    client_factory: ClientFactory, care: StubCare, world: object
) -> None:
    client = await client_factory("doctor.mai")
    await call(client, "timeline")
    assert [c.actor_role for c in care.callers] == [Role.DOCTOR]


# ------------------------------------------------------------------------- no service installed yet
async def test_every_route_says_unavailable_until_the_service_is_installed(
    client_factory: ClientFactory, app: FastAPI, world: object
) -> None:
    assert getattr(app.state, "care", None) is None
    client = await client_factory("owner")
    statuses = {name: (await call(client, name)).status_code for name in ROUTES}
    assert set(statuses.values()) == {503}
    body = (await call(client, "handoffs")).json()
    assert body["error"]["code"] == "channel_unavailable"


# ------------------------------------------------------------------------------------ live events
async def test_a_change_announces_the_patient_and_nothing_else(
    client_factory: ClientFactory,
    care: StubCare,
    announced: list[tuple[LiveEventType, UUID | None]],
    world: object,
) -> None:
    client = await client_factory("cs.maianh")
    await call(client, "accept")
    assert announced == [(LiveEventType.HANDOFF_CHANGED, PATIENT), (LiveEventType.CARE_CHANGED, PATIENT)]


async def test_telling_the_agent_announces_the_care_state_only(
    client_factory: ClientFactory,
    care: StubCare,
    announced: list[tuple[LiveEventType, UUID | None]],
    world: object,
) -> None:
    client = await client_factory("cs.maianh")
    await call(client, "tell")
    assert announced == [(LiveEventType.CARE_CHANGED, PATIENT)]


async def test_a_read_announces_nothing(
    client_factory: ClientFactory,
    care: StubCare,
    announced: list[tuple[LiveEventType, UUID | None]],
    world: object,
) -> None:
    client = await client_factory("cs.maianh")
    await call(client, "timeline")
    await call(client, "handoffs")
    assert announced == []


@pytest.mark.parametrize(
    ("role", "gets_care_events"),
    [
        (Role.OWNER, True),
        (Role.MANAGER, True),
        (Role.DOCTOR, True),
        (Role.CS_STAFF, True),
        (Role.RECEPTION, False),
    ],
)
def test_the_live_stream_carries_the_care_events_only_to_roles_that_may_read_them(
    role: Role, gets_care_events: bool
) -> None:
    user = AuthenticatedUser(
        user_id=uuid4(),
        clinic_id=uuid4(),
        role=role,
        display_name="Mẫu",
        clinic_name="Phòng khám mẫu",
        session_id=uuid4(),
        expires_at=NOW,
        absolute_expires_at=NOW,
    )
    access = live_access.stream_access_of(user)
    held = {LiveEventType.HANDOFF_CHANGED, LiveEventType.CARE_CHANGED} <= access.types
    assert held is gets_care_events
    assert (access.with_ids is False) is (role is Role.DOCTOR)

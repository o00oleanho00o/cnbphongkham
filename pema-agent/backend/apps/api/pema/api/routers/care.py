"""Supervision of the per-patient care agent (package M, step M5). New router, no zalo-agent source.

Staff supervise the care agents instead of driving them: who is waiting for me, accept or decline, the
timeline
of one patient's agent, return the conversation to the agent (optionally with a LOWER level for N days)
and tell
the agent something; owner and manager also administer skills, shifts, the 24/7 contact, SLA and alerts, and a
doctor (or manager, or owner) edits and approves the matrix of thresholds.

The route checks the permission (deny by default, ``pema.clinic.rbac.authorize``) and publishes the live
events
after the change; every rule and every refusal is the service's (``pema.care.supervision``). The routes answer
503 ``channel_unavailable`` until the composition root installs the service. No message text and no
patient name
travels on the live events.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Security

from pema.api.care_access import CareDep
from pema.api.dashboard_auth import Ctx
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.care.supervision import HandoffScope
from pema.clinic.rbac.authorize import require
from pema.live import emit_live
from pema_contracts.care import (
    CareAlertListOut,
    CareApprovalIn,
    CareMatrixIn,
    CareMatrixOut,
    CareTimingIn,
    CareTimingOut,
    HandoffDeclineIn,
    HandoffListOut,
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
from pema_contracts.roles import Permission

router = APIRouter(tags=["care"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])

Scope = Annotated[HandoffScope, Query(description="mine: asked of me now; all: every open round.")]


def _announce(patient_id: UUID, *, handoff: bool) -> None:
    if handoff:
        emit_live(LiveEventType.HANDOFF_CHANGED, patient_id)
    emit_live(LiveEventType.CARE_CHANGED, patient_id)


# ===================================================================================== staff side
@router.get("/care/handoffs", response_model=HandoffListOut, summary="Handoffs waiting for a person")
async def list_handoffs(ctx: Ctx, care: CareDep, scope: Scope = "mine") -> HandoffListOut:
    require(ctx, Permission.CARE_READ)
    return await care.list_handoffs(ctx, scope)


@router.post(
    "/care/handoffs/{patient_id}/accept",
    response_model=HandoffResultOut,
    summary="Take the conversation (HANDOFF_ROUTING to STAFF)",
)
async def accept_handoff(patient_id: UUID, ctx: Ctx, care: CareDep) -> HandoffResultOut:
    require(ctx, Permission.CARE_ACT)
    result = await care.accept_handoff(ctx, patient_id)
    _announce(patient_id, handoff=True)
    return result


@router.post(
    "/care/handoffs/{patient_id}/decline",
    response_model=HandoffResultOut,
    summary="Decline with a reason, optionally suggesting a colleague",
)
async def decline_handoff(
    patient_id: UUID, body: HandoffDeclineIn, ctx: Ctx, care: CareDep
) -> HandoffResultOut:
    require(ctx, Permission.CARE_ACT)
    result = await care.decline_handoff(ctx, patient_id, body)
    _announce(patient_id, handoff=True)
    return result


@router.get(
    "/care/patients/{patient_id}/timeline",
    response_model=PatientCareTimelineOut,
    summary="What the care agent of one patient did, holds and waits for",
)
async def patient_timeline(patient_id: UUID, ctx: Ctx, care: CareDep) -> PatientCareTimelineOut:
    require(ctx, Permission.CARE_READ)
    return await care.timeline(ctx, patient_id)


@router.post(
    "/care/patients/{patient_id}/release/preview",
    response_model=ReleasePreviewOut,
    summary="The consequence of a release, in words, before it is done",
)
async def preview_release(patient_id: UUID, body: ReleaseIn, ctx: Ctx, care: CareDep) -> ReleasePreviewOut:
    require(ctx, Permission.CARE_ACT)
    return await care.preview_release(ctx, patient_id, body)


@router.post(
    "/care/patients/{patient_id}/release",
    response_model=ReleaseResultOut,
    summary="Return the conversation to the agent (STAFF to AUTO), with a note and an optional lower level",
)
async def release_to_agent(patient_id: UUID, body: ReleaseIn, ctx: Ctx, care: CareDep) -> ReleaseResultOut:
    require(ctx, Permission.CARE_ACT)
    result = await care.release(ctx, patient_id, body)
    _announce(patient_id, handoff=True)
    return result


@router.post(
    "/care/patients/{patient_id}/tell-agent",
    response_model=TellAgentOut,
    summary="A free-text instruction for the agent of this patient (saved as care memory, source staff)",
)
async def tell_agent(patient_id: UUID, body: TellAgentIn, ctx: Ctx, care: CareDep) -> TellAgentOut:
    require(ctx, Permission.CARE_ACT)
    result = await care.tell_agent(ctx, patient_id, body)
    _announce(patient_id, handoff=False)
    return result


# ===================================================================================== admin side
@router.get(
    "/care/admin/staff",
    response_model=StaffCareProfileListOut,
    summary="Skills, shift and capacity of every staff member",
)
async def list_staff_profiles(ctx: Ctx, care: CareDep) -> StaffCareProfileListOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.list_staff_profiles(ctx)


@router.put(
    "/care/admin/staff/{user_id}",
    response_model=StaffCareProfileOut,
    summary="Change the skills, shift and capacity of one staff member",
)
async def update_staff_profile(
    user_id: UUID, body: StaffCareProfileIn, ctx: Ctx, care: CareDep
) -> StaffCareProfileOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.update_staff_profile(ctx, user_id, body)


@router.get("/care/admin/on-call", response_model=OnCallListOut, summary="The 24/7 on-call contacts")
async def list_on_call(ctx: Ctx, care: CareDep) -> OnCallListOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.list_on_call(ctx)


@router.post("/care/admin/on-call", response_model=OnCallContactOut, summary="Add an on-call contact")
async def create_on_call(body: OnCallContactIn, ctx: Ctx, care: CareDep) -> OnCallContactOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.create_on_call(ctx, body)


@router.put(
    "/care/admin/on-call/{contact_id}",
    response_model=OnCallContactOut,
    summary="Change or switch off an on-call contact",
)
async def update_on_call(
    contact_id: UUID, body: OnCallContactIn, ctx: Ctx, care: CareDep
) -> OnCallContactOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.update_on_call(ctx, contact_id, body)


@router.get(
    "/care/admin/matrix",
    response_model=CareMatrixOut,
    summary="Depth and autonomy matrix, with the pending-approval badge",
)
async def get_matrix(ctx: Ctx, care: CareDep) -> CareMatrixOut:
    require(ctx, Permission.CARE_MATRIX)
    return await care.get_matrix(ctx)


@router.put(
    "/care/admin/matrix",
    response_model=CareMatrixOut,
    summary="Save the cells of the matrix (the badge goes back to pending)",
)
async def save_matrix(body: CareMatrixIn, ctx: Ctx, care: CareDep) -> CareMatrixOut:
    require(ctx, Permission.CARE_MATRIX)
    return await care.save_matrix(ctx, body)


@router.post(
    "/care/admin/matrix/approval",
    response_model=CareMatrixOut,
    summary="Clear or restore the pending-doctor-approval badge",
)
async def approve_matrix(body: CareApprovalIn, ctx: Ctx, care: CareDep) -> CareMatrixOut:
    require(ctx, Permission.CARE_APPROVE)
    return await care.approve_matrix(ctx, body)


@router.get("/care/admin/timing", response_model=CareTimingOut, summary="SLA and chain length, send window")
async def get_timing(ctx: Ctx, care: CareDep) -> CareTimingOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.get_timing(ctx)


@router.put("/care/admin/timing", response_model=CareTimingOut, summary="Change the SLA and the chain length")
async def save_timing(body: CareTimingIn, ctx: Ctx, care: CareDep) -> CareTimingOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.save_timing(ctx, body)


@router.get(
    "/care/admin/alerts",
    response_model=CareAlertListOut,
    summary="Demotions, unresponsive patients, red flags, on-call used",
)
async def list_alerts(ctx: Ctx, care: CareDep) -> CareAlertListOut:
    require(ctx, Permission.CARE_ADMIN)
    return await care.list_alerts(ctx)

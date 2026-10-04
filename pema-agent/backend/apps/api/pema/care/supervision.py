"""What the supervision routes need from the care agent (package M, step M5). New module (not a port).

``routers/care.py`` is the HTTP face; this Protocol is the seam behind it. The routes check the permission of
the caller and publish the live events; the service owns the data and the rules (who may accept, which
levels a
release may use, what the matrix may hold, the scoping of a doctor to their own patients). It is installed as
``app.state.care`` by the composition root; a bare app (the route tests, the OpenAPI export) has none and the
routes answer 503 ``channel_unavailable``, like the live stream does.

State changes go through the existing domain objects: ``accept`` / ``decline`` / ``release_to_auto`` of
``pema.care.control.CareControl`` (the only way back to AUTO is a staff release), ``set_override`` of
``pema.care.autonomy``, ``care_memory`` rows of source ``staff``. An implementation never writes a rule of its
own: a refusal is a ``DomainError`` (``invalid_state`` for a conversation in the wrong state, ``forbidden``,
``validation_failed``, ``version_conflict``).
"""

from __future__ import annotations

from typing import Literal, Protocol
from uuid import UUID

from pema_contracts.actions import ActionContext
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

type HandoffScope = Literal["mine", "all"]


class CareSupervision(Protocol):
    # ------------------------------------------------------------------------------ staff side
    async def list_handoffs(self, ctx: ActionContext, scope: HandoffScope) -> HandoffListOut: ...

    async def accept_handoff(self, ctx: ActionContext, patient_id: UUID) -> HandoffResultOut: ...

    async def decline_handoff(
        self, ctx: ActionContext, patient_id: UUID, body: HandoffDeclineIn
    ) -> HandoffResultOut: ...

    async def timeline(self, ctx: ActionContext, patient_id: UUID) -> PatientCareTimelineOut: ...

    async def preview_release(
        self, ctx: ActionContext, patient_id: UUID, body: ReleaseIn
    ) -> ReleasePreviewOut: ...

    async def release(self, ctx: ActionContext, patient_id: UUID, body: ReleaseIn) -> ReleaseResultOut: ...

    async def tell_agent(self, ctx: ActionContext, patient_id: UUID, body: TellAgentIn) -> TellAgentOut: ...

    # ----------------------------------------------------------------------------- admin side
    async def list_staff_profiles(self, ctx: ActionContext) -> StaffCareProfileListOut: ...

    async def update_staff_profile(
        self, ctx: ActionContext, user_id: UUID, body: StaffCareProfileIn
    ) -> StaffCareProfileOut: ...

    async def list_on_call(self, ctx: ActionContext) -> OnCallListOut: ...

    async def create_on_call(self, ctx: ActionContext, body: OnCallContactIn) -> OnCallContactOut: ...

    async def update_on_call(
        self, ctx: ActionContext, contact_id: UUID, body: OnCallContactIn
    ) -> OnCallContactOut: ...

    async def get_matrix(self, ctx: ActionContext) -> CareMatrixOut: ...

    async def save_matrix(self, ctx: ActionContext, body: CareMatrixIn) -> CareMatrixOut: ...

    async def approve_matrix(self, ctx: ActionContext, body: CareApprovalIn) -> CareMatrixOut: ...

    async def get_timing(self, ctx: ActionContext) -> CareTimingOut: ...

    async def save_timing(self, ctx: ActionContext, body: CareTimingIn) -> CareTimingOut: ...

    async def list_alerts(self, ctx: ActionContext) -> CareAlertListOut: ...

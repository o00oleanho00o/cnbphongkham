# ported from: prototype/shared/clinic.js (studio, photos: view filter, "Ảnh trước / sau" page)
"""Before / After Studio: the read model behind ``/studio``.

In the old Clinic Web ``data-nav="studio"`` is "Ảnh trước / sau" (design spec I7): for ONE patient, pick a
view (Chính diện, Má trái, Má phải), show the first and the latest photo of that view side by side or with a
slider, with the metadata (region, view, session, media consent) and the notice that alignment is not checked
and no medical effect may be read from the images. The first photo is "Trước", the last one "Sau".

This action serves the part the server decides: who may look (``patient.read_360``, and a doctor only at the
patients they own or are scheduled for), the patient header (code, name, the concern taken from the live
treatment plan), the views, and whether the patient's newest ``media`` consent is granted (the screen says
"Chưa có đồng ý" otherwise and offers no upload). Reading it is audited like the Patient 360 (photos are
sensitive).

Photos: the photo store (``clinic.media``, upload with consent) is the Patient 360 step (U3). Until it lands
``photos`` is always empty and the screen shows the clinic's illustrative placeholders exactly as the
prototype did for a patient with no upload; the day ``clinic.media`` exists only ``_photos`` changes. No image
is analysed or aligned anywhere (PLAN-AI01-U principle 6).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._scope import require_patient_access
from pema.clinic.actions.patients import load_patient
from pema.clinic.models import Consent, TreatmentPlan
from pema.clinic.rbac import require
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.catalog import StudioOut, StudioPhotoOut
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

VIEWS: tuple[str, ...] = ("Chính diện", "Má trái", "Má phải")
"""The three views of ``studio-view`` in the prototype; the first one is the default."""
LIVE_PLAN_STATUSES = ("planned", "active")


async def _media_consent(session: AsyncSession, ctx: ActionContext, patient_id: UUID) -> bool:
    newest = await session.scalar(
        select(Consent.granted)
        .where(
            Consent.clinic_id == ctx.clinic_id,
            Consent.patient_id == patient_id,
            Consent.kind == "media",
        )
        .order_by(Consent.created_at.desc(), Consent.id.desc())
        .limit(1)
    )
    return bool(newest)


async def _photos(
    _session: AsyncSession, _ctx: ActionContext, _patient_id: UUID, _view: str
) -> list[StudioPhotoOut]:
    """The milestone photos of ``view``, oldest first. Empty until the Patient 360 step adds a media store."""
    return []


async def get_studio(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID, *, view: str | None = None
) -> StudioOut:
    require(ctx, Permission.PATIENT_READ_360)
    chosen = view or VIEWS[0]
    if chosen not in VIEWS:
        raise DomainError(ErrorCode.VALIDATION_FAILED, "Góc ảnh không hợp lệ.")
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient_id)
        concern = await session.scalar(
            select(TreatmentPlan.title)
            .where(
                TreatmentPlan.clinic_id == ctx.clinic_id,
                TreatmentPlan.patient_id == patient_id,
                TreatmentPlan.status.in_(LIVE_PLAN_STATUSES),
            )
            .order_by(TreatmentPlan.title, TreatmentPlan.id)
            .limit(1)
        )
        consent = await _media_consent(session, ctx, patient_id)
        photos = await _photos(session, ctx, patient_id, chosen)
        await audit.record(
            session, ctx, "studio.view", "patient", patient_id, {"view": chosen, "photos": len(photos)}
        )
        return StudioOut(
            patient_id=patient.id,
            patient_code=patient.code,
            patient_name=patient.full_name,
            concern=concern,
            view=chosen,
            views=list(VIEWS),
            media_consent=consent,
            photos=photos,
        )

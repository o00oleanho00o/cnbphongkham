"""Dashboard KPIs (package U, step U2). New router; the numbers come from the dashboard action."""

from __future__ import annotations

from fastapi import APIRouter, Security

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import dashboard
from pema_contracts.dashboard import DashboardKpisOut, DashboardRange

router = APIRouter(
    tags=["dashboard"],
    responses=ERROR_RESPONSES,
    dependencies=[Security(cookie_scheme)],
)


@router.get(
    "/dashboard/kpis",
    response_model=DashboardKpisOut,
    summary="Clinic KPIs for today, this week or this month",
    description=(
        "Only numbers the database holds. `appointments` and `patients` need `appointment.read`, `care` "
        "needs `crm.task.read`; a block the caller may not read is null. A doctor gets own appointments "
        "only. No revenue: there is no finance data until package U6."
    ),
)
async def get_kpis(db: Database, ctx: Ctx, range: DashboardRange = DashboardRange.TODAY) -> DashboardKpisOut:
    return await dashboard.kpis(db, ctx, range_=range)

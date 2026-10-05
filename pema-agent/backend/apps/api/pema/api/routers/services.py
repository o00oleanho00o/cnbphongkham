"""Service catalog and treatment protocols (package U, step U4).

Reads are for everybody who sees the schedule; every change needs ``admin.rules`` (owner, manager). The rules,
the versioned price and rate terms, and the audit are in ``pema.clinic.actions.services`` and ``.protocols``.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import protocols, services
from pema_contracts.catalog import (
    ProtocolCreate,
    ProtocolOut,
    ProtocolUpdate,
    ServiceCreate,
    ServiceDetailOut,
    ServiceOut,
    ServiceUpdate,
)

router = APIRouter(tags=["services"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])
protocols_router = APIRouter(
    tags=["protocols"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)]
)


@router.get("/services", response_model=list[ServiceOut], summary="Service catalog")
async def list_services(db: Database, ctx: Ctx, active: bool | None = None) -> list[ServiceOut]:
    return await services.list_services(db, ctx, active=active)


@router.post(
    "/services",
    response_model=ServiceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a service (first price and rate snapshot)",
)
async def create_service(body: ServiceCreate, db: Database, ctx: Ctx) -> ServiceOut:
    return await services.create_service(db, ctx, body)


@router.get(
    "/services/{service_id}",
    response_model=ServiceDetailOut,
    summary="One service with the history of its price and rate snapshots",
)
async def get_service(service_id: UUID, db: Database, ctx: Ctx) -> ServiceDetailOut:
    return await services.get_service(db, ctx, service_id)


@router.patch(
    "/services/{service_id}",
    response_model=ServiceOut,
    summary="Edit a service; a change of price, rate, basis, duration or buffer adds a snapshot",
)
async def update_service(service_id: UUID, body: ServiceUpdate, db: Database, ctx: Ctx) -> ServiceOut:
    return await services.update_service(db, ctx, service_id, body)


@protocols_router.get("/protocols", response_model=list[ProtocolOut], summary="Follow-up protocols")
async def list_protocols(db: Database, ctx: Ctx) -> list[ProtocolOut]:
    return await protocols.list_protocols(db, ctx)


@protocols_router.post(
    "/protocols",
    response_model=ProtocolOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a protocol (milestones and review day are data)",
)
async def create_protocol(body: ProtocolCreate, db: Database, ctx: Ctx) -> ProtocolOut:
    return await protocols.create_protocol(db, ctx, body)


@protocols_router.patch(
    "/protocols/{protocol_id}", response_model=ProtocolOut, summary="Edit milestones, review day, window"
)
async def update_protocol(protocol_id: UUID, body: ProtocolUpdate, db: Database, ctx: Ctx) -> ProtocolOut:
    return await protocols.update_protocol(db, ctx, protocol_id, body)

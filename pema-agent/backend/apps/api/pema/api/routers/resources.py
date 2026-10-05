"""Doctors, rooms and room blocks, and the before/after photo studio (package U, step U4)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import resources, studio
from pema_contracts.catalog import (
    ResourcesOut,
    RoomBlockCreate,
    RoomBlockOut,
    RoomCreate,
    RoomOut,
    RoomUpdate,
    StudioOut,
)

router = APIRouter(tags=["resources"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])
studio_router = APIRouter(tags=["studio"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])


@router.get(
    "/resources",
    response_model=ResourcesOut,
    summary="Doctors (account + shift of care staff + load of the day), rooms and room blocks",
)
async def get_resources(
    db: Database,
    ctx: Ctx,
    day: Annotated[date | None, Query(description="Day of the load; default today (+07:00).")] = None,
) -> ResourcesOut:
    return await resources.list_resources(db, ctx, day=day)


@router.post(
    "/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED, summary="Add a treatment room"
)
async def create_room(body: RoomCreate, db: Database, ctx: Ctx) -> RoomOut:
    return await resources.create_room(db, ctx, body)


@router.patch("/rooms/{room_id}", response_model=RoomOut, summary="Rename, resize or (de)activate a room")
async def update_room(room_id: UUID, body: RoomUpdate, db: Database, ctx: Ctx) -> RoomOut:
    return await resources.update_room(db, ctx, room_id, body)


@router.post(
    "/room-blocks",
    response_model=RoomBlockOut,
    status_code=status.HTTP_201_CREATED,
    summary="Block a room for a window of a day (08:00-18:00, with a reason)",
)
async def create_room_block(body: RoomBlockCreate, db: Database, ctx: Ctx) -> RoomBlockOut:
    return await resources.add_block(db, ctx, body)


@router.delete(
    "/room-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a room block"
)
async def delete_room_block(block_id: UUID, db: Database, ctx: Ctx) -> Response:
    await resources.remove_block(db, ctx, block_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@studio_router.get(
    "/studio/{patient_id}",
    response_model=StudioOut,
    summary="Before/after studio of one patient (views, media consent, milestone photos)",
)
async def get_studio(
    patient_id: UUID,
    db: Database,
    ctx: Ctx,
    view: Annotated[str | None, Query(description="One of the studio views; default the first.")] = None,
) -> StudioOut:
    return await studio.get_studio(db, ctx, patient_id, view=view)

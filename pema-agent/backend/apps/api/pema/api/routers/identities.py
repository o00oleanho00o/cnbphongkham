"""Channel identities and the roster of who covers them (package O, step O1).

``GET /identities`` and the roster reads are for every operator (owner, manager, doctor, cs_staff: the Inbox
filters by identity and shows who is on duty); changing an identity (``PATCH /identities/{id}``) and every
roster write belong to the owner and the manager. The routes never return a credential: ``IdentityOut`` has
no such field (``tests/ops/test_credential_boundary.py``). QR login, bot tokens and friends stay under
``/admin/accounts``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response, Security, status

from pema.api.dashboard_auth import Ctx, Database
from pema.api.deps import ERROR_RESPONSES, cookie_scheme
from pema.clinic.actions import _common, identities, roster
from pema_contracts.ops import (
    IdentityOut,
    IdentityUpdate,
    OnDutyOut,
    RosterEntryCreate,
    RosterEntryOut,
    RosterEntryUpdate,
)

router = APIRouter(tags=["identities"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])
roster_router = APIRouter(tags=["roster"], responses=ERROR_RESPONSES, dependencies=[Security(cookie_scheme)])


@router.get(
    "/identities",
    response_model=list[IdentityOut],
    summary="Channel accounts as clinic identities: purpose, state, send limits",
    description=(
        "Customer-facing identities first, then the internal notifier. Each row carries the purpose, whether "
        "the account and its channel are enabled, the per-identity overrides and the limits that really "
        "apply (override, else the channel row). No credential, cookie, QR payload or token is ever returned."
    ),
)
async def list_identities(db: Database, ctx: Ctx) -> list[IdentityOut]:
    return await identities.list_identities(db, ctx)


@router.patch(
    "/identities/{account_id}",
    response_model=IdentityOut,
    summary="Set the purpose, label and send limits of one identity",
    description=(
        "Owner and manager. A limit sent as null clears its override (the channel row applies again). "
        "Moving an account to `internal` is refused while a conversation or a roster entry still points at "
        "it."
    ),
)
async def update_identity(account_id: str, body: IdentityUpdate, db: Database, ctx: Ctx) -> IdentityOut:
    return await identities.update_identity_settings(db, ctx, account_id, body)


@router.get(
    "/identities/{account_id}/on-duty",
    response_model=OnDutyOut,
    summary="Who covers one identity at a moment",
)
async def identity_on_duty(
    account_id: str,
    db: Database,
    ctx: Ctx,
    at: Annotated[datetime | None, Query(description="The moment to look at; default now.")] = None,
) -> OnDutyOut:
    return await roster.on_duty(db, ctx, account_id, at or _common.now())


@roster_router.get(
    "/roster",
    response_model=list[RosterEntryOut],
    summary="Roster entries: who covers which identity, when",
)
async def list_roster(
    db: Database,
    ctx: Ctx,
    account_id: Annotated[str | None, Query(description="Only the entries of this identity.")] = None,
    user_id: Annotated[UUID | None, Query(description="Only the entries of this operator.")] = None,
) -> list[RosterEntryOut]:
    return await roster.list_roster(db, ctx, account_id=account_id, user_id=user_id)


@roster_router.post(
    "/roster",
    response_model=RosterEntryOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add a roster entry (owner, manager)",
)
async def create_roster_entry(body: RosterEntryCreate, db: Database, ctx: Ctx) -> RosterEntryOut:
    return await roster.create_entry(db, ctx, body)


@roster_router.patch("/roster/{entry_id}", response_model=RosterEntryOut, summary="Change a roster entry")
async def update_roster_entry(
    entry_id: UUID, body: RosterEntryUpdate, db: Database, ctx: Ctx
) -> RosterEntryOut:
    return await roster.update_entry(db, ctx, entry_id, body)


@roster_router.delete(
    "/roster/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a roster entry"
)
async def delete_roster_entry(entry_id: UUID, db: Database, ctx: Ctx) -> Response:
    await roster.delete_entry(db, ctx, entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

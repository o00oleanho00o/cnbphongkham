# ported from: prototype/shared/operations-data.js (updateService, services) and
# prototype/finance_server.py (mutate 'rate': a rate or basis change bumps the service version)
"""The service catalog: what the clinic sells, for how long, at what price and with which commission terms.

Forced deviations from the JavaScript:

* The prototype kept two copies of the catalog (operations: price, duration, buffer, rooms; finance: rate,
  basis, version) in two ``localStorage`` states. Here it is one row (``clinic.service``) plus append-only
  snapshots of the terms (``clinic.service_version``).
* The prototype overwrote the price in place and bumped ``version`` only for a rate change. Here a change of
  price, rate, basis, duration or buffer inserts the NEXT snapshot and the old ones stay readable: a booking
  or a finance entry made under version N keeps the terms of version N ("Lịch đã đặt giữ giá và thời lượng tại
  lúc đặt"; PB02 rate snapshots). Name, active flag, protocol and rooms are plain edits of the service row.
* ``updateService`` limited the duration to 15-180 minutes and the buffer to 0-60; the contract keeps 5-480
  and 0-120 (the database bounds) and the FE form keeps the prototype's narrower numbers.

Permissions (ARCH-PB01, "Quản trị catalog/role": manager, owner): everybody who may see the schedule reads the
list (``appointment.read``); changes need ``admin.rules``. The commission ``rate_bp`` and ``basis`` are
payroll terms and are returned only to ``admin.rules`` holders.
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import check_version, lost_race_is_conflict, not_found
from pema.clinic.models import Protocol, Room, Service, ServiceVersion
from pema.clinic.rbac import has_permission, require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.catalog import (
    ServiceBasis,
    ServiceCreate,
    ServiceDetailOut,
    ServiceOut,
    ServiceTermsOut,
    ServiceUpdate,
)
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import Permission

READ_PERMISSIONS = (Permission.APPOINTMENT_READ, Permission.ADMIN_RULES)


def _payroll_visible(ctx: ActionContext) -> bool:
    return has_permission(ctx, Permission.ADMIN_RULES)


def terms_out(row: ServiceVersion, *, payroll: bool) -> ServiceTermsOut:
    return ServiceTermsOut(
        version_no=row.version_no,
        price_vnd=row.price_vnd,
        rate_bp=row.rate_bp if payroll else None,
        basis=ServiceBasis(row.basis) if payroll else None,
        duration_min=row.duration_min,
        buffer_min=row.buffer_min,
        changed_by=row.changed_by,
        created_at=row.created_at,
    )


def service_out(service: Service, terms: ServiceVersion, *, payroll: bool) -> ServiceOut:
    return ServiceOut(
        id=service.id,
        code=service.code,
        name=service.name,
        active=service.active,
        protocol_code=service.protocol_code,
        room_ids=list(service.room_ids),
        price_vnd=terms.price_vnd,
        rate_bp=terms.rate_bp if payroll else None,
        basis=ServiceBasis(terms.basis) if payroll else None,
        duration_min=terms.duration_min,
        buffer_min=terms.buffer_min,
        terms_version=service.terms_version,
        version=service.version,
    )


async def _load(session: AsyncSession, ctx: ActionContext, service_id: UUID) -> Service:
    row = await session.scalar(
        select(Service).where(Service.id == service_id, Service.clinic_id == ctx.clinic_id)
    )
    if row is None:
        raise not_found("dịch vụ")
    return row


async def terms_snapshot(
    session: AsyncSession, clinic_id: UUID, service_id: UUID, version_no: int | None = None
) -> ServiceVersion:
    """The terms of a service as they were in ``version_no`` (the current ones when omitted). Orders and
    finance entries call this with the version they stored, never with "now"."""
    query = select(ServiceVersion).where(
        ServiceVersion.clinic_id == clinic_id, ServiceVersion.service_id == service_id
    )
    if version_no is None:
        query = query.order_by(ServiceVersion.version_no.desc()).limit(1)
    else:
        query = query.where(ServiceVersion.version_no == version_no)
    row = await session.scalar(query)
    if row is None:
        raise not_found("phiên bản điều khoản dịch vụ")
    return row


async def _current_terms(
    session: AsyncSession, ctx: ActionContext, services: Sequence[Service]
) -> dict[UUID, ServiceVersion]:
    if not services:
        return {}
    rows = (
        await session.scalars(
            select(ServiceVersion).where(
                ServiceVersion.clinic_id == ctx.clinic_id,
                ServiceVersion.service_id.in_([s.id for s in services]),
            )
        )
    ).all()
    wanted = {s.id: s.terms_version for s in services}
    return {r.service_id: r for r in rows if wanted.get(r.service_id) == r.version_no}


async def _check_links(
    session: AsyncSession, ctx: ActionContext, *, protocol_code: str | None, room_ids: Sequence[UUID]
) -> None:
    if protocol_code is not None:
        found = await session.scalar(
            select(Protocol.id).where(Protocol.clinic_id == ctx.clinic_id, Protocol.code == protocol_code)
        )
        if found is None:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Giao thức theo dõi không tồn tại.")
    if room_ids:
        rooms = set(
            (
                await session.scalars(
                    select(Room.id).where(Room.clinic_id == ctx.clinic_id, Room.id.in_(list(room_ids)))
                )
            ).all()
        )
        if rooms != set(room_ids):
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Có phòng không tồn tại trong danh sách phòng.")


async def list_services(
    db: ClinicDatabase, ctx: ActionContext, *, active: bool | None = None
) -> list[ServiceOut]:
    require_any(ctx, READ_PERMISSIONS)
    payroll = _payroll_visible(ctx)
    async with db.session() as session:
        query = select(Service).where(Service.clinic_id == ctx.clinic_id).order_by(Service.name, Service.code)
        if active is not None:
            query = query.where(Service.active.is_(active))
        services = (await session.scalars(query)).all()
        terms = await _current_terms(session, ctx, services)
        return [service_out(s, terms[s.id], payroll=payroll) for s in services if s.id in terms]


async def get_service(db: ClinicDatabase, ctx: ActionContext, service_id: UUID) -> ServiceDetailOut:
    require_any(ctx, READ_PERMISSIONS)
    payroll = _payroll_visible(ctx)
    async with db.session() as session:
        service = await _load(session, ctx, service_id)
        history = (
            await session.scalars(
                select(ServiceVersion)
                .where(ServiceVersion.clinic_id == ctx.clinic_id, ServiceVersion.service_id == service.id)
                .order_by(ServiceVersion.version_no.desc())
            )
        ).all()
        current = next((h for h in history if h.version_no == service.terms_version), None)
        if current is None:
            raise not_found("điều khoản dịch vụ")
        base = service_out(service, current, payroll=payroll)
        return ServiceDetailOut(**base.model_dump(), history=[terms_out(h, payroll=payroll) for h in history])


async def create_service(db: ClinicDatabase, ctx: ActionContext, payload: ServiceCreate) -> ServiceOut:
    require(ctx, Permission.ADMIN_RULES)
    async with db.session() as session:
        await _check_links(session, ctx, protocol_code=payload.protocol_code, room_ids=payload.room_ids)
        service = Service(
            clinic_id=ctx.clinic_id,
            code=payload.code,
            name=payload.name,
            active=payload.active,
            protocol_code=payload.protocol_code,
            room_ids=list(payload.room_ids),
            terms_version=1,
        )
        terms = ServiceVersion(
            clinic_id=ctx.clinic_id,
            version_no=1,
            price_vnd=payload.price_vnd,
            rate_bp=payload.rate_bp,
            basis=payload.basis.value,
            duration_min=payload.duration_min,
            buffer_min=payload.buffer_min,
            changed_by=ctx.actor_user_id,
        )
        try:
            async with session.begin_nested():
                session.add(service)
                await session.flush()
                terms.service_id = service.id
                session.add(terms)
                await session.flush()
        except IntegrityError as exc:
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Mã dịch vụ đã tồn tại.") from exc
        await audit.record(
            session,
            ctx,
            "service.create",
            "service",
            service.id,
            {"code": service.code, "terms_version": 1, "active": service.active},
        )
        await session.refresh(terms)
        return service_out(service, terms, payroll=True)


async def update_service(
    db: ClinicDatabase, ctx: ActionContext, service_id: UUID, payload: ServiceUpdate
) -> ServiceOut:
    """Edit a service. Any change of the terms inserts the next snapshot; the number of the current snapshot
    moves with it, in the same transaction, so a reader never sees a snapshot that is not the current one."""
    require(ctx, Permission.ADMIN_RULES)
    sent = payload.model_fields_set
    async with db.session() as session:
        service = await _load(session, ctx, service_id)
        check_version(service.version, payload.version)
        current = await terms_snapshot(session, ctx.clinic_id, service.id, service.terms_version)
        if "protocol_code" in sent or payload.room_ids is not None:
            await _check_links(
                session,
                ctx,
                protocol_code=payload.protocol_code if "protocol_code" in sent else None,
                room_ids=payload.room_ids or [],
            )

        changed: list[str] = []
        if payload.name is not None and payload.name != service.name:
            service.name = payload.name
            changed.append("name")
        if payload.active is not None and payload.active != service.active:
            service.active = payload.active
            changed.append("active")
        if "protocol_code" in sent and payload.protocol_code != service.protocol_code:
            service.protocol_code = payload.protocol_code
            changed.append("protocol_code")
        if payload.room_ids is not None and set(payload.room_ids) != set(service.room_ids):
            service.room_ids = list(payload.room_ids)
            changed.append("room_ids")

        price = current.price_vnd if payload.price_vnd is None else payload.price_vnd
        rate = current.rate_bp if payload.rate_bp is None else payload.rate_bp
        basis = current.basis if payload.basis is None else payload.basis.value
        duration = current.duration_min if payload.duration_min is None else payload.duration_min
        buffer = current.buffer_min if payload.buffer_min is None else payload.buffer_min
        term_changes = [
            field
            for field, before, after in (
                ("price_vnd", current.price_vnd, price),
                ("rate_bp", current.rate_bp, rate),
                ("basis", current.basis, basis),
                ("duration_min", current.duration_min, duration),
                ("buffer_min", current.buffer_min, buffer),
            )
            if before != after
        ]
        new_terms: ServiceVersion | None = None
        if term_changes:
            service.terms_version = current.version_no + 1
            new_terms = ServiceVersion(
                clinic_id=ctx.clinic_id,
                service_id=service.id,
                version_no=service.terms_version,
                price_vnd=price,
                rate_bp=rate,
                basis=basis,
                duration_min=duration,
                buffer_min=buffer,
                changed_by=ctx.actor_user_id,
            )
            session.add(new_terms)
            changed.extend(term_changes)

        if not changed:
            return service_out(service, current, payroll=True)
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "service.update",
            "service",
            service.id,
            {
                "changed_fields": changed,
                "terms_version": service.terms_version,
                "new_terms_version": new_terms is not None,
            },
        )
        return service_out(service, new_terms or current, payroll=True)

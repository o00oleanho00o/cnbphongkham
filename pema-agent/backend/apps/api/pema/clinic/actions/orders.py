# ported from: prototype/shared/order-data.js (saveOrder, approveOrder, orderPrintData)
"""Quick orders: a draft of prescription and consultation lines made by the cashier, approved by the doctor,
then printed on A5 sheets (Đơn thuốc, Phiếu tư vấn).

Forced deviations from the JavaScript (everything lived in ``localStorage`` per patient):

* an order is a row of ``clinic.order`` with lines in ``clinic.order_item`` (a snapshot of name, unit, route
  and price per line); ``version`` is the optimistic lock and also what the prototype counted: 1 at
  creation, +1 on every save and on the approval;
* the prototype created an invoice with every save and refused an edit "Đơn đã thu tiền hoặc thiếu hóa đơn".
  Invoices belong to step U6 (``actions.finance_cash``): the order carries ``invoice_id`` (set when the
  cashier raises the invoice) and the mirror ``received_vnd`` / ``paid`` that a receipt sets through
  ``set_payment_state``; a saved draft rewrites the amount of its invoice (``_invoices.sync_order_invoice``).
  An edit is refused as soon as money is received;
* the prototype let the page approve for ``order.doctor`` whoever held the "clinical" capability (owner or
  doctor). Here ``order.approve`` is held by the doctor and the owner; a doctor may approve only the orders of
  which he is the responsible doctor ("Bác sĩ duyệt phải là bác sĩ phụ trách đơn."), the owner any order;
* the doctor of an order must be an active ``doctor`` account ("Chọn bác sĩ trong danh sách.");
* an approved order is idempotent to approve again (returns it unchanged) and immutable otherwise
  ("Chỉ được sửa đơn nháp còn tồn tại.").

Rules kept as they were: the catalog route is the default, any other route needs a reason; a saved line keeps
the name, unit and price of the draft it was first saved in (a later catalog import changes nothing); approval
needs every line classified, a usage on every printed line, a diagnosis and at least one printed line; a draft
cannot be printed.

Permissions: ``order.read`` / ``order.write`` / ``order.approve`` (``rbac.matrix``), narrowed for a doctor to
the patients he owns or is scheduled for. Audit details carry ids, counts and field names, never the
diagnosis, the note or a usage text.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes

from pema.clinic import audit
from pema.clinic.actions._common import lost_race_is_conflict, not_found, now
from pema.clinic.actions._invoices import sync_order_invoice
from pema.clinic.actions._scope import patient_scope, require_patient_access
from pema.clinic.actions.catalog import load_products
from pema.clinic.actions.patients import load_patient
from pema.clinic.domain.orders import (
    DRAFT_NOT_APPROVED_MESSAGE,
    NO_DIAGNOSIS_MESSAGE,
    ROUTES,
    UNRESOLVED,
    lines_are_complete,
    split_by_route,
    validate_lines_for_approval,
    validation_error,
)
from pema.clinic.models import Order, OrderItem, Patient, Product, UserAccount
from pema.clinic.rbac import is_role, require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.common import VN_TZ, Page
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.orders import (
    ApprovedOrderGroupOut,
    OrderApprove,
    OrderCreate,
    OrderItemIn,
    OrderItemOut,
    OrderOut,
    OrderPatientOut,
    OrderPrintOut,
    OrderRoute,
    OrderStatus,
    OrderSummaryOut,
    OrderUpdate,
)
from pema_contracts.patients import Gender
from pema_contracts.roles import Permission, Role

READ_PERMISSIONS = (Permission.ORDER_READ, Permission.ORDER_WRITE)
STALE_MESSAGE = "Đơn đã thay đổi ở cửa sổ khác. Hãy mở lại."
ONLY_DRAFTS_MESSAGE = "Chỉ được sửa đơn nháp còn tồn tại."
PAID_MESSAGE = "Đơn đã thu tiền; không thể sửa."
CANNOT_APPROVE_MESSAGE = "Đơn không thể duyệt."
WRONG_DOCTOR_MESSAGE = "Bác sĩ duyệt phải là bác sĩ phụ trách đơn."
PICK_DOCTOR_MESSAGE = "Chọn bác sĩ trong danh sách."


# ------------------------------------------------------------------------------------------- mapping
def item_out(row: OrderItem) -> OrderItemOut:
    return OrderItemOut(
        line_no=row.line_no,
        product_code=row.product_code,
        name=row.name,
        source_type=row.source_type,
        unit=row.unit,
        catalog_route=OrderRoute(row.catalog_route),
        route=OrderRoute(row.route),
        route_reason=row.route_reason,
        quantity=row.quantity,
        unit_price_vnd=row.unit_price_vnd,
        usage=row.usage,
        note=row.note,
    )


def _editable(order: Order) -> bool:
    return order.status == OrderStatus.DRAFT.value and order.received_vnd == 0 and not order.paid


async def _names(session: AsyncSession, ctx: ActionContext, ids: Sequence[UUID | None]) -> dict[UUID, str]:
    wanted = {i for i in ids if i is not None}
    if not wanted:
        return {}
    rows = await session.execute(
        select(UserAccount.id, UserAccount.display_name).where(
            UserAccount.clinic_id == ctx.clinic_id, UserAccount.id.in_(wanted)
        )
    )
    return {row.id: row.display_name for row in rows}


def _summary(order: Order, patient: Patient, names: dict[UUID, str], item_count: int) -> OrderSummaryOut:
    return OrderSummaryOut(
        id=order.id,
        patient_id=order.patient_id,
        patient_code=patient.code,
        patient_name=patient.full_name,
        doctor_id=order.doctor_id,
        doctor_name=names.get(order.doctor_id, ""),
        status=OrderStatus(order.status),
        order_date=order.order_date,
        item_count=item_count,
        total_vnd=order.total_vnd,
        reviewed_by_name=names.get(order.reviewed_by) if order.reviewed_by else None,
        reviewed_at=order.reviewed_at,
        created_at=order.created_at,
        version=order.version,
    )


async def _items(session: AsyncSession, ctx: ActionContext, order_id: UUID) -> list[OrderItem]:
    return list(
        (
            await session.scalars(
                select(OrderItem)
                .where(OrderItem.clinic_id == ctx.clinic_id, OrderItem.order_id == order_id)
                .order_by(OrderItem.line_no)
            )
        ).all()
    )


async def _order_out(session: AsyncSession, ctx: ActionContext, order: Order) -> OrderOut:
    patient = await load_patient(session, ctx, order.patient_id)
    rows = await _items(session, ctx, order.id)
    names = await _names(session, ctx, [order.doctor_id, order.reviewed_by])
    views = [item_out(r) for r in rows]
    unresolved = sum(1 for r in rows if r.route == UNRESOLVED)
    return OrderOut(
        **_summary(order, patient, names, len(rows)).model_dump(),
        diagnosis=order.diagnosis,
        note=order.note,
        items=views,
        received_vnd=order.received_vnd,
        paid=order.paid,
        invoice_id=order.invoice_id,
        editable=_editable(order),
        unresolved_count=unresolved,
        ready_to_approve=bool(order.diagnosis.strip()) and lines_are_complete(views),
    )


async def _load_order(session: AsyncSession, ctx: ActionContext, order_id: UUID) -> Order:
    row = await session.scalar(select(Order).where(Order.id == order_id, Order.clinic_id == ctx.clinic_id))
    if row is None:
        raise not_found("đơn")
    if not _is_order_doctor(
        ctx, row
    ):  # the responsible doctor opens the order whatever the patient scope says
        await require_patient_access(session, ctx, row.patient_id)
    return row


def _is_order_doctor(ctx: ActionContext, order: Order) -> bool:
    return is_role(ctx, Role.DOCTOR) and ctx.actor_user_id == order.doctor_id


def _today() -> date:
    return now().astimezone(VN_TZ).date()


def _age(birth: date | None) -> int | None:
    if birth is None:
        return None
    today = _today()
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


# --------------------------------------------------------------------------------------------- lines
async def _doctor(session: AsyncSession, ctx: ActionContext, doctor_id: UUID | None) -> UUID:
    if doctor_id is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, PICK_DOCTOR_MESSAGE)
    found = await session.scalar(
        select(UserAccount.id).where(
            UserAccount.clinic_id == ctx.clinic_id,
            UserAccount.id == doctor_id,
            UserAccount.role == Role.DOCTOR.value,
            UserAccount.active.is_(True),
        )
    )
    if found is None:
        raise DomainError(ErrorCode.VALIDATION_FAILED, PICK_DOCTOR_MESSAGE)
    return doctor_id


def _build_lines(
    order_id: UUID,
    ctx: ActionContext,
    items: Sequence[OrderItemIn],
    products: dict[str, Product],
    previous: dict[str, OrderItem],
) -> list[OrderItem]:
    """``saveOrder``: the catalog (or the snapshot of the draft) decides name, unit, type and price."""
    lines: list[OrderItem] = []
    for index, line in enumerate(items, start=1):
        code = line.product_code.strip().upper()
        product = products.get(code)
        before = previous.get(code)
        if product is None and before is None:
            raise validation_error(f"Dòng {index}: chọn sản phẩm từ catalog.")
        catalog_route = before.catalog_route if before else (product.route if product else UNRESOLVED)
        route = line.route.value if line.route is not None else catalog_route
        if route not in ROUTES:
            raise validation_error(f"Dòng {index}: phân loại không hợp lệ.")
        reason = line.route_reason.strip()
        if route != catalog_route and not reason:
            raise validation_error(f"Dòng {index}: ghi lý do thay đổi phân loại.")
        source = before or product
        if source is None:  # unreachable: guarded above
            raise validation_error(f"Dòng {index}: chọn sản phẩm từ catalog.")
        lines.append(
            OrderItem(
                clinic_id=ctx.clinic_id,
                order_id=order_id,
                line_no=index,
                product_code=code,
                name=source.name,
                source_type=source.source_type,
                unit=source.unit,
                row_number=source.row_number,
                catalog_route=catalog_route,
                route=route,
                route_reason=reason,
                quantity=line.quantity,
                unit_price_vnd=before.unit_price_vnd if before else (product.price_vnd if product else 0),
                usage=line.usage.strip(),
                note=line.note.strip(),
            )
        )
    return lines


def _last_catalog_hash(products: dict[str, Product], lines: Sequence[OrderItem]) -> str | None:
    hashes = {products[x.product_code].catalog_hash for x in lines if x.product_code in products}
    return sorted(hashes)[-1] if hashes else None


# ------------------------------------------------------------------------------------------- actions
async def create_draft(db: ClinicDatabase, ctx: ActionContext, payload: OrderCreate) -> OrderOut:
    require(ctx, Permission.ORDER_WRITE)
    async with db.session() as session:
        patient = await load_patient(session, ctx, payload.patient_id)
        await require_patient_access(session, ctx, patient.id)
        products = {p.code: p for p in await load_products(session, ctx)}
        order_id = uuid4()
        doctor_id = await _doctor(session, ctx, payload.doctor_id or patient.doctor_id)
        lines = _build_lines(order_id, ctx, payload.items, products, {})
        order = Order(
            id=order_id,
            clinic_id=ctx.clinic_id,
            patient_id=patient.id,
            doctor_id=doctor_id,
            status=OrderStatus.DRAFT.value,
            order_date=_today(),
            diagnosis=payload.diagnosis.strip(),
            note=payload.note.strip(),
            total_vnd=sum(x.quantity * x.unit_price_vnd for x in lines),
            catalog_hash=_last_catalog_hash(products, lines),
            created_by=ctx.actor_user_id,
        )
        session.add(order)
        await session.flush()  # the order row first: the lines reference it
        session.add_all(lines)
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "order.create_draft",
            "order",
            order.id,
            {"patient_id": str(patient.id), "item_count": len(lines), "total_vnd": order.total_vnd},
        )
        return await _order_out(session, ctx, order)


async def update_draft(
    db: ClinicDatabase, ctx: ActionContext, order_id: UUID, payload: OrderUpdate
) -> OrderOut:
    require(ctx, Permission.ORDER_WRITE)
    async with db.session() as session:
        order = await _load_order(session, ctx, order_id)
        if order.status != OrderStatus.DRAFT.value:
            raise DomainError(ErrorCode.INVALID_STATE, ONLY_DRAFTS_MESSAGE)
        if payload.version != order.version:
            raise DomainError(
                ErrorCode.VERSION_CONFLICT, STALE_MESSAGE, details={"current_version": order.version}
            )
        products = {p.code: p for p in await load_products(session, ctx)}
        old = await _items(session, ctx, order.id)
        previous = {x.product_code: x for x in old}
        lines = _build_lines(order.id, ctx, payload.items, products, previous)
        doctor_id = await _doctor(session, ctx, payload.doctor_id or order.doctor_id)
        if not _editable(order):
            raise DomainError(ErrorCode.INVALID_STATE, PAID_MESSAGE)
        order.doctor_id = doctor_id
        for row in old:
            await session.delete(row)
        await session.flush()
        session.add_all(lines)
        order.diagnosis = payload.diagnosis.strip()
        order.note = payload.note.strip()
        order.total_vnd = sum(x.quantity * x.unit_price_vnd for x in lines)
        order.catalog_hash = _last_catalog_hash(products, lines) or order.catalog_hash
        attributes.flag_modified(order, "note")  # every save counts as a version, as in the prototype
        with lost_race_is_conflict():
            await session.flush()
        invoice_synced = await sync_order_invoice(session, ctx, order)  # the invoice follows the total (U6)
        await audit.record(
            session,
            ctx,
            "order.update_draft",
            "order",
            order.id,
            {
                "item_count": len(lines),
                "total_vnd": order.total_vnd,
                "version": order.version,
                "invoice_synced": invoice_synced,
            },
        )
        return await _order_out(session, ctx, order)


async def approve(db: ClinicDatabase, ctx: ActionContext, order_id: UUID, payload: OrderApprove) -> OrderOut:
    require(ctx, Permission.ORDER_APPROVE)
    async with db.session() as session:
        order = await _load_order(session, ctx, order_id)
        if order.status == OrderStatus.APPROVED.value:
            return await _order_out(session, ctx, order)
        if order.status != OrderStatus.DRAFT.value:
            raise DomainError(ErrorCode.INVALID_STATE, CANNOT_APPROVE_MESSAGE)
        if is_role(ctx, Role.DOCTOR) and ctx.actor_user_id != order.doctor_id:
            raise DomainError(ErrorCode.FORBIDDEN, WRONG_DOCTOR_MESSAGE)
        if payload.version != order.version:
            raise DomainError(
                ErrorCode.VERSION_CONFLICT, STALE_MESSAGE, details={"current_version": order.version}
            )
        lines = await _items(session, ctx, order.id)
        validate_lines_for_approval([item_out(r) for r in lines])
        if not order.diagnosis.strip():
            raise validation_error(NO_DIAGNOSIS_MESSAGE)
        order.status = OrderStatus.APPROVED.value
        order.reviewed_by = ctx.actor_user_id
        order.reviewed_at = now()
        with lost_race_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "order.approve",
            "order",
            order.id,
            {"patient_id": str(order.patient_id), "item_count": len(lines), "version": order.version},
        )
        return await _order_out(session, ctx, order)


async def get_order(db: ClinicDatabase, ctx: ActionContext, order_id: UUID) -> OrderOut:
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        return await _order_out(session, ctx, await _load_order(session, ctx, order_id))


async def list_orders(
    db: ClinicDatabase,
    ctx: ActionContext,
    *,
    patient_id: UUID | None = None,
    status: OrderStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Page[OrderSummaryOut]:
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        base = (
            select(Order, Patient)
            .join(Patient, (Patient.clinic_id == Order.clinic_id) & (Patient.id == Order.patient_id))
            .where(Order.clinic_id == ctx.clinic_id)
        )
        scope = patient_scope(ctx)
        if scope is not None:
            base = base.where(or_(scope, Order.doctor_id == ctx.actor_user_id))
        if patient_id is not None:
            base = base.where(Order.patient_id == patient_id)
        if status is not None:
            base = base.where(Order.status == status.value)
        total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
        rows = (
            await session.execute(
                base.order_by(Order.created_at.desc(), Order.id).limit(limit).offset(offset)
            )
        ).all()
        ids = [order.id for order, _ in rows]
        counts: dict[UUID, int] = {}
        if ids:
            counted = await session.execute(
                select(OrderItem.order_id, func.count())
                .where(OrderItem.clinic_id == ctx.clinic_id, OrderItem.order_id.in_(ids))
                .group_by(OrderItem.order_id)
            )
            counts = {row[0]: int(row[1]) for row in counted}
        names = await _names(
            session, ctx, [x for order, _ in rows for x in (order.doctor_id, order.reviewed_by)]
        )
        items = [_summary(order, patient, names, counts.get(order.id, 0)) for order, patient in rows]
    return Page[OrderSummaryOut](items=items, total=total, limit=limit, offset=offset)


async def print_data(
    db: ClinicDatabase, ctx: ActionContext, order_id: UUID, *, require_approved: bool = False
) -> OrderPrintOut:
    """``orderPrintData``: the order, the patient and the lines split into the two sheets. With
    ``require_approved`` a draft or an incomplete order is refused ("Đơn nháp cần bác sĩ duyệt trước khi
    in.")."""
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        order = await _load_order(session, ctx, order_id)
        rows = await _items(session, ctx, order.id)
        complete = lines_are_complete([item_out(r) for r in rows])
        if require_approved:
            validate_lines_for_approval([item_out(r) for r in rows])
            if order.status != OrderStatus.APPROVED.value:
                raise DomainError(ErrorCode.INVALID_STATE, DRAFT_NOT_APPROVED_MESSAGE)
        patient = await load_patient(session, ctx, order.patient_id)
        out = await _order_out(session, ctx, order)
    split = split_by_route(out.items)
    return OrderPrintOut(
        order=out,
        patient=OrderPatientOut(
            code=patient.code,
            full_name=patient.full_name,
            age=_age(patient.birth_date),
            gender=Gender(patient.gender) if patient.gender in {g.value for g in Gender} else Gender.UNKNOWN,
        ),
        prescription=split.prescription,
        consultation=split.consultation,
        excluded=split.excluded,
        unresolved=split.unresolved,
        printable=complete and order.status == OrderStatus.APPROVED.value,
    )


async def approved_for_patient(
    db: ClinicDatabase, ctx: ActionContext, patient_id: UUID
) -> list[ApprovedOrderGroupOut]:
    """What the patient app shows for this patient (a preview for staff; the patient-facing exposure is a
    later step): approved orders only, the lines grouped as Đơn thuốc and Phiếu tư vấn; "Không in" and
    unclassified lines never appear."""
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        patient = await load_patient(session, ctx, patient_id)
        await require_patient_access(session, ctx, patient.id)
        orders = (
            await session.scalars(
                select(Order)
                .where(
                    Order.clinic_id == ctx.clinic_id,
                    Order.patient_id == patient_id,
                    Order.status == OrderStatus.APPROVED.value,
                )
                .order_by(Order.reviewed_at.desc(), Order.id)
            )
        ).all()
        names = await _names(session, ctx, [o.doctor_id for o in orders])
        groups: list[ApprovedOrderGroupOut] = []
        for order in orders:
            lines = [item_out(r) for r in await _items(session, ctx, order.id)]
            split = split_by_route(lines)
            groups.append(
                ApprovedOrderGroupOut(
                    order_id=order.id,
                    order_date=order.order_date,
                    doctor_name=names.get(order.doctor_id, ""),
                    diagnosis=order.diagnosis,
                    note=order.note,
                    prescription=split.prescription,
                    consultation=split.consultation,
                    approved_at=order.reviewed_at,
                )
            )
        return groups


async def set_payment_state(
    session: AsyncSession,
    ctx: ActionContext,
    order_id: UUID,
    *,
    received_vnd: int,
    paid: bool,
    invoice_id: UUID | None = None,
) -> None:
    """The seam for step U6: the invoice of an order says how much was collected. It is not a REST route and
    never changes an approved order's content (the database refuses that). An order with money received can no
    longer be edited."""
    require(ctx, Permission.ORDER_WRITE)
    row = await session.scalar(select(Order).where(Order.id == order_id, Order.clinic_id == ctx.clinic_id))
    if row is None:
        raise not_found("đơn")
    row.received_vnd = received_vnd
    row.paid = paid
    if invoice_id is not None:
        row.invoice_id = invoice_id
    await audit.record(
        session,
        ctx,
        "order.payment_state",
        "order",
        row.id,
        {"received_vnd": received_vnd, "paid": paid},
    )

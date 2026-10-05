# ported from: prototype/finance_server.py (Finance.rows, Finance.view, mutate 'entry', 'approve', 'void',
# 'close', 'paid') and prototype/finance/finance.js (the overview, the commission table, the period actions)
"""PB02 finance, the performed-procedure side: the overview of a month, the commission table, recording /
approving / voiding a performed procedure, closing a month and confirming its payout, and the CSV export.

Forced deviations from the Python prototype (one JSON document in a SQLite table, role and doctor picked by
two request headers):

* the role projection comes from the signed-in user, not from a header. ``finance.read`` (owner, accountant)
  gets the clinic projection; ``finance.read_own`` (doctor; the owner too) gets only the rows where the caller
  performed, and never the collected cash, the debt, the invoices or the receipts. The owner may ask for the
  personal projection with ``scope=own`` ("BS. Tâm · Bác sĩ điều trị"); a doctor can never ask for the
  clinic one;
* the accountant has no role of its own in this system: the manager holds ``finance.read`` /
  ``finance.write``;
* performers are user accounts of role doctor or owner; the prototype's fixed ``D0``..``D3`` are gone;
* a month is serialized with a Postgres advisory lock, taken by every action that changes an entry of the
  month and by the close, so an entry can never slip into a month while it is being frozen; the database
  also refuses a change of a closed month's entries (trigger) as a second line of defence;
* a closed month keeps a JSON snapshot of the whole commission table including the doctors' names, and reads
  of that month come from the snapshot;
* a service that is switched off cannot get a new entry; voiding the entry of an invoice it created sets that
  invoice to zero only when no other live entry is attached to it (the prototype zeroed it regardless);
* the prototype's ``audit`` list in ``view`` was never shown by the page; every mutation writes
  ``clinic.audit_log`` instead (ids, counts and field names, never the note, the reason or a name).

Money stays in the receipts side (``actions.finance_cash``). Audit actions: ``finance.entry.create``,
``finance.entry.approve``, ``finance.entry.void``, ``finance.period.close``, ``finance.period.pay``.
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import date
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.actions._common import lost_race_is_conflict, not_found, now
from pema.clinic.actions._invoices import invoice_number
from pema.clinic.actions.patients import load_patient
from pema.clinic.actions.services import terms_snapshot
from pema.clinic.finance import domain
from pema.clinic.finance.domain import EntryFacts, Person, Row
from pema.clinic.models import (
    FinancePeriod,
    Invoice,
    Patient,
    Payment,
    ProcedureEntry,
    ProcedureEntryPerson,
    Service,
    UserAccount,
)
from pema.clinic.rbac import has_permission, require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.catalog import ServiceBasis
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.finance import (
    EntryCreate,
    EntryOut,
    EntryPersonOut,
    EntryStatus,
    EntryVoid,
    FinanceDoctorOut,
    FinanceEntriesOut,
    FinanceOverviewOut,
    FinancePeriodOut,
    FinanceRowOut,
    FinanceScope,
    FinanceSummaryOut,
    FinanceTeamOut,
    PeriodListOut,
    PeriodPay,
    PeriodRowOut,
    PeriodStatus,
)
from pema_contracts.roles import Permission, Role

READ_PERMISSIONS = (Permission.FINANCE_READ, Permission.FINANCE_READ_OWN)
PERFORMER_ROLES = (Role.DOCTOR.value, Role.OWNER.value)
PERIOD_PAID_MESSAGE = "Kỳ đã xác nhận chi"
SERVICE_OFF_MESSAGE = "Thủ thuật đã ngừng, không ghi thêm lượt"
UNKNOWN_SERVICE_MESSAGE = "Không có thủ thuật"
HISTORY_MONTHS = 12
BYTE_ORDER_MARK = chr(0xFEFF)  # Excel reads the accents of a UTF-8 CSV only when it starts with one


def today() -> date:
    """The accounting day: Vietnam time, whatever the server's zone is."""
    return now().astimezone(VN_TZ).date()


def _invalid_state(message: str) -> DomainError:
    return DomainError(ErrorCode.INVALID_STATE, message)


@contextmanager
def closed_period_is_conflict() -> Generator[None]:
    """The trigger of a closed month raises when a change slips in after the close committed; same answer as
    the check the action makes first."""
    try:
        yield
    except DBAPIError as exc:
        if "finance period is closed" in str(exc.orig):
            raise _invalid_state(domain.PERIOD_CLOSED_MESSAGE) from exc
        raise


async def lock_month(session: AsyncSession, ctx: ActionContext, month: str) -> None:
    """Serialize the changes of one month of this clinic until the transaction ends."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"finance:{ctx.clinic_id}:{month}"},
    )


# ------------------------------------------------------------------------------------------------ scopes
def resolve_scope(ctx: ActionContext, requested: FinanceScope | None) -> FinanceScope:
    """Which projection the caller gets. The default is the widest one the caller holds."""
    require_any(ctx, READ_PERMISSIONS)
    clinic = has_permission(ctx, Permission.FINANCE_READ)
    if requested is None:
        return FinanceScope.CLINIC if clinic else FinanceScope.OWN
    if requested is FinanceScope.CLINIC:
        require(ctx, Permission.FINANCE_READ)
    else:
        require(ctx, Permission.FINANCE_READ_OWN)
        if ctx.actor_user_id is None:
            require(ctx, Permission.FINANCE_READ)  # an actor without a user has no "own"
    return requested


# ----------------------------------------------------------------------------------------------- loading
async def _names(session: AsyncSession, ctx: ActionContext, ids: Sequence[UUID]) -> dict[UUID, str]:
    if not ids:
        return {}
    rows = await session.execute(
        select(UserAccount.id, UserAccount.display_name).where(
            UserAccount.clinic_id == ctx.clinic_id, UserAccount.id.in_(set(ids))
        )
    )
    return {row.id: row.display_name for row in rows}


async def _performers(session: AsyncSession, ctx: ActionContext) -> list[FinanceDoctorOut]:
    rows = await session.execute(
        select(UserAccount.id, UserAccount.display_name)
        .where(
            UserAccount.clinic_id == ctx.clinic_id,
            UserAccount.active.is_(True),
            UserAccount.role.in_(PERFORMER_ROLES),
        )
        .order_by(UserAccount.display_name, UserAccount.id)
    )
    return [FinanceDoctorOut(id=row.id, name=row.display_name) for row in rows]


async def _facts(
    session: AsyncSession, ctx: ActionContext, first: date, last_exclusive: date, *, with_people: bool = True
) -> list[EntryFacts]:
    """The entries of ``[first, last_exclusive)`` with the invoice they belong to and who performed them."""
    rows = (
        await session.execute(
            select(ProcedureEntry, Patient.code, Invoice.amount_vnd, Invoice.received_vnd)
            .join(
                Patient,
                (Patient.clinic_id == ProcedureEntry.clinic_id) & (Patient.id == ProcedureEntry.patient_id),
            )
            .join(
                Invoice,
                (Invoice.clinic_id == ProcedureEntry.clinic_id) & (Invoice.id == ProcedureEntry.invoice_id),
            )
            .where(
                ProcedureEntry.clinic_id == ctx.clinic_id,
                ProcedureEntry.entry_date >= first,
                ProcedureEntry.entry_date < last_exclusive,
            )
            .order_by(ProcedureEntry.entry_date, ProcedureEntry.created_at, ProcedureEntry.id)
        )
    ).all()
    people: dict[UUID, list[Person]] = defaultdict(list)
    if with_people and rows:
        found = await session.scalars(
            select(ProcedureEntryPerson)
            .where(
                ProcedureEntryPerson.clinic_id == ctx.clinic_id,
                ProcedureEntryPerson.entry_id.in_([entry.id for entry, *_ in rows]),
            )
            .order_by(ProcedureEntryPerson.entry_id, ProcedureEntryPerson.position)
        )
        for person in found:
            people[person.entry_id].append(Person(person.doctor_id, person.share_bp, person.rate_bp))
    return [
        EntryFacts(
            id=entry.id,
            entry_date=entry.entry_date,
            patient_code=code,
            service_name=entry.service_name,
            status=entry.status,
            basis=entry.basis,
            list_vnd=entry.list_vnd,
            net_vnd=entry.net_vnd,
            note=entry.void_reason
            if entry.status == domain.STATUS_VOID and entry.void_reason
            else entry.note,
            invoice_amount_vnd=amount,
            invoice_received_vnd=received,
            people=tuple(people[entry.id]),
        )
        for entry, code, amount, received in rows
    ]


async def _period(session: AsyncSession, ctx: ActionContext, month: str) -> FinancePeriod | None:
    return await session.scalar(
        select(FinancePeriod).where(FinancePeriod.clinic_id == ctx.clinic_id, FinancePeriod.month == month)
    )


def _period_out(month: str, period: FinancePeriod | None) -> FinancePeriodOut:
    if period is None:
        return FinancePeriodOut(month=month, status=PeriodStatus.OPEN)
    return FinancePeriodOut(
        month=month,
        status=PeriodStatus(period.status),
        closed_at=period.closed_at,
        paid_at=period.paid_at,
        reference=period.reference,
    )


async def _month_rows(
    session: AsyncSession, ctx: ActionContext, month: str, period: FinancePeriod | None
) -> tuple[list[EntryFacts], list[tuple[Row, str]]]:
    """The facts of the month (live) and its commission rows with the doctors' names: from the snapshot when
    the month is closed (a closed month never reads the live rates, shares or receipts again), computed
    otherwise."""
    first = domain.parse_month(month)
    facts = await _facts(session, ctx, first, domain.next_month_start(first))
    if period is not None:
        return facts, domain.rows_from_snapshot(period.snapshot)
    rows = domain.compute_rows(facts)
    names = await _names(session, ctx, [r.doctor_id for r in rows])
    return facts, [(row, names.get(row.doctor_id, "")) for row in rows]


def _row_out(row: Row, doctor_name: str) -> FinanceRowOut:
    return FinanceRowOut(
        entry_id=row.entry_id,
        date=row.date,
        patient_code=row.patient_code,
        service_name=row.service_name,
        doctor_id=row.doctor_id,
        doctor_name=doctor_name,
        status=EntryStatus(row.status),
        basis=ServiceBasis(row.basis),
        base_vnd=row.base_vnd,
        rate_bp=row.rate_bp,
        share_bp=row.share_bp,
        revenue_vnd=row.revenue_vnd,
        fee_vnd=row.fee_vnd,
        note=row.note,
    )


def _projected(rows: list[tuple[Row, str]], scope: FinanceScope, ctx: ActionContext) -> list[tuple[Row, str]]:
    if scope is FinanceScope.CLINIC:
        return rows
    return [(row, name) for row, name in rows if row.doctor_id == ctx.actor_user_id]


# ------------------------------------------------------------------------------------------------ overview
async def overview(
    db: ClinicDatabase, ctx: ActionContext, month: str, scope: FinanceScope | None = None
) -> FinanceOverviewOut:
    """``Finance.view`` and the "Tổng quan" tab: four numbers, the team and what waits for the accountant."""
    chosen = resolve_scope(ctx, scope)
    first = domain.parse_month(month)
    after = domain.next_month_start(first)
    async with db.session() as session:
        period = await _period(session, ctx, month)
        facts, all_rows = await _month_rows(session, ctx, month, period)
        rows = _projected(all_rows, chosen, ctx)
        plain = [row for row, _ in rows]
        if chosen is FinanceScope.CLINIC:
            summary = domain.summarize(
                plain, entries_net_vnd=sum(e.net_vnd for e in facts if e.status != domain.STATUS_VOID)
            )
            collected = await session.scalar(
                select(func.coalesce(func.sum(Payment.amount_vnd), 0)).where(
                    Payment.clinic_id == ctx.clinic_id, Payment.paid_on >= first, Payment.paid_on < after
                )
            )
            debt = await session.scalar(
                select(func.coalesce(func.sum(Invoice.amount_vnd - Invoice.received_vnd), 0)).where(
                    Invoice.clinic_id == ctx.clinic_id
                )
            )
            out = FinanceSummaryOut(
                revenue_vnd=summary.revenue_vnd,
                fee_vnd=summary.fee_vnd,
                pending_vnd=summary.pending_vnd,
                collected_vnd=int(collected or 0),
                debt_vnd=int(debt or 0),
            )
            doctors = await _performers(session, ctx)
            known = {d.id for d in doctors}
            for row, name in rows:  # a doctor who left the clinic still has rows in an old month
                if row.doctor_id not in known:
                    known.add(row.doctor_id)
                    doctors.append(FinanceDoctorOut(id=row.doctor_id, name=name))
        else:
            summary = domain.summarize(plain)
            out = FinanceSummaryOut(
                revenue_vnd=summary.revenue_vnd, fee_vnd=summary.fee_vnd, pending_vnd=summary.pending_vnd
            )
            me = ctx.actor_user_id
            names = await _names(session, ctx, [me] if me else [])
            doctors = [FinanceDoctorOut(id=me, name=names.get(me, ""))] if me else []
        lines = domain.team_lines(plain, [d.id for d in doctors])
        team = [
            FinanceTeamOut(
                doctor_id=line.doctor_id,
                doctor_name=next(d.name for d in doctors if d.id == line.doctor_id),
                entry_count=line.entry_count,
                revenue_vnd=line.revenue_vnd,
                fee_vnd=line.fee_vnd,
            )
            for line in lines
        ]
        pending = len({row.entry_id for row in plain if row.status == domain.STATUS_PENDING})
        return FinanceOverviewOut(
            month=month,
            today=today(),
            scope=chosen,
            summary=out,
            period=_period_out(month, period),
            team=team,
            pending_entries=pending,
        )


# ------------------------------------------------------------------------------------------------ entries
async def list_entries(
    db: ClinicDatabase, ctx: ActionContext, month: str, scope: FinanceScope | None = None
) -> FinanceEntriesOut:
    """The commission table of a month ("Tiền thủ thuật" tab), in the caller's projection."""
    chosen = resolve_scope(ctx, scope)
    async with db.session() as session:
        period = await _period(session, ctx, month)
        _, all_rows = await _month_rows(session, ctx, month, period)
        rows = _projected(all_rows, chosen, ctx)
        if chosen is FinanceScope.CLINIC:
            doctors = await _performers(session, ctx)
        else:
            me = ctx.actor_user_id
            names = await _names(session, ctx, [me] if me else [])
            doctors = [FinanceDoctorOut(id=me, name=names.get(me, ""))] if me else []
        return FinanceEntriesOut(
            month=month,
            today=today(),
            scope=chosen,
            period=_period_out(month, period),
            rows=[_row_out(row, name) for row, name in rows],
            doctors=doctors,
            can_write=has_permission(ctx, Permission.FINANCE_WRITE) and chosen is FinanceScope.CLINIC,
        )


async def list_performers(db: ClinicDatabase, ctx: ActionContext) -> list[FinanceDoctorOut]:
    """Who can be named as a performer (active doctors and the owner)."""
    require(ctx, Permission.FINANCE_WRITE)
    async with db.session() as session:
        return await _performers(session, ctx)


async def _entry_out(session: AsyncSession, ctx: ActionContext, entry: ProcedureEntry) -> EntryOut:
    patient = await load_patient(session, ctx, entry.patient_id)
    invoice = await session.scalar(
        select(Invoice).where(Invoice.clinic_id == ctx.clinic_id, Invoice.id == entry.invoice_id)
    )
    if invoice is None:  # unreachable: foreign key
        raise not_found("hóa đơn")
    people_rows = (
        await session.scalars(
            select(ProcedureEntryPerson)
            .where(ProcedureEntryPerson.clinic_id == ctx.clinic_id, ProcedureEntryPerson.entry_id == entry.id)
            .order_by(ProcedureEntryPerson.position)
        )
    ).all()
    people = tuple(Person(p.doctor_id, p.share_bp, p.rate_bp) for p in people_rows)
    facts = EntryFacts(
        id=entry.id,
        entry_date=entry.entry_date,
        patient_code=patient.code,
        service_name=entry.service_name,
        status=entry.status,
        basis=entry.basis,
        list_vnd=entry.list_vnd,
        net_vnd=entry.net_vnd,
        note=entry.note,
        invoice_amount_vnd=invoice.amount_vnd,
        invoice_received_vnd=invoice.received_vnd,
        people=people,
    )
    names = await _names(session, ctx, [p.doctor_id for p in people])
    return EntryOut(
        id=entry.id,
        entry_date=entry.entry_date,
        patient_id=entry.patient_id,
        patient_code=patient.code,
        service_id=entry.service_id,
        service_name=entry.service_name,
        terms_version=entry.terms_version,
        basis=ServiceBasis(entry.basis),
        invoice_id=entry.invoice_id,
        invoice_number=invoice.number,
        owns_invoice=entry.owns_invoice,
        list_vnd=entry.list_vnd,
        discount_vnd=entry.discount_vnd,
        net_vnd=entry.net_vnd,
        status=EntryStatus(entry.status),
        note=entry.note,
        void_reason=entry.void_reason,
        people=[
            EntryPersonOut(
                doctor_id=row.doctor_id,
                doctor_name=names.get(row.doctor_id, ""),
                share_bp=row.share_bp,
                rate_bp=row.rate_bp,
                revenue_vnd=row.revenue_vnd,
                fee_vnd=row.fee_vnd,
            )
            for row in domain.compute_rows([facts])
        ],
        version=entry.version,
    )


async def _load_entry(session: AsyncSession, ctx: ActionContext, entry_id: UUID) -> ProcedureEntry:
    entry = await session.scalar(
        select(ProcedureEntry).where(ProcedureEntry.id == entry_id, ProcedureEntry.clinic_id == ctx.clinic_id)
    )
    if entry is None:
        raise not_found("lượt thủ thuật")
    return entry


async def _check_performers(session: AsyncSession, ctx: ActionContext, people: Sequence[Person]) -> None:
    wanted = {p.doctor_id for p in people}
    found = (
        await session.scalars(
            select(UserAccount.id).where(
                UserAccount.clinic_id == ctx.clinic_id,
                UserAccount.id.in_(wanted),
                UserAccount.active.is_(True),
                UserAccount.role.in_(PERFORMER_ROLES),
            )
        )
    ).all()
    if set(found) != wanted:
        raise domain.fail(domain.INVALID_PERFORMER_MESSAGE)


async def create_entry(db: ClinicDatabase, ctx: ActionContext, payload: EntryCreate) -> EntryOut:
    """``mutate('entry')``: a completed procedure goes to the accountant's queue as ``pending``, with the
    service terms and the shares and rates of each performer frozen on it."""
    require(ctx, Permission.FINANCE_WRITE)
    people = tuple(Person(p.doctor_id, p.share_bp, p.rate_bp) for p in payload.people)
    net = domain.validate_amounts(payload.list_vnd, payload.discount_vnd)
    domain.validate_people(people)
    note = domain.require_note(payload.note)
    domain.require_entry_day(payload.entry_date, today())
    month = domain.month_of(payload.entry_date)
    async with db.session() as session:
        await lock_month(session, ctx, month)
        if await _period(session, ctx, month) is not None:
            raise _invalid_state(domain.PERIOD_CLOSED_MESSAGE)
        service = await session.scalar(
            select(Service).where(Service.id == payload.service_id, Service.clinic_id == ctx.clinic_id)
        )
        if service is None:
            raise domain.fail(UNKNOWN_SERVICE_MESSAGE)
        if not service.active:
            raise domain.fail(SERVICE_OFF_MESSAGE)
        terms = await terms_snapshot(session, ctx.clinic_id, service.id, service.terms_version)
        patient = await load_patient(session, ctx, payload.patient_id)
        await _check_performers(session, ctx, people)

        owns = payload.invoice_id is None
        if payload.invoice_id is not None:
            invoice = await session.scalar(
                select(Invoice)
                .where(Invoice.id == payload.invoice_id, Invoice.clinic_id == ctx.clinic_id)
                .with_for_update()
            )
            if invoice is None or invoice.patient_id != patient.id:
                raise domain.fail(domain.WRONG_INVOICE_MESSAGE)
            allocated = await session.scalar(
                select(func.coalesce(func.sum(ProcedureEntry.net_vnd), 0)).where(
                    ProcedureEntry.clinic_id == ctx.clinic_id,
                    ProcedureEntry.invoice_id == invoice.id,
                    ProcedureEntry.status != domain.STATUS_VOID,
                )
            )
            if int(allocated or 0) + net > invoice.amount_vnd:
                raise domain.fail(domain.OVER_ALLOCATED_MESSAGE)
        else:
            invoice = Invoice(
                clinic_id=ctx.clinic_id,
                number=invoice_number(payload.entry_date),
                patient_id=patient.id,
                source="finance",
                amount_vnd=net,
                received_vnd=0,
                invoice_date=payload.entry_date,
                created_by=ctx.actor_user_id,
            )
            session.add(invoice)
            await session.flush()

        entry = ProcedureEntry(
            clinic_id=ctx.clinic_id,
            patient_id=patient.id,
            service_id=service.id,
            service_name=service.name,
            terms_version=terms.version_no,
            basis=terms.basis,
            entry_date=payload.entry_date,
            invoice_id=invoice.id,
            owns_invoice=owns,
            list_vnd=payload.list_vnd,
            discount_vnd=payload.discount_vnd,
            net_vnd=net,
            status=domain.STATUS_PENDING,
            note=note,
            created_by=ctx.actor_user_id,
        )
        with closed_period_is_conflict():
            session.add(entry)
            await session.flush()
            session.add_all(
                ProcedureEntryPerson(
                    clinic_id=ctx.clinic_id,
                    entry_id=entry.id,
                    position=index,
                    doctor_id=person.doctor_id,
                    share_bp=person.share_bp,
                    rate_bp=person.rate_bp,
                )
                for index, person in enumerate(people, start=1)
            )
            await session.flush()
        await audit.record(
            session,
            ctx,
            "finance.entry.create",
            "procedure_entry",
            entry.id,
            {
                "patient_id": str(patient.id),
                "service_id": str(service.id),
                "terms_version": terms.version_no,
                "net_vnd": net,
                "people": len(people),
                "invoice_id": str(invoice.id),
                "owns_invoice": owns,
                "month": month,
            },
        )
        return await _entry_out(session, ctx, entry)


async def approve_entry(db: ClinicDatabase, ctx: ActionContext, entry_id: UUID) -> EntryOut:
    """``mutate('approve')``: pending -> approved. Approving an approved entry changes nothing."""
    require(ctx, Permission.FINANCE_WRITE)
    async with db.session() as session:
        entry = await _load_entry(session, ctx, entry_id)
        month = domain.month_of(entry.entry_date)
        await lock_month(session, ctx, month)
        await session.refresh(entry)
        if await _period(session, ctx, month) is not None:
            raise _invalid_state(domain.PERIOD_CLOSED_EDIT_MESSAGE)
        if entry.status == domain.STATUS_VOID:
            raise _invalid_state(domain.ENTRY_VOID_MESSAGE)
        if entry.status != domain.STATUS_APPROVED:
            entry.status = domain.STATUS_APPROVED
            entry.approved_by = ctx.actor_user_id
            entry.approved_at = now()
            with lost_race_is_conflict(), closed_period_is_conflict():
                await session.flush()
            await audit.record(
                session, ctx, "finance.entry.approve", "procedure_entry", entry.id, {"month": month}
            )
        return await _entry_out(session, ctx, entry)


async def void_entry(db: ClinicDatabase, ctx: ActionContext, entry_id: UUID, payload: EntryVoid) -> EntryOut:
    """``mutate('void')``: cancel an entry before the month is closed, with a reason. An entry whose invoice
    has money received is refused (a refund or an adjustment is a separate process, not in this version)."""
    require(ctx, Permission.FINANCE_WRITE)
    async with db.session() as session:
        entry = await _load_entry(session, ctx, entry_id)
        month = domain.month_of(entry.entry_date)
        await lock_month(session, ctx, month)
        await session.refresh(entry)
        if await _period(session, ctx, month) is not None:
            raise _invalid_state(domain.PERIOD_CLOSED_EDIT_MESSAGE)
        if entry.status == domain.STATUS_VOID:
            raise _invalid_state(domain.ENTRY_VOID_MESSAGE)
        reason = payload.reason.strip()
        if not reason:
            raise domain.fail(domain.VOID_REASON_MESSAGE)
        invoice = await session.scalar(
            select(Invoice)
            .where(Invoice.id == entry.invoice_id, Invoice.clinic_id == ctx.clinic_id)
            .with_for_update()
        )
        if invoice is None:  # unreachable: foreign key
            raise not_found("hóa đơn")
        if invoice.received_vnd != 0:
            raise _invalid_state(domain.VOID_PAID_MESSAGE)
        if entry.owns_invoice:
            others = await session.scalar(
                select(func.count()).where(
                    ProcedureEntry.clinic_id == ctx.clinic_id,
                    ProcedureEntry.invoice_id == invoice.id,
                    ProcedureEntry.id != entry.id,
                    ProcedureEntry.status != domain.STATUS_VOID,
                )
            )
            if not others:
                invoice.amount_vnd = 0
        entry.status = domain.STATUS_VOID
        entry.void_reason = reason
        with lost_race_is_conflict(), closed_period_is_conflict():
            await session.flush()
        await audit.record(
            session,
            ctx,
            "finance.entry.void",
            "procedure_entry",
            entry.id,
            {"month": month, "invoice_id": str(invoice.id), "invoice_zeroed": invoice.amount_vnd == 0},
        )
        return await _entry_out(session, ctx, entry)


# ------------------------------------------------------------------------------------------------ periods
async def list_periods(db: ClinicDatabase, ctx: ActionContext) -> PeriodListOut:
    """The last 12 months with their status and, for an open one, why it cannot be closed yet."""
    require(ctx, Permission.FINANCE_READ)
    current = today()
    months = domain.previous_months(current, HISTORY_MONTHS)
    first = domain.parse_month(months[-1])
    after = domain.next_month_start(domain.parse_month(months[0]))
    async with db.session() as session:
        facts = await _facts(session, ctx, first, after, with_people=False)
        periods = {
            p.month: p
            for p in (
                await session.scalars(
                    select(FinancePeriod).where(
                        FinancePeriod.clinic_id == ctx.clinic_id, FinancePeriod.month.in_(months)
                    )
                )
            ).all()
        }
    by_month: dict[str, list[EntryFacts]] = defaultdict(list)
    for fact in facts:
        by_month[domain.month_of(fact.entry_date)].append(fact)
    items: list[PeriodRowOut] = []
    for month in months:
        entries = by_month.get(month, [])
        period = periods.get(month)
        blocker = None if period else domain.close_blocker(domain.parse_month(month), current, entries)
        items.append(
            PeriodRowOut(
                month=month,
                status=PeriodStatus(period.status) if period else PeriodStatus.OPEN,
                entry_count=len(entries),
                pending_count=sum(1 for e in entries if e.status == domain.STATUS_PENDING),
                closable=period is None and blocker is None,
                blocker=blocker,
                closed_at=period.closed_at if period else None,
                paid_at=period.paid_at if period else None,
                reference=period.reference if period else None,
            )
        )
    return PeriodListOut(today=current, items=items)


async def close_period(db: ClinicDatabase, ctx: ActionContext, month: str) -> FinancePeriodOut:
    """``mutate('close')``: freeze the commission table of a month that ended. Refused while an entry waits
    for approval or an entry on the collected basis is not paid in full (its fee would be lost to the next
    month)."""
    require(ctx, Permission.FINANCE_WRITE)
    first = domain.parse_month(month)
    after = domain.next_month_start(first)
    async with db.session() as session:
        await lock_month(session, ctx, month)
        if await _period(session, ctx, month) is not None:
            raise _invalid_state(domain.PERIOD_CLOSED_MESSAGE)
        facts = await _facts(session, ctx, first, after)
        blocker = domain.close_blocker(first, today(), facts)
        if blocker is not None:
            raise _invalid_state(blocker)
        rows = domain.compute_rows(facts)
        names = await _names(session, ctx, [r.doctor_id for r in rows])
        period = FinancePeriod(
            clinic_id=ctx.clinic_id,
            month=month,
            status="closed",
            closed_at=now(),
            closed_by=ctx.actor_user_id,
            snapshot=[domain.snapshot_row(r, names.get(r.doctor_id, "")) for r in rows],
        )
        session.add(period)
        await session.flush()
        await audit.record(
            session,
            ctx,
            "finance.period.close",
            "finance_period",
            month,
            {"month": month, "entries": len(facts), "rows": len(rows)},
        )
        return _period_out(month, period)


async def pay_period(
    db: ClinicDatabase, ctx: ActionContext, month: str, payload: PeriodPay
) -> FinancePeriodOut:
    """``mutate('paid')``: the accounting confirmation that the closed month's fees were paid out, with the
    voucher. It moves no money (AGENT.md: no payments in this product)."""
    require(ctx, Permission.FINANCE_WRITE)
    domain.parse_month(month)
    reference = payload.reference.strip()
    if not reference:
        raise domain.fail("Cần mã chứng từ chi")
    async with db.session() as session:
        await lock_month(session, ctx, month)
        period = await _period(session, ctx, month)
        if period is None:
            raise _invalid_state(domain.CLOSE_BEFORE_PAY_MESSAGE)
        if period.status == PeriodStatus.PAID.value:
            raise _invalid_state(PERIOD_PAID_MESSAGE)
        period.status = PeriodStatus.PAID.value
        period.reference = reference
        period.paid_at = now()
        period.paid_by = ctx.actor_user_id
        await session.flush()
        await audit.record(session, ctx, "finance.period.pay", "finance_period", month, {"month": month})
        return _period_out(month, period)


# -------------------------------------------------------------------------------------------------- csv
async def export_csv(
    db: ClinicDatabase, ctx: ActionContext, month: str, scope: FinanceScope | None = None
) -> str:
    """The commission table as a CSV for Excel, in the caller's projection (a doctor exports only their
    rows). The text starts with a byte order mark so Excel reads the accents; every cell that could be read
    as a formula is prefixed with an apostrophe."""
    chosen = resolve_scope(ctx, scope)
    async with db.session() as session:
        period = await _period(session, ctx, month)
        _, all_rows = await _month_rows(session, ctx, month, period)
    rows = _projected(all_rows, chosen, ctx)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(domain.CSV_HEADER)
    for row, name in rows:
        writer.writerow(domain.csv_record(row, name))
    return BYTE_ORDER_MARK + out.getvalue()

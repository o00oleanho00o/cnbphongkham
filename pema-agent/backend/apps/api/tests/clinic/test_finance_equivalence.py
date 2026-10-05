# ruff: noqa: PT018
# translated from prototype/finance_test.py (every test of the file, in its order) and extended with the rules the
# new module adds: closed months at the database, overpayment, performers, the order link (package U, step U6)
"""PB02 finance on a real Postgres. Each ``test_*`` that carries the name of a case of ``prototype/finance_test.py``
proves the same rule through the actions (and, where the prototype went through HTTP, through the HTTP API). Needs
``PEMA_TEST_DATABASE_URL`` (skipped otherwise)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError

from pema.api.clinic_testing import ClientFactory
from pema.clinic.actions import catalog, finance, finance_cash, services
from pema.clinic.actions.seed_demo import DEMO_DAY, SeedResult
from pema.clinic.domain.orders import parse_catalog_rows
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.catalog import ServiceBasis, ServiceOut, ServiceUpdate
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.finance import (
    EntryCreate,
    EntryOut,
    EntryPersonIn,
    EntryVoid,
    FinanceScope,
    InvoiceFromOrder,
    InvoiceOut,
    PaymentCreate,
    PaymentMethod,
    PeriodPay,
    PeriodStatus,
)
from pema_contracts.roles import ActorType, Role

pytestmark = pytest.mark.db

MONTH = f"{DEMO_DAY.year:04d}-{DEMO_DAY.month:02d}"  # 2026-09, the month of the frozen clock
LAST_MONTH = "2026-08"
FINANCE = "/api/v1/finance"
CATALOG_JSON = Path(__file__).resolve().parents[6] / "prototype" / "shared" / "product-catalog.json"

ROLES = {
    "owner": Role.OWNER,
    "manager": Role.MANAGER,
    "doctor.mai": Role.DOCTOR,
    "doctor.an": Role.DOCTOR,
    "reception.lan": Role.RECEPTION,
    "cs.thu": Role.CS_STAFF,
}
OWNER_AND_MAI = (("owner", 7000, 1500), ("doctor.mai", 3000, 500))


def _as(world: SeedResult, key: str) -> ActionContext:
    return ActionContext(
        clinic_id=world.clinic_id,
        actor_type=ActorType.USER,
        actor_user_id=world.users[key],
        actor_role=ROLES[key],
        source=ActionSource.UI,
    )


def _people(world: SeedResult, spec: tuple[tuple[str, int, int], ...]) -> list[EntryPersonIn]:
    return [EntryPersonIn(doctor_id=world.users[k], share_bp=s, rate_bp=r) for k, s, r in spec]


async def _service(db: ClinicDatabase, world: SeedResult, code: str = "laser-co2") -> ServiceOut:
    listed = await services.list_services(db, _as(world, "manager"))
    return next(s for s in listed if s.code == code)


async def _entry(
    db: ClinicDatabase,
    world: SeedResult,
    *,
    who: str = "manager",
    people: tuple[tuple[str, int, int], ...] = OWNER_AND_MAI,
    service: ServiceOut | None = None,
    patient: str = "P025",
    **fields: Any,
) -> EntryOut:
    """``entry()`` of the prototype test: a laser procedure of 2.5 million with 100 thousand off, two performers."""
    chosen = service or await _service(db, world)
    body: dict[str, Any] = {
        "patient_id": world.patients[patient],
        "service_id": chosen.id,
        "entry_date": DEMO_DAY,
        "list_vnd": 2_500_000,
        "discount_vnd": 100_000,
        "note": "Đã hoàn tất (mẫu)",
        "people": _people(world, people),
    }
    body.update(fields)
    return await finance.create_entry(db, _as(world, who), EntryCreate(**body))


async def _pay(
    db: ClinicDatabase, world: SeedResult, invoice: UUID, amount: int, key: str, *, who: str = "manager"
) -> Any:
    payload = PaymentCreate(id=key, invoice_id=invoice, amount_vnd=amount, method=PaymentMethod.CASH)
    return await finance_cash.record_payment(db, _as(world, who), payload)


async def _rows(
    db: ClinicDatabase, world: SeedResult, entry: EntryOut, month: str = MONTH, who: str = "owner"
) -> Any:
    listed = await finance.list_entries(db, _as(world, who), month)
    return [r for r in listed.rows if r.entry_id == entry.id]


async def _refused(call: Any, code: ErrorCode, message: str | None = None) -> DomainError:
    with pytest.raises(DomainError) as caught:
        await call
    assert caught.value.code is code, (caught.value.code, caught.value.message)
    if message is not None:
        assert caught.value.message == message
    return caught.value


def _count(admin: Engine, table: str) -> int:
    with admin.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM clinic.{table}")).scalar_one())  # noqa: S608  - own constants


def _error(response: httpx.Response) -> tuple[int, str, str]:
    body = response.json()["error"]
    return response.status_code, body["code"], body["message"]


# ----------------------------------------------------------------------------------- test_split_discount_and_snapshot
async def test_split_discount_and_snapshot(db: ClinicDatabase, world: SeedResult) -> None:
    entry = await _entry(db, world)
    rows = await _rows(db, world, entry)
    assert [r.fee_vnd for r in rows] == [360_000, 120_000]
    assert sum(r.revenue_vnd for r in rows) == 2_400_000
    assert [r.revenue_vnd for r in rows] == [1_680_000, 720_000]  # the example of docs/24

    laser = await _service(db, world)
    changed = await services.update_service(
        db,
        _as(world, "manager"),
        laser.id,
        ServiceUpdate(version=laser.version, rate_bp=3000, basis=ServiceBasis.LIST),
    )
    assert changed.terms_version == 2
    again = await _rows(db, world, entry)
    assert [r.fee_vnd for r in again] == [
        360_000,
        120_000,
    ]  # the rate and the basis of the entry are a snapshot
    assert {r.basis.value for r in again} == {"net"}
    assert (entry.terms_version, entry.basis) == (1, ServiceBasis.NET)


# ------------------------------------------------------ test_new_mobile_patient_keeps_procedure_invoice_and_receipt_context
async def test_a_new_patient_keeps_the_procedure_invoice_and_receipt_context(
    db: ClinicDatabase, world: SeedResult
) -> None:
    entry = await _entry(db, world, patient="P026")
    receipt = await _pay(db, world, entry.invoice_id, 100_000, "mobile-receipt")
    assert receipt.patient_code == "P026"
    invoices = await finance_cash.list_invoices(db, _as(world, "manager"), patient_id=world.patients["P026"])
    assert [(i.id, i.patient_code) for i in invoices.items] == [(entry.invoice_id, "P026")]
    mine = await _rows(db, world, entry, who="doctor.mai")
    assert mine and all(r.patient_code == "P026" and r.doctor_id == world.users["doctor.mai"] for r in mine)


# ------------------------------------------------------------------------------------- test_validation_rollback
INVALID_ENTRIES: list[tuple[str, dict[str, Any], int]] = [
    ("no people", {"people": []}, 422),
    ("discount over the list price", {"discount_vnd": 3_000_000}, 422),
    ("shares do not add up to 100 %", {"people": [("owner", 7000, 2000)]}, 422),
    ("a rate over 100 %", {"people": [("owner", 10000, 11000)]}, 422),
    ("no note", {"note": ""}, 422),
    ("rates over 100 % together", {"people": [("owner", 5000, 6000), ("doctor.mai", 5000, 5000)]}, 422),
    ("the same performer twice", {"people": [("owner", 5000, 0), ("owner", 5000, 0)]}, 422),
]


@pytest.mark.parametrize(
    ("label", "override", "status"), INVALID_ENTRIES, ids=[i[0] for i in INVALID_ENTRIES]
)
async def test_validation_rolls_back_and_writes_nothing(
    label: str,
    override: dict[str, Any],
    status: int,
    db: ClinicDatabase,
    world: SeedResult,
    admin: Engine,
    client_factory: ClientFactory,
) -> None:
    laser = await _service(db, world)
    before = {t: _count(admin, t) for t in ("procedure_entry", "procedure_entry_person", "invoice")}
    body: dict[str, Any] = {
        "patient_id": str(world.patients["P025"]),
        "service_id": str(laser.id),
        "entry_date": DEMO_DAY.isoformat(),
        "list_vnd": 2_500_000,
        "discount_vnd": 100_000,
        "note": "Đã hoàn tất (mẫu)",
    }
    people = override.pop("people", [("owner", 7000, 1500), ("doctor.mai", 3000, 500)])
    body["people"] = [{"doctor_id": str(world.users[k]), "share_bp": s, "rate_bp": r} for k, s, r in people]
    body.update(override)
    manager = await client_factory("manager")
    response = await manager.post(f"{FINANCE}/entries", json=body)
    assert response.status_code == status, (label, response.text)
    assert {t: _count(admin, t) for t in before} == before


async def test_a_future_day_an_unknown_service_and_a_service_that_is_off_write_nothing(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    laser = await _service(db, world)
    before = _count(admin, "procedure_entry"), _count(admin, "invoice")
    await _refused(
        _entry(db, world, entry_date=DEMO_DAY.replace(day=21)),
        ErrorCode.VALIDATION_FAILED,
        "Ngày thực hiện không hợp lệ",
    )
    await _refused(
        _entry(db, world, service=laser.model_copy(update={"id": UUID(int=1)})), ErrorCode.VALIDATION_FAILED
    )
    await services.update_service(
        db, _as(world, "manager"), laser.id, ServiceUpdate(version=laser.version, active=False)
    )
    await _refused(_entry(db, world), ErrorCode.VALIDATION_FAILED, finance.SERVICE_OFF_MESSAGE)
    assert (_count(admin, "procedure_entry"), _count(admin, "invoice")) == before


# ---------------------------------------------------------------------------------- test_role_projection_and_write
async def test_role_projection_and_write(db: ClinicDatabase, world: SeedResult) -> None:
    entry = await _entry(db, world)
    await _pay(db, world, entry.invoice_id, 100_000, "projection-receipt")
    doctor = _as(world, "doctor.mai")

    mine = await finance.list_entries(db, doctor, MONTH)
    assert mine.scope is FinanceScope.OWN and mine.can_write is False
    assert mine.rows and all(r.doctor_id == world.users["doctor.mai"] for r in mine.rows)
    assert [d.id for d in mine.doctors] == [world.users["doctor.mai"]]
    summary = (await finance.overview(db, doctor, MONTH)).summary
    assert summary.collected_vnd is None and summary.debt_vnd is None  # no clinic cash in a personal view
    assert summary.revenue_vnd == 720_000  # the doctor's share only

    await _refused(finance_cash.list_invoices(db, doctor), ErrorCode.FORBIDDEN)
    await _refused(finance_cash.list_payments(db, doctor, MONTH), ErrorCode.FORBIDDEN)
    await _refused(finance_cash.list_notifications(db, doctor), ErrorCode.FORBIDDEN)
    await _refused(finance.list_periods(db, doctor), ErrorCode.FORBIDDEN)
    await _refused(finance.overview(db, doctor, MONTH, FinanceScope.CLINIC), ErrorCode.FORBIDDEN)
    await _refused(_entry(db, world, who="doctor.mai"), ErrorCode.FORBIDDEN)
    await _refused(finance.approve_entry(db, doctor, entry.id), ErrorCode.FORBIDDEN)
    await _refused(finance.void_entry(db, doctor, entry.id, EntryVoid(reason="x")), ErrorCode.FORBIDDEN)
    await _refused(finance.close_period(db, doctor, LAST_MONTH), ErrorCode.FORBIDDEN)
    laser = await _service(db, world)
    await _refused(
        services.update_service(db, doctor, laser.id, ServiceUpdate(version=laser.version, rate_bp=3000)),
        ErrorCode.FORBIDDEN,
    )


async def test_the_projection_follows_the_session_and_never_a_header(
    db: ClinicDatabase, world: SeedResult, client_factory: ClientFactory
) -> None:
    await _entry(db, world)
    doctor = await client_factory("doctor.mai")
    forged = {"X-Pema-Role": "owner", "X-Pema-Doctor": "D0"}  # the prototype trusted these two headers
    data = (await doctor.get(f"{FINANCE}/entries", params={"month": MONTH}, headers=forged)).json()
    assert data["scope"] == "own"
    assert data["rows"] and all(r["doctor_name"] == "BS. Mai (mẫu)" for r in data["rows"])
    assert (
        await doctor.get(f"{FINANCE}/overview", params={"month": MONTH, "scope": "clinic"})
    ).status_code == 403
    assert (await doctor.get(f"{FINANCE}/invoices", headers=forged)).status_code == 403


async def test_who_reads_what_across_the_six_roles(db: ClinicDatabase, world: SeedResult) -> None:
    await _entry(db, world)
    for key in ("owner", "manager"):
        overview = await finance.overview(db, _as(world, key), MONTH)
        assert overview.scope is FinanceScope.CLINIC and overview.summary.collected_vnd == 0
    owner_own = await finance.list_entries(db, _as(world, "owner"), MONTH, FinanceScope.OWN)
    assert owner_own.rows and all(r.doctor_id == world.users["owner"] for r in owner_own.rows)
    assert owner_own.can_write is False  # a personal view is read only
    await _refused(
        finance.list_entries(db, _as(world, "manager"), MONTH, FinanceScope.OWN), ErrorCode.FORBIDDEN
    )
    for key in ("reception.lan", "cs.thu"):
        await _refused(finance.overview(db, _as(world, key), MONTH), ErrorCode.FORBIDDEN)
        await _refused(finance.list_entries(db, _as(world, key), MONTH), ErrorCode.FORBIDDEN)
        await _refused(finance.export_csv(db, _as(world, key), MONTH), ErrorCode.FORBIDDEN)
    await _refused(finance_cash.list_invoices(db, _as(world, "cs.thu")), ErrorCode.FORBIDDEN)
    assert (
        await finance_cash.list_invoices(db, _as(world, "reception.lan"))
    ).total == 1  # the cashier sees invoices


async def test_the_performer_is_never_taken_from_the_doctor_in_charge(
    db: ClinicDatabase, world: SeedResult
) -> None:
    """P025 is looked after by BS. Mai: an entry that names only the owner has no row for her."""
    entry = await _entry(db, world, people=(("owner", 10000, 1500),))
    rows = await _rows(db, world, entry)
    assert [r.doctor_id for r in rows] == [world.users["owner"]]
    assert await _rows(db, world, entry, who="doctor.mai") == []


@pytest.mark.parametrize("performer", ["manager", "reception.lan", "cs.thu"])
async def test_only_a_doctor_or_the_owner_can_be_named_as_a_performer(
    performer: str, db: ClinicDatabase, world: SeedResult
) -> None:
    await _refused(
        _entry(db, world, people=((performer, 10000, 1000),)),
        ErrorCode.VALIDATION_FAILED,
        "Người thực hiện không hợp lệ",
    )


# ------------------------------------------------------ test_payment_idempotency_notification_and_persistence
async def test_payment_idempotency_notification_and_persistence(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    entry = await _entry(db, world)
    first = await _pay(db, world, entry.invoice_id, 1_000_000, "test-receipt")
    again = await _pay(db, world, entry.invoice_id, 1_000_000, "test-receipt")
    assert (first.replayed, again.replayed) == (False, True) and again.id == first.id
    owner = _as(world, "owner")
    notes = await finance_cash.list_notifications(db, owner)
    assert len(notes) == 1  # one receipt, one notification, whatever the retries
    assert notes[0].amount_vnd == 1_000_000 and notes[0].read is False
    assert notes[0].title == "Đã nhận thanh toán" and notes[0].body == "P025 · 1.000.000 đ · Tiền mặt"
    invoice = (await finance_cash.list_invoices(db, owner)).items[0]
    assert invoice.received_vnd == 1_000_000 and invoice.due_vnd == 1_400_000  # received once
    assert _count(admin, "payment") == 1

    await _refused(
        _pay(db, world, entry.invoice_id, 1, "test-receipt"),
        ErrorCode.DUPLICATE_REQUEST,
        "Mã giao dịch đã dùng cho nội dung khác",
    )
    await _refused(
        _pay(db, world, entry.invoice_id, 2_000_000, "test-over"),
        ErrorCode.VALIDATION_FAILED,
        "Số thu vượt công nợ",
    )
    assert _count(admin, "payment") == 1 and len(await finance_cash.list_notifications(db, owner)) == 1

    read = await finance_cash.mark_notification_read(db, owner, notes[0].id)
    assert read.read is True
    assert (await finance_cash.list_notifications(db, owner))[0].read is True
    await finance_cash.mark_notification_read(db, owner, notes[0].id)  # reading again changes nothing
    with admin.connect() as conn:
        audited = conn.execute(
            text("SELECT count(*) FROM clinic.audit_log WHERE action = 'finance.notification.read'")
        ).scalar_one()
    assert audited == 1


async def test_a_same_key_with_another_invoice_or_method_is_refused(
    db: ClinicDatabase, world: SeedResult
) -> None:
    one = await _entry(db, world)
    two = await _entry(db, world, patient="P026")
    await _pay(db, world, one.invoice_id, 100_000, "shared-key")
    await _refused(_pay(db, world, two.invoice_id, 100_000, "shared-key"), ErrorCode.DUPLICATE_REQUEST)
    other_method = PaymentCreate(
        id="shared-key", invoice_id=one.invoice_id, amount_vnd=100_000, method=PaymentMethod.TRANSFER
    )
    await _refused(
        finance_cash.record_payment(db, _as(world, "manager"), other_method), ErrorCode.DUPLICATE_REQUEST
    )


async def test_the_owner_alone_reads_the_notifications(db: ClinicDatabase, world: SeedResult) -> None:
    entry = await _entry(db, world)
    await _pay(db, world, entry.invoice_id, 50_000, "inbox-receipt")
    note = (await finance_cash.list_notifications(db, _as(world, "owner")))[0]
    for key in ("manager", "reception.lan", "doctor.mai", "cs.thu"):
        await _refused(finance_cash.list_notifications(db, _as(world, key)), ErrorCode.FORBIDDEN)
        await _refused(finance_cash.mark_notification_read(db, _as(world, key), note.id), ErrorCode.FORBIDDEN)
    await _refused(
        finance_cash.mark_notification_read(db, _as(world, "owner"), UUID(int=7)), ErrorCode.NOT_FOUND
    )


# ---------------------------------------------------------------------------------- test_parallel_payment_serialized
async def test_parallel_payment_serialized(db: ClinicDatabase, world: SeedResult, admin: Engine) -> None:
    entry = await _entry(db, world)
    results = await asyncio.gather(
        *[_pay(db, world, entry.invoice_id, 1_000_000, "concurrent-payment") for _ in range(5)]
    )
    assert len({r.id for r in results}) == 1 and sorted(r.replayed for r in results) == [False] + [True] * 4
    assert len(await finance_cash.list_notifications(db, _as(world, "owner"))) == 1
    assert _count(admin, "payment") == 1
    invoice = (await finance_cash.list_invoices(db, _as(world, "manager"))).items[0]
    assert invoice.received_vnd == 1_000_000


async def test_two_different_receipts_in_parallel_never_pass_the_open_balance(
    db: ClinicDatabase, world: SeedResult
) -> None:
    entry = await _entry(db, world)  # 2,400,000 to collect
    outcomes = await asyncio.gather(
        *[_pay(db, world, entry.invoice_id, 1_000_000, f"race-{i}") for i in range(3)], return_exceptions=True
    )
    paid = [o for o in outcomes if not isinstance(o, BaseException)]
    refused = [o for o in outcomes if isinstance(o, DomainError)]
    assert len(paid) == 2 and len(refused) == 1 and refused[0].message == "Số thu vượt công nợ"
    invoice = (await finance_cash.list_invoices(db, _as(world, "manager"))).items[0]
    assert invoice.received_vnd == 2_000_000


async def test_overpayment_is_refused_and_a_paid_invoice_takes_no_more(
    db: ClinicDatabase, world: SeedResult
) -> None:
    entry = await _entry(db, world)
    await _refused(
        _pay(db, world, entry.invoice_id, 2_400_001, "over-1"),
        ErrorCode.VALIDATION_FAILED,
        "Số thu vượt công nợ",
    )
    await _pay(db, world, entry.invoice_id, 2_400_000, "exact")
    await _refused(
        _pay(db, world, entry.invoice_id, 1, "after-paid"), ErrorCode.VALIDATION_FAILED, "Số thu vượt công nợ"
    )
    due = await finance_cash.list_invoices(db, _as(world, "manager"), due_only=True)
    assert due.total == 0
    await _refused(_pay(db, world, UUID(int=3), 1, "no-invoice"), ErrorCode.NOT_FOUND)


async def test_the_database_itself_refuses_to_take_more_than_the_invoice(
    db: ClinicDatabase, world: SeedResult
) -> None:
    entry = await _entry(db, world)
    async with db.session() as session:
        with pytest.raises(DBAPIError, match=r"invoice_check|check constraint"):
            await session.execute(
                text("UPDATE clinic.invoice SET received_vnd = amount_vnd + 1 WHERE id = :id"),
                {"id": entry.invoice_id},
            )


# ------------------------------------------------------------------------- test_collected_and_close_snapshot
async def test_collected_and_close_snapshot(db: ClinicDatabase, world: SeedResult, admin: Engine) -> None:
    laser = await _service(db, world)
    await services.update_service(
        db,
        _as(world, "manager"),
        laser.id,
        ServiceUpdate(version=laser.version, rate_bp=2000, basis=ServiceBasis.COLLECTED),
    )
    entry = await _entry(db, world, entry_date=DEMO_DAY.replace(month=8, day=10))
    assert entry.basis is ServiceBasis.COLLECTED and entry.terms_version == 2
    await _pay(db, world, entry.invoice_id, 1_200_000, "collect-a")
    manager = _as(world, "manager")
    collected_open = "Còn lượt tính theo thực thu chưa thu đủ; chưa thể chốt để tránh mất tiền kỳ sau"
    await _refused(finance.close_period(db, manager, LAST_MONTH), ErrorCode.INVALID_STATE, collected_open)
    await finance.approve_entry(db, manager, entry.id)
    await _refused(finance.close_period(db, manager, LAST_MONTH), ErrorCode.INVALID_STATE, collected_open)
    half = await _rows(db, world, entry, LAST_MONTH)
    assert sum(r.fee_vnd for r in half) == 240_000  # the collected base follows the receipts so far

    await _pay(db, world, entry.invoice_id, 1_200_000, "collect-b")
    closed = await finance.close_period(db, manager, LAST_MONTH)
    assert closed.status is PeriodStatus.CLOSED and closed.closed_at is not None
    frozen = await _rows(db, world, entry, LAST_MONTH)
    assert sum(r.fee_vnd for r in frozen) == 480_000

    current = await _service(db, world)
    await services.update_service(
        db, manager, current.id, ServiceUpdate(version=current.version, rate_bp=3000, basis=ServiceBasis.LIST)
    )
    assert frozen == await _rows(
        db, world, entry, LAST_MONTH
    )  # a closed month never reads the live terms again
    assert frozen == await _rows(db, world, entry, LAST_MONTH, who="manager")
    with admin.connect() as conn:
        snapshot = conn.execute(
            text("SELECT snapshot FROM clinic.finance_period WHERE month = :m"), {"m": LAST_MONTH}
        ).scalar_one()
    assert len(snapshot) == 2 and snapshot[0]["doctor_name"] == "BS. Tâm (mẫu)"  # the names are frozen too

    closed_edit = "Kỳ đã chốt, không được sửa"
    await _refused(finance.approve_entry(db, manager, entry.id), ErrorCode.INVALID_STATE, closed_edit)
    await _refused(
        finance.void_entry(db, manager, entry.id, EntryVoid(reason="test")),
        ErrorCode.INVALID_STATE,
        closed_edit,
    )
    await _refused(
        _entry(db, world, entry_date=DEMO_DAY.replace(month=8, day=12)), ErrorCode.INVALID_STATE, "Kỳ đã chốt"
    )
    await _refused(finance.close_period(db, manager, LAST_MONTH), ErrorCode.INVALID_STATE, "Kỳ đã chốt")

    await _refused(
        finance.pay_period(db, manager, MONTH, PeriodPay(reference="CHI-00")), ErrorCode.INVALID_STATE
    )
    paid = await finance.pay_period(db, manager, LAST_MONTH, PeriodPay(reference="CHI-01"))
    assert (paid.status, paid.reference) == (PeriodStatus.PAID, "CHI-01") and paid.paid_at is not None
    overview = await finance.overview(db, _as(world, "owner"), LAST_MONTH)
    assert overview.period.status is PeriodStatus.PAID
    await _refused(
        finance.pay_period(db, manager, LAST_MONTH, PeriodPay(reference="CHI-02")),
        ErrorCode.INVALID_STATE,
        finance.PERIOD_PAID_MESSAGE,
    )


# --------------------------------------------------------------------------- the closed month at the database
async def test_a_closed_month_is_immutable_at_the_database_too(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    entry = await _entry(db, world, entry_date=DEMO_DAY.replace(month=8, day=3))
    manager = _as(world, "manager")
    await finance.approve_entry(db, manager, entry.id)
    await finance.close_period(db, manager, LAST_MONTH)
    statements = [
        "UPDATE clinic.procedure_entry SET status = 'void', void_reason = 'x' WHERE id = :id",
        "UPDATE clinic.procedure_entry SET list_vnd = 1, net_vnd = 1 - discount_vnd WHERE id = :id",
        "DELETE FROM clinic.procedure_entry_person WHERE entry_id = :id",
        "UPDATE clinic.procedure_entry_person SET rate_bp = 0 WHERE entry_id = :id",
        "DELETE FROM clinic.procedure_entry WHERE id = :id",
    ]
    for statement in statements:
        async with db.session() as session:
            with pytest.raises(DBAPIError, match="finance period is closed"):
                await session.execute(text(statement), {"id": entry.id})
    # not even the table owner can slip a new entry into the month
    with admin.begin() as conn, pytest.raises(DBAPIError, match="finance period is closed"):
        conn.execute(
            text(
                "INSERT INTO clinic.procedure_entry (clinic_id, patient_id, service_id, service_name, terms_version, basis,"
                " entry_date, invoice_id, list_vnd, net_vnd, note) SELECT clinic_id, patient_id, service_id, service_name,"
                " terms_version, basis, entry_date, invoice_id, list_vnd, net_vnd, note FROM clinic.procedure_entry"
                " WHERE id = :id"
            ),
            {"id": entry.id},
        )
    async with db.session() as session:
        for statement in (
            "UPDATE clinic.finance_period SET snapshot = '[]'::jsonb WHERE month = :m",
            "UPDATE clinic.finance_period SET month = '2026-07' WHERE month = :m",
            "DELETE FROM clinic.finance_period WHERE month = :m",
        ):
            with pytest.raises(DBAPIError, match="finance period"):
                async with session.begin_nested():
                    await session.execute(text(statement), {"m": LAST_MONTH})
        # a month that is not closed still takes entries
        await session.execute(text("SELECT 1"))
    still_open = await _entry(db, world, patient="P027")
    assert still_open.entry_date == DEMO_DAY


async def test_close_period_serializes_with_new_entries(db: ClinicDatabase, world: SeedResult) -> None:
    """An entry made while the month is being closed lands before the freeze (and is in the snapshot) or is
    refused: it can never be missing from a closed month."""
    first = await _entry(db, world, entry_date=DEMO_DAY.replace(month=8, day=3))
    manager = _as(world, "manager")
    await finance.approve_entry(db, manager, first.id)
    results = await asyncio.gather(
        finance.close_period(db, manager, LAST_MONTH),
        _entry(db, world, entry_date=DEMO_DAY.replace(month=8, day=4)),
        return_exceptions=True,
    )
    listed = await finance.list_entries(db, manager, LAST_MONTH)
    in_month = {r.entry_id for r in listed.rows}
    late = results[1]
    if isinstance(late, DomainError):
        assert late.code is ErrorCode.INVALID_STATE and in_month == {first.id}
    else:
        assert isinstance(results[0], DomainError)  # the close was refused because the late entry is pending
        assert in_month == {first.id, late.id}  # type: ignore[union-attr]


# ------------------------------------------------------------------------- test_void_and_no_close_current_month
async def test_void_and_no_close_current_month(db: ClinicDatabase, world: SeedResult) -> None:
    entry = await _entry(db, world)
    manager = _as(world, "manager")
    voided = await finance.void_entry(db, manager, entry.id, EntryVoid(reason="Ghi nhầm"))
    assert voided.status.value == "void" and voided.void_reason == "Ghi nhầm"
    invoice = (await finance_cash.list_invoices(db, manager)).items[0]
    assert invoice.amount_vnd == 0  # the invoice made for the entry goes to zero
    await _refused(
        finance.close_period(db, manager, MONTH), ErrorCode.INVALID_STATE, "Chỉ chốt tháng đã kết thúc"
    )
    await _refused(
        finance.close_period(db, manager, "2026-10"), ErrorCode.INVALID_STATE, "Chỉ chốt tháng đã kết thúc"
    )
    await _refused(
        finance.void_entry(db, manager, entry.id, EntryVoid(reason="again")),
        ErrorCode.INVALID_STATE,
        "Lượt đã hủy",
    )
    await _refused(finance.approve_entry(db, manager, entry.id), ErrorCode.INVALID_STATE, "Lượt đã hủy")
    rows = await _rows(db, world, entry)
    assert {r.status.value for r in rows} == {"void"} and {r.note for r in rows} == {"Ghi nhầm"}
    overview = await finance.overview(db, _as(world, "owner"), MONTH)
    assert (
        overview.summary.revenue_vnd == 0 and overview.summary.fee_vnd == 0 and overview.pending_entries == 0
    )


async def test_an_entry_with_money_received_cannot_be_voided(db: ClinicDatabase, world: SeedResult) -> None:
    entry = await _entry(db, world)
    await _pay(db, world, entry.invoice_id, 100_000, "before-void")
    await _refused(
        finance.void_entry(db, _as(world, "manager"), entry.id, EntryVoid(reason="Sai")),
        ErrorCode.INVALID_STATE,
        "Lượt đã thu tiền; cần quy trình hoàn/điều chỉnh riêng",
    )


async def test_approving_twice_changes_nothing(db: ClinicDatabase, world: SeedResult, admin: Engine) -> None:
    entry = await _entry(db, world)
    manager = _as(world, "manager")
    once = await finance.approve_entry(db, manager, entry.id)
    twice = await finance.approve_entry(db, manager, entry.id)
    assert (once.status.value, twice.status.value, once.version) == ("approved", "approved", twice.version)
    with admin.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM clinic.audit_log WHERE action = 'finance.entry.approve'")
        ).scalar_one()
    assert count == 1
    await _refused(finance.approve_entry(db, manager, UUID(int=9)), ErrorCode.NOT_FOUND)


# ---------------------------------------------------------------------------- test_revenue_rounding_reconciles
async def test_revenue_rounding_reconciles(db: ClinicDatabase, world: SeedResult) -> None:
    entry = await _entry(
        db,
        world,
        list_vnd=101,
        discount_vnd=0,
        people=(("owner", 3333, 1000), ("doctor.mai", 3333, 1000), ("doctor.an", 3334, 1000)),
    )
    rows = await _rows(db, world, entry)
    assert sum(r.revenue_vnd for r in rows) == 101
    overview = await finance.overview(db, _as(world, "owner"), MONTH)
    assert (
        overview.summary.revenue_vnd == 101
    )  # a procedure shared by three doctors counts once for the clinic
    assert sum(t.revenue_vnd for t in overview.team) == 101


# ---------------------------------------------------------------------- test_http_csv_and_role_projection
async def test_http_csv_and_role_projection(
    db: ClinicDatabase, world: SeedResult, client_factory: ClientFactory
) -> None:
    await _entry(db, world)
    doctor = await client_factory("doctor.mai")
    state = (await doctor.get(f"{FINANCE}/entries", params={"month": MONTH})).json()
    assert state["rows"] and all(x["doctor_name"] == "BS. Mai (mẫu)" for x in state["rows"])
    exported = await doctor.get(f"{FINANCE}/export", params={"month": MONTH})
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert (
        exported.headers["content-disposition"] == f'attachment; filename="Pema-tien-thu-thuat-{MONTH}.csv"'
    )
    body = exported.content.decode("utf-8-sig")
    assert exported.content.startswith(b"\xef\xbb\xbf")  # a byte order mark for Excel
    assert "BS. Mai (mẫu)" in body and "BS. Tâm (mẫu)" not in body
    assert (
        body.splitlines()[0] == "Ngay,Ho so,Thu thuat,Bac si,Doanh so,Co so,Ty le %,Tien thu thuat,Trang thai"
    )
    manager = await client_factory("manager")
    everyone = (await manager.get(f"{FINANCE}/export", params={"month": MONTH})).content.decode("utf-8-sig")
    assert "BS. Mai (mẫu)" in everyone and "BS. Tâm (mẫu)" in everyone and len(everyone.splitlines()) == 3


async def test_the_csv_neutralises_a_name_that_starts_like_a_formula(
    db: ClinicDatabase, world: SeedResult, admin: Engine, client_factory: ClientFactory
) -> None:
    await _entry(db, world)
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.user_account SET display_name = '=HYPERLINK(\"x\")' WHERE role = 'owner'")
        )
    manager = await client_factory("manager")
    body = (await manager.get(f"{FINANCE}/export", params={"month": MONTH})).content.decode("utf-8-sig")
    assert "'=HYPERLINK" in body and ",=HYPERLINK" not in body


async def test_bad_months_are_refused_and_an_anonymous_caller_gets_401(
    client_factory: ClientFactory, world: SeedResult, app: FastAPI
) -> None:
    manager = await client_factory("manager")
    for bad in ("2026-13", "2026-9", "x", "2026-09-01"):
        response = await manager.get(f"{FINANCE}/overview", params={"month": bad})
        assert response.status_code == 422, bad
    assert (await manager.post(f"{FINANCE}/periods/2026-13/close")).status_code == 422
    anonymous = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    try:
        assert (await anonymous.get(f"{FINANCE}/overview", params={"month": MONTH})).status_code == 401
    finally:
        await anonymous.aclose()


# ------------------------------------------------------------ the order link (test_link_existing_invoice...)
def _catalog_rows() -> Any:
    if not CATALOG_JSON.exists():
        pytest.skip("prototype catalog not in this checkout")
    return parse_catalog_rows(json.loads(CATALOG_JSON.read_text(encoding="utf-8")))


@pytest.fixture
async def loaded(db: ClinicDatabase, world: SeedResult) -> SeedResult:
    system = ActionContext(
        clinic_id=world.clinic_id,
        actor_type=ActorType.SYSTEM,
        source=ActionSource.SYSTEM,
        request_id="finance-order",
    )
    await catalog.import_catalog(db, system, _catalog_rows(), source_name="product-catalog.json")
    return world


async def _order(
    client: httpx.AsyncClient, world: SeedResult, patient: str = "P025", **fields: Any
) -> dict[str, Any]:
    body = {
        "patient_id": str(world.patients[patient]),
        "diagnosis": "Nám · tăng sắc tố (mẫu)",
        "items": [
            {"product_code": "H002", "quantity": 1, "usage": "Bôi lớp mỏng, sáng và tối (mẫu)"},
            {"product_code": "H005", "quantity": 2, "usage": "Bôi lớp mỏng, sáng và tối (mẫu)"},
        ],
        **fields,
    }
    response = await client.post("/api/v1/orders", json=body)
    assert response.status_code == 201, response.text
    return response.json()


async def _invoice_of(
    db: ClinicDatabase, world: SeedResult, order: dict[str, Any], who: str = "manager"
) -> InvoiceOut:
    return await finance_cash.create_for_order(
        db, _as(world, who), InvoiceFromOrder(order_id=UUID(order["id"]))
    )


async def test_link_existing_invoice_without_duplicate_debt(
    db: ClinicDatabase, loaded: SeedResult, admin: Engine, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _order(reception, loaded)
    invoice = await _invoice_of(db, loaded, order)
    assert invoice.amount_vnd == order["total_vnd"] > 0 and invoice.source.value == "order"
    before = _count(admin, "invoice")
    entry = await _entry(db, loaded, list_vnd=invoice.amount_vnd, discount_vnd=0, invoice_id=invoice.id)
    assert _count(admin, "invoice") == before  # no second debt
    assert entry.invoice_id == invoice.id and entry.owns_invoice is False
    await _refused(
        _entry(db, loaded, list_vnd=1_000, discount_vnd=0, invoice_id=invoice.id),
        ErrorCode.VALIDATION_FAILED,
        "Giá trị lượt vượt phần hóa đơn chưa phân bổ",
    )
    await _refused(
        _entry(db, loaded, list_vnd=1_000, discount_vnd=0, invoice_id=invoice.id, patient="P026"),
        ErrorCode.VALIDATION_FAILED,
        "Hóa đơn không thuộc bệnh nhân này",
    )
    await finance.void_entry(db, _as(loaded, "manager"), entry.id, EntryVoid(reason="Sai phân bổ"))
    again = (
        await finance_cash.list_invoices(db, _as(loaded, "manager"), patient_id=loaded.patients["P025"])
    ).items[0]
    assert again.amount_vnd == invoice.amount_vnd  # an invoice the entry did not create is never zeroed
    assert _count(admin, "invoice") == before


async def test_voiding_the_entry_that_made_an_invoice_keeps_it_when_another_entry_uses_it(
    db: ClinicDatabase, world: SeedResult
) -> None:
    first = await _entry(db, world)
    second = await _entry(
        db, world, list_vnd=1_000_000, discount_vnd=1_000_000, invoice_id=first.invoice_id
    )  # net 0
    assert second.owns_invoice is False
    manager = _as(world, "manager")
    await finance.void_entry(db, manager, first.id, EntryVoid(reason="Sai"))
    invoice = next(
        i for i in (await finance_cash.list_invoices(db, manager)).items if i.id == first.invoice_id
    )
    assert invoice.amount_vnd == 2_400_000  # another live entry still stands on it


async def test_an_order_invoice_is_raised_once_and_follows_the_draft(
    db: ClinicDatabase, loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _order(reception, loaded)
    billable = await finance_cash.list_billable_orders(db, _as(loaded, "reception.lan"))
    assert [b.order_id for b in billable] == [UUID(order["id"])] and billable[0].patient_code == "P025"
    invoice = await _invoice_of(db, loaded, order, who="reception.lan")
    same = await _invoice_of(db, loaded, order)
    assert same.id == invoice.id and same.number == invoice.number
    assert await finance_cash.list_billable_orders(db, _as(loaded, "reception.lan")) == []
    fetched = (await reception.get(f"/api/v1/orders/{order['id']}")).json()
    assert (
        fetched["invoice_id"] == str(invoice.id) and fetched["version"] == order["version"]
    )  # no stale draft

    saved = await reception.put(
        f"/api/v1/orders/{order['id']}",
        json={
            "version": order["version"],
            "diagnosis": order["diagnosis"],
            "items": [{"product_code": "H002", "quantity": 3, "usage": "Bôi lớp mỏng (mẫu)"}],
        },
    )
    assert saved.status_code == 200, saved.text
    after = (await finance_cash.list_invoices(db, _as(loaded, "manager"))).items[0]
    assert (
        after.amount_vnd == saved.json()["total_vnd"] != invoice.amount_vnd
    )  # the invoice follows the total


async def test_a_receipt_on_an_order_invoice_mirrors_to_the_order_and_locks_it(
    db: ClinicDatabase, loaded: SeedResult, client_factory: ClientFactory
) -> None:
    reception = await client_factory("reception.lan")
    order = await _order(reception, loaded)
    invoice = await _invoice_of(db, loaded, order)
    part = invoice.amount_vnd // 2
    await _pay(db, loaded, invoice.id, part, "order-part", who="reception.lan")
    midway = (await reception.get(f"/api/v1/orders/{order['id']}")).json()
    assert (midway["received_vnd"], midway["paid"], midway["editable"]) == (part, False, False)
    locked = await reception.put(
        f"/api/v1/orders/{order['id']}",
        json={
            "version": midway["version"],
            "diagnosis": "x",
            "items": [{"product_code": "H002", "quantity": 1}],
        },
    )
    assert _error(locked)[0] == 409 and _error(locked)[2] == "Đơn đã thu tiền; không thể sửa."
    again = await _pay(db, loaded, invoice.id, part, "order-part", who="reception.lan")
    assert again.replayed is True
    await _pay(db, loaded, invoice.id, invoice.amount_vnd - part, "order-rest")
    done = (await reception.get(f"/api/v1/orders/{order['id']}")).json()
    assert (done["received_vnd"], done["paid"]) == (invoice.amount_vnd, True)
    assert (
        len(await finance_cash.list_notifications(db, _as(loaded, "owner"))) == 2
    )  # one per receipt, none for the retry


async def test_an_order_without_value_or_unknown_gets_no_invoice(
    db: ClinicDatabase, loaded: SeedResult
) -> None:
    await _refused(
        finance_cash.create_for_order(db, _as(loaded, "manager"), InvoiceFromOrder(order_id=UUID(int=5))),
        ErrorCode.NOT_FOUND,
    )
    for key in ("doctor.mai", "cs.thu"):
        await _refused(
            finance_cash.create_for_order(db, _as(loaded, key), InvoiceFromOrder(order_id=UUID(int=5))),
            ErrorCode.FORBIDDEN,
        )


# ----------------------------------------------------------------- test_legacy_sync_not_double_collection
async def test_a_receipt_retried_from_another_channel_is_never_collected_twice(
    db: ClinicDatabase, loaded: SeedResult, client_factory: ClientFactory
) -> None:
    """The prototype mirrored the receipts of the old cashier and refused to collect them again. The cashier is the
    order flow now: the same guarantee is the idempotency key, whichever screen retries."""
    reception = await client_factory("reception.lan")
    order = await _order(reception, loaded)
    invoice = await _invoice_of(db, loaded, order)
    key = "WEB-PAY-300000"
    first = await _pay(db, loaded, invoice.id, 300_000, key, who="reception.lan")
    for who in ("reception.lan", "manager", "owner"):
        retried = await _pay(db, loaded, invoice.id, 300_000, key, who=who)
        assert retried.id == first.id and retried.replayed
    summary = (await finance_cash.list_invoices(db, _as(loaded, "manager"))).items[0]
    assert summary.received_vnd == 300_000
    assert len(await finance_cash.list_notifications(db, _as(loaded, "owner"))) == 1


# ---------------------------------------------------------------------------------------- periods and audit
async def test_the_periods_list_says_why_a_month_cannot_be_closed(
    db: ClinicDatabase, world: SeedResult
) -> None:
    await _entry(db, world, entry_date=DEMO_DAY.replace(month=8, day=10))  # pending
    manager = _as(world, "manager")
    listed = await finance.list_periods(db, manager)
    assert len(listed.items) == 12 and listed.items[0].month == MONTH and listed.items[1].month == LAST_MONTH
    assert listed.items[0].blocker == "Chỉ chốt tháng đã kết thúc" and listed.items[0].closable is False
    august = listed.items[1]
    assert (august.entry_count, august.pending_count, august.blocker) == (1, 1, "Còn lượt chờ duyệt")
    assert listed.items[2].blocker == "Kỳ không có dữ liệu"
    entry = (await finance.list_entries(db, manager, LAST_MONTH)).rows[0].entry_id
    await finance.approve_entry(db, manager, entry)
    assert (await finance.list_periods(db, manager)).items[1].closable is True
    await finance.close_period(db, manager, LAST_MONTH)
    closed = (await finance.list_periods(db, manager)).items[1]
    assert (closed.status, closed.closable, closed.blocker) == (PeriodStatus.CLOSED, False, None)
    await _refused(finance.list_periods(db, _as(world, "reception.lan")), ErrorCode.FORBIDDEN)


async def test_every_finance_mutation_is_audited_without_personal_text(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    manager = _as(world, "manager")
    entry = await _entry(
        db, world, entry_date=DEMO_DAY.replace(month=8, day=10), note="Ghi chú riêng tư của lượt"
    )
    voided = await _entry(db, world, entry_date=DEMO_DAY.replace(month=8, day=11))
    await finance.void_entry(db, manager, voided.id, EntryVoid(reason="Lý do hủy riêng tư"))
    await finance.approve_entry(db, manager, entry.id)
    receipt = await _pay(db, world, entry.invoice_id, 10_000, "audit-receipt")
    await finance_cash.mark_notification_read(
        db, _as(world, "owner"), (await finance_cash.list_notifications(db, _as(world, "owner")))[0].id
    )
    await finance.close_period(db, manager, LAST_MONTH)
    await finance.pay_period(db, manager, LAST_MONTH, PeriodPay(reference="CHI-AUDIT"))
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT action, entity_id, details::text FROM clinic.audit_log WHERE action LIKE 'finance.%' ORDER BY id"
            )
        ).all()
    actions = [r[0] for r in rows]
    assert actions == [
        "finance.entry.create",
        "finance.entry.create",
        "finance.entry.void",
        "finance.entry.approve",
        "finance.payment.record",
        "finance.notification.read",
        "finance.period.close",
        "finance.period.pay",
    ]
    blob = " ".join(r[2] for r in rows)
    for private in ("Ghi chú riêng tư", "Lý do hủy riêng tư", "BS. Mai", "P025"):
        assert private not in blob
    assert str(receipt.id) in {r[1] for r in rows}


async def test_a_failed_receipt_leaves_neither_a_notification_nor_an_audit_row(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    entry = await _entry(db, world)
    await _refused(_pay(db, world, entry.invoice_id, 9_999_999, "fails"), ErrorCode.VALIDATION_FAILED)
    assert _count(admin, "payment") == 0 and _count(admin, "finance_notification") == 0
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM clinic.audit_log WHERE action = 'finance.payment.record'")
            ).scalar_one()
            == 0
        )


async def test_the_receipts_of_a_month_are_listed_for_finance_readers_only(
    db: ClinicDatabase, world: SeedResult
) -> None:
    entry = await _entry(db, world)
    await _pay(db, world, entry.invoice_id, 100_000, "listed-1")
    await _pay(db, world, entry.invoice_id, 200_000, "listed-2")
    listed = await finance_cash.list_payments(db, _as(world, "manager"), MONTH)
    assert [p.amount_vnd for p in listed.items] == [200_000, 100_000] or {
        p.amount_vnd for p in listed.items
    } == {100_000, 200_000}
    assert listed.total == 2 and all(p.paid_on == DEMO_DAY for p in listed.items)
    assert (await finance_cash.list_payments(db, _as(world, "manager"), LAST_MONTH)).total == 0
    overview = await finance.overview(db, _as(world, "owner"), MONTH)
    assert overview.summary.collected_vnd == 300_000 and overview.summary.debt_vnd == 2_100_000
    assert overview.summary.revenue_vnd == 2_400_000  # performed revenue and cash are different numbers
    await _refused(finance_cash.list_payments(db, _as(world, "reception.lan"), MONTH), ErrorCode.FORBIDDEN)

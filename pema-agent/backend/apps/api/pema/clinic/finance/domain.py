# ported from: prototype/finance_server.py (money, Finance.rows, Finance.view summary, mutate 'entry' and
# 'close' validation); prototype/finance_test.py (test_revenue_rounding_reconciles,
# test_split_discount_and_snapshot)
"""PB02 finance rules that need no database: rounding, the split of revenue between performers, the commission
rows, the monthly summary, the validation of an entry and the reasons a month cannot be closed.

Forced deviations from the Python/JSON prototype:

* money and rates are the same integers (VND, basis points); ``money(base, rate)`` is the prototype's
  ``(base * rate + 5000) // 10000`` (round half up, on the dong);
* a performer is a user account (``doctor_id`` uuid) instead of the fixed ids ``D0``..``D3``; "at most four
  performers" and "each performer once" are kept;
* the prototype limited an entry to a patient code ``P001``..``P999``; here the patient must exist in the
  clinic (checked by the action);
* messages are the prototype's Vietnamese sentences, raised as ``DomainError(VALIDATION_FAILED)``.

Rules kept as they were, because they are the PB02 rules of AGENT.md: performed revenue is never mixed with
collected cash; the rate and the basis are a snapshot of the entry, so a later change of the service terms
moves nothing; the performer is never taken from the doctor in charge of the record; a closed month is frozen.

This module is pure: it imports no database code.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from pema_contracts.errors import DomainError, ErrorCode

MAX_PEOPLE = 4
BASIS_NET = "net"
BASIS_LIST = "list"
BASIS_COLLECTED = "collected"
STATUS_PENDING = "pending"
STATUS_APPROVED = "approved"
STATUS_VOID = "void"

INVALID_MONTH_MESSAGE = "Tháng không hợp lệ"
INVALID_DAY_MESSAGE = "Ngày thực hiện không hợp lệ"
PERIOD_CLOSED_MESSAGE = "Kỳ đã chốt"
PERIOD_CLOSED_EDIT_MESSAGE = "Kỳ đã chốt, không được sửa"
NEED_PEOPLE_MESSAGE = "Cần người thực hiện"
DUPLICATE_PEOPLE_MESSAGE = "Trùng người thực hiện"
INVALID_PERFORMER_MESSAGE = "Người thực hiện không hợp lệ"
SHARE_TOTAL_MESSAGE = "Tổng tỷ trọng doanh số phải là 100%"
RATE_TOTAL_MESSAGE = "Tổng tỷ lệ tiền thủ thuật không vượt 100%"
NOTE_REQUIRED_MESSAGE = "Ghi chú xác nhận hoàn tất là bắt buộc"
INVALID_AMOUNT_MESSAGE = "Số tiền/tỷ lệ không hợp lệ"
OVER_ALLOCATED_MESSAGE = "Giá trị lượt vượt phần hóa đơn chưa phân bổ"
WRONG_INVOICE_MESSAGE = "Hóa đơn không thuộc bệnh nhân này"
ENTRY_VOID_MESSAGE = "Lượt đã hủy"
VOID_REASON_MESSAGE = "Cần lý do hủy"
VOID_PAID_MESSAGE = "Lượt đã thu tiền; cần quy trình hoàn/điều chỉnh riêng"
ONLY_ENDED_MONTHS_MESSAGE = "Chỉ chốt tháng đã kết thúc"
NO_DATA_MESSAGE = "Kỳ không có dữ liệu"
COLLECTED_OPEN_MESSAGE = "Còn lượt tính theo thực thu chưa thu đủ; chưa thể chốt để tránh mất tiền kỳ sau"
PENDING_LEFT_MESSAGE = "Còn lượt chờ duyệt"
CLOSE_BEFORE_PAY_MESSAGE = "Cần chốt kỳ trước khi xác nhận chi"
OVERPAYMENT_MESSAGE = "Số thu vượt công nợ"
KEY_REUSED_MESSAGE = "Mã giao dịch đã dùng cho nội dung khác"

_MONTH = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def fail(message: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, message)


def money(base: int, rate_bp: int) -> int:
    """``money``: ``base`` x ``rate`` (basis points), rounded half up to the dong."""
    return (base * rate_bp + 5000) // 10000


def format_vnd(amount: int) -> str:
    """``1.000.000``: the way the prototype wrote an amount in a notification."""
    return format(amount, ",").replace(",", ".")


# ------------------------------------------------------------------------------------------------- months
def parse_month(month: str) -> date:
    """The first day of ``YYYY-MM``; ``valid_day(month + '-01')`` of the prototype."""
    found = _MONTH.match(month)
    if found is None:
        raise fail(INVALID_MONTH_MESSAGE)
    return date(int(found.group(1)), int(found.group(2)), 1)


def month_of(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def next_month_start(first: date) -> date:
    return date(first.year + 1, 1, 1) if first.month == 12 else date(first.year, first.month + 1, 1)


def previous_months(today: date, count: int) -> list[str]:
    """``count`` months ending with the current one, newest first."""
    months: list[str] = []
    year, month = today.year, today.month
    for _ in range(count):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return months


# ---------------------------------------------------------------------------------------------- entries
@dataclass(frozen=True)
class Person:
    """One performer of one procedure with the snapshot of the share and the rate that applied."""

    doctor_id: UUID
    share_bp: int
    rate_bp: int


def validate_amounts(list_vnd: int, discount_vnd: int) -> int:
    """The net price. The contract bounds the numbers; this keeps the relation (discount within the list
    price)."""
    if list_vnd < 1 or discount_vnd < 0 or discount_vnd > list_vnd:
        raise fail(INVALID_AMOUNT_MESSAGE)
    return list_vnd - discount_vnd


def validate_people(people: Sequence[Person]) -> None:
    """``mutate('entry')``: one to four performers, each once, shares add up to 100 %, rates to at most 100 %.
    That the performers are doctors of this clinic is checked by the action, which knows the accounts."""
    if not 0 < len(people) <= MAX_PEOPLE:
        raise fail(NEED_PEOPLE_MESSAGE)
    if len({p.doctor_id for p in people}) != len(people):
        raise fail(DUPLICATE_PEOPLE_MESSAGE)
    for person in people:
        if not 1 <= person.share_bp <= 10000 or not 0 <= person.rate_bp <= 10000:
            raise fail(INVALID_AMOUNT_MESSAGE)
    if sum(p.share_bp for p in people) != 10000:
        raise fail(SHARE_TOTAL_MESSAGE)
    if sum(p.rate_bp for p in people) > 10000:
        raise fail(RATE_TOTAL_MESSAGE)


def require_note(note: str) -> str:
    cleaned = note.strip()
    if not cleaned:
        raise fail(NOTE_REQUIRED_MESSAGE)
    return cleaned


def require_entry_day(day: date, today: date) -> None:
    """The procedure was done: not in the future."""
    if day > today:
        raise fail(INVALID_DAY_MESSAGE)


# -------------------------------------------------------------------------------------------- the rows
@dataclass(frozen=True)
class EntryFacts:
    """What the commission table needs to know about one entry and the invoice it belongs to."""

    id: UUID
    entry_date: date
    patient_code: str
    service_name: str
    status: str
    basis: str
    list_vnd: int
    net_vnd: int
    note: str
    invoice_amount_vnd: int
    invoice_received_vnd: int
    people: tuple[Person, ...]


@dataclass(frozen=True)
class Row:
    entry_id: UUID
    date: date
    patient_code: str
    service_name: str
    doctor_id: UUID
    status: str
    basis: str
    base_vnd: int
    rate_bp: int
    share_bp: int
    revenue_vnd: int
    fee_vnd: int
    note: str


def base_for(entry: EntryFacts) -> int:
    """The amount the commission rate applies to. ``collected`` follows what the invoice has received so far
    (frozen when the month is closed)."""
    if entry.basis == BASIS_NET:
        return entry.net_vnd
    if entry.basis == BASIS_LIST:
        return entry.list_vnd
    return min(entry.net_vnd, entry.net_vnd * entry.invoice_received_vnd // max(1, entry.invoice_amount_vnd))


def revenue_split(net_vnd: int, people: Sequence[Person]) -> list[int]:
    """The revenue of each performer: ``net`` x share, the last performer takes the remainder so that the rows
    add up to the net price exactly."""
    split: list[int] = []
    allocated = 0
    for index, person in enumerate(people):
        revenue = net_vnd - allocated if index == len(people) - 1 else net_vnd * person.share_bp // 10000
        allocated += revenue
        split.append(revenue)
    return split


def compute_rows(entries: Iterable[EntryFacts]) -> list[Row]:
    """``Finance.rows``: one row per performer of every entry, in the order of the entries."""
    rows: list[Row] = []
    for entry in entries:
        base = base_for(entry)
        for person, revenue in zip(entry.people, revenue_split(entry.net_vnd, entry.people), strict=True):
            rows.append(
                Row(
                    entry_id=entry.id,
                    date=entry.entry_date,
                    patient_code=entry.patient_code,
                    service_name=entry.service_name,
                    doctor_id=person.doctor_id,
                    status=entry.status,
                    basis=entry.basis,
                    base_vnd=base,
                    rate_bp=person.rate_bp,
                    share_bp=person.share_bp,
                    revenue_vnd=revenue,
                    fee_vnd=money(base, person.rate_bp),
                    note=entry.note,
                )
            )
    return rows


# ------------------------------------------------------------------------------------------- summaries
@dataclass(frozen=True)
class Summary:
    revenue_vnd: int
    fee_vnd: int
    pending_vnd: int


def summarize(rows: Sequence[Row], *, entries_net_vnd: int | None = None) -> Summary:
    """``view``: the fee of the approved rows, the fee still pending, and the performed revenue. A personal
    projection sums the revenue of the caller's rows; the clinic projection sums the net price of the entries
    (``entries_net_vnd``) so a procedure shared by two doctors counts once."""
    active = [r for r in rows if r.status != STATUS_VOID]
    revenue = sum(r.revenue_vnd for r in active) if entries_net_vnd is None else entries_net_vnd
    return Summary(
        revenue_vnd=revenue,
        fee_vnd=sum(r.fee_vnd for r in active if r.status == STATUS_APPROVED),
        pending_vnd=sum(r.fee_vnd for r in active if r.status == STATUS_PENDING),
    )


@dataclass(frozen=True)
class TeamLine:
    doctor_id: UUID
    entry_count: int
    revenue_vnd: int
    fee_vnd: int


def team_lines(rows: Sequence[Row], doctor_ids: Iterable[UUID]) -> list[TeamLine]:
    """ "Đóng góp của đội ngũ": per doctor, the non-void rows: how many, the revenue, the approved fee."""
    lines: list[TeamLine] = []
    for doctor_id in doctor_ids:
        mine = [r for r in rows if r.doctor_id == doctor_id and r.status != STATUS_VOID]
        lines.append(
            TeamLine(
                doctor_id=doctor_id,
                entry_count=len(mine),
                revenue_vnd=sum(r.revenue_vnd for r in mine),
                fee_vnd=sum(r.fee_vnd for r in mine if r.status == STATUS_APPROVED),
            )
        )
    return lines


# --------------------------------------------------------------------------------------------- closing
def close_blocker(month_start: date, today: date, entries: Sequence[EntryFacts]) -> str | None:
    """Why ``month`` cannot be closed, in the order of ``mutate('close')``: only a month that ended; a month
    with data; every entry paid in full when its fee is on the collected basis; nothing left pending. The
    caller has already refused a month that is closed. ``None`` when the month may be closed."""
    if month_start >= date(today.year, today.month, 1):
        return ONLY_ENDED_MONTHS_MESSAGE
    if not entries:
        return NO_DATA_MESSAGE
    if any(
        e.status != STATUS_VOID
        and e.basis == BASIS_COLLECTED
        and e.invoice_received_vnd < e.invoice_amount_vnd
        for e in entries
    ):
        return COLLECTED_OPEN_MESSAGE
    if any(e.status == STATUS_PENDING for e in entries):
        return PENDING_LEFT_MESSAGE
    return None


# ------------------------------------------------------------------------------------------------ csv
CSV_HEADER = (
    "Ngay",
    "Ho so",
    "Thu thuat",
    "Bac si",
    "Doanh so",
    "Co so",
    "Ty le %",
    "Tien thu thuat",
    "Trang thai",
)


def csv_safe(value: object) -> str:
    """A cell Excel cannot read as a formula: text that starts with ``=``, ``+``, ``-`` or ``@`` (and a tab
    or a carriage return, which Excel also strips before looking) gets a leading apostrophe."""
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_PREFIXES) else text


def csv_record(row: Row, doctor_name: str) -> list[str]:
    """One line of the export, in the column order of ``CSV_HEADER``. The rate is written as a percentage."""
    return [
        csv_safe(x)
        for x in (
            row.date.isoformat(),
            row.patient_code,
            row.service_name,
            doctor_name,
            row.revenue_vnd,
            row.base_vnd,
            row.rate_bp / 100,
            row.fee_vnd,
            row.status,
        )
    ]


def snapshot_row(row: Row, doctor_name: str) -> dict[str, object]:
    """The JSON form of a row kept in a closed period (the doctor's name is frozen with it)."""
    return {
        "entry_id": str(row.entry_id),
        "date": row.date.isoformat(),
        "patient_code": row.patient_code,
        "service_name": row.service_name,
        "doctor_id": str(row.doctor_id),
        "doctor_name": doctor_name,
        "status": row.status,
        "basis": row.basis,
        "base_vnd": row.base_vnd,
        "rate_bp": row.rate_bp,
        "share_bp": row.share_bp,
        "revenue_vnd": row.revenue_vnd,
        "fee_vnd": row.fee_vnd,
        "note": row.note,
    }


def rows_from_snapshot(snapshot: Iterable[Mapping[str, object]]) -> list[tuple[Row, str]]:
    """The rows (and the frozen doctor names) of a closed period, as they were when it was closed."""
    out: list[tuple[Row, str]] = []
    for item in snapshot:
        out.append(
            (
                Row(
                    entry_id=UUID(str(item["entry_id"])),
                    date=date.fromisoformat(str(item["date"])),
                    patient_code=str(item["patient_code"]),
                    service_name=str(item["service_name"]),
                    doctor_id=UUID(str(item["doctor_id"])),
                    status=str(item["status"]),
                    basis=str(item["basis"]),
                    base_vnd=int(str(item["base_vnd"])),
                    rate_bp=int(str(item["rate_bp"])),
                    share_bp=int(str(item["share_bp"])),
                    revenue_vnd=int(str(item["revenue_vnd"])),
                    fee_vnd=int(str(item["fee_vnd"])),
                    note=str(item["note"]),
                ),
                str(item["doctor_name"]),
            )
        )
    return out

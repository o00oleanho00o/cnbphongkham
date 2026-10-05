# translated from prototype/finance_test.py (money, split, rounding, validation) and extended (package U, step U6)
"""PB02 rules that need no database: rounding, the split of revenue between performers, the commission rows, the
summary, the reasons a month cannot be closed and the CSV formula guard."""

from __future__ import annotations

from datetime import date
from uuid import UUID, uuid4

import pytest

from pema.clinic.finance import domain
from pema.clinic.finance.domain import EntryFacts, Person
from pema_contracts.errors import DomainError, ErrorCode

A, B, C = uuid4(), uuid4(), uuid4()


def _entry(**kw: object) -> EntryFacts:
    base: dict[str, object] = {
        "id": uuid4(),
        "entry_date": date(2026, 9, 10),
        "patient_code": "P025",
        "service_name": "Laser theo chỉ định",
        "status": "approved",
        "basis": "net",
        "list_vnd": 2_500_000,
        "net_vnd": 2_400_000,
        "note": "Đã hoàn tất",
        "invoice_amount_vnd": 2_400_000,
        "invoice_received_vnd": 0,
        "people": (Person(A, 7000, 1500), Person(B, 3000, 500)),
    }
    base.update(kw)
    return EntryFacts(**base)  # type: ignore[arg-type]


def _refused(message: str) -> pytest.RaisesExc[DomainError]:
    return pytest.raises(DomainError, match=message)


# ------------------------------------------------------------------------------------------- the money
@pytest.mark.parametrize(
    ("base", "rate", "expected"),
    [
        (2_400_000, 1500, 360_000),  # the example of docs/24: 15 % of 2.4 million
        (2_400_000, 500, 120_000),
        (1, 5000, 1),  # half a dong rounds up
        (1, 4999, 0),
        (3, 5000, 2),
        (0, 10000, 0),
        (333_333, 1000, 33_333),
    ],
)
def test_money_rounds_half_up_on_the_dong(base: int, rate: int, expected: int) -> None:
    assert domain.money(base, rate) == expected


def test_the_split_follows_the_documented_example() -> None:
    rows = domain.compute_rows([_entry()])
    assert [r.revenue_vnd for r in rows] == [1_680_000, 720_000]
    assert [r.fee_vnd for r in rows] == [360_000, 120_000]
    assert sum(r.revenue_vnd for r in rows) == 2_400_000  # revenue and fee are two different numbers


def test_revenue_rounding_reconciles_to_the_net_price() -> None:
    people = (Person(A, 3333, 1000), Person(B, 3333, 1000), Person(C, 3334, 1000))
    rows = domain.compute_rows([_entry(list_vnd=101, net_vnd=101, invoice_amount_vnd=101, people=people)])
    assert sum(r.revenue_vnd for r in rows) == 101
    assert [r.revenue_vnd for r in rows] == [33, 33, 35]  # the last performer takes the remainder


@pytest.mark.parametrize("net", [1, 7, 99, 100_001, 2_400_000])
def test_revenue_always_adds_up_whatever_the_shares(net: int) -> None:
    assert sum(domain.revenue_split(net, (Person(A, 3333, 0), Person(B, 3333, 0), Person(C, 3334, 0)))) == net


# ---------------------------------------------------------------------------------------------- bases
def test_the_basis_decides_what_the_rate_applies_to() -> None:
    assert domain.base_for(_entry(basis="net")) == 2_400_000
    assert domain.base_for(_entry(basis="list")) == 2_500_000
    assert domain.base_for(_entry(basis="collected", invoice_received_vnd=1_200_000)) == 1_200_000
    assert domain.base_for(_entry(basis="collected", invoice_received_vnd=2_400_000)) == 2_400_000
    assert domain.base_for(_entry(basis="collected", invoice_received_vnd=0)) == 0


def test_a_collected_base_never_exceeds_the_net_price_and_survives_an_empty_invoice() -> None:
    assert domain.base_for(
        _entry(basis="collected", invoice_amount_vnd=1_000_000, invoice_received_vnd=1_000_000)
    ) == (2_400_000)
    assert domain.base_for(_entry(basis="collected", invoice_amount_vnd=0, invoice_received_vnd=0)) == 0


def test_the_snapshot_of_a_row_does_not_follow_later_terms() -> None:
    entry = _entry()
    first = domain.compute_rows([entry])
    again = domain.compute_rows([entry])  # the rate lives on the person: nothing else can move it
    assert first == again
    assert [r.rate_bp for r in first] == [1500, 500]


# ------------------------------------------------------------------------------------------ validation
def test_a_valid_split_passes() -> None:
    domain.validate_people((Person(A, 7000, 1500), Person(B, 3000, 500)))
    domain.validate_people((Person(A, 10000, 10000),))
    domain.validate_people(
        (Person(A, 2500, 0), Person(B, 2500, 0), Person(C, 2500, 0), Person(uuid4(), 2500, 0))
    )


@pytest.mark.parametrize(
    ("people", "message"),
    [
        ((), domain.NEED_PEOPLE_MESSAGE),
        ((Person(A, 5000, 0),) * 5, domain.NEED_PEOPLE_MESSAGE),
        ((Person(A, 5000, 0), Person(A, 5000, 0)), domain.DUPLICATE_PEOPLE_MESSAGE),
        ((Person(A, 7000, 2000),), domain.SHARE_TOTAL_MESSAGE),
        ((Person(A, 6000, 0), Person(B, 6000, 0)), domain.SHARE_TOTAL_MESSAGE),
        ((Person(A, 5000, 6000), Person(B, 5000, 5000)), domain.RATE_TOTAL_MESSAGE),
        ((Person(A, 10000, 11000),), domain.INVALID_AMOUNT_MESSAGE),
        ((Person(A, 0, 0), Person(B, 10000, 0)), domain.INVALID_AMOUNT_MESSAGE),
    ],
)
def test_an_invalid_split_is_refused_with_the_prototype_message(
    people: tuple[Person, ...], message: str
) -> None:
    with pytest.raises(DomainError) as caught:
        domain.validate_people(people)
    assert caught.value.code is ErrorCode.VALIDATION_FAILED
    assert caught.value.message == message


def test_amounts_keep_the_discount_inside_the_list_price() -> None:
    assert domain.validate_amounts(2_500_000, 100_000) == 2_400_000
    assert domain.validate_amounts(1, 1) == 0
    for list_vnd, discount in ((3_000_000, 3_000_001), (0, 0), (10, -1)):
        with _refused(domain.INVALID_AMOUNT_MESSAGE):
            domain.validate_amounts(list_vnd, discount)


def test_the_note_is_required_and_the_day_cannot_be_in_the_future() -> None:
    assert domain.require_note("  Đã hoàn tất  ") == "Đã hoàn tất"
    with _refused(domain.NOTE_REQUIRED_MESSAGE):
        domain.require_note("   ")
    domain.require_entry_day(date(2026, 9, 20), date(2026, 9, 20))
    with _refused(domain.INVALID_DAY_MESSAGE):
        domain.require_entry_day(date(2026, 9, 21), date(2026, 9, 20))


# -------------------------------------------------------------------------------------------- summary
def test_the_summary_keeps_revenue_fee_and_pending_apart() -> None:
    rows = domain.compute_rows(
        [
            _entry(status="approved"),
            _entry(status="pending", net_vnd=1_000_000, list_vnd=1_000_000, invoice_amount_vnd=1_000_000),
            _entry(status="void"),
        ]
    )
    summary = domain.summarize(rows)
    assert summary.revenue_vnd == 2_400_000 + 1_000_000  # void rows count for nothing
    assert summary.fee_vnd == 360_000 + 120_000  # approved only
    assert summary.pending_vnd == 150_000 + 50_000  # pending only, never part of the approved fee


def test_the_clinic_revenue_counts_a_shared_procedure_once() -> None:
    rows = domain.compute_rows([_entry()])
    assert domain.summarize(rows, entries_net_vnd=2_400_000).revenue_vnd == 2_400_000
    assert domain.summarize(rows).revenue_vnd == 2_400_000


def test_the_team_lines_count_live_rows_per_doctor() -> None:
    rows = domain.compute_rows([_entry(), _entry(status="void"), _entry(status="pending")])
    lines = {line.doctor_id: line for line in domain.team_lines(rows, [A, B, C])}
    assert (lines[A].entry_count, lines[A].revenue_vnd, lines[A].fee_vnd) == (2, 3_360_000, 360_000)
    assert (lines[B].entry_count, lines[B].revenue_vnd, lines[B].fee_vnd) == (2, 1_440_000, 120_000)
    assert (lines[C].entry_count, lines[C].revenue_vnd, lines[C].fee_vnd) == (0, 0, 0)


# ---------------------------------------------------------------------------------------------- closing
AUGUST = date(2026, 8, 1)
SEPTEMBER = date(2026, 9, 1)
TODAY = date(2026, 9, 20)


def test_only_a_month_that_ended_can_be_closed() -> None:
    assert domain.close_blocker(SEPTEMBER, TODAY, [_entry()]) == domain.ONLY_ENDED_MONTHS_MESSAGE
    assert domain.close_blocker(date(2026, 10, 1), TODAY, [_entry()]) == domain.ONLY_ENDED_MONTHS_MESSAGE
    assert domain.close_blocker(AUGUST, TODAY, [_entry()]) is None


def test_an_empty_month_cannot_be_closed() -> None:
    assert domain.close_blocker(AUGUST, TODAY, []) == domain.NO_DATA_MESSAGE


def test_a_pending_entry_blocks_the_close() -> None:
    assert (
        domain.close_blocker(AUGUST, TODAY, [_entry(), _entry(status="pending")])
        == domain.PENDING_LEFT_MESSAGE
    )


def test_an_entry_on_the_collected_basis_must_be_paid_in_full_first() -> None:
    owed = _entry(basis="collected", invoice_received_vnd=1_200_000)
    assert domain.close_blocker(AUGUST, TODAY, [owed]) == domain.COLLECTED_OPEN_MESSAGE
    paid = _entry(basis="collected", invoice_received_vnd=2_400_000)
    assert domain.close_blocker(AUGUST, TODAY, [paid]) is None
    voided = _entry(basis="collected", invoice_received_vnd=0, status="void")
    assert domain.close_blocker(AUGUST, TODAY, [voided, _entry()]) is None  # a void entry owes nothing


def test_the_collected_check_comes_before_the_pending_check_as_in_the_prototype() -> None:
    both = [_entry(basis="collected", status="pending", invoice_received_vnd=1)]
    assert domain.close_blocker(AUGUST, TODAY, both) == domain.COLLECTED_OPEN_MESSAGE


# -------------------------------------------------------------------------------------------- months
def test_months_parse_and_walk_across_a_year() -> None:
    assert domain.parse_month("2026-09") == date(2026, 9, 1)
    assert domain.month_of(date(2026, 9, 20)) == "2026-09"
    assert domain.next_month_start(date(2026, 12, 1)) == date(2027, 1, 1)
    assert domain.next_month_start(date(2026, 9, 1)) == date(2026, 10, 1)
    assert domain.previous_months(date(2026, 2, 3), 4) == ["2026-02", "2026-01", "2025-12", "2025-11"]
    for bad in ("2026-13", "2026-9", "26-09", "2026-09-01", "", "abcd-ef"):
        with _refused(domain.INVALID_MONTH_MESSAGE):
            domain.parse_month(bad)


def test_an_amount_is_written_with_dots() -> None:
    assert domain.format_vnd(1_000_000) == "1.000.000"
    assert domain.format_vnd(950) == "950"


# ------------------------------------------------------------------------------------------------ csv
@pytest.mark.parametrize("danger", ["=1+1", "+1", "-1+2", "@SUM(A1)", "\t=1", "\r=1", '=HYPERLINK("x")'])
def test_a_cell_that_could_be_a_formula_gets_an_apostrophe(danger: str) -> None:
    assert domain.csv_safe(danger) == "'" + danger


@pytest.mark.parametrize("fine", ["BS. Mai (mẫu)", "Laser theo chỉ định", "1500000", "P025", "", "a=b"])
def test_other_cells_are_left_alone(fine: str) -> None:
    assert domain.csv_safe(fine) == fine


def test_the_csv_line_follows_the_header_and_writes_the_rate_as_a_percentage() -> None:
    row = domain.compute_rows([_entry()])[0]
    record = domain.csv_record(row, "BS. Tâm (mẫu)")
    assert len(record) == len(domain.CSV_HEADER) == 9
    assert record == [
        "2026-09-10",
        "P025",
        "Laser theo chỉ định",
        "BS. Tâm (mẫu)",
        "1680000",
        "2400000",
        "15.0",
        "360000",
        "approved",
    ]


def test_a_doctor_name_that_starts_like_a_formula_is_neutralised() -> None:
    row = domain.compute_rows([_entry()])[0]
    assert domain.csv_record(row, "=cmd|' /C calc'!A0")[3].startswith("'=")


def test_a_snapshot_round_trips_with_the_frozen_names() -> None:
    rows = domain.compute_rows([_entry()])
    frozen = [domain.snapshot_row(r, f"BS {i}") for i, r in enumerate(rows)]
    back = domain.rows_from_snapshot(frozen)
    assert [r for r, _ in back] == rows
    assert [n for _, n in back] == ["BS 0", "BS 1"]
    assert isinstance(back[0][0].doctor_id, UUID)

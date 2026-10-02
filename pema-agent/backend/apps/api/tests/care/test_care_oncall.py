"""The 24/7 on-call contact: which row is current, read on every call, audited use (package M, M2c).

New tests (no zalo-agent original). No database: ``InMemoryOnCallSource`` stands in for the view
``clinic_agent.on_call_contact``. Every number here is a placeholder flagged ``is_fixture``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pema.care.oncall import MAX_CACHE_TTL_SECONDS, OnCallDirectory, pick_on_call
from pema.care.routing_types import OnCallRow
from pema.care.testing import FakeClock, InMemoryCareStore, vn
from pema.care.testing_routing import InMemoryOnCallSource

NOW = vn(2026, 10, 5, 10, 0)
CLINIC = UUID(int=1)


def row(number: str, *, days_ago: int = 30, until_days: int | None = None, active: bool = True) -> OnCallRow:
    return OnCallRow(
        id=uuid4(),
        zalo_number=number,
        owner="Trực (mẫu)",
        valid_from=NOW - timedelta(days=days_ago),
        valid_to=None if until_days is None else NOW + timedelta(days=until_days),
        active=active,
        is_fixture=True,
    )


# -------------------------------------------------------------------------------------- picking
def test_the_active_row_that_covers_now_is_picked() -> None:
    assert pick_on_call([row("0000000001")], NOW) is not None
    assert pick_on_call([], NOW) is None


def test_inactive_expired_and_future_rows_are_never_picked() -> None:
    rows = [
        row("0000000001", active=False),
        row("0000000002", days_ago=60, until_days=-1),
        row("0000000003", days_ago=-2),
    ]
    assert pick_on_call(rows, NOW) is None


def test_the_end_of_validity_is_exclusive_and_the_start_inclusive() -> None:
    only = OnCallRow(
        id=uuid4(), zalo_number="0000000001", owner="x", valid_from=NOW, valid_to=NOW + timedelta(hours=1)
    )
    assert pick_on_call([only], NOW) is only
    assert pick_on_call([only], NOW + timedelta(hours=1)) is None
    assert pick_on_call([only], NOW - timedelta(seconds=1)) is None


def test_the_row_that_became_valid_last_wins_and_ties_are_deterministic() -> None:
    older = row("0000000001", days_ago=30)
    newer = row("0000000002", days_ago=2)
    assert pick_on_call([older, newer], NOW) is newer
    assert pick_on_call([newer, older], NOW) is newer
    first = OnCallRow(id=UUID(int=5), zalo_number="1", owner="x", valid_from=NOW - timedelta(days=1))
    second = OnCallRow(id=UUID(int=9), zalo_number="2", owner="x", valid_from=NOW - timedelta(days=1))
    assert pick_on_call([first, second], NOW) is second
    assert pick_on_call([second, first], NOW) is second


def test_a_scheduled_replacement_takes_over_at_its_start() -> None:
    now_row = row("0000000001", days_ago=30, until_days=1)
    next_row = row("0000000002", days_ago=-1)
    assert pick_on_call([now_row, next_row], NOW) is now_row
    assert pick_on_call([now_row, next_row], NOW + timedelta(days=1, minutes=1)) is next_row


# ------------------------------------------------------------------------------------ the lookup
async def test_every_call_reads_the_database_by_default() -> None:
    source = InMemoryOnCallSource(number="0000000001")
    directory = OnCallDirectory(source)
    first = await directory.current_on_call(CLINIC, NOW)
    assert first is not None
    assert first.zalo_number == "0000000001"
    assert first.is_fixture
    source.set_number("0000000002")  # the dashboard edit
    second = await directory.current_on_call(CLINIC, NOW)
    assert second is not None
    assert second.zalo_number == "0000000002"
    assert source.reads == 2


async def test_no_contact_configured_is_none() -> None:
    directory = OnCallDirectory(InMemoryOnCallSource(number=None))
    assert await directory.current_on_call(CLINIC, NOW) is None


async def test_an_optional_cache_never_lives_longer_than_sixty_seconds() -> None:
    clock = FakeClock(datetime(2026, 10, 5, 3, 0, tzinfo=UTC))
    source = InMemoryOnCallSource(number="0000000001")
    directory = OnCallDirectory(
        source, cache_ttl_seconds=3600, monotonic=lambda: clock.now.timestamp()
    )  # asks for an hour, gets 60 s
    assert MAX_CACHE_TTL_SECONDS == 60.0
    await directory.current_on_call(CLINIC, clock.now)
    source.set_number("0000000002")
    clock.advance(timedelta(seconds=59))
    stale = await directory.current_on_call(CLINIC, clock.now)
    assert stale is not None
    assert stale.zalo_number == "0000000001"
    clock.advance(timedelta(seconds=2))
    fresh = await directory.current_on_call(CLINIC, clock.now)
    assert fresh is not None
    assert fresh.zalo_number == "0000000002"
    assert source.reads == 2


async def test_a_negative_cache_time_means_no_cache() -> None:
    clock = FakeClock(NOW)
    source = InMemoryOnCallSource(number="0000000001")
    directory = OnCallDirectory(source, cache_ttl_seconds=-5, monotonic=lambda: clock.now.timestamp())
    await directory.current_on_call(CLINIC, NOW)
    await directory.current_on_call(CLINIC, NOW)
    assert source.reads == 2


# ---------------------------------------------------------------------------------------- audit
async def test_every_use_is_one_oncall_used_line_without_the_number() -> None:
    care = InMemoryCareStore()
    agent = care.add_patient("P900")
    directory = OnCallDirectory(InMemoryOnCallSource(number="0000000001"), care)
    await directory.record_use(agent.id, "notify", "D4", NOW)
    (line,) = care.actions
    assert line.action_type == "oncall_used:notify"
    assert line.disposition == "paused"
    assert line.depth == "D4"
    assert "0000000001" not in line.action_type


async def test_record_use_without_a_recorder_is_a_no_op() -> None:
    await OnCallDirectory(InMemoryOnCallSource()).record_use(uuid4(), "chain", None, NOW)

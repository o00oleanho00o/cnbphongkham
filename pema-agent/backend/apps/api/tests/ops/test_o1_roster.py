"""Roster: who covers each identity, when (package O, step O1). New tests (no zalo-agent original).

The pure half checks ``slot_covers`` (a weekday set, an explicit date, a slot across midnight, the end excluded,
the +07:00 clock). The database half (needs ``PEMA_TEST_DATABASE_URL``) checks ``who_is_on``, the validation of
the user and of the identity, RBAC, the audit rows (ids and times, never the note) and the HTTP routes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.clinic.actions import roster
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.common import VN_TZ
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import RosterEntryCreate, RosterEntryUpdate, Weekday


def vn(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=VN_TZ)


# 2026-09-21 is a Monday, 2026-09-20 a Sunday.
MON = (2026, 9, 21)
TUE = (2026, 9, 22)
SUN = (2026, 9, 20)


# ------------------------------------------------------------------------------------------ pure rules
def test_a_weekday_slot_covers_its_days_and_hours_only() -> None:
    days = ["mon", "wed"]
    start, end = time(8, 0), time(17, 0)
    assert roster.slot_covers(days, None, start, end, vn(*MON, 8, 0))
    assert roster.slot_covers(days, None, start, end, vn(*MON, 16, 59))
    assert not roster.slot_covers(days, None, start, end, vn(*MON, 7, 59))
    assert not roster.slot_covers(days, None, start, end, vn(*TUE, 10, 0))
    assert roster.slot_covers(days, None, start, end, vn(2026, 9, 23, 10, 0))


def test_the_end_of_a_slot_is_not_covered_and_the_start_is() -> None:
    assert roster.slot_covers(["mon"], None, time(8, 0), time(12, 0), vn(*MON, 8, 0))
    assert not roster.slot_covers(["mon"], None, time(8, 0), time(12, 0), vn(*MON, 12, 0))


def test_a_night_slot_runs_into_the_next_morning() -> None:
    days, start, end = ["mon"], time(22, 0), time(6, 0)
    assert roster.slot_covers(days, None, start, end, vn(*MON, 22, 0))
    assert roster.slot_covers(days, None, start, end, vn(*MON, 23, 59))
    assert roster.slot_covers(days, None, start, end, vn(*TUE, 0, 0))  # across midnight
    assert roster.slot_covers(days, None, start, end, vn(*TUE, 5, 59))
    assert not roster.slot_covers(days, None, start, end, vn(*TUE, 6, 0))  # the end is not covered
    assert not roster.slot_covers(
        days, None, start, end, vn(*MON, 5, 0)
    )  # the morning belongs to SUNDAY's slot
    assert not roster.slot_covers(days, None, start, end, vn(*TUE, 22, 30))  # Tuesday is not in the set


def test_a_night_slot_of_sunday_ends_on_monday_morning() -> None:
    assert roster.slot_covers(["sun"], None, time(22, 0), time(6, 0), vn(*MON, 3, 0))
    assert not roster.slot_covers(["sun"], None, time(22, 0), time(6, 0), vn(2026, 9, 22, 3, 0))


def test_an_explicit_date_covers_that_date_only_and_crosses_midnight_too() -> None:
    day = date(2026, 9, 21)
    assert roster.slot_covers(None, day, time(9, 0), time(11, 0), vn(*MON, 10, 0))
    assert not roster.slot_covers(None, day, time(9, 0), time(11, 0), vn(*TUE, 10, 0))
    assert not roster.slot_covers(None, day, time(9, 0), time(11, 0), vn(2026, 9, 28, 10, 0))  # not weekly
    assert roster.slot_covers(None, day, time(23, 0), time(2, 0), vn(*TUE, 1, 0))
    assert not roster.slot_covers(None, day, time(23, 0), time(2, 0), vn(*TUE, 2, 0))


def test_the_clock_is_the_clinic_clock_whatever_zone_the_moment_comes_in() -> None:
    # 01:30 UTC on Monday is 08:30 in Ho Chi Minh City
    moment = datetime(2026, 9, 21, 1, 30, tzinfo=UTC)
    assert roster.slot_covers(["mon"], None, time(8, 0), time(9, 0), moment)
    # 22:30 UTC on Sunday is 05:30 on Monday in Ho Chi Minh City
    late = datetime(2026, 9, 20, 22, 30, tzinfo=UTC)
    assert roster.slot_covers(["mon"], None, time(5, 0), time(6, 0), late)
    assert not roster.slot_covers(["sun"], None, time(5, 0), time(6, 0), late)


# ------------------------------------------------------------------------------------- the DTO rules
def test_an_entry_has_exactly_one_of_weekdays_and_a_date_and_distinct_times() -> None:
    uid = uuid4()
    ok = RosterEntryCreate(account_id="long", user_id=uid, weekdays=[Weekday.MON], start="08:00", end="12:00")
    assert ok.weekdays == [Weekday.MON]
    with pytest.raises(ValueError, match="exactly one"):
        RosterEntryCreate(account_id="long", user_id=uid, start="08:00", end="12:00")
    with pytest.raises(ValueError, match="exactly one"):
        RosterEntryCreate(
            account_id="long",
            user_id=uid,
            weekdays=[Weekday.MON],
            on_date=date(2026, 9, 21),
            start="08:00",
            end="12:00",
        )
    with pytest.raises(ValueError, match="differ"):
        RosterEntryCreate(account_id="long", user_id=uid, weekdays=[Weekday.MON], start="08:00", end="08:00")
    with pytest.raises(ValueError, match="String should match"):
        RosterEntryCreate(account_id="long", user_id=uid, weekdays=[Weekday.MON], start="8am", end="12:00")


def test_the_weekdays_are_sorted_and_deduplicated() -> None:
    entry = RosterEntryCreate(
        account_id="long",
        user_id=uuid4(),
        weekdays=[Weekday.FRI, Weekday.MON, Weekday.FRI],
        start="08:00",
        end="12:00",
    )
    assert entry.weekdays == [Weekday.MON, Weekday.FRI]


# ------------------------------------------------------------------------------------------- database
@pytest.mark.db
class TestRosterDatabase:
    async def _entry(self, db: ClinicDatabase, ctx: Any, world: SeedResult, key: str, **kwargs: Any) -> Any:
        base: dict[str, Any] = {
            "account_id": "long",
            "user_id": world.users[key],
            "weekdays": [Weekday.MON],
            "start": "08:00",
            "end": "17:00",
        }
        return await roster.create_entry(db, ctx, RosterEntryCreate(**{**base, **kwargs}))

    async def test_who_is_on_lists_the_operators_who_cover_the_moment(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        add_account("hoa")
        manager = staff_ctx("manager")
        await self._entry(db, manager, world, "cs.thu")
        await self._entry(db, manager, world, "doctor.mai", start="12:00", end="18:00")
        await self._entry(db, manager, world, "cs.maianh", weekdays=None, on_date=date(2026, 9, 21))
        await self._entry(db, manager, world, "cs.maianh", account_id="hoa")

        names = [op.name for op in await roster.who_is_on(db, world.clinic_id, "long", vn(*MON, 13, 0))]
        assert names == ["BS. Mai (mẫu)", "CSKH Mai Anh (mẫu)", "CSKH Thu (mẫu)"]
        morning = await roster.who_is_on(db, world.clinic_id, "long", vn(*MON, 9, 0))
        assert [op.name for op in morning] == ["CSKH Mai Anh (mẫu)", "CSKH Thu (mẫu)"]
        assert await roster.who_is_on(db, world.clinic_id, "long", vn(*TUE, 9, 0)) == []
        assert [op.name for op in await roster.who_is_on(db, world.clinic_id, "hoa", vn(*MON, 9, 0))] == [
            "CSKH Mai Anh (mẫu)"
        ]
        assert await roster.who_is_on(db, world.clinic_id, "ghost", vn(*MON, 9, 0)) == []

    async def test_one_operator_with_two_entries_is_listed_once(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        manager = staff_ctx("manager")
        await self._entry(db, manager, world, "cs.thu")
        await self._entry(db, manager, world, "cs.thu", weekdays=None, on_date=date(2026, 9, 21))
        assert len(await roster.who_is_on(db, world.clinic_id, "long", vn(*MON, 9, 0))) == 1

    async def test_a_slot_across_midnight_is_found_the_next_morning(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        await self._entry(db, staff_ctx("owner"), world, "cs.thu", start="22:00", end="06:00")
        assert len(await roster.who_is_on(db, world.clinic_id, "long", vn(*MON, 23, 0))) == 1
        assert len(await roster.who_is_on(db, world.clinic_id, "long", vn(*TUE, 5, 30))) == 1
        assert await roster.who_is_on(db, world.clinic_id, "long", vn(*TUE, 6, 0)) == []

    async def test_a_locked_user_or_one_who_lost_an_assignable_role_drops_out(
        self, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        manager = staff_ctx("manager")
        await self._entry(db, manager, world, "cs.thu")
        await self._entry(db, manager, world, "cs.maianh")
        assert len(await roster.who_is_on(db, world.clinic_id, "long", vn(*MON, 9, 0))) == 2
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE clinic.user_account SET active = false WHERE id = :u"),
                {"u": world.users["cs.thu"]},
            )
            conn.execute(
                text("UPDATE clinic.user_account SET role = 'reception' WHERE id = :u"),
                {"u": world.users["cs.maianh"]},
            )
        assert await roster.who_is_on(db, world.clinic_id, "long", vn(*MON, 9, 0)) == []
        # the entries stay, for the manager to fix
        assert len(await roster.list_roster(db, manager)) == 2

    @pytest.mark.parametrize("key", ["reception.lan", "accountant.hoa"])
    async def test_only_assignable_roles_can_be_rostered(
        self, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any, key: str
    ) -> None:
        add_account("long")
        with pytest.raises(DomainError) as refused:
            await self._entry(db, staff_ctx("manager"), world, key)
        assert refused.value.code is ErrorCode.VALIDATION_FAILED
        with admin.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM clinic.account_roster")).scalar() == 0

    async def test_a_locked_user_cannot_be_added_and_an_unknown_user_gets_the_same_answer(
        self, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE clinic.user_account SET active = false WHERE id = :u"),
                {"u": world.users["cs.thu"]},
            )
        manager = staff_ctx("manager")
        with pytest.raises(DomainError) as locked:
            await self._entry(db, manager, world, "cs.thu")
        with pytest.raises(DomainError) as unknown:
            await roster.create_entry(
                db,
                manager,
                RosterEntryCreate(
                    account_id="long", user_id=uuid4(), weekdays=[Weekday.MON], start="08:00", end="17:00"
                ),
            )
        assert (locked.value.code, str(locked.value)) == (unknown.value.code, str(unknown.value))

    async def test_an_internal_or_unknown_identity_has_no_roster(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("bell", purpose="internal")
        manager = staff_ctx("manager")
        with pytest.raises(DomainError) as internal:
            await self._entry(db, manager, world, "cs.thu", account_id="bell")
        assert internal.value.code is ErrorCode.INVALID_STATE
        with pytest.raises(DomainError) as unknown:
            await self._entry(db, manager, world, "cs.thu", account_id="ghost")
        assert unknown.value.code is ErrorCode.NOT_FOUND

    async def test_owner_and_manager_write_and_operators_only_read(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        created = await self._entry(db, staff_ctx("owner"), world, "cs.thu", note="Ca sáng")
        assert created.note == "Ca sáng"
        for key in ("doctor.mai", "cs.thu"):
            ctx = staff_ctx(key)
            assert len(await roster.list_roster(db, ctx)) == 1
            with pytest.raises(DomainError) as refused:
                await self._entry(db, ctx, world, "cs.maianh")
            assert refused.value.code is ErrorCode.FORBIDDEN
            with pytest.raises(DomainError) as refused_delete:
                await roster.delete_entry(db, ctx, created.id)
            assert refused_delete.value.code is ErrorCode.FORBIDDEN
        for key in ("reception.lan", "accountant.hoa"):
            with pytest.raises(DomainError) as refused_read:
                await roster.list_roster(db, staff_ctx(key))
            assert refused_read.value.code is ErrorCode.FORBIDDEN

    async def test_the_listing_filters_by_identity_and_operator(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        add_account("hoa")
        manager = staff_ctx("manager")
        await self._entry(db, manager, world, "cs.thu")
        await self._entry(db, manager, world, "cs.maianh", account_id="hoa")
        assert [e.account_id for e in await roster.list_roster(db, manager, account_id="hoa")] == ["hoa"]
        assert [e.user_id for e in await roster.list_roster(db, manager, user_id=world.users["cs.thu"])] == [
            world.users["cs.thu"]
        ]
        assert len(await roster.list_roster(db, manager)) == 2

    async def test_update_changes_times_days_and_kind_with_the_version(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        manager = staff_ctx("manager")
        created = await self._entry(db, manager, world, "cs.thu")
        changed = await roster.update_entry(
            db,
            manager,
            created.id,
            RosterEntryUpdate(version=created.version, start="09:00", weekdays=[Weekday.TUE, Weekday.THU]),
        )
        assert (changed.start, changed.end, changed.weekdays) == (
            "09:00",
            "17:00",
            [Weekday.TUE, Weekday.THU],
        )
        assert changed.version == created.version + 1
        # a date replaces the weekdays (the kind switches)
        dated = await roster.update_entry(
            db, manager, created.id, RosterEntryUpdate(version=changed.version, on_date=date(2026, 9, 25))
        )
        assert (dated.weekdays, dated.on_date) == (None, date(2026, 9, 25))
        # and back
        weekly = await roster.update_entry(
            db, manager, created.id, RosterEntryUpdate(version=dated.version, weekdays=[Weekday.SAT])
        )
        assert (weekly.weekdays, weekly.on_date) == ([Weekday.SAT], None)
        # a clock that makes start equal end is refused
        with pytest.raises(DomainError) as same:
            await roster.update_entry(
                db, manager, created.id, RosterEntryUpdate(version=weekly.version, start="17:00")
            )
        assert same.value.code is ErrorCode.VALIDATION_FAILED

    async def test_update_with_an_old_version_is_a_conflict_and_hands_over_to_a_valid_user_only(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        manager = staff_ctx("manager")
        created = await self._entry(db, manager, world, "cs.thu")
        await roster.update_entry(db, manager, created.id, RosterEntryUpdate(version=1, end="18:00"))
        with pytest.raises(DomainError) as stale:
            await roster.update_entry(db, manager, created.id, RosterEntryUpdate(version=1, end="19:00"))
        assert stale.value.code is ErrorCode.VERSION_CONFLICT
        with pytest.raises(DomainError) as refused:
            await roster.update_entry(
                db, manager, created.id, RosterEntryUpdate(version=2, user_id=world.users["reception.lan"])
            )
        assert refused.value.code is ErrorCode.VALIDATION_FAILED
        moved = await roster.update_entry(
            db, manager, created.id, RosterEntryUpdate(version=2, user_id=world.users["cs.maianh"])
        )
        assert moved.user_id == world.users["cs.maianh"]

    async def test_every_write_leaves_an_audit_row_without_the_note(
        self, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        owner = staff_ctx("owner")
        created = await self._entry(db, owner, world, "cs.thu", note="ghi chú riêng tư (mẫu)")
        updated = await roster.update_entry(
            db, owner, created.id, RosterEntryUpdate(version=1, end="18:00", note="đổi ghi chú (mẫu)")
        )
        await roster.delete_entry(db, owner, updated.id)
        with admin.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT action, actor_role, details::text AS details FROM clinic.audit_log "
                    "WHERE action LIKE 'roster.%' AND entity_id = :e ORDER BY id"
                ),
                {"e": str(created.id)},
            ).all()
        assert [row.action for row in rows] == ["roster.create", "roster.update", "roster.delete"]
        assert {row.actor_role for row in rows} == {"owner"}
        assert "riêng tư" not in "".join(row.details for row in rows)
        assert "ghi chú" not in "".join(row.details for row in rows)
        assert '"changed_fields": ["end", "note"]' in rows[1].details
        assert str(world.users["cs.thu"]) in rows[0].details

    async def test_deleting_an_entry_and_an_unknown_one(
        self, db: ClinicDatabase, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        manager = staff_ctx("manager")
        created = await self._entry(db, manager, world, "cs.thu")
        await roster.delete_entry(db, manager, created.id)
        assert await roster.list_roster(db, manager) == []
        with pytest.raises(DomainError) as missing:
            await roster.delete_entry(db, manager, created.id)
        assert missing.value.code is ErrorCode.NOT_FOUND

    async def test_deleting_an_account_removes_its_roster_and_a_user_leaves_theirs_behind_never(
        self, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        add_account("long")
        await self._entry(db, staff_ctx("manager"), world, "cs.thu")
        with admin.begin() as conn:
            conn.execute(text("DELETE FROM agent.accounts WHERE id = 'long'"))
            assert conn.execute(text("SELECT count(*) FROM clinic.account_roster")).scalar() == 0

    async def test_the_table_refuses_a_bad_shape(
        self, admin: Engine, world: SeedResult, add_account: Any
    ) -> None:
        from sqlalchemy.exc import IntegrityError

        add_account("long")
        base = {"c": world.clinic_id, "u": world.users["cs.thu"]}
        cases = [
            "weekdays, on_date, start_time, end_time) VALUES (:c, 'long', :u, NULL, NULL, '08:00', '12:00')",
            "weekdays, on_date, start_time, end_time) VALUES (:c, 'long', :u, ARRAY['mon'], '2026-09-21', '08:00', '12:00')",
            "weekdays, start_time, end_time) VALUES (:c, 'long', :u, ARRAY['funday'], '08:00', '12:00')",
            "weekdays, start_time, end_time) VALUES (:c, 'long', :u, ARRAY[]::text[], '08:00', '12:00')",
            "weekdays, start_time, end_time) VALUES (:c, 'long', :u, ARRAY['mon'], '08:00', '08:00')",
        ]
        for tail in cases:
            with pytest.raises(IntegrityError), admin.begin() as conn:
                conn.execute(
                    text(f"INSERT INTO clinic.account_roster (clinic_id, account_id, user_id, {tail}"),
                    base,
                )

    async def test_the_http_routes(self, client_factory: Any, world: SeedResult, add_account: Any) -> None:
        add_account("long")
        manager = await client_factory("manager")
        body = {
            "account_id": "long",
            "user_id": str(world.users["cs.thu"]),
            "weekdays": ["mon", "tue"],
            "start": "08:00",
            "end": "12:00",
            "note": "Ca sáng (mẫu)",
        }
        created = await manager.post("/api/v1/roster", json=body)
        assert created.status_code == 201, created.text
        entry = created.json()
        assert (entry["weekdays"], entry["user_role"], entry["version"]) == (["mon", "tue"], "cs_staff", 1)

        bad = await manager.post("/api/v1/roster", json={**body, "on_date": "2026-09-21"})
        assert bad.status_code == 422

        doctor = await client_factory("doctor.mai")
        listed = await doctor.get("/api/v1/roster", params={"account_id": "long"})
        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [entry["id"]]
        assert (await doctor.post("/api/v1/roster", json=body)).status_code == 403
        assert (await doctor.delete(f"/api/v1/roster/{entry['id']}")).status_code == 403

        on_duty = await doctor.get(
            "/api/v1/identities/long/on-duty", params={"at": "2026-09-21T09:00:00+07:00"}
        )
        assert on_duty.status_code == 200, on_duty.text
        assert [op["role"] for op in on_duty.json()["operators"]] == ["cs_staff"]
        nobody = await doctor.get(
            "/api/v1/identities/long/on-duty", params={"at": "2026-09-21T13:00:00+07:00"}
        )
        assert nobody.json()["operators"] == []
        assert (await doctor.get("/api/v1/identities/ghost/on-duty")).status_code == 404

        patched = await manager.patch(f"/api/v1/roster/{entry['id']}", json={"version": 1, "end": "13:00"})
        assert patched.status_code == 200, patched.text
        stale = await manager.patch(f"/api/v1/roster/{entry['id']}", json={"version": 1, "end": "14:00"})
        assert stale.status_code == 409
        assert (await manager.delete(f"/api/v1/roster/{entry['id']}")).status_code == 204

        reception = await client_factory("reception.lan")
        assert (await reception.get("/api/v1/roster")).status_code == 403

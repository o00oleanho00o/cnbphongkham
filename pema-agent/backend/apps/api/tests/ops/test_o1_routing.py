"""Routing preference: the operators rostered for the patient's identity are asked first (package O, step O1).

New tests (no zalo-agent original). The first half runs M's REAL ``RoutingService`` over M's in-memory fakes
(``make_routing_rig``) with ``RosterRoutingDirectory`` in front of the directory and a fake roster source: no
database, no clock. The second half (needs ``PEMA_TEST_DATABASE_URL``) checks the SQL roster source. The care
package is not edited: the on-call contact stays the LAST link of every chain.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.care.handoff_types import Depth, Urgency
from pema.care.routing import RoutingService
from pema.care.routing_types import Candidate, CandidateKind, Ownership
from pema.care.testing_routing import RoutingRig, make_routing_rig
from pema.clinic.actions.seed_demo import SeedResult
from pema.composition.roster_routing import RosterRoutingDirectory, SqlRosterSource
from pema.core.db import ClinicDatabase
from pema_contracts.ops import OnDutyOperator
from pema_contracts.roles import Role

IDENTITY = "long"


class FakeRoster:
    """``RosterSource`` over dicts: which identity a patient writes to, who is on duty there."""

    def __init__(self) -> None:
        self.identity: str | None = IDENTITY
        self.on_duty: list[OnDutyOperator] = []
        self.fail = False
        self.asked_at: list[datetime] = []

    def put(self, user_id: UUID, role: Role = Role.CS_STAFF) -> None:
        self.on_duty.append(OnDutyOperator(id=user_id, name="Người trực (mẫu)", role=role))

    async def identity_of_patient(self, patient_id: UUID) -> str | None:
        if self.fail:
            raise RuntimeError("roster unavailable")
        return self.identity

    async def who_is_on(self, account_id: str, at: datetime) -> Sequence[OnDutyOperator]:
        self.asked_at.append(at)
        assert account_id == IDENTITY
        return self.on_duty


def service_with_roster(rig: RoutingRig, roster: FakeRoster) -> RoutingService:
    """The same ``RoutingService`` as the rig's, but its directory is the roster adapter over the rig's."""
    return RoutingService(
        store=rig.routing_store,
        directory=RosterRoutingDirectory(rig.directory, source=roster, clock=rig.clock),
        oncall=rig.oncall,
        config_source=rig.routing_config,
        notifier=rig.notifier,
        sla=rig.sla,
        window=rig.window,
        clock=rig.clock,
    )


async def chain(
    rig: RoutingRig, roster: FakeRoster, depth: Depth = Depth.D2, skill: str = "general"
) -> list[Candidate]:
    await rig.open_round(depth, Urgency.NORMAL, required_skill=skill)
    return await service_with_roster(rig, roster).build_candidates(rig.request, rig.clock.now)


def users(candidates: Sequence[Candidate]) -> list[UUID | None]:
    return [c.user_id for c in candidates]


async def test_a_rostered_operator_is_asked_first_then_the_others_then_the_on_call_contact() -> None:
    rig = make_routing_rig()
    free = rig.directory.add_staff("cs_staff", load=0)
    middle = rig.directory.add_staff("cs_staff", load=2)
    rostered = rig.directory.add_staff("cs_staff", load=4)  # the busiest: M alone would ask them last
    roster = FakeRoster()
    roster.put(rostered)
    result = await chain(rig, roster)
    assert users(result) == [rostered, free, middle, None]
    assert result[-1].kind is CandidateKind.ON_CALL
    assert rig.clock.now in roster.asked_at  # the roster is read at the routing moment


async def test_without_the_roster_the_same_chain_is_the_one_of_package_m() -> None:
    rig = make_routing_rig()
    free = rig.directory.add_staff("cs_staff", load=0)
    rostered = rig.directory.add_staff("cs_staff", load=4)
    await rig.open_round(Depth.D2, Urgency.NORMAL, required_skill="general")
    plain = await rig.service.build_candidates(rig.request, rig.clock.now)
    assert users(plain) == [free, rostered, None]
    empty = FakeRoster()  # nobody on duty for the identity
    assert users(await service_with_roster(rig, empty).build_candidates(rig.request, rig.clock.now)) == users(
        plain
    )
    unknown = FakeRoster()  # the patient has no identity yet
    unknown.identity = None
    unknown.put(rostered)
    assert users(
        await service_with_roster(rig, unknown).build_candidates(rig.request, rig.clock.now)
    ) == users(plain)


async def test_a_rostered_doctor_and_a_rostered_cs_member_both_come_first() -> None:
    rig = make_routing_rig()
    others = [rig.directory.add_staff("cs_staff", load=0), rig.directory.add_staff("doctor", load=0)]
    cs = rig.directory.add_staff("cs_staff", load=5)
    doctor = rig.directory.add_staff("doctor", load=5)
    roster = FakeRoster()
    roster.put(doctor, Role.DOCTOR)
    roster.put(cs)
    result = await chain(rig, roster)
    assert users(result)[:2] == [cs, doctor]  # M's own order of the owner slots: cs owner, then the doctor
    assert set(users(result)[2:-1]) <= set(others)
    assert users(result)[-1] is None


async def test_the_role_rule_of_a_deep_handoff_still_applies_to_a_rostered_operator() -> None:
    rig = make_routing_rig()
    doctor_on_shift = rig.directory.add_staff("doctor", load=0)
    cs = rig.directory.add_staff("cs_staff", load=0)
    roster = FakeRoster()
    roster.put(cs)  # a cs member may not take a D4 handoff, rostered or not
    result = await chain(rig, roster, Depth.D4, "medical")
    assert users(result) == [doctor_on_shift, None]
    assert cs not in users(result)


async def test_the_on_call_contact_stays_the_last_link_and_is_not_replaced() -> None:
    rig = make_routing_rig()
    rostered = rig.directory.add_staff("cs_staff")
    roster = FakeRoster()
    roster.put(rostered)
    await rig.open_round(Depth.D2, Urgency.NORMAL, required_skill="general")
    plain = await rig.service.build_candidates(rig.request, rig.clock.now)
    preferred = await service_with_roster(rig, roster).build_candidates(rig.request, rig.clock.now)
    assert preferred[-1] == plain[-1]
    assert preferred[-1].kind is CandidateKind.ON_CALL
    assert [c.kind for c in preferred].count(CandidateKind.ON_CALL) == 1


async def test_a_rostered_operator_without_a_staff_profile_is_not_routable() -> None:
    rig = make_routing_rig()
    regular = rig.directory.add_staff("cs_staff")
    roster = FakeRoster()
    roster.put(uuid4())  # on the roster, but the care directory has no profile for them
    result = await chain(rig, roster)
    assert users(result) == [regular, None]


async def test_a_rostered_operator_takes_the_owner_slot_and_the_real_owner_follows_on_shift() -> None:
    rig = make_routing_rig()
    real_owner = rig.directory.add_staff("cs_staff", load=1)
    rostered = rig.directory.add_staff("cs_staff", load=3)
    rig.directory.own(rig.agent.patient_id, cs_owner=real_owner)
    roster = FakeRoster()
    roster.put(rostered)
    result = await chain(rig, roster)
    assert users(result) == [rostered, real_owner, None]


async def test_a_roster_that_cannot_be_read_never_stops_a_handoff(caplog: pytest.LogCaptureFixture) -> None:
    rig = make_routing_rig()
    regular = rig.directory.add_staff("cs_staff")
    roster = FakeRoster()
    roster.fail = True
    with caplog.at_level(logging.ERROR):
        result = await chain(rig, roster)
    assert users(result) == [regular, None]
    assert any("roster lookup failed" in record.getMessage() for record in caplog.records)
    assert all("unavailable" not in record.getMessage() for record in caplog.records)


async def test_the_adapter_leaves_the_staff_list_alone() -> None:
    rig = make_routing_rig()
    rig.directory.add_staff("cs_staff")
    adapter = RosterRoutingDirectory(rig.directory, source=FakeRoster(), clock=rig.clock)
    assert list(await adapter.list_staff(UUID(int=1))) == list(await rig.directory.list_staff(UUID(int=1)))
    patient = uuid4()
    inner = Ownership(cs_owner=uuid4(), doctor=uuid4())
    rig.directory.owners[patient] = inner
    assert await adapter.ownership(patient) == inner  # no identity is on duty: the inner answer, untouched


# ------------------------------------------------------------------------------------------- database
@pytest.mark.db
class TestSqlRosterSource:
    async def test_identity_of_patient_is_the_account_of_the_latest_conversation(
        self, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
    ) -> None:
        add_account("long")
        add_account("hoa")
        patient = world.patients["P025"]
        source = SqlRosterSource(db, world.clinic_id)
        assert (
            await source.identity_of_patient(patient) is None
        )  # the seeded conversation has no identity yet
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE clinic.conversation SET account_id = 'long' WHERE id = :i"),
                {"i": world.conversation_id},
            )
        assert await source.identity_of_patient(patient) == "long"
        with admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, patient_id, account_id, "
                    "last_inbound_at) VALUES (:c, 'zalo_personal', 'newer', :p, 'hoa', now() + interval '1 day')"
                ),
                {"c": world.clinic_id, "p": patient},
            )
        assert await source.identity_of_patient(patient) == "hoa"  # the one that wrote last
        assert await source.identity_of_patient(world.patients["P026"]) is None

    async def test_the_adapter_over_the_database_puts_the_rostered_operator_in_the_owner_slot(
        self, db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any, staff_ctx: Any
    ) -> None:
        from pema.clinic.actions import roster
        from pema_contracts.ops import RosterEntryCreate, Weekday

        add_account("long")
        with admin.begin() as conn:
            conn.execute(
                text("UPDATE clinic.conversation SET account_id = 'long' WHERE id = :i"),
                {"i": world.conversation_id},
            )
        await roster.create_entry(
            db,
            staff_ctx("manager"),
            RosterEntryCreate(
                account_id="long",
                user_id=world.users["cs.thu"],
                weekdays=[Weekday.MON],
                start="08:00",
                end="17:00",
            ),
        )
        rig = make_routing_rig()
        monday_9 = datetime(2026, 9, 21, 9, 0, tzinfo=roster.VN_TZ)
        adapter = RosterRoutingDirectory(
            rig.directory, source=SqlRosterSource(db, world.clinic_id), clock=lambda: monday_9
        )
        owners = await adapter.ownership(world.patients["P025"])
        assert owners.cs_owner == world.users["cs.thu"]
        tuesday = RosterRoutingDirectory(
            rig.directory,
            source=SqlRosterSource(db, world.clinic_id),
            clock=lambda: datetime(2026, 9, 22, 9, 0, tzinfo=roster.VN_TZ),
        )
        assert (await tuesday.ownership(world.patients["P025"])).cs_owner is None

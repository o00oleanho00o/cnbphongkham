"""The bridge between package M's control state machine and the assignment (package O, step O2).

New tests (no zalo-agent original). Need ``PEMA_TEST_DATABASE_URL`` for the clinic side; package M is replaced by
its own in-memory fakes (``pema.care.testing``): ``CareControl`` over ``InMemoryControlStore``. The care agent
points at the synthetic patient P025 of the seed so the clinic side finds the patient's conversations.

* M's ``accept`` becomes a ``claim`` of the open conversation with the LATEST inbound message (the other
  conversations of the patient are left alone);
* a conversation nobody can claim (none open, or a colleague holds it) leaves M's accept standing;
* the clinic's "release to the agent" asks M's state and calls M's ``release_to_auto``;
* M's release frees the thread the staff member holds.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import record_inbound
from pema.care.control import CareControl
from pema.care.models import ControlState
from pema.care.ports import CareAgentSnapshot, HandoffSpec
from pema.care.testing import FakeClock, InMemoryCareStore, InMemoryControlStore, StaticHandoffConfig, vn
from pema.clinic.actions import assignment
from pema.clinic.actions.assignment import CareHandback, CareHandbackRefusedError
from pema.clinic.actions.seed_demo import SeedResult
from pema.composition.care_assignment import CareAssignmentBridge
from pema.core.db import ClinicDatabase
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import ReleaseRequest

pytestmark = pytest.mark.db

NOW = vn(2026, 10, 3, 10, 0)


class Rig:
    def __init__(self, db: ClinicDatabase, world: SeedResult) -> None:
        self.patient_id: UUID = world.patients["P025"]
        self.care = InMemoryCareStore()
        self.agent = CareAgentSnapshot(
            id=UUID(int=77),
            clinic_id=world.clinic_id,
            patient_id=self.patient_id,
            profile="patient_channel",
        )
        self.care.agents[self.agent.id] = self.agent
        self.controls = InMemoryControlStore(self.care)
        self.control = CareControl(
            store=self.controls, config_source=StaticHandoffConfig(), channel=None, clock=FakeClock(NOW)
        )
        self.bridge = CareAssignmentBridge(db, self.control, self.controls)

    async def open_round(self) -> None:
        spec = HandoffSpec(
            reason="depth_at_or_above_threshold",
            summary="Khách: P025 (tóm tắt mẫu)",
            depth="D4",
            confidence=0.8,
            required_skill="medical",
            urgency="urgent",
        )
        await self.controls.open_handoff(self.agent, spec, log_action="control:auto_to_handoff", at=NOW)

    @property
    def state(self) -> ControlState:
        return self.care.states.get(self.patient_id, ControlState.AUTO)


def holder_of(admin: Engine, conversation_id: UUID) -> UUID | None:
    with admin.connect() as conn:
        return conn.execute(
            text("SELECT assigned_user_id FROM clinic.conversation WHERE id = :c"), {"c": conversation_id}
        ).scalar_one()


async def two_threads(db: ClinicDatabase, admin: Engine, world: SeedResult) -> tuple[UUID, UUID]:
    """Two open conversations of P025: the first has the older inbound message, the second the newer."""
    older = await record_inbound(db, world, text="Tin cũ (mẫu)")
    newer = await record_inbound(db, world, text="Tin mới (mẫu)")
    with admin.begin() as conn:
        for cid, hours in ((older.conversation_id, 5), (newer.conversation_id, 1)):
            conn.execute(
                text(
                    "UPDATE clinic.conversation SET last_inbound_at = now() - make_interval(hours => :h) WHERE id = :c"
                ),
                {"h": hours, "c": cid},
            )
        conn.execute(  # the seed's own conversation of P025 is older than both
            text("UPDATE clinic.conversation SET last_inbound_at = now() - interval '9 hours' WHERE id = :c"),
            {"c": world.conversation_id},
        )
    return older.conversation_id, newer.conversation_id


async def test_the_bridge_is_the_care_handback_the_clinic_asks_for(
    db: ClinicDatabase, world: SeedResult
) -> None:
    assert isinstance(Rig(db, world).bridge, CareHandback)


async def test_an_accepted_handoff_claims_the_conversation_with_the_latest_inbound_message(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    older, newer = await two_threads(db, admin, world)
    rig = Rig(db, world)
    await rig.open_round()
    mai = staff_ctx("cs.maianh")

    request = await rig.bridge.accept_and_claim(mai, rig.patient_id)

    assert request.accepted_by == world.users["cs.maianh"]
    assert rig.state is ControlState.STAFF
    assert holder_of(admin, newer) == world.users["cs.maianh"]
    assert holder_of(admin, older) is None
    assert world.conversation_id is not None
    assert holder_of(admin, world.conversation_id) is None


async def test_the_open_conversation_is_found_by_patient_and_closed_ones_are_skipped(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    older, newer = await two_threads(db, admin, world)
    assert await assignment.open_conversation_of_patient(db, world.clinic_id, world.patients["P025"]) == newer
    with admin.begin() as conn:
        conn.execute(text("UPDATE clinic.conversation SET status = 'closed' WHERE id = :c"), {"c": newer})
    assert await assignment.open_conversation_of_patient(db, world.clinic_id, world.patients["P025"]) == older
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.conversation SET status = 'closed' WHERE patient_id = :p"),
            {"p": world.patients["P025"]},
        )
    assert await assignment.open_conversation_of_patient(db, world.clinic_id, world.patients["P025"]) is None


async def test_an_accept_stands_when_a_colleague_already_holds_the_thread(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    older, newer = await two_threads(db, admin, world)
    await assignment.claim(db, staff_ctx("cs.thu"), newer)
    rig = Rig(db, world)
    await rig.open_round()

    request = await rig.bridge.accept_and_claim(staff_ctx("cs.maianh"), rig.patient_id)

    assert request.accepted_by == world.users["cs.maianh"]
    assert rig.state is ControlState.STAFF, "M's accept stands"
    assert holder_of(admin, newer) == world.users["cs.thu"], "the colleague keeps the thread"
    assert holder_of(admin, older) is None


async def test_an_accept_stands_when_the_patient_has_no_open_conversation(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    await two_threads(db, admin, world)
    rig = Rig(db, world)
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.conversation SET status = 'closed' WHERE patient_id = :p"),
            {"p": rig.patient_id},
        )
    await rig.open_round()
    request = await rig.bridge.accept_and_claim(staff_ctx("cs.maianh"), rig.patient_id)
    assert request.accepted_by == world.users["cs.maianh"]
    assert rig.state is ControlState.STAFF


async def test_the_release_to_the_agent_asks_m_for_the_state_and_calls_its_release(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    _, newer = await two_threads(db, admin, world)
    rig = Rig(db, world)
    mai = staff_ctx("cs.maianh")
    await rig.open_round()

    # still routing (nobody accepted): not the STAFF state, the clinic's release to the agent is refused
    await assignment.claim(db, mai, newer)
    with pytest.raises(DomainError) as refused:
        await assignment.release(db, mai, newer, ReleaseRequest(to_agent=True), care=rig.bridge)
    assert refused.value.code is ErrorCode.INVALID_STATE
    assert holder_of(admin, newer) == world.users["cs.maianh"]

    await rig.control.accept(mai, rig.patient_id)
    assert rig.state is ControlState.STAFF
    out = await assignment.release(
        db, mai, newer, ReleaseRequest(to_agent=True, note="Khách đã yên tâm"), care=rig.bridge
    )
    assert out.assigned_user_id is None
    assert rig.state is ControlState.AUTO
    assert [fact for _, fact, source in rig.controls.memory if source == "staff"] == ["Khách đã yên tâm"]


async def test_a_release_in_m_frees_the_thread_the_staff_member_holds(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    _, newer = await two_threads(db, admin, world)
    rig = Rig(db, world)
    mai, thu = staff_ctx("cs.maianh"), staff_ctx("cs.thu")
    await rig.open_round()
    await rig.bridge.accept_and_claim(mai, rig.patient_id)
    assert holder_of(admin, newer) == world.users["cs.maianh"]

    snapshot = await rig.bridge.release_and_free(mai, rig.patient_id, "Đã xử lý xong")

    assert snapshot.state is ControlState.AUTO
    assert holder_of(admin, newer) is None

    # a release by somebody who does not hold the thread leaves the holder alone (and does not raise)
    rig2 = Rig(db, world)
    await assignment.claim(db, thu, newer)
    await rig2.open_round()
    await rig2.control.accept(mai, rig2.patient_id)
    await rig2.bridge.release_and_free(mai, rig2.patient_id, "Xong")
    assert holder_of(admin, newer) == world.users["cs.thu"]


async def test_m_refusing_the_release_is_the_clinics_error_type_and_the_thread_stays_held(
    db: ClinicDatabase, admin: Engine, world: SeedResult, staff_ctx: Any
) -> None:
    _, newer = await two_threads(db, admin, world)
    rig = Rig(db, world)
    mai = staff_ctx("cs.maianh")
    await assignment.claim(db, mai, newer)
    # the patient is in AUTO (nobody accepted): M refuses ``release_to_auto`` and the bridge says so
    with pytest.raises(CareHandbackRefusedError):
        await rig.bridge.release_to_auto(mai, rig.patient_id, "Không ở trạng thái nhân viên")
    assert rig.state is ControlState.AUTO
    assert holder_of(admin, newer) == world.users["cs.maianh"]

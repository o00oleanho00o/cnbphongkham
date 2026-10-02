"""Synthetic dev data for package M: three staff profiles, a fake on-call number, two owned patients.

New module (not a port). EVERYTHING here is fictional (AGENT.md): the people are the demo accounts of
``pema.clinic.actions.seed_demo`` (``doctor.mai``, ``cs.maianh``, ``cs.thu``; the caller passes the ids of
``SeedResult``), the on-call number is the placeholder ``0000000001`` and its row has ``is_fixture = true`` so
nothing can mistake it for the clinic's real 24/7 contact (entered on the dashboard, never in code).

Idempotent: ids come from ``uuid5`` and every insert is ``ON CONFLICT`` (profiles and the on-call row are left
alone when they exist; ownership of the two patients is set to the values below). The two patients are paired
with their care agent through ``ensure_care_agent``, the same call the creation hook makes. M2b adds the
row of the skill ``handoff`` (``agent.skills``) with its temporary, doctor-pending defaults.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID, uuid5

from sqlalchemy.dialects.postgresql import insert as pg_insert

from pema.care.handoff_skill import ensure_handoff_skill
from pema.care.models import OnCallContact, PatientOwnership, StaffProfile
from pema.care.pairing import ensure_care_agent
from pema.core.db import ClinicDatabase, get_installation_clinic_id

_NAMESPACE = UUID("6f1c2b0e-0000-4000-8000-00000000c101")

FIXTURE_ON_CALL_NUMBER = "0000000001"
FIXTURE_ON_CALL_OWNER = "Trực tổng đài (mẫu)"

# user key of seed_demo, role, skills, languages
STAFF: tuple[tuple[str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("doctor.mai", "doctor", ("laser", "nam"), ("vi", "en")),
    ("cs.maianh", "cs_staff", ("dat_lich", "thanh_toan"), ("vi",)),
    ("cs.thu", "cs_staff", ("khieu_nai", "mun"), ("vi", "en")),
)
# patient code of seed_demo -> (cs owner key, doctor key)
OWNERSHIP: tuple[tuple[str, str, str], ...] = (
    ("P025", "cs.maianh", "doctor.mai"),
    ("P026", "cs.thu", "doctor.mai"),
)
WEEKDAY_SHIFT: dict[str, list[list[str]]] = {
    day: [["08:00", "17:00"]] for day in ("mon", "tue", "wed", "thu", "fri")
}


@dataclass(frozen=True)
class CareSeedResult:
    staff_profiles: dict[str, UUID]
    care_agents: dict[str, UUID]
    on_call_contact: UUID


def _id(*parts: str) -> UUID:
    return uuid5(_NAMESPACE, ":".join(parts))


async def seed_care_dev(
    db: ClinicDatabase, *, users: Mapping[str, UUID], patients: Mapping[str, UUID]
) -> CareSeedResult:
    """Add the package-M dev data to the clinic of the installation (``be_app`` session)."""
    clinic_id = await get_installation_clinic_id(db)
    profile_ids = {key: _id("staff", key) for key, *_ in STAFF}
    on_call_id = _id("on-call", FIXTURE_ON_CALL_NUMBER)
    care_agents: dict[str, UUID] = {}
    async with db.session() as session:
        for key, role, skills, languages in STAFF:
            await session.execute(
                pg_insert(StaffProfile)
                .values(
                    id=profile_ids[key],
                    clinic_id=clinic_id,
                    user_id=users[key],
                    role=role,
                    skills=list(skills),
                    shift=WEEKDAY_SHIFT,
                    capacity=5,
                    languages=list(languages),
                )
                .on_conflict_do_nothing(index_elements=[StaffProfile.user_id])
            )
        await session.execute(
            pg_insert(OnCallContact)
            .values(
                id=on_call_id,
                clinic_id=clinic_id,
                zalo_number=FIXTURE_ON_CALL_NUMBER,
                owner=FIXTURE_ON_CALL_OWNER,
                active=True,
                is_fixture=True,
            )
            .on_conflict_do_nothing(index_elements=[OnCallContact.id])
        )
        await ensure_handoff_skill(session, clinic_id)
        for code, cs_key, doctor_key in OWNERSHIP:
            patient_id = patients[code]
            care_agents[code] = (await ensure_care_agent(session, patient_id, clinic_id=clinic_id)).id
            insert = pg_insert(PatientOwnership).values(
                clinic_id=clinic_id, patient_id=patient_id, cs_owner=users[cs_key], doctor=users[doctor_key]
            )
            await session.execute(
                insert.on_conflict_do_update(
                    index_elements=[PatientOwnership.patient_id],
                    set_={"cs_owner": insert.excluded.cs_owner, "doctor": insert.excluded.doctor},
                )
            )
    return CareSeedResult(profile_ids, care_agents, on_call_id)

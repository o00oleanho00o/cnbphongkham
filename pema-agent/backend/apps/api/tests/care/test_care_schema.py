"""Schema of package M (step M1): tables, constraints, triggers, ORM parity, migration round trip.

New tests (no zalo-agent original). Needs ``PEMA_TEST_DATABASE_URL`` (skipped otherwise). Single tenant: the
recipe's "RLS by clinic_id" steps do not apply (``CONTRACTS-AI01.md`` 10.8); ``clinic_id`` is the fixed
installation id and a foreign key to ``clinic.clinic`` guards it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from pema.care import models
from pema.care.models import CareAgent, CareBase, CareMemory
from pema.care.pairing import ensure_care_agent
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

API_INI = Path(__file__).resolve().parents[2] / "alembic.ini"
AGENT_TABLES = {
    "care_agents", "care_memory", "conversation_control", "handoff_requests", "tasks", "actions_log", "skills",
    "paused_reminders",
}  # fmt: skip
CLINIC_TABLES = {"staff_profiles", "patient_ownership", "on_call_contacts"}
COMMON_COLUMNS = {"clinic_id", "created_at", "updated_at", "version"}
M1_PARENT = "st_0009_single_tenant"
"""The revision before ``m_0001_care_tables``: M2c's ``m_0002`` sits on top of it, so ``-1`` is no longer M1."""


def _columns(engine: Engine, schema: str, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table, schema=schema)}


def _exec(admin: Engine, sql: str, **params: Any) -> None:
    with admin.begin() as conn:
        conn.execute(text(sql), params)


def _scalar(admin: Engine, sql: str, **params: Any) -> Any:
    with admin.connect() as conn:
        return conn.execute(text(sql), params).scalar_one()


async def _care_agent(db: ClinicDatabase, world: SeedResult, code: str = "P025") -> UUID:
    async with db.session() as session:
        return (await ensure_care_agent(session, world.patients[code])).id


# ------------------------------------------------------------------------------------ shape
def test_every_package_m_table_exists_with_the_common_columns(admin: Engine, pg_url: str) -> None:
    for table in AGENT_TABLES:
        assert _columns(admin, "agent", table) >= COMMON_COLUMNS, table
    for table in CLINIC_TABLES:
        assert _columns(admin, "clinic", table) >= COMMON_COLUMNS, table


def test_no_package_m_table_has_row_level_security_or_a_policy(admin: Engine, pg_url: str) -> None:
    with admin.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname IN ('agent', 'clinic') AND c.relkind = 'r' AND c.relname = ANY(:t)"
            ),
            {"t": sorted(AGENT_TABLES | CLINIC_TABLES)},
        ).all()
        policies = conn.execute(text("SELECT count(*) FROM pg_policy")).scalar_one()
    assert {r[0] for r in rows} == AGENT_TABLES | CLINIC_TABLES
    assert [r[0] for r in rows if r[1]] == []
    assert policies == 0


def test_the_orm_mapping_has_exactly_the_columns_of_the_database(admin: Engine, pg_url: str) -> None:
    mapped = {(t.schema, t.name): {c.name for c in t.columns} for t in CareBase.metadata.tables.values()}
    assert {name for _, name in mapped} == AGENT_TABLES | CLINIC_TABLES
    for (schema, table), columns in mapped.items():
        assert schema is not None
        assert columns == _columns(admin, schema, table), (schema, table)


def test_care_memory_holds_no_clinical_record_column(admin: Engine, pg_url: str) -> None:
    """không cột nào của care_memory chứa dữ liệu hồ sơ y khoa (PLAN-M mục 10)"""
    assert _columns(admin, "agent", "care_memory") == {
        "id", "clinic_id", "care_agent_id", "fact", "source", "valid_until", "version", "created_at", "updated_at",
    }  # fmt: skip
    assert {c.name for c in CareMemory.__table__.columns} == _columns(admin, "agent", "care_memory")


def test_the_enums_of_the_models_match_the_check_constraints(admin: Engine, pg_url: str) -> None:
    checks = {
        "care_memory": (models.MemorySource, "source"),
        "conversation_control": (models.ControlState, "state"),
        "handoff_requests": (models.HandoffOutcome, "outcome"),
        "actions_log": (models.ActionDisposition, "disposition"),
        "tasks": (models.TaskStatus, "status"),
    }
    with admin.connect() as conn:
        for table, (enum, column) in checks.items():
            definition = " ".join(
                conn.execute(
                    text(
                        "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                        "WHERE c.conrelid = CAST(:t AS regclass) AND c.contype = 'c'"
                    ),
                    {"t": f"agent.{table}"},
                )
                .scalars()
                .all()
            )
            for member in enum:
                assert f"'{member.value}'" in definition, (table, column, member)


# ------------------------------------------------------------------------------------ constraints
async def test_one_care_agent_per_patient_is_enforced_by_the_database(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    await _care_agent(db, world)
    with pytest.raises(IntegrityError):
        _exec(
            admin,
            "INSERT INTO agent.care_agents (clinic_id, patient_id) VALUES (:c, :p)",
            c=world.clinic_id,
            p=world.patients["P025"],
        )


async def test_autonomy_override_must_be_null_or_level_and_until(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent_id = await _care_agent(db, world)
    _exec(
        admin,
        "UPDATE agent.care_agents SET autonomy_override = CAST(:v AS jsonb) WHERE id = :i",
        v='{"level": "L0", "until": "2026-09-27T09:00:00+07:00"}',
        i=agent_id,
    )
    for bad in ('{"level": "L3", "until": "2026-09-27"}', '{"level": "L0"}', "[]"):
        with pytest.raises(IntegrityError):
            _exec(
                admin,
                "UPDATE agent.care_agents SET autonomy_override = CAST(:v AS jsonb) WHERE id = :i",
                v=bad,
                i=agent_id,
            )


async def test_care_memory_source_is_patient_staff_or_doctor_edit(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent_id = await _care_agent(db, world)
    for source in ("patient", "staff", "doctor_edit"):
        _exec(
            admin,
            "INSERT INTO agent.care_memory (clinic_id, care_agent_id, fact, source) VALUES (:c, :a, 'thích nhắn buổi tối (mẫu)', :s)",
            c=world.clinic_id,
            a=agent_id,
            s=source,
        )
    for source, fact in (("system", "x"), ("patient", ""), ("patient", "x" * 501)):
        with pytest.raises(IntegrityError):
            _exec(
                admin,
                "INSERT INTO agent.care_memory (clinic_id, care_agent_id, fact, source) VALUES (:c, :a, :f, :s)",
                c=world.clinic_id,
                a=agent_id,
                f=fact,
                s=source,
            )


async def test_conversation_control_defaults_to_auto_and_staff_needs_an_owner(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    patient = world.patients["P025"]
    _exec(
        admin,
        "INSERT INTO agent.conversation_control (clinic_id, patient_id) VALUES (:c, :p)",
        c=world.clinic_id,
        p=patient,
    )
    with admin.connect() as conn:
        row = conn.execute(
            text("SELECT state, staff_owner, auto_release_after FROM agent.conversation_control")
        ).one()
    assert (row.state, row.staff_owner, row.auto_release_after) == ("AUTO", None, None)
    _exec(admin, "UPDATE agent.conversation_control SET state = 'HANDOFF_ROUTING'")
    with pytest.raises(IntegrityError):
        _exec(admin, "UPDATE agent.conversation_control SET state = 'STAFF'")
    _exec(
        admin,
        "UPDATE agent.conversation_control SET state = 'STAFF', staff_owner = :u",
        u=world.users["cs.maianh"],
    )
    with pytest.raises(IntegrityError):
        _exec(admin, "UPDATE agent.conversation_control SET state = 'PAUSED'")
    with pytest.raises(IntegrityError):  # one control row per patient
        _exec(
            admin,
            "INSERT INTO agent.conversation_control (clinic_id, patient_id) VALUES (:c, :p)",
            c=world.clinic_id,
            p=patient,
        )


_HANDOFF = (
    "INSERT INTO agent.handoff_requests (clinic_id, patient_id, reason, depth, confidence{extra}) "
    "VALUES (:c, :p, 'cần người (mẫu)', :d, :f{values})"
)


async def test_handoff_requests_keep_one_open_request_per_patient_and_a_closed_outcome(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    patient = world.patients["P025"]
    ins = _HANDOFF.format(extra="", values="")
    _exec(admin, ins, c=world.clinic_id, p=patient, d="D4", f=0.4)
    with pytest.raises(IntegrityError):  # a second OPEN request
        _exec(admin, ins, c=world.clinic_id, p=patient, d="D3", f=0.5)
    _exec(admin, "UPDATE agent.handoff_requests SET outcome = 'cancelled', resolved_at = now()")
    _exec(admin, ins, c=world.clinic_id, p=patient, d="D3", f=0.5)  # a new round after the first closed
    assert _scalar(admin, "SELECT count(*) FROM agent.handoff_requests") == 2


async def test_handoff_requests_validate_depth_confidence_outcome_and_acceptance(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    patient = world.patients["P026"]
    ins = _HANDOFF.format(extra="", values="")
    for depth, confidence in (("D6", 0.5), ("D1", 1.5), ("D1", -0.1)):
        with pytest.raises(IntegrityError):
            _exec(admin, ins, c=world.clinic_id, p=patient, d=depth, f=confidence)
    _exec(admin, ins, c=world.clinic_id, p=patient, d="D5", f=0.9)
    with pytest.raises(IntegrityError):  # accepted needs accepted_by
        _exec(admin, "UPDATE agent.handoff_requests SET outcome = 'accepted'")
    with pytest.raises(IntegrityError):  # accepted_by only with accepted
        _exec(admin, "UPDATE agent.handoff_requests SET accepted_by = :u", u=world.users["cs.thu"])
    with pytest.raises(IntegrityError):
        _exec(admin, "UPDATE agent.handoff_requests SET outcome = 'dropped'")
    _exec(
        admin,
        "UPDATE agent.handoff_requests SET outcome = 'accepted', accepted_by = :u",
        u=world.users["cs.thu"],
    )
    _exec(admin, "UPDATE agent.handoff_requests SET candidates = CAST(:v AS jsonb)", v='["u1", "u2"]')
    with pytest.raises(IntegrityError):
        _exec(admin, "UPDATE agent.handoff_requests SET candidates = CAST(:v AS jsonb)", v='{"a": 1}')


async def test_tasks_form_a_tree_and_actions_log_takes_the_three_dispositions(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    agent_id = await _care_agent(db, world)
    parent, child = uuid4(), uuid4()
    task = (
        "INSERT INTO agent.tasks (id, clinic_id, parent_id, care_agent_id, agent_id, status) "
        "VALUES (:i, :c, :par, :a, 'scheduler', :s)"
    )
    _exec(admin, task, i=parent, c=world.clinic_id, par=None, a=agent_id, s="running")
    _exec(admin, task, i=child, c=world.clinic_id, par=parent, a=agent_id, s="needs_human")
    with pytest.raises(IntegrityError):
        _exec(admin, task, i=uuid4(), c=world.clinic_id, par=uuid4(), a=agent_id, s="queued")
    with pytest.raises(IntegrityError):
        _exec(admin, task, i=uuid4(), c=world.clinic_id, par=None, a=agent_id, s="exploded")
    log = (
        "INSERT INTO agent.actions_log (clinic_id, care_agent_id, action_type, depth, disposition) "
        "VALUES (:c, :a, 'appointment_reminder', :d, :s)"
    )
    for disposition in ("auto_sent", "reviewed", "paused"):
        _exec(admin, log, c=world.clinic_id, a=agent_id, d="D1", s=disposition)
    with pytest.raises(IntegrityError):
        _exec(admin, log, c=world.clinic_id, a=agent_id, d="D1", s="deleted")
    _exec(admin, "DELETE FROM agent.tasks WHERE id = :i", i=parent)  # cascades to the child
    assert _scalar(admin, "SELECT count(*) FROM agent.tasks WHERE id = :i", i=child) == 0


def test_skills_are_unique_per_name_and_limited_to_the_two_profiles(world: SeedResult, admin: Engine) -> None:
    ins = (
        "INSERT INTO agent.skills (clinic_id, name, instruction, enabled_for_profiles) "
        "VALUES (:c, :n, 'hướng dẫn (mẫu)', CAST(:p AS text[]))"
    )
    _exec(admin, ins, c=world.clinic_id, n="handoff", p="{patient_channel}")
    with pytest.raises(IntegrityError):
        _exec(admin, ins, c=world.clinic_id, n="handoff", p="{patient_channel}")
    with pytest.raises(IntegrityError):
        _exec(admin, ins, c=world.clinic_id, n="other", p="{everyone}")
    with pytest.raises(IntegrityError):
        _exec(admin, ins, c=world.clinic_id, n="Bad Name", p="{}")


def test_staff_profiles_on_call_and_ownership_constraints(world: SeedResult, admin: Engine) -> None:
    profile = (
        "INSERT INTO clinic.staff_profiles (clinic_id, user_id, role, skills) VALUES (:c, :u, :r, '{laser}')"
    )
    _exec(admin, profile, c=world.clinic_id, u=world.users["cs.thu"], r="cs_staff")
    with pytest.raises(IntegrityError):  # one profile per user
        _exec(admin, profile, c=world.clinic_id, u=world.users["cs.thu"], r="cs_staff")
    with pytest.raises(IntegrityError):
        _exec(admin, profile, c=world.clinic_id, u=world.users["cs.maianh"], r="patient")
    with pytest.raises(IntegrityError):  # the user must exist in this clinic
        _exec(admin, profile, c=world.clinic_id, u=uuid4(), r="cs_staff")
    assert _scalar(admin, "SELECT languages FROM clinic.staff_profiles") == ["vi"]
    assert _scalar(admin, "SELECT capacity FROM clinic.staff_profiles") == 5

    call = "INSERT INTO clinic.on_call_contacts (clinic_id, zalo_number, owner, valid_to) VALUES (:c, :n, 'Trực (mẫu)', :v)"
    _exec(admin, call, c=world.clinic_id, n="0000000009", v=None)
    for number in ("abc", "12", "0000 000 009"):
        with pytest.raises(IntegrityError):
            _exec(admin, call, c=world.clinic_id, n=number, v=None)
    with pytest.raises(IntegrityError):  # valid_to must come after valid_from
        _exec(admin, call, c=world.clinic_id, n="0000000008", v="2000-01-01T00:00:00+00:00")
    assert _scalar(admin, "SELECT is_fixture FROM clinic.on_call_contacts") is False

    own = "INSERT INTO clinic.patient_ownership (clinic_id, patient_id, cs_owner, doctor) VALUES (:c, :p, :o, :d)"
    _exec(
        admin,
        own,
        c=world.clinic_id,
        p=world.patients["P025"],
        o=world.users["cs.maianh"],
        d=world.users["doctor.mai"],
    )
    with pytest.raises(IntegrityError):
        _exec(admin, own, c=world.clinic_id, p=world.patients["P025"], o=None, d=None)


# ------------------------------------------------------------------------------------ triggers, versions
async def test_updated_at_moves_on_update_and_the_version_guards_lost_races(
    db: ClinicDatabase, world: SeedResult
) -> None:
    agent_id = await _care_agent(db, world)
    async with db.session() as second:
        b = await second.get(CareAgent, agent_id)
        assert b is not None
        async with db.session() as first:
            a = await first.get(CareAgent, agent_id)
            assert a is not None
            created = a.updated_at
            a.paused = True
            await first.flush()
            assert a.version == 2
            assert a.updated_at >= created
        b.paused = True  # another writer committed meanwhile: this UPDATE matches no row
        with pytest.raises(StaleDataError):
            await second.flush()
        await second.rollback()


# ------------------------------------------------------------------------------------ migration
def test_the_migration_downgrades_one_step_and_upgrades_again(admin: Engine, pg_url: str) -> None:
    """alembic downgrade về trước M1 rồi upgrade heads đều chạy được trên DB sạch; downgrade gỡ sạch bảng và view"""
    cfg = Config(str(API_INI))
    command.downgrade(cfg, M1_PARENT)
    with admin.connect() as conn:
        left = conn.execute(
            text(
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relname = ANY(:t) AND n.nspname IN ('agent', 'clinic', 'clinic_agent')"
            ),
            {"t": sorted(AGENT_TABLES | CLINIC_TABLES | {"staff_profile", "on_call_contact"})},
        ).scalar_one()
    assert left == 0
    command.upgrade(cfg, "heads")
    assert _columns(admin, "agent", "care_agents") >= {"patient_id", "autonomy_levels", "autonomy_override"}
    assert _columns(admin, "clinic", "on_call_contacts") >= {"zalo_number", "is_fixture"}


async def test_the_upgrade_pairs_existing_patients_and_copies_their_owners(
    world: SeedResult, admin: Engine
) -> None:
    """bệnh nhân có sẵn khi nâng cấp được ghép care_agent và chép CSKH phụ trách/bác sĩ sang patient_ownership"""
    cfg = Config(str(API_INI))
    command.downgrade(cfg, M1_PARENT)
    command.upgrade(cfg, "heads")
    patients = _scalar(admin, "SELECT count(*) FROM clinic.patient")
    assert patients >= len(world.patients)
    assert _scalar(admin, "SELECT count(*) FROM agent.care_agents") == patients
    assert _scalar(admin, "SELECT count(*) FROM clinic.patient_ownership") == patients
    with admin.connect() as conn:
        mismatches = conn.execute(
            text(
                "SELECT count(*) FROM clinic.patient p JOIN clinic.patient_ownership o ON o.patient_id = p.id "
                "WHERE o.cs_owner IS DISTINCT FROM p.cs_owner_id OR o.doctor IS DISTINCT FROM p.doctor_id"
            )
        ).scalar_one()
    assert mismatches == 0

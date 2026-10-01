"""DDL acceptance tests on a clean Postgres (pgvector image).

Set ``PEMA_TEST_DATABASE_URL`` to a superuser URL of a throwaway database, for example::

    docker run -d --name pema-pg-test -e POSTGRES_PASSWORD=testpw -e POSTGRES_DB=pema \\
        -p 127.0.0.1:55432:5432 pgvector/pgvector:pg17
    PEMA_TEST_DATABASE_URL=postgresql+psycopg://postgres:testpw@127.0.0.1:55432/pema make test-db

Without the variable every test here is skipped. The fixture drops every Pema schema first and re-runs
the alembic history, so never point it at data you care about.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from pema.core.db import ClinicDatabase

API_DIR = Path(__file__).resolve().parents[1]
API_INI = API_DIR / "alembic.ini"
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"

pytestmark = pytest.mark.db

ADMIN_URL = os.environ.get("PEMA_TEST_DATABASE_URL")
if not ADMIN_URL:
    pytest.skip("PEMA_TEST_DATABASE_URL not set; no Postgres to test against", allow_module_level=True)

CLINIC_TABLES = {
    "clinic", "user_account", "patient", "episode", "treatment_plan", "treatment_session",
    "appointment", "crm_rule", "crm_task", "crm_activity", "channel_setting", "channel_identity",
    "conversation", "message", "review_item", "consent", "message_template", "audit_log",
}  # fmt: skip
AGENT_TABLES = {
    "runtime_settings", "agents", "accounts", "threads", "history", "contacts", "memories",
    "image_descriptions", "friend_requests", "usage", "usage_steps", "jobs", "job_runs",
    "proactive_send_counters", "kb_document", "kb_chunk", "agent_kb_document", "mcp_servers",
    "agent_mcp_servers", "channel_update_seen",
}  # fmt: skip
VIEWS = {
    "patient_ref", "patient_appointment", "patient_open_task", "patient_care_plan",
    "patient_last_session", "consent_current", "identity_verified", "channel_policy",
    "message_template_approved",
}  # fmt: skip


def _reset(engine: Engine) -> None:
    with engine.begin() as conn:
        for schema in ("clinic_agent", "agent", "clinic", "ctx"):
            conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text("DROP TABLE IF EXISTS public.alembic_version_pema"))


@pytest.fixture(scope="module")
def admin_engine() -> Iterator[Engine]:
    assert ADMIN_URL is not None
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = ADMIN_URL
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    engine = create_engine(ADMIN_URL)
    _reset(engine)
    command.upgrade(Config(str(API_INI)), "heads")
    yield engine
    engine.dispose()


def _role_engine(role: str, password: str) -> Engine:
    assert ADMIN_URL is not None
    return create_engine(make_url(ADMIN_URL).set(username=role, password=password))


@pytest.fixture(scope="module")
def be_engine(admin_engine: Engine) -> Iterator[Engine]:
    engine = _role_engine("be_app", BE_PASSWORD)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def worker_engine(admin_engine: Engine) -> Iterator[Engine]:
    engine = _role_engine("agent_worker", WORKER_PASSWORD)
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def two_clinics(admin_engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    """Two clinics, each with one synthetic patient, one agent/account and one verified identity."""
    clinic_a, clinic_b = uuid.uuid4(), uuid.uuid4()
    with admin_engine.begin() as conn:
        for clinic_id, slug in ((clinic_a, "clinic-a"), (clinic_b, "clinic-b")):
            conn.execute(
                text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, :name)"),
                {"id": clinic_id, "slug": slug, "name": f"Synthetic {slug}"},
            )
            patient_id = conn.execute(
                text(
                    "INSERT INTO clinic.patient (clinic_id, code, full_name, phone, birth_date) "
                    "VALUES (:c, 'P001', 'Synthetic Patient', '0000000000', '1990-01-01') RETURNING id"
                ),
                {"c": clinic_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, patient_id, "
                    "verification_status, verified_at) "
                    "VALUES (:c, 'zalo_bot', 'uid-1', :p, 'verified', now())"
                ),
                {"c": clinic_id, "p": patient_id},
            )
            conn.execute(
                text("INSERT INTO agent.agents (clinic_id, id, name) VALUES (:c, 'default', 'Default')"),
                {"c": clinic_id},
            )
            conn.execute(
                text(
                    "INSERT INTO agent.accounts (clinic_id, id, label, channel, agent_id) "
                    "VALUES (:c, 'bot-1', 'Bot', 'zalo_bot', 'default')"
                ),
                {"c": clinic_id},
            )
    return clinic_a, clinic_b


def _in_clinic(conn: Connection, clinic_id: uuid.UUID | None) -> None:
    if clinic_id is not None:
        conn.execute(text("SELECT set_config('app.clinic_id', :c, true)"), {"c": str(clinic_id)})


def _tables(engine: Engine, schema: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": schema}
        )
        return {r[0] for r in rows}


def test_schemas_contain_expected_tables_and_views(admin_engine: Engine) -> None:
    assert _tables(admin_engine, "clinic") >= CLINIC_TABLES
    assert _tables(admin_engine, "agent") >= AGENT_TABLES
    assert _tables(admin_engine, "clinic_agent") >= VIEWS


def test_every_table_has_rls_enabled_and_a_clinic_policy(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT n.nspname, c.relname, c.relrowsecurity, "
                "(SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname IN ('clinic', 'agent') AND c.relkind = 'r'"
            )
        ).all()
    assert {r[1] for r in rows if r[0] == "clinic"} >= CLINIC_TABLES
    assert {r[1] for r in rows if r[0] == "agent"} >= AGENT_TABLES
    assert [(r[0], r[1]) for r in rows if not r[2] or r[3] < 1] == []


def test_every_table_carries_clinic_id(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT t.table_schema, t.table_name FROM information_schema.tables t "
                "WHERE t.table_schema IN ('clinic', 'agent') AND t.table_type = 'BASE TABLE' "
                "AND NOT EXISTS (SELECT 1 FROM information_schema.columns c WHERE c.table_schema = t.table_schema "
                "AND c.table_name = t.table_name AND c.column_name IN ('clinic_id') ) "
                "AND NOT (t.table_schema = 'clinic' AND t.table_name = 'clinic')"
            )
        ).all()
    assert rows == []


def test_agent_worker_has_no_privilege_on_clinic_schema(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        assert (
            conn.execute(text("SELECT has_schema_privilege('agent_worker', 'clinic', 'USAGE')")).scalar()
            is False
        )
        for table in CLINIC_TABLES:
            for priv in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                allowed = conn.execute(
                    text("SELECT has_table_privilege('agent_worker', :t, :p)"),
                    {"t": f"clinic.{table}", "p": priv},
                ).scalar()
                assert allowed is False, (table, priv)


def test_agent_worker_reads_clinic_data_only_through_views(
    worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, _ = two_clinics
    with worker_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        codes = conn.execute(text("SELECT code FROM clinic_agent.patient_ref")).scalars().all()
        assert codes == ["P001"]
        with pytest.raises(ProgrammingError):
            conn.execute(text("SELECT * FROM clinic.patient"))


def test_views_expose_no_contact_or_birth_data(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'clinic_agent'")
            )
        }
    assert not cols & {"phone", "birth_date", "address", "note", "reason", "photo", "credential_ciphertext"}


def test_views_are_empty_without_a_clinic_context(worker_engine: Engine, two_clinics: object) -> None:
    with worker_engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM clinic_agent.patient_ref")).scalar() == 0


def test_agent_worker_cannot_write_clinic_tables_directly(
    worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, _ = two_clinics
    with worker_engine.connect() as conn, pytest.raises(ProgrammingError):
        _in_clinic(conn, clinic_a)
        conn.execute(text("UPDATE clinic.patient SET marketing_opt_out = true"))


def test_be_app_sees_only_its_own_clinic(be_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]) -> None:
    clinic_a, clinic_b = two_clinics
    with be_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        assert conn.execute(text("SELECT count(*) FROM clinic.patient")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM clinic.clinic")).scalar() == 1
    with be_engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM clinic.patient")).scalar() == 0  # fail closed
    with be_engine.begin() as conn:
        _in_clinic(conn, clinic_b)
        with pytest.raises((IntegrityError, DBAPIError)):
            conn.execute(
                text("INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, 'P002', 'X')"),
                {"c": clinic_a},
            )


def test_agent_tables_are_isolated_per_clinic_for_both_roles(
    be_engine: Engine, worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, clinic_b = two_clinics
    for engine in (be_engine, worker_engine):
        with engine.begin() as conn:
            _in_clinic(conn, clinic_a)
            assert conn.execute(text("SELECT count(*) FROM agent.accounts")).scalar() == 1
            assert conn.execute(text("SELECT clinic_id FROM agent.accounts")).scalar_one() == clinic_a
        with engine.begin() as conn:
            assert conn.execute(text("SELECT count(*) FROM agent.accounts")).scalar() == 0
        with engine.begin() as conn:
            _in_clinic(conn, clinic_b)
            with pytest.raises(DBAPIError):
                conn.execute(
                    text("INSERT INTO agent.agents (clinic_id, id, name) VALUES (:c, 'x', 'X')"),
                    {"c": clinic_a},
                )


def test_lookups_work_for_both_roles_without_context(
    be_engine: Engine, worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, clinic_b = two_clinics
    for engine in (be_engine, worker_engine):
        with engine.begin() as conn:
            assert conn.execute(text("SELECT ctx.resolve_clinic('clinic-a')")).scalar_one() == clinic_a
            assert conn.execute(text("SELECT ctx.resolve_clinic('nope')")).scalar_one() is None
            ids = set(conn.execute(text("SELECT ctx.list_active_clinic_ids()")).scalars().all())
            assert {clinic_a, clinic_b} <= ids


def test_resolve_identity_function(worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]) -> None:
    clinic_a, _ = two_clinics
    with worker_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        row = conn.execute(text("SELECT * FROM clinic_agent.resolve_identity('zalo_bot', 'uid-1')")).one()
        assert (row.status, row.patient_code) == ("verified", "P001")
        unknown = conn.execute(
            text("SELECT * FROM clinic_agent.resolve_identity('zalo_bot', 'stranger')")
        ).one()
        assert (unknown.status, unknown.patient_id) == ("unlinked", None)
        conn.execute(text("SELECT clinic_agent.touch_identity('zalo_bot', 'stranger', 'Someone')"))
        again = conn.execute(
            text("SELECT * FROM clinic_agent.resolve_identity('zalo_bot', 'stranger')")
        ).one()
        assert again.status == "unlinked"


def test_functions_refuse_to_run_without_a_clinic_context(worker_engine: Engine, two_clinics: object) -> None:
    with worker_engine.connect() as conn, pytest.raises(DBAPIError):
        conn.execute(text("SELECT clinic_agent.touch_identity('zalo_bot', 'x', '')"))


def _create_review(conn: Connection, job_id: str, kind: str, risk: str) -> uuid.UUID:
    return conn.execute(
        text(
            "SELECT clinic_agent.create_review_item(:job, :kind, 'agent_turn', 'P001', NULL, 'draft text', "
            "NULL, '[]'::jsonb, :risk, ARRAY[]::text[], 'qwen3-8b', 'v1')"
        ),
        {"job": job_id, "kind": kind, "risk": risk},
    ).scalar_one()


def test_create_review_item_is_idempotent_audited_and_flags_doctor(
    worker_engine: Engine, admin_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, _ = two_clinics
    with worker_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        first = _create_review(conn, "turn-1", "reply_draft", "normal")
        assert _create_review(conn, "turn-1", "reply_draft", "normal") == first
        alert = _create_review(conn, "turn-2", "triage_alert", "red_flag")
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, requires_doctor FROM clinic.review_item WHERE clinic_id = :c ORDER BY created_at"
            ),
            {"c": clinic_a},
        ).all()
        assert [(r.id, r.requires_doctor) for r in rows] == [(first, False), (alert, True)]
        audit = conn.execute(
            text(
                "SELECT count(*) FROM clinic.audit_log WHERE clinic_id = :c AND actor_type = 'agent' "
                "AND action = 'review_item.create'"
            ),
            {"c": clinic_a},
        ).scalar()
        assert audit == 2


def test_audit_log_is_append_only(be_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]) -> None:
    clinic_a, _ = two_clinics
    with be_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        conn.execute(
            text(
                "INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type) "
                "VALUES (:c, 'user', 'patient.create', 'patient')"
            ),
            {"c": clinic_a},
        )
    with be_engine.connect() as conn, pytest.raises(DBAPIError):
        _in_clinic(conn, clinic_a)
        conn.execute(text("UPDATE clinic.audit_log SET action = 'tampered'"))


def test_birthday_rule_can_never_be_auto_send(
    admin_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, _ = two_clinics
    with admin_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO clinic.crm_rule (clinic_id, rule_key, name, trigger, suggested_action, send_mode) "
                "VALUES (:c, 'birthday', 'Birthday', 'birthday', 'greet', 'auto_reminder')"
            ),
            {"c": clinic_a},
        )


def test_verified_identity_needs_a_patient(
    admin_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, _ = two_clinics
    with admin_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, verification_status) "
                "VALUES (:c, 'zalo_bot', 'nobody', 'verified')"
            ),
            {"c": clinic_a},
        )


def test_once_job_must_run_exactly_once(
    worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, _ = two_clinics
    insert = text(
        "INSERT INTO agent.jobs (clinic_id, id, account_id, thread_id, thread_type, name, kind, payload, "
        "schedule_kind, max_runs, dedupe_key) VALUES (:c, :id, 'bot-1', 't1', 0, 'n', 'message', 'p', 'once', "
        ":max_runs, :dedupe)"
    )
    with worker_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        conn.execute(insert, {"c": clinic_a, "id": "job-ok", "max_runs": 1, "dedupe": "d1:P001:evt"})
    with worker_engine.connect() as conn, pytest.raises(IntegrityError):
        _in_clinic(conn, clinic_a)
        conn.execute(insert, {"c": clinic_a, "id": "job-bad", "max_runs": 5, "dedupe": None})
    with worker_engine.connect() as conn, pytest.raises(IntegrityError):
        _in_clinic(conn, clinic_a)
        conn.execute(insert, {"c": clinic_a, "id": "job-dup", "max_runs": 1, "dedupe": "d1:P001:evt"})


def test_kb_chunk_supports_fts_and_vector_search(
    worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]
) -> None:
    clinic_a, _ = two_clinics
    vec = "[" + ",".join(["0.1"] * 1024) + "]"
    with worker_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        conn.execute(
            text(
                "INSERT INTO agent.kb_document (clinic_id, id, name, kind) VALUES (:c, 'doc1', 'Faq', 'text')"
            ),
            {"c": clinic_a},
        )
        conn.execute(
            text(
                "INSERT INTO agent.kb_chunk (clinic_id, source_id, ord, content, folded, embedding) "
                "VALUES (:c, 'doc1', 0, 'Cham soc sau laser', 'cham soc sau laser', CAST(:v AS vector))"
            ),
            {"c": clinic_a, "v": vec},
        )
        fts = conn.execute(
            text("SELECT count(*) FROM agent.kb_chunk WHERE tsv @@ plainto_tsquery('simple', 'laser')")
        ).scalar()
        assert fts == 1
        nearest = conn.execute(
            text("SELECT source_id FROM agent.kb_chunk ORDER BY embedding <=> CAST(:v AS vector) LIMIT 1"),
            {"v": vec},
        ).scalar()
        assert nearest == "doc1"


def test_default_binding_is_closed(worker_engine: Engine, two_clinics: tuple[uuid.UUID, uuid.UUID]) -> None:
    """Default-deny of KB and MCP: no binding rows exist until someone creates them."""
    clinic_a, _ = two_clinics
    with worker_engine.begin() as conn:
        _in_clinic(conn, clinic_a)
        assert conn.execute(text("SELECT count(*) FROM agent.agent_kb_document")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM agent.agent_mcp_servers")).scalar() == 0


async def test_clinic_database_sets_the_context_for_both_roles(
    two_clinics: tuple[uuid.UUID, uuid.UUID],
) -> None:
    """``pema.core.db.ClinicDatabase``: the session helper every package uses."""
    assert ADMIN_URL is not None
    clinic_a, clinic_b = two_clinics
    be_url = (
        make_url(ADMIN_URL).set(username="be_app", password=BE_PASSWORD).render_as_string(hide_password=False)
    )
    worker_url = (
        make_url(ADMIN_URL)
        .set(username="agent_worker", password=WORKER_PASSWORD)
        .render_as_string(hide_password=False)
    )
    be_db, worker_db = ClinicDatabase(be_url), ClinicDatabase(worker_url)
    try:
        async with be_db.session(clinic_a) as session:
            rows = (await session.execute(text("SELECT code FROM clinic.patient"))).scalars().all()
            assert rows == ["P001"]
        async with be_db.session(clinic_b) as session:
            clinic_ids = (await session.execute(text("SELECT clinic_id FROM clinic.patient"))).scalars().all()
            assert clinic_ids == [clinic_b]
        async with be_db.system_session() as session:
            assert (await session.execute(text("SELECT count(*) FROM clinic.patient"))).scalar() == 0
        assert await be_db.resolve_clinic("clinic-a") == clinic_a
        assert await worker_db.resolve_clinic("no-such-clinic") is None
        assert {clinic_a, clinic_b} <= set(await worker_db.list_active_clinic_ids())
        async with worker_db.session(clinic_a) as session:
            assert (await session.execute(text("SELECT count(*) FROM agent.accounts"))).scalar() == 1
            assert (
                await session.execute(text("SELECT count(*) FROM clinic_agent.patient_ref"))
            ).scalar() == 1
    finally:
        await be_db.dispose()
        await worker_db.dispose()


async def test_clinic_database_rolls_back_on_error(two_clinics: tuple[uuid.UUID, uuid.UUID]) -> None:
    assert ADMIN_URL is not None
    clinic_a, _ = two_clinics
    be_url = (
        make_url(ADMIN_URL).set(username="be_app", password=BE_PASSWORD).render_as_string(hide_password=False)
    )
    db = ClinicDatabase(be_url)
    try:
        with pytest.raises(RuntimeError, match="boom"):
            async with db.session(clinic_a) as session:
                await session.execute(
                    text(
                        "INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, 'P777', 'Gone')"
                    ),
                    {"c": clinic_a},
                )
                raise RuntimeError("boom")
        async with db.session(clinic_a) as session:
            codes = (await session.execute(text("SELECT code FROM clinic.patient"))).scalars().all()
            assert "P777" not in codes
    finally:
        await db.dispose()


def test_downgrade_then_upgrade_round_trips(admin_engine: Engine) -> None:
    cfg = Config(str(API_INI))
    command.downgrade(cfg, "base")
    assert _tables(admin_engine, "clinic") == set()
    command.upgrade(cfg, "heads")
    assert _tables(admin_engine, "clinic") >= CLINIC_TABLES


# ------------------------------------------------------------------ package G (SECURITY-REVIEW-AI01 SEC-10)
def test_every_security_definer_function_pins_a_search_path_ending_in_pg_temp(admin_engine: Engine) -> None:
    """mọi hàm SECURITY DEFINER cố định search_path và để pg_temp cuối cùng (không bị che bởi bảng tạm)"""
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT p.oid::regprocedure::text AS sig, "
                "(SELECT substr(c, 13) FROM unnest(p.proconfig) AS c WHERE c LIKE 'search_path=%') AS sp "
                "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE p.prosecdef AND n.nspname IN ('ctx', 'clinic_agent', 'clinic', 'agent')"
            )
        ).all()
    assert len(rows) >= 10, "the definer functions of the migrations must be found"
    for sig, search_path in rows:
        assert search_path is not None, f"{sig} has no fixed search_path"
        assert search_path.split(",")[0].strip() == "pg_catalog", sig
        assert search_path.split(",")[-1].strip() == "pg_temp", sig


def test_no_function_of_the_agent_door_is_executable_by_public(admin_engine: Engine) -> None:
    """không hàm nào của ctx/clinic_agent mở cho PUBLIC; agent_worker chỉ chạy được các hàm được cấp"""
    with admin_engine.connect() as conn:
        public = (
            conn.execute(
                text(
                    "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname IN ('ctx', 'clinic_agent') "
                    "AND EXISTS (SELECT 1 FROM aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) a "
                    "WHERE a.grantee = 0 AND a.privilege_type = 'EXECUTE')"
                )
            )
            .scalars()
            .all()
        )
        assert public == []
        temp_for_public = conn.execute(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_database d, "
                "aclexplode(COALESCE(d.datacl, acldefault('d', d.datdba))) a "
                "WHERE d.datname = current_database() AND a.grantee = 0 AND a.privilege_type = 'TEMPORARY')"
            )
        ).scalar_one()
    assert temp_for_public is False

"""DDL acceptance tests on a clean Postgres (pgvector image).

Single tenant (package ST-A): one installation is ONE clinic. These tests prove that ``clinic.clinic`` accepts
exactly one row, that there is no row level security and no clinic context any more, that ``agent_worker``
is still shut out of ``clinic.*`` and keeps its door (``clinic_agent``), and that the migration builds a
database with the clinic from the environment.

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
from collections.abc import Generator, Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError

from pema.config.env import get_settings
from pema.core.db import ClinicDatabase, InstallationClinicMismatchError, get_installation_clinic_id
from pema.core.installation import INSTALLATION_SLUG, ensure_clinic
from pema.core.testing import ensure_test_clinic, truncate_installation_data
from pema_contracts.actions import ActionContext
from pema_contracts.installation import (
    InstallationClinicNotLoadedError,
    installation_clinic_id,
    reset_installation_clinic_id,
)
from pema_contracts.roles import ActorType

API_DIR = Path(__file__).resolve().parents[1]
API_INI = API_DIR / "alembic.ini"
BE_PASSWORD = "be-app-test-secret"
WORKER_PASSWORD = "agent-worker-test-secret"
CLINIC_NAME = "Phong kham thu nghiem"
PRE_SINGLE_TENANT_REVISION = "h_0008_merge_heads"

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
    os.environ["PEMA_CLINIC_NAME"] = CLINIC_NAME
    os.environ.pop("PEMA_CLINIC_ID", None)
    get_settings.cache_clear()
    engine = create_engine(ADMIN_URL)
    _reset(engine)
    command.upgrade(Config(str(API_INI)), "heads")
    yield engine
    engine.dispose()
    os.environ.pop("PEMA_CLINIC_NAME", None)
    get_settings.cache_clear()


def _role_engine(role: str, password: str) -> Engine:
    assert ADMIN_URL is not None
    return create_engine(make_url(ADMIN_URL).set(username=role, password=password))


def _role_url(role: str, password: str) -> str:
    assert ADMIN_URL is not None
    return make_url(ADMIN_URL).set(username=role, password=password).render_as_string(hide_password=False)


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
def clinic(admin_engine: Engine) -> uuid.UUID:
    """THE clinic of the installation, with one synthetic patient, one agent/account and one verified identity."""
    with admin_engine.begin() as conn:
        clinic_id = ensure_test_clinic(conn)
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
    return clinic_id


@pytest.fixture
def clean_settings_and_cache() -> Iterator[None]:
    get_settings.cache_clear()
    reset_installation_clinic_id()
    yield
    get_settings.cache_clear()
    reset_installation_clinic_id()


def _tables(engine: Engine, schema: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s"), {"s": schema}
        )
        return {r[0] for r in rows}


def _count(conn: Connection, sql: str) -> int:
    return int(conn.execute(text(sql)).scalar_one())


# ------------------------------------------------------------------ schema
def test_schemas_contain_expected_tables_and_views(admin_engine: Engine) -> None:
    assert _tables(admin_engine, "clinic") >= CLINIC_TABLES
    assert _tables(admin_engine, "agent") >= AGENT_TABLES
    assert _tables(admin_engine, "clinic_agent") >= VIEWS


def test_no_table_has_row_level_security_or_a_policy(admin_engine: Engine) -> None:
    """không bảng nào còn RLS hay policy (cài đặt một phòng khám, DB riêng)"""
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname IN ('clinic', 'agent') AND c.relkind = 'r'"
            )
        ).all()
        policies = _count(conn, "SELECT count(*) FROM pg_policy")
    assert {r[1] for r in rows if r[0] == "clinic"} >= CLINIC_TABLES
    assert {r[1] for r in rows if r[0] == "agent"} >= AGENT_TABLES
    assert [(r[0], r[1]) for r in rows if r[2] or r[3]] == []
    assert policies == 0


def test_the_multi_tenant_functions_are_gone(admin_engine: Engine) -> None:
    """ctx.current_clinic_id, ctx.resolve_clinic, ctx.list_active_clinic_ids không còn; không hàm/view nào nhắc tới"""
    with admin_engine.connect() as conn:
        names = set(
            conn.execute(
                text(
                    "SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname = 'ctx'"
                )
            )
            .scalars()
            .all()
        )
        referencing = (
            conn.execute(
                text(
                    "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname IN ('ctx', 'clinic', 'clinic_agent', 'agent') "
                    "AND (p.prosrc LIKE '%current_clinic_id%' OR p.prosrc LIKE '%app.clinic_id%' "
                    "OR p.prosrc LIKE '%resolve_clinic%' OR p.prosrc LIKE '%list_active_clinic_ids%')"
                )
            )
            .scalars()
            .all()
        )
        views = (
            conn.execute(
                text(
                    "SELECT viewname FROM pg_views WHERE schemaname IN ('clinic', 'clinic_agent', 'agent') "
                    "AND (definition LIKE '%current_clinic_id%' OR definition LIKE '%app.clinic_id%')"
                )
            )
            .scalars()
            .all()
        )
    assert names == {"the_clinic_id"}
    assert referencing == []
    assert views == []


def test_every_table_carries_clinic_id(admin_engine: Engine) -> None:
    """cột clinic_id vẫn có ở mọi bảng: nó là mã cài đặt cố định"""
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


def test_views_keep_security_barrier(admin_engine: Engine) -> None:
    """các view clinic_agent được dựng lại vẫn security_barrier"""
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT c.relname, c.reloptions FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname = 'clinic_agent' AND c.relkind = 'v'"
            )
        ).all()
    assert {r[0] for r in rows} >= VIEWS
    assert [r[0] for r in rows if not r[1] or "security_barrier=true" not in r[1]] == []


# ------------------------------------------------------------------ exactly one clinic
def test_migration_builds_exactly_one_clinic_from_the_environment(
    admin_engine: Engine, clinic: uuid.UUID
) -> None:
    """migration trên DB trống ra đúng một phòng khám, tên lấy từ PEMA_CLINIC_NAME"""
    with admin_engine.connect() as conn:
        rows = conn.execute(text("SELECT id, slug, name, singleton FROM clinic.clinic")).all()
    assert len(rows) == 1
    assert (rows[0].id, rows[0].slug, rows[0].name, rows[0].singleton) == (
        clinic,
        INSTALLATION_SLUG,
        CLINIC_NAME,
        True,
    )


def test_a_second_clinic_row_cannot_be_inserted(
    admin_engine: Engine, be_engine: Engine, clinic: uuid.UUID
) -> None:
    """không chèn được dòng phòng khám thứ hai (cả chủ DB lẫn be_app)"""
    insert = text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, 'Second')")
    for engine in (admin_engine, be_engine):
        with engine.connect() as conn, pytest.raises(IntegrityError):
            conn.execute(insert, {"id": uuid.uuid4(), "slug": f"second-{uuid.uuid4().hex[:6]}"})
    with admin_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO clinic.clinic (id, slug, name, singleton) VALUES (:id, 'other', 'Second', false)"
            ),
            {"id": uuid.uuid4()},
        )
    with admin_engine.connect() as conn:
        assert _count(conn, "SELECT count(*) FROM clinic.clinic") == 1


def test_the_singleton_flag_cannot_be_switched_off(be_engine: Engine, clinic: uuid.UUID) -> None:
    with be_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(text("UPDATE clinic.clinic SET singleton = false"))


def test_the_clinic_row_cannot_be_deleted(admin_engine: Engine, be_engine: Engine, clinic: uuid.UUID) -> None:
    for engine in (admin_engine, be_engine):
        with engine.connect() as conn, pytest.raises(DBAPIError, match="cannot be deleted"):
            conn.execute(text("DELETE FROM clinic.clinic"))


def test_ensure_clinic_is_idempotent_and_never_renames(admin_engine: Engine, clinic: uuid.UUID) -> None:
    """ensure_clinic chạy lại nhiều lần: cùng id, không đổi tên, id khác thì báo lỗi"""
    with admin_engine.begin() as conn:
        assert ensure_clinic(conn) == clinic
        assert ensure_clinic(conn, "Another name") == clinic
        assert ensure_clinic(conn, clinic_id=clinic) == clinic
        assert conn.execute(text("SELECT name FROM clinic.clinic")).scalar_one() == CLINIC_NAME
        assert _count(conn, "SELECT count(*) FROM clinic.clinic") == 1
    with admin_engine.connect() as conn, pytest.raises(DBAPIError, match="another id"):
        ensure_clinic(conn, clinic_id=uuid.uuid4())


def test_ensure_test_clinic_returns_the_clinic_and_sets_the_installation_id(
    admin_engine: Engine, clinic: uuid.UUID, clean_settings_and_cache: None
) -> None:
    with pytest.raises(InstallationClinicNotLoadedError):
        installation_clinic_id()
    with admin_engine.begin() as conn:
        assert ensure_test_clinic(conn) == clinic
    assert installation_clinic_id() == clinic
    context = ActionContext(actor_type=ActorType.USER)
    assert context.clinic_id == clinic


def test_runtime_roles_cannot_run_ensure_clinic(
    be_engine: Engine, worker_engine: Engine, clinic: uuid.UUID
) -> None:
    for engine in (be_engine, worker_engine):
        with engine.connect() as conn, pytest.raises(ProgrammingError):
            conn.execute(text("SELECT clinic.ensure_clinic('X')"))


# ------------------------------------------------------------------ grants (unchanged by the removal of RLS)
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


def test_agent_worker_reads_clinic_data_only_through_views(worker_engine: Engine, clinic: uuid.UUID) -> None:
    """agent_worker vẫn bị chặn trên clinic.* thô, đọc được view clinic_agent (không cần ngữ cảnh)"""
    with worker_engine.begin() as conn:
        codes = conn.execute(text("SELECT code FROM clinic_agent.patient_ref")).scalars().all()
        assert codes == ["P001"]
        assert conn.execute(text("SELECT clinic_id FROM clinic_agent.patient_ref")).scalar_one() == clinic
    for table in ("clinic.patient", "clinic.clinic", "clinic.audit_log"):
        with worker_engine.connect() as conn, pytest.raises(ProgrammingError):
            conn.execute(text(f"SELECT * FROM {table}"))  # noqa: S608 - fixed names


def test_views_expose_no_contact_or_birth_data(admin_engine: Engine) -> None:
    with admin_engine.connect() as conn:
        cols = {
            r[0]
            for r in conn.execute(
                text("SELECT column_name FROM information_schema.columns WHERE table_schema = 'clinic_agent'")
            )
        }
    assert not cols & {"phone", "birth_date", "address", "note", "reason", "photo", "credential_ciphertext"}


def test_agent_worker_cannot_write_clinic_tables_directly(worker_engine: Engine, clinic: uuid.UUID) -> None:
    with worker_engine.connect() as conn, pytest.raises(ProgrammingError):
        conn.execute(text("UPDATE clinic.patient SET marketing_opt_out = true"))


def test_be_app_reads_the_installation_data_without_any_context(be_engine: Engine, clinic: uuid.UUID) -> None:
    """không còn RLS: be_app đọc mọi dòng của bảng nó được cấp quyền, đây là chấp nhận được vì chỉ một phòng khám"""
    with be_engine.begin() as conn:
        assert _count(conn, "SELECT count(*) FROM clinic.patient") == 1
        assert _count(conn, "SELECT count(*) FROM clinic.clinic") == 1
        assert conn.execute(text("SELECT clinic_id FROM clinic.patient")).scalar_one() == clinic


def test_agent_tables_are_open_to_both_roles_without_context(
    be_engine: Engine, worker_engine: Engine, clinic: uuid.UUID
) -> None:
    for engine in (be_engine, worker_engine):
        with engine.begin() as conn:
            assert _count(conn, "SELECT count(*) FROM agent.accounts") == 1
            assert conn.execute(text("SELECT clinic_id FROM agent.accounts")).scalar_one() == clinic


def test_the_clinic_id_function_is_open_to_both_runtime_roles(
    be_engine: Engine, worker_engine: Engine, clinic: uuid.UUID
) -> None:
    for engine in (be_engine, worker_engine):
        with engine.begin() as conn:
            assert conn.execute(text("SELECT ctx.the_clinic_id()")).scalar_one() == clinic


def test_the_clinic_id_function_fails_closed_when_no_clinic_is_installed(
    admin_engine: Engine, clinic: uuid.UUID
) -> None:
    """DB chưa có phòng khám thì hàm báo lỗi (không trả NULL), kể cả các hàm clinic_agent (giao dịch rồi rollback)"""
    with admin_engine.connect() as conn:
        try:
            conn.execute(text("ALTER TABLE clinic.clinic DISABLE TRIGGER ALL"))
            conn.execute(text("DELETE FROM clinic.clinic"))
            with pytest.raises(DBAPIError, match="no clinic installed"):
                conn.execute(text("SELECT ctx.the_clinic_id()"))
            conn.rollback()
            conn.execute(text("ALTER TABLE clinic.clinic DISABLE TRIGGER ALL"))
            conn.execute(text("DELETE FROM clinic.clinic"))
            with pytest.raises(DBAPIError, match="no clinic installed"):
                conn.execute(text("SELECT clinic_agent.touch_identity('zalo_bot', 'x', '')"))
        finally:
            conn.rollback()
    with admin_engine.connect() as conn:
        assert _count(conn, "SELECT count(*) FROM clinic.clinic") == 1


# ------------------------------------------------------------------ clinic_agent functions still work
def test_resolve_identity_function(worker_engine: Engine, clinic: uuid.UUID) -> None:
    with worker_engine.begin() as conn:
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


def _create_review(conn: Connection, job_id: str, kind: str, risk: str) -> uuid.UUID:
    return conn.execute(
        text(
            "SELECT clinic_agent.create_review_item(:job, :kind, 'agent_turn', 'P001', NULL, 'draft text', "
            "NULL, '[]'::jsonb, :risk, ARRAY[]::text[], 'qwen3-8b', 'v1')"
        ),
        {"job": job_id, "kind": kind, "risk": risk},
    ).scalar_one()


def test_create_review_item_is_idempotent_audited_and_flags_doctor(
    worker_engine: Engine, admin_engine: Engine, clinic: uuid.UUID
) -> None:
    with worker_engine.begin() as conn:
        first = _create_review(conn, "turn-1", "reply_draft", "normal")
        assert _create_review(conn, "turn-1", "reply_draft", "normal") == first
        alert = _create_review(conn, "turn-2", "triage_alert", "red_flag")
    with admin_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, requires_doctor FROM clinic.review_item WHERE clinic_id = :c ORDER BY created_at"
            ),
            {"c": clinic},
        ).all()
        assert [(r.id, r.requires_doctor) for r in rows] == [(first, False), (alert, True)]
        audit = conn.execute(
            text(
                "SELECT count(*) FROM clinic.audit_log WHERE clinic_id = :c AND actor_type = 'agent' "
                "AND action = 'review_item.create'"
            ),
            {"c": clinic},
        ).scalar()
        assert audit == 2


def test_the_inbox_functions_write_for_the_installation_clinic(
    worker_engine: Engine, admin_engine: Engine, clinic: uuid.UUID
) -> None:
    """record_inbound_message / record_outbound_message lấy phòng khám từ dòng duy nhất, không từ ngữ cảnh"""
    with worker_engine.begin() as conn:
        conn.execute(
            text(
                "SELECT * FROM clinic_agent.record_inbound_message("
                "'zalo_bot', 'upd-1', 'thread-1', 'uid-1', 'Synthetic', 'xin chao', now(), 'agent')"
            )
        )
    with admin_engine.connect() as conn:
        clinic_ids = conn.execute(text("SELECT DISTINCT clinic_id FROM clinic.message")).scalars().all()
    assert clinic_ids == [clinic]


def test_audit_log_is_append_only(be_engine: Engine, clinic: uuid.UUID) -> None:
    with be_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type) "
                "VALUES (:c, 'user', 'patient.create', 'patient')"
            ),
            {"c": clinic},
        )
    with be_engine.connect() as conn, pytest.raises(DBAPIError):
        conn.execute(text("UPDATE clinic.audit_log SET action = 'tampered'"))
    with be_engine.connect() as conn, pytest.raises(DBAPIError):
        conn.execute(text("DELETE FROM clinic.audit_log"))


def test_birthday_rule_can_never_be_auto_send(admin_engine: Engine, clinic: uuid.UUID) -> None:
    with admin_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO clinic.crm_rule (clinic_id, rule_key, name, trigger, suggested_action, send_mode) "
                "VALUES (:c, 'birthday', 'Birthday', 'birthday', 'greet', 'auto_reminder')"
            ),
            {"c": clinic},
        )


def test_verified_identity_needs_a_patient(admin_engine: Engine, clinic: uuid.UUID) -> None:
    with admin_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO clinic.channel_identity (clinic_id, channel, external_user_id, verification_status) "
                "VALUES (:c, 'zalo_bot', 'nobody', 'verified')"
            ),
            {"c": clinic},
        )


def test_a_row_cannot_point_at_a_clinic_that_does_not_exist(be_engine: Engine, clinic: uuid.UUID) -> None:
    """clinic_id vẫn là khóa ngoại về dòng duy nhất"""
    with be_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text("INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, 'P404', 'X')"),
            {"c": uuid.uuid4()},
        )


def test_once_job_must_run_exactly_once(worker_engine: Engine, clinic: uuid.UUID) -> None:
    insert = text(
        "INSERT INTO agent.jobs (clinic_id, id, account_id, thread_id, thread_type, name, kind, payload, "
        "schedule_kind, max_runs, dedupe_key) VALUES (:c, :id, 'bot-1', 't1', 0, 'n', 'message', 'p', 'once', "
        ":max_runs, :dedupe)"
    )
    with worker_engine.begin() as conn:
        conn.execute(insert, {"c": clinic, "id": "job-ok", "max_runs": 1, "dedupe": "d1:P001:evt"})
    with worker_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(insert, {"c": clinic, "id": "job-bad", "max_runs": 5, "dedupe": None})
    with worker_engine.connect() as conn, pytest.raises(IntegrityError):
        conn.execute(insert, {"c": clinic, "id": "job-dup", "max_runs": 1, "dedupe": "d1:P001:evt"})


def test_kb_chunk_supports_fts_and_vector_search(worker_engine: Engine, clinic: uuid.UUID) -> None:
    vec = "[" + ",".join(["0.1"] * 1024) + "]"
    with worker_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO agent.kb_document (clinic_id, id, name, kind) VALUES (:c, 'doc1', 'Faq', 'text')"
            ),
            {"c": clinic},
        )
        conn.execute(
            text(
                "INSERT INTO agent.kb_chunk (clinic_id, source_id, ord, content, folded, embedding) "
                "VALUES (:c, 'doc1', 0, 'Cham soc sau laser', 'cham soc sau laser', CAST(:v AS vector))"
            ),
            {"c": clinic, "v": vec},
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


def test_default_binding_is_closed(worker_engine: Engine, clinic: uuid.UUID) -> None:
    """Default-deny of KB and MCP: no binding rows exist until someone creates them."""
    with worker_engine.begin() as conn:
        assert _count(conn, "SELECT count(*) FROM agent.agent_kb_document") == 0
        assert _count(conn, "SELECT count(*) FROM agent.agent_mcp_servers") == 0


# ------------------------------------------------------------------ pema.core.db
async def test_clinic_database_session_needs_no_clinic_for_both_roles(clinic: uuid.UUID) -> None:
    """``pema.core.db.ClinicDatabase``: ``session()`` takes no clinic for either role"""
    be_db = ClinicDatabase(_role_url("be_app", BE_PASSWORD))
    worker_db = ClinicDatabase(_role_url("agent_worker", WORKER_PASSWORD))
    try:
        async with be_db.session() as session:
            rows = (await session.execute(text("SELECT code FROM clinic.patient"))).scalars().all()
            assert rows == ["P001"]
        async with worker_db.session() as session:
            assert (await session.execute(text("SELECT count(*) FROM agent.accounts"))).scalar() == 1
            assert (
                await session.execute(text("SELECT count(*) FROM clinic_agent.patient_ref"))
            ).scalar() == 1
    finally:
        await be_db.dispose()
        await worker_db.dispose()


async def test_get_installation_clinic_id_reads_the_database_once_and_caches(
    clinic: uuid.UUID, clean_settings_and_cache: None
) -> None:
    be_db = ClinicDatabase(_role_url("be_app", BE_PASSWORD))
    worker_db = ClinicDatabase(_role_url("agent_worker", WORKER_PASSWORD))
    try:
        assert be_db.installation_clinic_id is None
        assert await get_installation_clinic_id(be_db) == clinic
        assert be_db.installation_clinic_id == clinic
        assert installation_clinic_id() == clinic
        assert await get_installation_clinic_id(worker_db) == clinic  # the worker role may call it too
        # cached: a closed engine no longer matters
        await be_db.dispose()
        assert await get_installation_clinic_id(be_db) == clinic
    finally:
        await be_db.dispose()
        await worker_db.dispose()


async def test_installation_id_from_the_environment_is_used_and_verified(
    clinic: uuid.UUID, monkeypatch: pytest.MonkeyPatch, clean_settings_and_cache: None
) -> None:
    db = ClinicDatabase(_role_url("be_app", BE_PASSWORD))
    try:
        monkeypatch.setenv("PEMA_CLINIC_ID", str(clinic))
        get_settings.cache_clear()
        assert await get_installation_clinic_id(db, verify=True) == clinic

        other = uuid.uuid4()
        monkeypatch.setenv("PEMA_CLINIC_ID", str(other))
        get_settings.cache_clear()
        fresh = ClinicDatabase(_role_url("be_app", BE_PASSWORD))
        try:
            assert await get_installation_clinic_id(fresh) == other  # no check without verify
            with pytest.raises(InstallationClinicMismatchError):
                await get_installation_clinic_id(fresh, verify=True)
        finally:
            await fresh.dispose()
    finally:
        await db.dispose()


async def test_clinic_database_rolls_back_on_error(clinic: uuid.UUID) -> None:
    db = ClinicDatabase(_role_url("be_app", BE_PASSWORD))
    try:
        with pytest.raises(RuntimeError, match="boom"):
            async with db.session() as session:
                await session.execute(
                    text(
                        "INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, 'P777', 'Gone')"
                    ),
                    {"c": clinic},
                )
                raise RuntimeError("boom")
        async with db.session() as session:
            codes = (await session.execute(text("SELECT code FROM clinic.patient"))).scalars().all()
            assert "P777" not in codes
    finally:
        await db.dispose()


# ------------------------------------------------------------------ migrations
@contextmanager
def _scratch_database(monkeypatch: pytest.MonkeyPatch) -> Generator[tuple[Engine, Config]]:
    """An EMPTY database on the test server (own name), migration URL pointed at it."""
    assert ADMIN_URL is not None
    name = f"pema_sta_{uuid.uuid4().hex[:10]}"
    maintenance = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")
    with maintenance.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = make_url(ADMIN_URL).set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("PEMA_MIGRATION_DATABASE_URL", url)
    engine = create_engine(url)
    try:
        yield engine, Config(str(API_INI))
    finally:
        engine.dispose()
        with maintenance.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        maintenance.dispose()


def test_migration_on_an_empty_database_uses_the_clinic_name_and_id_of_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wanted = uuid.uuid4()
    monkeypatch.setenv("PEMA_CLINIC_NAME", "Phong kham Hoa Sen")
    monkeypatch.setenv("PEMA_CLINIC_ID", str(wanted))
    with _scratch_database(monkeypatch) as (engine, cfg):
        command.upgrade(cfg, "heads")
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT id, name, slug FROM clinic.clinic")).all()
        assert [(r.id, r.name, r.slug) for r in rows] == [(wanted, "Phong kham Hoa Sen", INSTALLATION_SLUG)]


def test_migration_on_an_empty_database_generates_the_id_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PEMA_CLINIC_NAME", raising=False)
    monkeypatch.delenv("PEMA_CLINIC_ID", raising=False)
    with _scratch_database(monkeypatch) as (engine, cfg):
        command.upgrade(cfg, "heads")
        with engine.connect() as conn:
            first = conn.execute(text("SELECT id FROM clinic.clinic")).scalar_one()
            assert conn.execute(text("SELECT name FROM clinic.clinic")).scalar_one() == "Pema Clinic"
        command.downgrade(cfg, PRE_SINGLE_TENANT_REVISION)
        command.upgrade(cfg, "heads")
        with engine.connect() as conn:
            assert conn.execute(text("SELECT id FROM clinic.clinic")).scalar_one() == first


def test_the_upgrade_refuses_a_database_that_already_holds_two_clinics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _scratch_database(monkeypatch) as (engine, cfg):
        command.upgrade(cfg, PRE_SINGLE_TENANT_REVISION)
        with engine.begin() as conn:
            for slug in ("a", "b"):
                conn.execute(
                    text("INSERT INTO clinic.clinic (id, slug, name) VALUES (:id, :slug, 'X')"),
                    {"id": uuid.uuid4(), "slug": slug},
                )
        with pytest.raises(DBAPIError, match="more than one clinic"):
            command.upgrade(cfg, "heads")
        with engine.connect() as conn:  # the failed upgrade left no half-done change behind
            assert (
                _count(
                    conn,
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema = 'clinic' AND table_name = 'clinic' AND column_name = 'singleton'",
                )
                == 0
            )


def test_single_tenant_migration_downgrades_to_rls_and_upgrades_again(
    admin_engine: Engine, clinic: uuid.UUID
) -> None:
    """downgrade về h_0008 trả lại RLS và hàm cũ, upgrade lại giữ nguyên phòng khám"""
    cfg = Config(str(API_INI))
    command.downgrade(cfg, PRE_SINGLE_TENANT_REVISION)
    with admin_engine.connect() as conn:
        assert _count(conn, "SELECT count(*) FROM pg_policy") == 41
        assert (
            _count(
                conn,
                "SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE n.nspname IN ('clinic', 'agent') AND c.relkind = 'r' AND c.relrowsecurity",
            )
            == 41
        )
        assert _count(conn, "SELECT count(*) FROM pg_proc WHERE proname = 'current_clinic_id'") == 1
        assert (
            _count(conn, "SELECT count(*) FROM pg_proc WHERE proname IN ('the_clinic_id', 'ensure_clinic')")
            == 0
        )
        assert _count(conn, "SELECT count(*) FROM clinic.clinic") == 1
    command.upgrade(cfg, "heads")
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT id FROM clinic.clinic")).scalar_one() == clinic
        assert _count(conn, "SELECT count(*) FROM pg_policy") == 0
        assert _count(conn, "SELECT count(*) FROM clinic.patient") == 1


def test_downgrade_then_upgrade_round_trips(admin_engine: Engine) -> None:
    cfg = Config(str(API_INI))
    command.downgrade(cfg, "base")
    assert _tables(admin_engine, "clinic") == set()
    command.upgrade(cfg, "heads")
    assert _tables(admin_engine, "clinic") >= CLINIC_TABLES
    with admin_engine.connect() as conn:
        assert conn.execute(text("SELECT name FROM clinic.clinic")).scalar_one() == CLINIC_NAME


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
    assert "ctx.the_clinic_id()" in {sig for sig, _ in rows}
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
                    "WHERE (n.nspname IN ('ctx', 'clinic_agent') OR p.proname = 'ensure_clinic') "
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


# ------------------------------------------------------------------ last: it empties the tables
def test_truncate_installation_data_keeps_the_clinic_row(admin_engine: Engine) -> None:
    """helper cho fixture: dọn dữ liệu mọi bảng trừ clinic.clinic (kể cả audit_log append-only)"""
    with admin_engine.begin() as conn:  # the round trip above rebuilt the database: take its clinic
        clinic = ensure_test_clinic(conn)
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.patient (clinic_id, code, full_name) VALUES (:c, 'P-TRUNC', 'Synthetic')"
            ),
            {"c": clinic},
        )
        conn.execute(
            text(
                "INSERT INTO clinic.audit_log (clinic_id, actor_type, action, entity_type) "
                "VALUES (:c, 'system', 'test.truncate', 'test')"
            ),
            {"c": clinic},
        )
    with admin_engine.begin() as conn:
        truncate_installation_data(conn)
    with admin_engine.connect() as conn:
        assert _count(conn, "SELECT count(*) FROM clinic.patient") == 0
        assert _count(conn, "SELECT count(*) FROM clinic.audit_log") == 0
        assert _count(conn, "SELECT count(*) FROM agent.accounts") == 0
        assert conn.execute(text("SELECT id FROM clinic.clinic")).scalar_one() == clinic
    with admin_engine.connect() as conn, pytest.raises(DBAPIError):  # the append-only guard is back
        conn.execute(text("TRUNCATE clinic.audit_log"))

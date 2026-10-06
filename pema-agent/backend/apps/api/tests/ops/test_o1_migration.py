"""The O1 migration: backfill counts, up/down/up on rows that use the new values, one head (package O, step O1).

New tests (no zalo-agent original). Needs ``PEMA_TEST_DATABASE_URL``. The downgrade goes to the NAMED previous
revision (``u9_0010_patient_parity``), never ``-1``, while rows that only the new schema can hold exist (an
internal account, a roster entry, a conversation that points at an identity, a consented bell id).
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.api.clinic_testing import API_INI, BE_PASSWORD, WORKER_PASSWORD
from pema.clinic.actions.seed_demo import SeedResult

pytestmark = pytest.mark.db

REVISION = "o1_0010_identities_roster"
PREVIOUS = "u9_0010_patient_parity"
MIGRATION = Path(API_INI).parent / "alembic" / "versions" / "o1_0010_identities_roster.py"
NINE_ARGS = "clinic_agent.record_inbound_message(text,text,text,text,text,text,timestamptz,text,text)"


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("o1_migration_under_test", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _config(pg_url: str) -> Config:
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = pg_url
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    return Config(str(API_INI))


def _head(pg_url: str) -> str:
    """The head of the stack (later steps stack on this one)."""
    head = ScriptDirectory.from_config(_config(pg_url)).get_current_head()
    assert head is not None
    return head


def _scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def test_there_is_one_head_and_it_stacks_on_the_previous_one(pg_url: str) -> None:
    script = ScriptDirectory.from_config(_config(pg_url))
    assert len(script.get_heads()) == 1, "one alembic head"
    assert REVISION in {r.revision for r in script.walk_revisions()}
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_the_backfill_sets_only_what_agent_threads_proves(
    admin: Engine, world: SeedResult, add_account: Any
) -> None:
    migration = _load_migration()
    add_account("long")
    add_account("hoa")
    add_account("tro-ly", channel="zalo_bot")
    add_account("bell", purpose="internal")
    cid = world.clinic_id
    threads = [  # (account, thread)
        ("long", "ta"),  # a: proven by exactly one customer account of the same channel
        ("long", "tb"),  # b: two accounts know the thread: ambiguous
        ("hoa", "tb"),
        ("tro-ly", "td"),  # d: thread of an account of ANOTHER channel
        ("bell", "te"),  # e: thread of the internal notifier
    ]
    with admin.begin() as conn:
        baseline = migration.backfill_conversation_accounts(conn, dry_run=True)
        for account, thread in threads:
            conn.execute(
                text(
                    "INSERT INTO agent.threads (clinic_id, account_id, thread_id, thread_type) "
                    "VALUES (:c, :a, :t, 0)"
                ),
                {"c": cid, "a": account, "t": thread},
            )
        for thread in ("ta", "tb", "tc", "td", "te"):
            conn.execute(
                text(
                    "INSERT INTO clinic.conversation (clinic_id, channel, external_ref) "
                    "VALUES (:c, 'zalo_personal', :t)"
                ),
                {"c": cid, "t": thread},
            )
        conn.execute(  # f: already has an identity: never touched, never counted
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 'tf', 'hoa')"
            ),
            {"c": cid},
        )

    with admin.begin() as conn:
        dry = migration.backfill_conversation_accounts(conn, dry_run=True)
    assert (dry.set, dry.ambiguous, dry.unproven) == (1, 1, baseline.unproven + 3)
    assert dry.left_null == dry.ambiguous + dry.unproven
    assert _scalar(admin, "SELECT account_id FROM clinic.conversation WHERE external_ref = 'ta'") is None, (
        "a dry run changes nothing"
    )

    with admin.begin() as conn:
        done = migration.backfill_conversation_accounts(conn, dry_run=False)
    assert (done.set, done.ambiguous, done.unproven) == (dry.set, dry.ambiguous, dry.unproven)
    with admin.connect() as conn:
        rows = dict(conn.execute(text("SELECT external_ref, account_id FROM clinic.conversation")).all())
    assert rows["ta"] == "long"
    assert (rows["tb"], rows["tc"], rows["td"], rows["te"]) == (None, None, None, None)
    assert rows["tf"] == "hoa"
    with admin.begin() as conn:
        again = migration.backfill_conversation_accounts(conn, dry_run=True)
    assert again.set == 0  # idempotent


def test_a_round_trip_through_the_named_previous_revision_with_rows_that_use_the_new_values(
    pg_url: str, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    add_account("bell", purpose="internal", send_gap_min_s=1, send_gap_max_s=5, daily_cap=3)
    cid = world.clinic_id
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.account_roster (clinic_id, account_id, user_id, weekdays, start_time, end_time) "
                "VALUES (:c, 'long', :u, ARRAY['mon','tue'], '22:00', '06:00')"
            ),
            {"c": cid, "u": world.users["cs.thu"]},
        )
        conn.execute(
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 'thread-x', 'long')"
            ),
            {"c": cid},
        )
        conn.execute(
            text(
                "INSERT INTO clinic.staff_profiles (clinic_id, user_id, role, notify_zalo_user_id, "
                "notify_zalo_consented_at) VALUES (:c, :u, 'cs_staff', 'zalo-bell-synthetic', now())"
            ),
            {"c": cid, "u": world.users["cs.thu"]},
        )
        # a thread that proves the pair the backfill of the NEXT upgrade will rebuild
        conn.execute(
            text(
                "INSERT INTO agent.threads (clinic_id, account_id, thread_id, thread_type) "
                "VALUES (:c, 'long', 'thread-x', 0)"
            ),
            {"c": cid},
        )

    config = _config(pg_url)
    command.downgrade(config, PREVIOUS)
    assert _scalar(admin, "SELECT version_num FROM public.alembic_version_pema") == PREVIOUS
    assert _scalar(admin, "SELECT to_regclass('clinic.account_roster') IS NULL")
    for table, column in (
        ("agent.accounts", "purpose"),
        ("agent.accounts", "daily_cap"),
        ("clinic.conversation", "account_id"),
        ("clinic.staff_profiles", "notify_zalo_user_id"),
    ):
        schema, name = table.split(".")
        assert not _scalar(
            admin,
            "SELECT count(*) FROM information_schema.columns "
            "WHERE table_schema = :s AND table_name = :t AND column_name = :c",
            s=schema,
            t=name,
            c=column,
        ), f"{table}.{column} is gone after the downgrade"
    # the conversation and the staff profile are still there; the old function is the only one left and works
    assert _scalar(admin, "SELECT count(*) FROM clinic.conversation WHERE external_ref = 'thread-x'") == 1
    assert _scalar(admin, "SELECT count(*) FROM pg_proc WHERE proname = 'record_inbound_message'") == 1
    assert _scalar(admin, "SELECT pronargs FROM pg_proc WHERE proname = 'record_inbound_message'") == 8
    with admin.begin() as conn:
        row = conn.execute(
            text(
                "SELECT * FROM clinic_agent.record_inbound_message("
                "'zalo_personal', 'old-update', 'thread-old', 'uid-old', 'Khách', 'Chào', now(), 'system')"
            )
        ).one()
    assert row.o_duplicate is False

    command.upgrade(config, "heads")
    assert _scalar(admin, "SELECT version_num FROM public.alembic_version_pema") == _head(pg_url)
    assert (
        _scalar(admin, "SELECT count(*) FROM clinic.account_roster") == 0
    )  # the entry was dropped with the table
    assert _scalar(admin, "SELECT count(*) FROM agent.accounts WHERE purpose = 'internal'") == 0
    assert (
        _scalar(admin, "SELECT account_id FROM clinic.conversation WHERE external_ref = 'thread-x'") == "long"
    ), "the backfill of the upgrade rebuilt the pair that agent.threads proves"
    assert _scalar(admin, "SELECT notify_zalo_user_id FROM clinic.staff_profiles LIMIT 1") is None
    assert _scalar(admin, "SELECT count(*) FROM pg_proc WHERE proname = 'record_inbound_message'") == 2
    assert _scalar(admin, f"SELECT has_function_privilege('agent_worker', '{NINE_ARGS}', 'EXECUTE')")
    assert _scalar(admin, f"SELECT has_function_privilege('be_app', '{NINE_ARGS}', 'EXECUTE')")
    assert not _scalar(admin, f"SELECT has_function_privilege('public', '{NINE_ARGS}', 'EXECUTE')")


def test_the_worker_view_of_staff_profiles_does_not_expose_the_bell_id(
    admin: Engine, world: SeedResult
) -> None:
    columns = {
        row[0]
        for row in admin.connect().execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'clinic_agent' AND table_name = 'staff_profile'"
            )
        )
    }
    assert columns
    assert not {c for c in columns if c.startswith("notify_")}


def test_the_bell_id_and_its_consent_are_set_together_or_not_at_all(admin: Engine, world: SeedResult) -> None:
    from sqlalchemy.exc import IntegrityError

    for assignment in ("notify_zalo_user_id = 'x'", "notify_zalo_consented_at = now()"):
        with admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.staff_profiles (clinic_id, user_id, role) VALUES (:c, :u, 'cs_staff') "
                    "ON CONFLICT DO NOTHING"
                ),
                {"c": world.clinic_id, "u": world.users["cs.thu"]},
            )
        with pytest.raises(IntegrityError), admin.begin() as conn:
            conn.execute(
                text(f"UPDATE clinic.staff_profiles SET {assignment} WHERE user_id = :u"),  # noqa: S608
                {"u": world.users["cs.thu"]},
            )

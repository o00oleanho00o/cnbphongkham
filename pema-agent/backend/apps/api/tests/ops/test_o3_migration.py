"""The O3 migration: one head, constraints, grants, up/down/up on rows that use the new values (package O,
step O3).

New tests (no zalo-agent original). Need ``PEMA_TEST_DATABASE_URL``. The downgrade goes to the NAMED previous
revision (``o2_0010_assignment``), never ``-1``, while rows that only the new schema can hold exist (an outbox
row for the on-call contact, an acknowledged row, a push token, an SLA check).
"""

from __future__ import annotations

import os
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from pema.api.clinic_testing import API_INI, BE_PASSWORD, WORKER_PASSWORD
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

REVISION = "o3_0010_notifications"
PREVIOUS = "o2_0010_assignment"
HASH = "a" * 64
TABLES = (
    "notification_log",
    "push_token",
    "notify_setting",
    "notify_preference",
    "notify_link_code",
    "sla_check",
)
INSERT_OUTBOX = (
    "INSERT INTO clinic.notification_outbox (clinic_id, kind, recipient_kind, payload) "
    "VALUES (:c, :k, :rk, CAST('{}' AS jsonb))"
)


def _config(pg_url: str) -> Config:
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = pg_url
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    return Config(str(API_INI))


def _scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def test_there_is_one_head_and_it_stacks_on_o2(pg_url: str) -> None:
    script = ScriptDirectory.from_config(_config(pg_url))
    assert len(script.get_heads()) == 1
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS
    assert REVISION in {r.revision for r in script.walk_revisions()}


def test_the_new_tables_and_columns_exist(admin: Engine, world: SeedResult) -> None:
    for table in TABLES:
        assert _scalar(admin, f"SELECT to_regclass('clinic.{table}') IS NOT NULL"), table
    with admin.connect() as conn:
        columns = {
            row[0]
            for row in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_schema = 'clinic' "
                    "AND table_name = 'notification_outbox'"
                )
            )
        }
    assert {"attempts", "next_attempt_at", "chain_step", "lease_until", "acked_at", "acked_by"} <= columns


def test_the_on_call_kind_is_accepted_without_a_user_and_other_kinds_stay_refused(
    admin: Engine, world: SeedResult
) -> None:
    with admin.begin() as conn:
        conn.execute(
            text(INSERT_OUTBOX), {"c": world.clinic_id, "k": "handoff.handoff_on_call", "rk": "on_call"}
        )
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(text(INSERT_OUTBOX), {"c": world.clinic_id, "k": "x", "rk": "sms"})
    with pytest.raises(IntegrityError), admin.begin() as conn:  # an on-call row never names a user
        conn.execute(
            text(
                "INSERT INTO clinic.notification_outbox (clinic_id, kind, recipient_kind, recipient_user_id, "
                "payload) VALUES (:c, 'x', 'on_call', :u, CAST('{}' AS jsonb))"
            ),
            {"c": world.clinic_id, "u": world.users["owner"]},
        )


def test_the_chain_columns_are_checked(admin: Engine, world: SeedResult) -> None:
    for column, value in (("chain_step", "'sms'"), ("attempts", "-1")):
        with pytest.raises(IntegrityError), admin.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO clinic.notification_outbox (clinic_id, kind, recipient_kind, payload, {column}) "  # noqa: S608
                    f"VALUES (:c, 'x', 'team_group', CAST('{{}}' AS jsonb), {value})"
                ),
                {"c": world.clinic_id},
            )


async def test_the_log_is_append_only_for_the_application_role(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    with admin.begin() as conn:
        outbox = conn.execute(
            text(INSERT_OUTBOX + " RETURNING id"), {"c": world.clinic_id, "k": "x", "rk": "team_group"}
        ).scalar_one()
    async with db.session() as session:
        await session.execute(
            text(
                "INSERT INTO clinic.notification_log (clinic_id, outbox_id, provider, attempt, status) "
                "VALUES (:c, :o, 'in_app', 1, 'sent')"
            ),
            {"c": world.clinic_id, "o": outbox},
        )
    for statement in (
        "UPDATE clinic.notification_log SET status = 'failed'",
        "DELETE FROM clinic.notification_log",
    ):
        with pytest.raises(DBAPIError):
            async with db.session() as session:
                await session.execute(text(statement))
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.notification_log (clinic_id, outbox_id, provider, attempt, status) "
                "VALUES (:c, :o, 'sms', 1, 'sent')"
            ),
            {"c": world.clinic_id, "o": outbox},
        )


def test_a_push_token_is_unique_per_clinic_and_a_quiet_window_needs_both_ends(
    admin: Engine, world: SeedResult
) -> None:
    user = world.users["cs.maianh"]
    row = {"c": world.clinic_id, "u": user, "h": HASH}
    insert = (
        "INSERT INTO clinic.push_token (clinic_id, user_id, platform, token_hash, token_enc) "
        "VALUES (:c, :u, 'android', :h, 'enc')"
    )
    with admin.begin() as conn:
        conn.execute(text(insert), row)
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(text(insert), row)
    for start, end in (("22:00", None), ("22:00", "22:00")):
        with pytest.raises(IntegrityError), admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.notify_preference (clinic_id, user_id, quiet_start, quiet_end) "
                    "VALUES (:c, :u, :s, :e)"
                ),
                {"c": world.clinic_id, "u": user, "s": start, "e": end},
            )


def test_up_down_up_survives_rows_that_use_the_new_schema(
    pg_url: str, admin: Engine, world: SeedResult
) -> None:
    user = world.users["cs.maianh"]
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.notification_outbox (clinic_id, kind, recipient_kind, payload, attempts, "
                "acked_at, acked_by, chain_step) VALUES (:c, 'assignment.takeover', 'team_group', "
                "CAST('{}' AS jsonb), 2, now(), :u, 'done')"
            ),
            {"c": world.clinic_id, "u": user},
        )
        conn.execute(
            text(INSERT_OUTBOX), {"c": world.clinic_id, "k": "handoff.handoff_on_call", "rk": "on_call"}
        )
        conn.execute(
            text(
                "INSERT INTO clinic.push_token (clinic_id, user_id, platform, token_hash, token_enc) "
                "VALUES (:c, :u, 'ios', :h, 'enc')"
            ),
            {"c": world.clinic_id, "u": user, "h": HASH},
        )
        conn.execute(
            text(
                "INSERT INTO clinic.sla_check (clinic_id, request_id, idx, due_at, dedupe_key) "
                "VALUES (:c, gen_random_uuid(), 0, now(), 'sla:fixture:0')"
            ),
            {"c": world.clinic_id},
        )

    config = _config(pg_url)
    command.downgrade(config, PREVIOUS)
    assert _scalar(admin, "SELECT version_num FROM public.alembic_version_pema") == PREVIOUS
    for table in TABLES:
        assert _scalar(admin, f"SELECT to_regclass('clinic.{table}') IS NULL"), table
    # the O2 outbox is back, the on-call row (it cannot exist there) is gone, the other row kept its state
    assert _scalar(admin, "SELECT count(*) FROM clinic.notification_outbox") == 1
    assert _scalar(admin, "SELECT state FROM clinic.notification_outbox") == "pending"
    assert not _scalar(
        admin,
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'clinic' "
        "AND table_name = 'notification_outbox' AND column_name = 'acked_at'",
    )
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(text(INSERT_OUTBOX), {"c": world.clinic_id, "k": "x", "rk": "on_call"})

    command.upgrade(config, "heads")
    assert _scalar(admin, "SELECT version_num FROM public.alembic_version_pema") == REVISION
    assert _scalar(admin, "SELECT attempts FROM clinic.notification_outbox") == 0

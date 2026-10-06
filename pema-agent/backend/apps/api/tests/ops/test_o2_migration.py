"""The O2 migration: one head, constraints, grants, up/down/up on rows that use the new values (package O,
step O2).

New tests (no zalo-agent original). Need ``PEMA_TEST_DATABASE_URL``. The downgrade goes to the NAMED previous
revision (``o1_0010_identities_roster``), never ``-1``, while rows that only the new schema can hold exist (a
conversation with a bumped ``assignment_version``, history rows, outbox rows).
"""

from __future__ import annotations

import os
from typing import Any
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from pema.api.clinic_testing import API_INI, BE_PASSWORD, WORKER_PASSWORD, record_inbound
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase

pytestmark = pytest.mark.db

REVISION = "o2_0010_assignment"
PREVIOUS = "o1_0010_identities_roster"


def _config(pg_url: str) -> Config:
    os.environ["PEMA_MIGRATION_DATABASE_URL"] = pg_url
    os.environ["PEMA_BE_APP_PASSWORD"] = BE_PASSWORD
    os.environ["PEMA_AGENT_WORKER_PASSWORD"] = WORKER_PASSWORD
    return Config(str(API_INI))


def _scalar(engine: Engine, sql: str, **params: Any) -> Any:
    with engine.connect() as conn:
        return conn.execute(text(sql), params).scalar()


def test_there_is_one_head_and_it_stacks_on_the_previous_one(pg_url: str) -> None:
    script = ScriptDirectory.from_config(_config(pg_url))
    assert script.get_heads() == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS


def test_the_new_column_and_tables_exist_with_the_right_shape(admin: Engine, world: SeedResult) -> None:
    assert _scalar(
        admin,
        "SELECT column_default FROM information_schema.columns WHERE table_schema = 'clinic' "
        "AND table_name = 'conversation' AND column_name = 'assignment_version'",
    ).startswith("1")
    assert _scalar(admin, "SELECT to_regclass('clinic.conversation_assignment') IS NOT NULL")
    assert _scalar(admin, "SELECT to_regclass('clinic.notification_outbox') IS NOT NULL")


def test_a_takeover_row_needs_a_reason_and_the_kind_is_closed(admin: Engine, world: SeedResult) -> None:
    conversation = world.conversation_id
    base = {"c": world.clinic_id, "v": conversation}
    for kind, reason in (("takeover", None), ("takeover", "   "), ("bogus", "x")):
        with pytest.raises(IntegrityError), admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.conversation_assignment (clinic_id, conversation_id, kind, reason) "
                    "VALUES (:c, :v, :k, :r)"
                ),
                {**base, "k": kind, "r": reason},
            )
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.conversation_assignment (clinic_id, conversation_id, kind, reason) "
                "VALUES (:c, :v, 'takeover', 'Cần trả lời')"
            ),
            base,
        )


def test_an_outbox_row_is_a_user_with_an_id_or_the_group_without_one(
    admin: Engine, world: SeedResult
) -> None:
    base = {"c": world.clinic_id, "v": world.conversation_id, "u": world.users["cs.thu"]}
    bad = (
        ("user", None),  # a user row without a user
        ("team_group", base["u"]),  # a group row with a user
        ("sms", None),  # an unknown recipient kind
    )
    for recipient_kind, user in bad:
        with pytest.raises(IntegrityError), admin.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO clinic.notification_outbox (clinic_id, kind, recipient_kind, "
                    "recipient_user_id, conversation_id, payload) VALUES (:c, 'assignment.claim', :rk, :u, "
                    ":v, '{}'::jsonb)"
                ),
                {**base, "rk": recipient_kind, "u": user},
            )
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.notification_outbox (clinic_id, kind, recipient_kind, conversation_id, "
                "payload) VALUES (:c, 'assignment.claim', 'team_group', :v, '{}'::jsonb)"
            ),
            base,
        )
    assert _scalar(admin, "SELECT state FROM clinic.notification_outbox LIMIT 1") == "pending"


async def test_the_application_role_can_append_to_the_history_but_not_rewrite_it(
    db: ClinicDatabase, world: SeedResult, admin: Engine
) -> None:
    async with db.session() as session:
        await session.execute(
            text(
                "INSERT INTO clinic.conversation_assignment (clinic_id, conversation_id, kind) "
                "VALUES (:c, :v, 'claim')"
            ),
            {"c": world.clinic_id, "v": world.conversation_id},
        )
    for statement in (
        "UPDATE clinic.conversation_assignment SET kind = 'release'",
        "DELETE FROM clinic.conversation_assignment",
    ):
        with pytest.raises(DBAPIError):
            async with db.session() as session:
                await session.execute(text(statement))
    assert _scalar(admin, "SELECT count(*) FROM clinic.conversation_assignment") == 1


def test_up_down_up_survives_rows_that_use_the_new_schema(
    pg_url: str, admin: Engine, world: SeedResult
) -> None:
    cid = world.clinic_id
    conversation = world.conversation_id
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE clinic.conversation SET assigned_user_id = :u, assignment_version = 4 WHERE id = :v"
            ),
            {"u": world.users["cs.maianh"], "v": conversation},
        )
        conn.execute(
            text(
                "INSERT INTO clinic.conversation_assignment (clinic_id, conversation_id, user_id, kind) "
                "VALUES (:c, :v, :u, 'claim')"
            ),
            {"c": cid, "v": conversation, "u": world.users["cs.maianh"]},
        )
        conn.execute(
            text(
                "INSERT INTO clinic.notification_outbox (clinic_id, kind, recipient_kind, conversation_id, "
                "payload) VALUES (:c, 'assignment.claim', 'team_group', :v, '{}'::jsonb)"
            ),
            {"c": cid, "v": conversation},
        )

    config = _config(pg_url)
    command.downgrade(config, PREVIOUS)
    assert _scalar(admin, "SELECT version_num FROM public.alembic_version_pema") == PREVIOUS
    assert _scalar(admin, "SELECT to_regclass('clinic.conversation_assignment') IS NULL")
    assert _scalar(admin, "SELECT to_regclass('clinic.notification_outbox') IS NULL")
    assert not _scalar(
        admin,
        "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'clinic' "
        "AND table_name = 'conversation' AND column_name = 'assignment_version'",
    )
    # the conversation and its holder are still there
    assert (
        _scalar(admin, "SELECT assigned_user_id FROM clinic.conversation WHERE id = :v", v=conversation)
        == (world.users["cs.maianh"])
    )

    command.upgrade(config, "heads")
    assert _scalar(admin, "SELECT version_num FROM public.alembic_version_pema") == REVISION
    assert _scalar(admin, "SELECT count(*) FROM clinic.notification_outbox") == 0
    assert (
        _scalar(admin, "SELECT assignment_version FROM clinic.conversation WHERE id = :v", v=conversation)
        == 1
    )
    # the upgrade wrote one `assign` row for the conversation that already had a holder
    rows = _scalar(
        admin,
        "SELECT count(*) FROM clinic.conversation_assignment WHERE conversation_id = :v AND kind = 'assign' "
        'AND "by" IS NULL AND user_id = :u',
        v=conversation,
        u=world.users["cs.maianh"],
    )
    assert rows == 1


async def test_the_backfill_row_is_only_written_for_held_conversations(
    pg_url: str, admin: Engine, world: SeedResult, db: ClinicDatabase
) -> None:
    held = await record_inbound(db, world, uid=f"stranger-{uuid4().hex[:8]}")
    free = await record_inbound(db, world, uid=f"stranger-{uuid4().hex[:8]}")
    with admin.begin() as conn:
        conn.execute(
            text("UPDATE clinic.conversation SET assigned_user_id = :u WHERE id = :v"),
            {"u": world.users["cs.thu"], "v": held.conversation_id},
        )
    config = _config(pg_url)
    command.downgrade(config, PREVIOUS)
    command.upgrade(config, "heads")
    per_conversation = {
        row[0]: row[1]
        for row in admin.connect().execute(
            text(
                "SELECT conversation_id, count(*) FROM clinic.conversation_assignment GROUP BY conversation_id"
            )
        )
    }
    assert per_conversation.get(held.conversation_id) == 1
    assert free.conversation_id not in per_conversation

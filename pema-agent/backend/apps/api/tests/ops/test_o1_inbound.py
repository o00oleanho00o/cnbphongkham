"""Inbound: every new conversation gets the identity that received it (package O, step O1).

New tests (no zalo-agent original). Needs ``PEMA_TEST_DATABASE_URL``. The bot pipeline is run with the testing
helpers of ``pema.channels.zalo_bot`` and the personal pipeline through ``ghi_tin_den_vao_history`` (the function
the personal router calls); the message each one hands to the Inbox is then written by the REAL
``ClinicAgentFacingActions`` as the ``agent_worker`` role. The database guards (an internal account never
becomes the identity of a conversation, deleting an account detaches its conversations) are checked directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError

from pema.channels.record_incoming_message import ghi_tin_den_vao_history, webhook_action_context
from pema.channels.zalo_bot.nang_luc_kenh_bot import ZALO_BOT_CAPABILITIES
from pema.channels.zalo_bot.testing import FakeConversation, make_router_stack, make_update
from pema.clinic.actions.agent_facing import ClinicAgentFacingActions
from pema.clinic.actions.seed_demo import SeedResult
from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.core.db import ClinicDatabase
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.testing import FakeChannel, fake_account_config

pytestmark = pytest.mark.db

SENT = datetime(2026, 9, 20, 2, 0, tzinfo=UTC)


def inbound(
    account_id: str, thread: str, *, channel: ChannelKind = ChannelKind.ZALO_PERSONAL
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        account_id=account_id,
        update_id=uuid4().hex,
        thread_id=thread,
        sender_id=f"uid-{thread}",
        sender_name="Khách mẫu",
        text="Xin chào (mẫu)",
        msg_id=uuid4().hex,
        sent_at=SENT,
    )


async def record(db: ClinicDatabase, world: SeedResult, message: InboundMessage) -> UUID:
    ref = await ClinicAgentFacingActions(db).record_inbound_message(
        webhook_action_context(world.clinic_id), message
    )
    return ref.conversation_id


def conversation_account(admin: Engine, conversation_id: UUID) -> str | None:
    with admin.connect() as conn:
        value = conn.execute(
            text("SELECT account_id FROM clinic.conversation WHERE id = :i"), {"i": conversation_id}
        ).scalar()
    return None if value is None else str(value)


# ----------------------------------------------------------------------------------------- the hook
async def test_the_personal_pipeline_stores_the_identity_that_received_the_message(
    worker_db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    history = FakeConversation()
    message = inbound("long", "thread-personal")
    recorded = await ghi_tin_den_vao_history(
        clinic_id=world.clinic_id,
        account_id="long",
        msg=message,
        luu_anh_ngay=False,
        history=history,
        inbox=ClinicAgentFacingActions(worker_db),
    )
    assert recorded.inbox is not None
    assert conversation_account(admin, recorded.inbox.conversation_id) == "long"


async def test_the_bot_pipeline_stores_the_identity_that_received_the_message(
    worker_db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    install_tuning_provider(
        StaticTuningProvider(
            {
                "SEND_DELAY_MIN_MS": 0,
                "SEND_DELAY_MAX_MS": 0,
                "MESSAGE_BATCH_DEBOUNCE_MS": 20,
                "BUSY_ACK_AFTER_MS": 0,
            }
        )
    )
    add_account("tro-ly-bot", channel="zalo_bot")
    stack = make_router_stack(
        account=fake_account_config(id="tro-ly-bot", clinic_id=world.clinic_id, channel=ChannelKind.ZALO_BOT)
    )
    channel = FakeChannel(caps=ZALO_BOT_CAPABILITIES, account="tro-ly-bot")
    await stack.router.route_bot_update(
        world.clinic_id, "tro-ly-bot", channel, make_update("chào", thread_id="thread-bot", message_id="m-1")
    )
    await stack.batcher.clear_pending_batches()
    [handed_over] = stack.inbox.recorded
    assert handed_over.account_id == "tro-ly-bot"  # what the pipeline hands to the Inbox
    conversation_id = await record(worker_db, world, handed_over)  # and what the Inbox does with it
    assert conversation_account(admin, conversation_id) == "tro-ly-bot"


async def test_the_identity_is_never_overwritten_by_a_later_message(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    add_account("hoa")
    first = await record(db, world, inbound("long", "thread-1"))
    again = await record(db, world, inbound("hoa", "thread-1"))
    assert again == first
    assert conversation_account(admin, first) == "long"


async def test_a_conversation_without_an_identity_gets_one_with_the_next_message(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    old = await record(db, world, inbound("unknown-yet", "thread-2"))
    assert conversation_account(admin, old) is None
    assert await record(db, world, inbound("long", "thread-2")) == old
    assert conversation_account(admin, old) == "long"


async def test_an_account_the_installation_does_not_know_never_loses_the_message(
    db: ClinicDatabase, admin: Engine, world: SeedResult
) -> None:
    conversation_id = await record(db, world, inbound("not-in-agent-accounts", "thread-3"))
    assert conversation_account(admin, conversation_id) is None
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM clinic.message WHERE conversation_id = :i"), {"i": conversation_id}
            ).scalar()
            == 1
        )


# ---------------------------------------------------------------- an internal account is never an identity
async def test_an_internal_account_is_refused_and_nothing_is_written(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("bell", purpose="internal")
    with pytest.raises(DBAPIError, match="internal account"):
        await record(db, world, inbound("bell", "thread-4"))
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM clinic.conversation WHERE external_ref = 'thread-4'")
            ).scalar()
            == 0
        )
        assert (
            conn.execute(text("SELECT count(*) FROM clinic.message WHERE channel = 'zalo_personal'")).scalar()
            == 0
        )


def test_the_database_refuses_a_conversation_that_points_at_an_internal_account(
    admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("bell", purpose="internal")
    add_account("long")
    with pytest.raises(IntegrityError, match="internal account"), admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 't-direct', 'bell')"
            ),
            {"c": world.clinic_id},
        )
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 't-ok', 'long')"
            ),
            {"c": world.clinic_id},
        )
    with pytest.raises(IntegrityError, match="internal account"), admin.begin() as conn:
        conn.execute(text("UPDATE clinic.conversation SET account_id = 'bell' WHERE external_ref = 't-ok'"))


def test_the_database_refuses_to_make_an_account_internal_while_conversations_point_at_it(
    admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 't-1', 'long')"
            ),
            {"c": world.clinic_id},
        )
    with pytest.raises(IntegrityError, match="still point"), admin.begin() as conn:
        conn.execute(text("UPDATE agent.accounts SET purpose = 'internal' WHERE id = 'long'"))


def test_the_foreign_key_refuses_an_unknown_account_id(admin: Engine, world: SeedResult) -> None:
    with pytest.raises(IntegrityError), admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 't-1', 'ghost')"
            ),
            {"c": world.clinic_id},
        )


# --------------------------------------------------------------------------- deleting an account, wrapper
def test_deleting_an_account_detaches_its_conversations_and_keeps_them(
    admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    with admin.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO clinic.conversation (clinic_id, channel, external_ref, account_id) "
                "VALUES (:c, 'zalo_personal', 't-1', 'long')"
            ),
            {"c": world.clinic_id},
        )
        conn.execute(text("DELETE FROM agent.accounts WHERE id = 'long'"))
    with admin.connect() as conn:
        row = conn.execute(
            text("SELECT clinic_id, account_id FROM clinic.conversation WHERE external_ref = 't-1'")
        ).one()
    assert (row.clinic_id, row.account_id) == (world.clinic_id, None)


async def test_the_old_eight_argument_function_still_works_and_leaves_the_identity_empty(
    db: ClinicDatabase, admin: Engine, world: SeedResult, add_account: Any
) -> None:
    add_account("long")
    async with db.session() as session:
        row = (
            await session.execute(
                text(
                    "SELECT * FROM clinic_agent.record_inbound_message("
                    "'zalo_personal', :u, 't-legacy', 'uid-1', 'Khách', 'Chào', :t, 'system')"
                ),
                {"u": uuid4().hex, "t": SENT},
            )
        ).one()
    assert row.o_duplicate is False
    assert conversation_account(admin, row.o_conversation_id) is None

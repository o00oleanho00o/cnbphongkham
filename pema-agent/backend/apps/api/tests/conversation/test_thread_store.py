# ported from: src/conversation/thread-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

The last test of the original ("backfill dựng threads từ messages cũ, không chạy lại khi đã có dữ liệu") is not
ported: ``backfillThreadsFromMessages`` rebuilt the table from an older SQLite file at upgrade time and Postgres
starts clean (PORT-MAP: ``startup-backfill`` is "no port"). Two tests are added for the forced differences: the
foreign key to ``agent.accounts`` and the ``NULLS LAST`` ordering.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from pema.conversation.pg_testing import ClinicEnv
from pema.conversation.thread_store import ThreadStoreImpl

pytestmark = pytest.mark.db


async def _activity(
    threads: ThreadStoreImpl,
    env: ClinicEnv,
    thread_id: str,
    *,
    display_name: str = "Hải",
    sender_name: str = "Hải",
    account_id: str = "acc-1",
) -> None:
    await threads.record_thread_activity(
        env.clinic_id,
        account_id=account_id,
        thread_id=thread_id,
        thread_type=0,
        display_name=display_name,
        sender_name=sender_name,
    )


async def test_thread_store_upsert_creates_thread_then_increments_message_count(env: ClinicEnv) -> None:
    """upsert tạo thread mới rồi tăng message_count các lần sau"""
    threads = ThreadStoreImpl(env.db)
    for _ in range(3):
        await _activity(threads, env, "t-dem")

    rows = await threads.list_threads(env.clinic_id, account_id="acc-1", query="t-dem")
    assert len(rows) == 1
    assert rows[0].message_count == 3
    assert rows[0].display_name == "Hải"


async def test_thread_store_empty_display_name_does_not_overwrite_existing_name(env: ClinicEnv) -> None:
    """displayName rỗng không ghi đè tên đã có"""
    threads = ThreadStoreImpl(env.db)
    await _activity(threads, env, "t-ten", display_name="Nhóm Gia Đình")
    await _activity(threads, env, "t-ten", display_name="")

    rows = await threads.list_threads(env.clinic_id, account_id="acc-1", query="t-ten")
    assert rows[0].display_name == "Nhóm Gia Đình"


async def test_thread_store_unseen_thread_has_bot_enabled_by_default(env: ClinicEnv) -> None:
    """thread chưa từng thấy mặc định bot bật"""
    threads = ThreadStoreImpl(env.db)
    assert await threads.is_bot_enabled(env.clinic_id, "acc-1", "t-chua-co") is True
    # ... but the scheduler's view of the same thread is "unknown", which is a blocking condition
    assert await threads.find_thread_status(env.clinic_id, "acc-1", "t-chua-co") is None


async def test_thread_store_bot_can_be_switched_off_and_on_per_thread(env: ClinicEnv) -> None:
    """tắt rồi bật lại bot cho thread"""
    threads = ThreadStoreImpl(env.db)
    await _activity(threads, env, "t-toggle")

    assert await threads.set_bot_enabled(env.clinic_id, "acc-1", "t-toggle", False) is True
    assert await threads.is_bot_enabled(env.clinic_id, "acc-1", "t-toggle") is False
    status = await threads.find_thread_status(env.clinic_id, "acc-1", "t-toggle")
    assert status is not None
    assert status.bot_enabled is False

    assert await threads.set_bot_enabled(env.clinic_id, "acc-1", "t-toggle", True) is True
    assert await threads.is_bot_enabled(env.clinic_id, "acc-1", "t-toggle") is True


async def test_thread_store_set_bot_enabled_returns_false_for_missing_thread(env: ClinicEnv) -> None:
    """setBotEnabled trả false với thread không tồn tại"""
    threads = ThreadStoreImpl(env.db)
    assert await threads.set_bot_enabled(env.clinic_id, "acc-1", "t-khong-ton-tai", False) is False


async def test_thread_store_has_display_name_and_set_display_name_for_groups_named_later(
    env: ClinicEnv,
) -> None:
    """hasDisplayName + setThreadDisplayName cho group lấy tên async"""
    threads = ThreadStoreImpl(env.db)
    await _activity(threads, env, "t-group", display_name="")
    assert await threads.has_display_name(env.clinic_id, "acc-1", "t-group") is False

    await threads.set_thread_display_name(env.clinic_id, "acc-1", "t-group", "Nhóm Dev")
    assert await threads.has_display_name(env.clinic_id, "acc-1", "t-group") is True


async def test_thread_store_summary_round_trip_and_defaults_for_a_missing_thread(env: ClinicEnv) -> None:
    """(thêm) summary + mốc đã gộp ghi/đọc lại đúng; thread chưa có dòng đọc ra rỗng và 0"""
    threads = ThreadStoreImpl(env.db)
    await _activity(threads, env, "t-sum")
    await threads.set_thread_summary(env.clinic_id, "acc-1", "t-sum", "tóm tắt", 42)

    stored = await threads.get_thread_summary(env.clinic_id, "acc-1", "t-sum")
    assert (stored.summary, stored.covers_to_message_id) == ("tóm tắt", 42)
    missing = await threads.get_thread_summary(env.clinic_id, "acc-1", "t-khong-co")
    assert (missing.summary, missing.covers_to_message_id) == ("", 0)
    assert await threads.get_thread_context_epoch(env.clinic_id, "acc-1", "t-khong-co") == 0


async def test_thread_store_recording_activity_for_an_unknown_account_is_refused(env: ClinicEnv) -> None:
    """(thêm) khóa ngoại tới accounts: thread của account không tồn tại là mồ côi nên bị từ chối"""
    threads = ThreadStoreImpl(env.db)
    with pytest.raises(IntegrityError):
        await _activity(threads, env, "t-mo-coi", account_id="acc-khong-co")


async def test_thread_store_list_puts_threads_without_messages_last(env: ClinicEnv) -> None:
    """(thêm) thread mới nhất đứng đầu; thread chưa có tin (last_message_at NULL) đứng cuối như SQLite"""
    threads = ThreadStoreImpl(env.db)
    await _activity(threads, env, "t-cu")
    await _activity(threads, env, "t-moi")
    await env.execute(
        "INSERT INTO agent.threads (clinic_id, account_id, thread_id, thread_type) "
        "VALUES (:c, 'acc-1', 't-chua-co-tin', 0)",
        c=env.clinic_id,
    )

    rows = await threads.list_threads(env.clinic_id, account_id="acc-1")
    assert [r.thread_id for r in rows] == ["t-moi", "t-cu", "t-chua-co-tin"]

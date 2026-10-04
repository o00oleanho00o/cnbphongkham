# ported from: src/config/account-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Config auto-accept kết bạn per-account. The friend request store is package C2's; the delete test inserts the
orphan candidate with SQL (the table is ``agent.friend_requests``, created by migration 0002).
"""

from __future__ import annotations

import pytest

from pema.config.account_store import AccountStoreImpl
from pema.conversation.pg_testing import ClinicEnv
from pema_contracts.channel import ChannelKind

pytestmark = pytest.mark.db


async def _create(store: AccountStoreImpl, env: ClinicEnv, account_id: str):
    return await store.create_account(
        env.clinic_id, account_id=account_id, label="Nick", channel=ChannelKind.ZALO_PERSONAL, agent_id=None
    )


async def test_account_store_new_account_has_auto_accept_off_and_a_one_minute_delay(env: ClinicEnv) -> None:
    """account mới: auto-accept TẮT, delay = 1 phút (mặc định)"""
    store = AccountStoreImpl(env.db)
    account = await _create(store, env, "acc-def")
    assert account.auto_accept_friends is False, "mặc định phải TẮT"
    assert account.auto_accept_friend_delay_minutes == 1, "delay mặc định 1 phút"


async def test_account_store_update_saves_and_get_reads_back_the_persisted_values(env: ClinicEnv) -> None:
    """updateAccount lưu đúng, getAccount đọc lại đúng (persist thật)"""
    store = AccountStoreImpl(env.db)
    await _create(store, env, "acc-upd")
    updated = await store.update_account(
        env.clinic_id, "acc-upd", {"auto_accept_friends": True, "auto_accept_friend_delay_minutes": 5}
    )
    assert updated is not None
    assert updated.auto_accept_friends is True
    assert updated.auto_accept_friend_delay_minutes == 5

    got = await store.get_account(env.clinic_id, "acc-upd")
    assert got is not None
    assert got.auto_accept_friends is True, "đọc lại từ DB phải khớp"
    assert got.auto_accept_friend_delay_minutes == 5


async def test_account_store_switching_back_to_false_is_saved_correctly(env: ClinicEnv) -> None:
    """tắt lại về false vẫn lưu đúng (không dính giá trị cũ)"""
    store = AccountStoreImpl(env.db)
    await _create(store, env, "acc-off")
    await store.update_account(env.clinic_id, "acc-off", {"auto_accept_friends": True})
    await store.update_account(env.clinic_id, "acc-off", {"auto_accept_friends": False})
    got = await store.get_account(env.clinic_id, "acc-off")
    assert got is not None
    assert got.auto_accept_friends is False


async def test_account_store_delete_also_removes_friend_requests_no_orphans_to_revive_on_the_same_id(
    env: ClinicEnv,
) -> None:
    """deleteAccount DỌN luôn friend_requests (không để mồ côi -> hồi sinh khi tạo lại cùng id)"""
    store = AccountStoreImpl(env.db)
    await _create(store, env, "acc-del")
    await env.execute(
        "INSERT INTO agent.friend_requests (clinic_id, account_id, from_uid) VALUES (:c, 'acc-del', 'u')",
        c=env.clinic_id,
    )
    await store.delete_account(env.clinic_id, "acc-del")
    left = await env.scalar("SELECT COUNT(*) FROM agent.friend_requests WHERE account_id = 'acc-del'")
    assert left == 0, "xóa account phải xóa cả pending của nó"

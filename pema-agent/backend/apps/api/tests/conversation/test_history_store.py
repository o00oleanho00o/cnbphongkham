# ported from: src/conversation/history-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

The original opened a SQLite file per test run; here every test gets a fresh clinic on a throwaway Postgres
(see ``pema.conversation.pg_testing``), which also proves the rows of one clinic never show in another.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.conversation.history_store import HistoryStoreImpl
from pema.conversation.pg_testing import ClinicEnv
from pema_contracts.conversation import StoredMessage

pytestmark = pytest.mark.db

MAX_PER_THREAD = 25


@pytest.fixture(autouse=True)
def _tuning() -> None:  # pyright: ignore[reportUnusedFunction]
    install_tuning_provider(
        StaticTuningProvider({"HISTORY_MAX_MESSAGES_PER_THREAD": MAX_PER_THREAD, "HISTORY_CONTEXT_LIMIT": 20})
    )


def _user(content: str, sender_name: str | None = None, images: list[str] | None = None) -> StoredMessage:
    return StoredMessage(role="user", content=content, sender_name=sender_name, images=images or [])


def _assistant(content: str) -> StoredMessage:
    return StoredMessage(role="assistant", content=content)


async def _read_all(store: HistoryStoreImpl, env: ClinicEnv, account_id: str, thread_id: str):
    """Đọc toàn bộ tin còn lại của thread - limit lớn hơn cap để thấy cả phần thừa."""
    return await store.get_recent_messages(env.clinic_id, account_id, thread_id, MAX_PER_THREAD * 10)


async def test_history_store_returns_messages_oldest_to_newest(env: ClinicEnv) -> None:
    """trả tin theo thứ tự thời gian cũ -> mới"""
    store = HistoryStoreImpl(env.db)
    await store.append_message(env.clinic_id, "acc-1", "t-thutu", _user("một", "Hải"))
    await store.append_message(env.clinic_id, "acc-1", "t-thutu", _assistant("hai"))
    await store.append_message(env.clinic_id, "acc-1", "t-thutu", _user("ba", "Hải"))

    rows = await _read_all(store, env, "acc-1", "t-thutu")
    assert [r.content for r in rows] == ["một", "hai", "ba"]
    assert [r.role for r in rows] == ["user", "assistant", "user"]


async def test_history_store_keeps_sender_name_of_user_and_none_for_assistant(env: ClinicEnv) -> None:
    """giữ senderName của user, để trống với assistant"""
    store = HistoryStoreImpl(env.db)
    await store.append_message(env.clinic_id, "acc-1", "t-ten", _user("hỏi", "Minh Triết"))
    await store.append_message(env.clinic_id, "acc-1", "t-ten", _assistant("đáp"))

    rows = await _read_all(store, env, "acc-1", "t-ten")
    assert rows[0].sender_name == "Minh Triết"
    assert rows[1].sender_name is None


async def test_history_store_limit_takes_the_n_newest_not_the_first_n(env: ClinicEnv) -> None:
    """limit lấy đúng N tin mới nhất chứ không phải N tin đầu"""
    store = HistoryStoreImpl(env.db)
    for i in range(1, 11):
        await store.append_message(env.clinic_id, "acc-1", "t-limit", _user(f"tin-{i}"))

    rows = await store.get_recent_messages(env.clinic_id, "acc-1", "t-limit", 3)
    assert [r.content for r in rows] == ["tin-8", "tin-9", "tin-10"]


async def test_history_store_prune_keeps_exactly_cap_newest_when_thread_exceeds_limit(env: ClinicEnv) -> None:
    """prune giữ đúng cap tin mới nhất khi thread vượt giới hạn"""
    store = HistoryStoreImpl(env.db)
    total = MAX_PER_THREAD + 15
    for i in range(1, total + 1):
        await store.append_message(env.clinic_id, "acc-1", "t-prune", _user(f"tin-{i}"))

    rows = await _read_all(store, env, "acc-1", "t-prune")
    assert len(rows) == MAX_PER_THREAD
    # Phần bị xóa phải là phần cũ nhất
    assert rows[0].content == f"tin-{total - MAX_PER_THREAD + 1}"
    assert rows[-1].content == f"tin-{total}"


async def test_history_store_thread_below_cap_loses_nothing(env: ClinicEnv) -> None:
    """thread chưa đủ cap thì không bị xóa gì"""
    store = HistoryStoreImpl(env.db)
    for i in range(1, 6):
        await store.append_message(env.clinic_id, "acc-1", "t-it", _user(f"tin-{i}"))

    assert len(await _read_all(store, env, "acc-1", "t-it")) == 5


async def test_history_store_prune_touches_only_the_thread_just_written(env: ClinicEnv) -> None:
    """prune chỉ đụng thread vừa ghi, không đụng thread khác"""
    store = HistoryStoreImpl(env.db)
    await store.append_message(env.clinic_id, "acc-1", "t-yen", _user("để yên"))

    for i in range(1, MAX_PER_THREAD + 11):
        await store.append_message(env.clinic_id, "acc-1", "t-on", _user(f"tin-{i}"))

    assert len(await _read_all(store, env, "acc-1", "t-yen")) == 1
    assert len(await _read_all(store, env, "acc-1", "t-on")) == MAX_PER_THREAD


async def test_history_store_same_thread_id_in_another_account_is_counted_separately(env: ClinicEnv) -> None:
    """thread trùng id ở account khác được tính riêng"""
    store = HistoryStoreImpl(env.db)
    await store.append_message(env.clinic_id, "acc-1", "t-chung", _user("của acc-1"))
    await store.append_message(env.clinic_id, "acc-2", "t-chung", _user("của acc-2"))

    acc1 = await _read_all(store, env, "acc-1", "t-chung")
    acc2 = await _read_all(store, env, "acc-2", "t-chung")
    assert [r.content for r in acc1] == ["của acc-1"]
    assert [r.content for r in acc2] == ["của acc-2"]


async def test_history_store_images_round_trip_and_message_without_images_is_empty(env: ClinicEnv) -> None:
    """images ghi kèm tin thì đọc lại nguyên vẹn, tin không ảnh trả undefined"""
    store = HistoryStoreImpl(env.db)
    await store.append_message(
        env.clinic_id,
        "acc-1",
        "t-anh",
        _user(
            "xem ảnh [gửi kèm 2 ảnh]",
            images=["media/acc-1/t-anh/m1-0.jpg", "media/acc-1/t-anh/m1-1.png"],
        ),
    )
    await store.append_message(env.clinic_id, "acc-1", "t-anh", _assistant("ảnh đẹp"))

    rows = await _read_all(store, env, "acc-1", "t-anh")
    assert rows[0].images == ["media/acc-1/t-anh/m1-0.jpg", "media/acc-1/t-anh/m1-1.png"]
    assert rows[1].images == []


async def test_history_store_set_message_images_attaches_to_a_written_message_by_id(env: ClinicEnv) -> None:
    """setMessageImages gắn ảnh vào tin đã ghi qua id (passive listen tải ảnh xong muộn)"""
    store = HistoryStoreImpl(env.db)
    row_id = await store.append_message(env.clinic_id, "acc-1", "t-muon", _user("[ảnh]"))
    await store.set_message_images(env.clinic_id, row_id, ["media/acc-1/t-muon/m9-0.webp"])

    rows = await _read_all(store, env, "acc-1", "t-muon")
    assert rows[0].images == ["media/acc-1/t-muon/m9-0.webp"]


async def test_history_store_images_are_also_in_list_messages_paged(env: ClinicEnv) -> None:
    """images cũng có trong listMessagesPaged (dashboard)"""
    store = HistoryStoreImpl(env.db)
    await store.append_message(
        env.clinic_id, "acc-1", "t-paged", _user("[ảnh]", images=["media/acc-1/t-paged/m2-0.jpg"])
    )

    rows = await store.list_messages_paged(env.clinic_id, "acc-1", "t-paged")
    assert rows[0].images == ["media/acc-1/t-paged/m2-0.jpg"]


async def test_history_store_list_messages_paged_is_keyset_by_id(env: ClinicEnv) -> None:
    """(thêm) phân trang keyset theo id: trang sau lấy tin cũ hơn id đã cho, không lệch khi có tin mới chen vào"""
    store = HistoryStoreImpl(env.db)
    for i in range(1, 8):
        await store.append_message(env.clinic_id, "acc-1", "t-keyset", _user(f"tin-{i}"))

    first = await store.list_messages_paged(env.clinic_id, "acc-1", "t-keyset", limit=3)
    assert [m.content for m in first] == ["tin-5", "tin-6", "tin-7"]
    assert first[0].id is not None
    await store.append_message(env.clinic_id, "acc-1", "t-keyset", _user("tin-8"))  # arrives between pages
    second = await store.list_messages_paged(
        env.clinic_id, "acc-1", "t-keyset", limit=3, before_id=first[0].id
    )
    assert [m.content for m in second] == ["tin-2", "tin-3", "tin-4"]


async def test_history_store_rows_of_another_clinic_are_invisible(env: ClinicEnv) -> None:
    """(thêm) RLS: cùng account/thread ở phòng khám khác không thấy nhau"""
    import uuid

    store = HistoryStoreImpl(env.db)
    other = env.add_clinic(uuid.uuid4(), ("acc-1",))
    await store.append_message(env.clinic_id, "acc-1", "t-rls", _user("của phòng A"))
    await store.append_message(other, "acc-1", "t-rls", _user("của phòng B"))

    assert [m.content for m in await store.get_recent_messages(env.clinic_id, "acc-1", "t-rls", 10)] == [
        "của phòng A"
    ]
    assert [m.content for m in await store.get_recent_messages(other, "acc-1", "t-rls", 10)] == [
        "của phòng B"
    ]


# Tin đến từ Zalo được ghi ở CUỐI lượt, nên để DB tự sinh `created_at` là lấy giờ KẾT THÚC lượt - lượt 249 giây
# làm mốc lệch 4 phút so với lúc người ta bấm gửi. Mà chính mốc này là nhãn `[dd/mm hh:mm]` model đọc.


async def test_history_store_explicit_created_at_stores_exactly_that_instant(env: ClinicEnv) -> None:
    """history-store - created_at tường minh: truyền createdAt thì lưu ĐÚNG giá trị đó, không phải giờ ghi"""
    store = HistoryStoreImpl(env.db)
    sent_at = datetime(2026, 8, 7, 16, 30, tzinfo=UTC)
    await store.append_message(
        env.clinic_id,
        "acc-1",
        "t-createdat",
        StoredMessage(role="user", content="tin gửi lúc 16:30 UTC", sender_name="Hải", created_at=sent_at),
    )

    rows = await _read_all(store, env, "acc-1", "t-createdat")
    assert rows[0].created_at == sent_at


async def test_history_store_omitted_created_at_defaults_to_now(env: ClinicEnv) -> None:
    """history-store - created_at tường minh: bỏ trống createdAt thì DB tự sinh giờ hiện tại - đường cũ không đổi"""
    store = HistoryStoreImpl(env.db)
    before = datetime.now(UTC)
    await store.append_message(env.clinic_id, "acc-1", "t-createdat-mac-dinh", _user("x"))
    after = datetime.now(UTC)

    created = (await _read_all(store, env, "acc-1", "t-createdat-mac-dinh"))[0].created_at
    assert created is not None, "phải là mốc thời gian đọc được"
    # Nới 1 giây mỗi đầu: now() của Postgres và đồng hồ của test không cùng một nguồn tới từng milli.
    assert (before - created).total_seconds() < 1
    assert (created - after).total_seconds() < 1


async def test_history_store_read_order_is_by_id_not_created_at(env: ClinicEnv) -> None:
    """history-store - created_at tường minh: thứ tự đọc ra theo id, KHÔNG theo created_at - tin cũ ghi sau vẫn nằm sau"""
    # Ca thật: listener nối lại sau khi mất mạng, nhận một loạt tin cũ. Sắp xếp theo created_at sẽ trộn chúng
    # vào giữa cuộc trò chuyện đang diễn ra.
    store = HistoryStoreImpl(env.db)
    for content, at in (
        ("mới", datetime(2026, 8, 7, 16, 0, tzinfo=UTC)),
        ("cũ hơn", datetime(2026, 8, 7, 10, 0, tzinfo=UTC)),
    ):
        await store.append_message(
            env.clinic_id,
            "acc-1",
            "t-thutu-id",
            StoredMessage(role="user", content=content, created_at=at),
        )

    assert [m.content for m in await _read_all(store, env, "acc-1", "t-thutu-id")] == ["mới", "cũ hơn"]

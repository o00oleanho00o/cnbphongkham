# ported from: src/conversation/image-description-store.ts
"""``image-description-store.ts`` has no test file of its own; its behaviour is only exercised through
``wipe-thread-context.test.ts``. These tests (new, same style) pin the contract the vision sidecar relies on:
described ONCE, overwritten on re-describe, pruned on the retention rhythm, keyed per clinic.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pema.conversation.image_description_store import ImageDescriptionStoreImpl
from pema.conversation.pg_testing import ClinicEnv

pytestmark = pytest.mark.db


async def test_image_description_store_returns_none_until_the_image_is_described(env: ClinicEnv) -> None:
    """ảnh chưa mô tả thì trả null"""
    store = ImageDescriptionStoreImpl(env.db)
    assert await store.get_image_description(env.clinic_id, "media/acc-1/t-1/m-1-0.jpg") is None


async def test_image_description_store_save_then_get_and_re_describe_overwrites(env: ClinicEnv) -> None:
    """lưu rồi đọc lại; mô tả lại thì ghi đè"""
    store = ImageDescriptionStoreImpl(env.db)
    rel = "media/acc-1/t-1/m-1-0.jpg"
    await store.save_image_description(env.clinic_id, rel, "ảnh một bàn tay", "model-a")
    assert await store.get_image_description(env.clinic_id, rel) == "ảnh một bàn tay"

    await store.save_image_description(env.clinic_id, rel, "ảnh cánh tay", "model-b")
    assert await store.get_image_description(env.clinic_id, rel) == "ảnh cánh tay"
    assert (
        await env.scalar("SELECT model FROM agent.image_descriptions WHERE rel_path = :p", p=rel) == "model-b"
    )


async def test_image_description_store_prune_removes_only_descriptions_older_than_the_retention(
    env: ClinicEnv,
) -> None:
    """dọn mô tả cũ hơn N ngày, giữ mô tả còn hạn, trả về số dòng đã xóa"""
    store = ImageDescriptionStoreImpl(env.db)
    await store.save_image_description(env.clinic_id, "media/a/old.jpg", "cũ", "m")
    await store.save_image_description(env.clinic_id, "media/a/new.jpg", "mới", "m")
    await env.execute(
        "UPDATE agent.image_descriptions SET created_at = :at WHERE rel_path = 'media/a/old.jpg'",
        at=datetime.now(UTC) - timedelta(days=8),
    )

    assert await store.prune_expired_image_descriptions(env.clinic_id, 7) == 1
    assert await store.get_image_description(env.clinic_id, "media/a/old.jpg") is None
    assert await store.get_image_description(env.clinic_id, "media/a/new.jpg") == "mới"


async def test_image_description_store_delete_by_paths_removes_exactly_those_paths(env: ClinicEnv) -> None:
    """xoaMoTaAnhTheoDuongDan: xóa đúng những đường dẫn được đưa vào, danh sách rỗng là no-op"""
    store = ImageDescriptionStoreImpl(env.db)
    for name in ("a", "b", "c"):
        await store.save_image_description(env.clinic_id, f"media/x/{name}.jpg", name, "m")

    assert await store.delete_descriptions_by_paths(env.clinic_id, []) == 0
    assert await store.delete_descriptions_by_paths(env.clinic_id, ["media/x/a.jpg", "media/x/c.jpg"]) == 2
    assert await store.get_image_description(env.clinic_id, "media/x/b.jpg") == "b"

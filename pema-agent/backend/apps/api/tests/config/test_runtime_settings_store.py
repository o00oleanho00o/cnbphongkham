# ported from: none (new: the store/snapshot that replace the synchronous SQLite reads of runtime-*-settings.ts)
"""``RuntimeSettingsSnapshot`` and the stores: write-through, "nothing loaded = no override", the timer refresh
picking up a change made by ANOTHER snapshot, and the ``TuningProvider`` use. Single tenant: one set of rows,
the ones of the installation clinic."""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import pytest

from pema.config.runtime_settings_store import InMemoryRuntimeSettingsStore, RuntimeSettingsSnapshot
from pema.config.runtime_tuning_settings import (
    get_tuning,
    install_tuning_provider,
    reset_tuning_provider,
    set_tuning,
)
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi

CLINIC = uuid4()


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    yield
    reset_tuning_provider()


async def test_write_through_is_readable_at_once_without_a_refresh() -> None:
    """ghi qua snapshot thì đọc đồng bộ thấy NGAY (không chờ timer)"""
    snap = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    assert snap.read("k") is None
    await snap.set(CLINIC, "k", "v")
    assert snap.read("k") == "v"
    await snap.delete(CLINIC, "k")
    assert snap.read("k") is None


async def test_nothing_is_overridden_until_the_first_refresh() -> None:
    """chưa nạp thì KHÔNG có override (môi trường và mặc định được dùng)"""
    store = InMemoryRuntimeSettingsStore()
    await store.set(CLINIC, "k", "a")
    snap = RuntimeSettingsSnapshot(store)
    assert snap.read("k") is None
    await snap.refresh(CLINIC)
    assert snap.read("k") == "a"


async def test_refresh_loop_picks_up_a_change_made_through_another_snapshot() -> None:
    """thay đổi do tiến trình KHÁC ghi được timer kéo về"""
    store = InMemoryRuntimeSettingsStore()
    reader = RuntimeSettingsSnapshot(store)
    writer = RuntimeSettingsSnapshot(store)
    await reader.refresh(CLINIC)
    reader.start_refresh_loop(interval_s=0.01)
    try:
        await writer.set(CLINIC, "k", "from-another-process")
        await doi_cho_den_khi(
            lambda: reader.read("k") == "from-another-process",
            WaitOptions(mo_ta="refresh picks up the write"),
        )
    finally:
        await reader.stop_refresh_loop()


async def test_snapshot_is_the_tuning_provider_and_prefixes_the_key() -> None:
    """snapshot là TuningProvider: get_tuning đọc override `tuning_<KEY>`"""
    snap = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    install_tuning_provider(snap)
    assert get_tuning("LLM_MAX_STEPS") == 10
    await set_tuning(CLINIC, "LLM_MAX_STEPS", 12, snapshot=snap)
    assert get_tuning("LLM_MAX_STEPS") == 12
    assert (await snap.store.load_all(CLINIC)) == {"tuning_LLM_MAX_STEPS": "12"}


async def test_delete_many_removes_only_the_listed_keys() -> None:
    """delete_many chỉ xóa các key được nêu"""
    store = InMemoryRuntimeSettingsStore()
    snap = RuntimeSettingsSnapshot(store)
    for key in ("a", "b", "c"):
        await snap.set(CLINIC, key, key)
    await snap.delete_many(CLINIC, ["a", "c"])
    assert await store.load_all(CLINIC) == {"b": "b"}
    assert snap.read("a") is None
    assert snap.read("b") == "b"

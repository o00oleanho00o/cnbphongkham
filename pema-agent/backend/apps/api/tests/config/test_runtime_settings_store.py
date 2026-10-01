# ported from: none (new: the store/snapshot that replace the synchronous SQLite reads of runtime-*-settings.ts)
"""``RuntimeSettingsSnapshot`` and the stores: write-through, per-clinic isolation, "no clinic = no override",
the timer refresh picking up a change made by ANOTHER snapshot, and the ``TuningProvider`` use."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from uuid import uuid4

import pytest

from pema.config.runtime_settings_store import (
    InMemoryRuntimeSettingsStore,
    RuntimeSettingsSnapshot,
    current_settings_clinic,
    set_settings_clinic,
    use_settings_clinic,
)
from pema.config.runtime_tuning_settings import (
    get_tuning,
    install_tuning_provider,
    reset_tuning_provider,
    set_tuning,
)
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi

CLINIC_A = uuid4()
CLINIC_B = uuid4()


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    yield
    reset_tuning_provider()
    set_settings_clinic(None)


async def test_write_through_is_readable_at_once_without_a_refresh() -> None:
    """ghi qua snapshot thì đọc đồng bộ thấy NGAY (không chờ timer)"""
    snap = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    with use_settings_clinic(CLINIC_A):
        assert snap.read("k") is None
        await snap.set(CLINIC_A, "k", "v")
        assert snap.read("k") == "v"
        await snap.delete(CLINIC_A, "k")
        assert snap.read("k") is None


async def test_each_clinic_sees_only_its_own_values() -> None:
    """mỗi phòng khám chỉ thấy giá trị của mình"""
    snap = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    await snap.set(CLINIC_A, "k", "a")
    await snap.set(CLINIC_B, "k", "b")
    with use_settings_clinic(CLINIC_A):
        assert snap.read("k") == "a"
    with use_settings_clinic(CLINIC_B):
        assert snap.read("k") == "b"


async def test_without_a_clinic_nothing_is_overridden() -> None:
    """không có clinic thì KHÔNG có override (không bao giờ thấy giá trị của clinic khác)"""
    snap = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    await snap.set(CLINIC_A, "k", "a")
    assert current_settings_clinic() is None
    assert snap.read("k") is None


async def test_concurrent_tasks_keep_their_own_clinic() -> None:
    """hai lượt song song của hai clinic không lẫn nhau (ContextVar theo task)"""
    snap = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    await snap.set(CLINIC_A, "k", "a")
    await snap.set(CLINIC_B, "k", "b")
    seen: dict[str, str | None] = {}

    async def turn(name: str, clinic: object) -> None:
        set_settings_clinic(clinic)  # type: ignore[arg-type]
        await asyncio.sleep(0)
        seen[name] = snap.read("k")

    await asyncio.gather(turn("a", CLINIC_A), turn("b", CLINIC_B))
    assert seen == {"a": "a", "b": "b"}


async def test_refresh_loop_picks_up_a_change_made_through_another_snapshot() -> None:
    """thay đổi do tiến trình KHÁC ghi được timer kéo về"""
    store = InMemoryRuntimeSettingsStore()
    reader = RuntimeSettingsSnapshot(store)
    writer = RuntimeSettingsSnapshot(store)
    await reader.refresh(CLINIC_A)
    reader.start_refresh_loop(interval_s=0.01)
    try:
        await writer.set(CLINIC_A, "k", "from-another-process")
        with use_settings_clinic(CLINIC_A):
            await doi_cho_den_khi(
                lambda: reader.read("k") == "from-another-process",
                WaitOptions(mo_ta="refresh picks up the write"),
            )
    finally:
        await reader.stop_refresh_loop()


async def test_snapshot_is_the_tuning_provider_and_prefixes_the_key() -> None:
    """snapshot là TuningProvider: get_tuning đọc override `tuning_<KEY>` của clinic hiện tại"""
    snap = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    install_tuning_provider(snap)
    with use_settings_clinic(CLINIC_A):
        assert get_tuning("LLM_MAX_STEPS") == 10
        await set_tuning(CLINIC_A, "LLM_MAX_STEPS", 12, snapshot=snap)
        assert get_tuning("LLM_MAX_STEPS") == 12
        assert (await snap.store.load_all(CLINIC_A)) == {"tuning_LLM_MAX_STEPS": "12"}
    with use_settings_clinic(CLINIC_B):
        assert get_tuning("LLM_MAX_STEPS") == 10, "override của clinic A không lọt sang clinic B"


async def test_delete_many_removes_only_the_listed_keys() -> None:
    """delete_many chỉ xóa các key được nêu"""
    store = InMemoryRuntimeSettingsStore()
    snap = RuntimeSettingsSnapshot(store)
    for key in ("a", "b", "c"):
        await snap.set(CLINIC_A, key, key)
    await snap.delete_many(CLINIC_A, ["a", "c"])
    assert await store.load_all(CLINIC_A) == {"b": "b"}

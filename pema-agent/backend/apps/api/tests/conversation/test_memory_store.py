# ported from: src/conversation/memory-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

The original seeded three facts once in ``before``; here the ``seeded`` fixture does it per test (every test has a
fresh clinic). A concurrency test is added for the advisory lock that replaces the single-process invariant.
"""

from __future__ import annotations

import asyncio

import pytest

from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.conversation.memory_store import MemoryStoreImpl
from pema.conversation.pg_testing import ClinicEnv

pytestmark = pytest.mark.db

MAX_FACTS = 5


@pytest.fixture(autouse=True)
def _tuning() -> None:  # pyright: ignore[reportUnusedFunction]
    install_tuning_provider(StaticTuningProvider({"MEMORY_MAX_FACTS_PER_SUBJECT": MAX_FACTS}))


@pytest.fixture
async def seeded(env: ClinicEnv) -> MemoryStoreImpl:
    memory = MemoryStoreImpl(env.db)
    # Fact về user A: 1 học ở DM, 1 học ở group G1
    await memory.save_memory_fact(
        env.clinic_id,
        account_id="acc-1",
        subject_id="user-a",
        content="A lương 50 triệu (bí mật DM)",
        learned_in_thread_id="user-a",
        learned_in_group=False,
    )
    await memory.save_memory_fact(
        env.clinic_id,
        account_id="acc-1",
        subject_id="user-a",
        content="A thích đá bóng (nói trong nhóm)",
        learned_in_thread_id="group-1",
        learned_in_group=True,
    )
    # Fact về group G1
    await memory.save_memory_fact(
        env.clinic_id,
        account_id="acc-1",
        subject_id="group-1",
        content="Nhóm chốt đi Đà Lạt tháng 8",
        learned_in_thread_id="group-1",
        learned_in_group=True,
    )
    return memory


async def _contents(
    memory: MemoryStoreImpl, env: ClinicEnv, thread_id: str, sender_id: str, *, is_group: bool
) -> list[str]:
    facts = await memory.get_memories_for_context(
        env.clinic_id, account_id="acc-1", thread_id=thread_id, sender_id=sender_id, is_group=is_group
    )
    return [f.content for f in facts]


# ----------------------------------------------------------------- quy tắc inject bất đối xứng


async def test_memory_store_asymmetric_private_chat_sees_every_fact_about_the_person(
    env: ClinicEnv, seeded: MemoryStoreImpl
) -> None:
    """chat riêng với A: thấy MỌI fact về A, kể cả fact học trong nhóm"""
    contents = await _contents(seeded, env, "user-a", "user-a", is_group=False)
    assert "A lương 50 triệu (bí mật DM)" in contents
    assert "A thích đá bóng (nói trong nhóm)" in contents


async def test_memory_store_asymmetric_group_never_shows_a_fact_learned_in_private(
    env: ClinicEnv, seeded: MemoryStoreImpl
) -> None:
    """trong group, A nói: fact DM của A TUYỆT ĐỐI không xuất hiện"""
    contents = await _contents(seeded, env, "group-1", "user-a", is_group=True)
    assert not any("lương 50 triệu" in c for c in contents), "fact DM bị lộ ra group!"
    assert "A thích đá bóng (nói trong nhóm)" in contents
    assert "Nhóm chốt đi Đà Lạt tháng 8" in contents


async def test_memory_store_asymmetric_group_other_speaker_sees_only_group_facts(
    env: ClinicEnv, seeded: MemoryStoreImpl
) -> None:
    """trong group, người KHÁC nói: chỉ thấy fact của group, không thấy fact của A"""
    assert await _contents(seeded, env, "group-1", "user-b", is_group=True) == ["Nhóm chốt đi Đà Lạt tháng 8"]


async def test_memory_store_asymmetric_private_chat_with_a_stranger_is_empty(
    env: ClinicEnv, seeded: MemoryStoreImpl
) -> None:
    """chat riêng với người lạ chưa có fact: rỗng"""
    assert await _contents(seeded, env, "user-z", "user-z", is_group=False) == []


# ----------------------------------------------------------------- chặn ghi trùng khít


async def _save(memory: MemoryStoreImpl, env: ClinicEnv, content: str, subject_id: str = "user-trung"):
    return await memory.save_memory_fact(
        env.clinic_id,
        account_id="acc-1",
        subject_id=subject_id,
        content=content,
        learned_in_thread_id=subject_id,
        learned_in_group=False,
    )


async def test_memory_store_duplicate_first_write_accepted_second_identical_rejected(env: ClinicEnv) -> None:
    """ghi lần đầu thì nhận, ghi y hệt lần hai thì từ chối"""
    memory = MemoryStoreImpl(env.db)
    first = await _save(memory, env, "B thích trà sữa ít đường")
    second = await _save(memory, env, "B thích trà sữa ít đường")
    assert (first.saved, first.reason) == (True, None)
    assert (second.saved, second.reason) == (False, "duplicate")


async def test_memory_store_duplicate_rejected_write_leaves_no_second_copy(env: ClinicEnv) -> None:
    """từ chối rồi thì KHÔNG có bản thứ hai trong kho"""
    memory = MemoryStoreImpl(env.db)
    await _save(memory, env, "B nuôi một con mèo tên Mun")
    await _save(memory, env, "B nuôi một con mèo tên Mun")
    contents = await _contents(memory, env, "user-trung", "user-trung", is_group=False)
    assert contents.count("B nuôi một con mèo tên Mun") == 1


async def test_memory_store_duplicate_ignores_surrounding_whitespace(env: ClinicEnv) -> None:
    """khác khoảng trắng hai đầu vẫn là trùng - model xuống dòng thừa là chuyện thường"""
    memory = MemoryStoreImpl(env.db)
    await _save(memory, env, "B làm ca đêm")
    result = await _save(memory, env, "  B làm ca đêm\n")
    assert (result.saved, result.reason) == (False, "duplicate")


async def test_memory_store_duplicate_differing_only_in_diacritics_are_two_facts(env: ClinicEnv) -> None:
    """chỉ khác DẤU là hai điều khác nhau, phải ghi cả hai"""
    # Cố ý không hạ chữ thường / bỏ dấu khi so: "mắt" với "mất" là hai nghĩa, chặn nhầm ở đây nghĩa là bot im
    # lặng không nhớ điều người dùng vừa dặn.
    memory = MemoryStoreImpl(env.db)
    assert (await _save(memory, env, "B hay đau mắt")).saved is True
    assert (await _save(memory, env, "B hay đau mất")).saved is True


async def test_memory_store_duplicate_same_content_for_another_subject_is_still_saved(env: ClinicEnv) -> None:
    """cùng nội dung nhưng KHÁC người thì vẫn ghi - trùng xét theo từng subject"""
    memory = MemoryStoreImpl(env.db)
    assert (await _save(memory, env, "Thích ăn cay", "user-trung-1")).saved is True
    assert (await _save(memory, env, "Thích ăn cay", "user-trung-2")).saved is True


async def test_memory_store_duplicate_concurrent_identical_saves_store_exactly_one(env: ClinicEnv) -> None:
    """(thêm) hai worker ghi CÙNG một fact đồng thời: khóa advisory chặn cả hai cùng qua cửa kiểm trùng"""
    memory = MemoryStoreImpl(env.db)
    results = await asyncio.gather(*[_save(memory, env, "C dị ứng tôm") for _ in range(4)])
    assert sorted(r.saved for r in results) == [False, False, False, True]
    assert (await _contents(memory, env, "user-trung", "user-trung", is_group=False)).count(
        "C dị ứng tôm"
    ) == 1


# ----------------------------------------------------------------- cap và xóa


async def test_memory_store_cap_oldest_fact_is_replaced_when_over_the_cap(env: ClinicEnv) -> None:
    """vượt cap thì fact cũ nhất bị thay"""
    memory = MemoryStoreImpl(env.db)
    for i in range(1, MAX_FACTS + 4):
        await memory.save_memory_fact(
            env.clinic_id,
            account_id="acc-1",
            subject_id="user-cap",
            content=f"fact-{i}",
            learned_in_thread_id="user-cap",
            learned_in_group=False,
        )
    contents = await _contents(memory, env, "user-cap", "user-cap", is_group=False)
    assert len(contents) == MAX_FACTS
    assert contents[0] == "fact-4"  # 1..3 bị xóa


async def test_memory_store_delete_fact_through_the_dashboard(
    env: ClinicEnv, seeded: MemoryStoreImpl
) -> None:
    """xóa fact qua dashboard"""
    listed = await seeded.list_memories(env.clinic_id, account_id="acc-1", query="Đà Lạt")
    assert len(listed) == 1
    assert await seeded.delete_memory_fact(env.clinic_id, "acc-1", listed[0].id) is True
    assert len(await seeded.list_memories(env.clinic_id, account_id="acc-1", query="Đà Lạt")) == 0


async def test_memory_store_delete_fact_of_another_account_is_refused(env: ClinicEnv) -> None:
    """xóa fact của account khác không được"""
    memory = MemoryStoreImpl(env.db)
    assert await memory.delete_memory_fact(env.clinic_id, "acc-khac", 99999) is False


async def test_memory_store_delete_cannot_remove_a_fact_through_the_wrong_account(
    env: ClinicEnv, seeded: MemoryStoreImpl
) -> None:
    """(thêm) id đúng nhưng account sai thì fact còn nguyên"""
    fact = (await seeded.list_memories(env.clinic_id, account_id="acc-1", query="Đà Lạt"))[0]
    assert await seeded.delete_memory_fact(env.clinic_id, "acc-2", fact.id) is False
    assert len(await seeded.list_memories(env.clinic_id, account_id="acc-1", query="Đà Lạt")) == 1

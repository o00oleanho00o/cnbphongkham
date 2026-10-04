# ported from: src/conversation/memory-edit-store.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Focus (as in the original): two things that break silently, (1) matching the wrong subject, (2) the asymmetric
privacy rule: in a group the facts learned in a private chat must not be editable AND must not be visible (a
clinic safety property too: what a patient said in a private chat must not surface in a group).
"""

from __future__ import annotations

import pytest

from pema.conversation.memory_edit_store import FactEditResult, FactEditScope, MemoryEditStoreImpl
from pema.conversation.memory_store import MemoryStoreImpl
from pema.conversation.pg_testing import ClinicEnv

pytestmark = pytest.mark.db

ACC = "acc-1"
NGUOI = "u-hai"
NHOM = "g-gia-dinh"

# Phạm vi khi đang chat RIÊNG với người đó - thấy hết điều nhớ về họ.
PRIVATE_SCOPE = FactEditScope(account_id=ACC, subject_id=NGUOI, only_group_facts=False)
# Phạm vi khi đang ở NHÓM và nói về người đó - chỉ điều học trong nhóm.
GROUP_SCOPE = FactEditScope(account_id=ACC, subject_id=NGUOI, only_group_facts=True)


async def _remember(env: ClinicEnv, subject_id: str, content: str, *, in_group: bool) -> None:
    await MemoryStoreImpl(env.db).save_memory_fact(
        env.clinic_id,
        account_id=ACC,
        subject_id=subject_id,
        content=content,
        learned_in_thread_id=NHOM if in_group else NGUOI,
        learned_in_group=in_group,
    )


async def _remembered(env: ClinicEnv, subject_id: str) -> list[str]:
    rows = await env.fetch(
        "SELECT content FROM agent.memories WHERE account_id = :a AND subject_id = :s ORDER BY id",
        a=ACC,
        s=subject_id,
    )
    return [r["content"] for r in rows]


def _existing(result: FactEditResult) -> list[str] | None:
    return result.existing_facts if result.kind == "no_match" else None


# ----------------------------------------------------------------- sửa điều đã nhớ


async def test_memory_edit_store_edit_matches_a_snippet_then_replaces_the_content(env: ClinicEnv) -> None:
    """khớp đoạn chữ rồi thay nội dung"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải đang ở Thành phố Hồ Chí Minh", in_group=False)
    result = await edits.edit_fact_by_snippet(
        env.clinic_id, PRIVATE_SCOPE, "Hồ Chí Minh", "Hải đã chuyển ra Hà Nội"
    )
    assert result.ok is True
    assert await _remembered(env, NGUOI) == ["Hải đã chuyển ra Hà Nội"]


async def test_memory_edit_store_edit_match_is_case_insensitive(env: ClinicEnv) -> None:
    """khớp KHÔNG phân biệt hoa thường"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải thích Cà Phê Đen", in_group=False)
    result = await edits.edit_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "cà phê đen", "Hải bỏ cà phê rồi")
    assert result.ok is True


async def test_memory_edit_store_edit_no_match_returns_the_current_facts_and_changes_nothing(
    env: ClinicEnv,
) -> None:
    """không khớp thì trả về danh sách đang nhớ, KHÔNG sửa bừa"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải thích cà phê đen", in_group=False)
    result = await edits.edit_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "trà sữa", "gì đó")
    assert result.ok is False
    assert result.kind == "no_match"
    assert _existing(result) == ["Hải thích cà phê đen"]
    assert await _remembered(env, NGUOI) == ["Hải thích cà phê đen"], "không được đụng gì"


async def test_memory_edit_store_edit_ambiguous_match_of_different_facts_is_refused(env: ClinicEnv) -> None:
    """khớp NHIỀU điều khác nhau thì từ chối, không đoán bừa"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải thích cà phê đen", in_group=False)
    await _remember(env, NGUOI, "Hải ghét cà phê sữa", in_group=False)
    result = await edits.edit_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "cà phê", "gì đó")
    assert result.ok is False
    assert result.kind == "ambiguous"
    assert len(await _remembered(env, NGUOI)) == 2, "không được sửa cái nào"


async def test_memory_edit_store_edit_ambiguous_match_of_identical_facts_acts_on_the_first(
    env: ClinicEnv,
) -> None:
    """khớp nhiều điều TRÙNG KHÍT thì làm trên cái đầu - học từ Hermes"""
    # Hermes: ``if len(unique_texts) > 1`` mới báo lỗi. Trùng khít thì không có gì để chọn nhầm, từ chối chỉ làm
    # model kẹt. Dựng hai bản trùng khít qua chính đường CÒN HỞ: ``save_memory_fact`` đã chặn ghi trùng, nhưng
    # sửa điều này thành giống hệt điều kia vẫn lọt, nên nhánh này chưa phải code chết.
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải thích cà phê đen", in_group=False)
    await _remember(env, NGUOI, "Hải thích trà sữa", in_group=False)
    await edits.edit_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "trà sữa", "Hải thích cà phê đen")
    assert await _remembered(env, NGUOI) == ["Hải thích cà phê đen", "Hải thích cà phê đen"], (
        "đường `sua` vẫn tạo ra được hai bản trùng khít"
    )

    result = await edits.edit_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "cà phê đen", "Hải thích trà")
    assert result.ok is True
    assert await _remembered(env, NGUOI) == ["Hải thích trà", "Hải thích cà phê đen"]


# ----------------------------------------------------------------- xóa điều đã nhớ


async def test_memory_edit_store_delete_removes_the_matching_fact_and_keeps_the_rest(env: ClinicEnv) -> None:
    """xóa đúng điều khớp, giữ nguyên phần còn lại"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải đang bị ốm", in_group=False)
    await _remember(env, NGUOI, "Hải thích cà phê đen", in_group=False)
    result = await edits.delete_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "bị ốm")
    assert result.ok is True
    assert result.old_content == "Hải đang bị ốm"
    assert await _remembered(env, NGUOI) == ["Hải thích cà phê đen"]


async def test_memory_edit_store_delete_with_nothing_remembered_reports_clearly_without_raising(
    env: ClinicEnv,
) -> None:
    """chưa nhớ gì thì báo rõ, không ném lỗi"""
    edits = MemoryEditStoreImpl(env.db)
    result = await edits.delete_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "bất kỳ")
    assert result.ok is False
    assert _existing(result) == []


# ----------------------------------------------------------------- luật riêng-tư bất đối xứng khi sửa/xóa


async def test_memory_edit_store_privacy_group_cannot_edit_a_fact_learned_in_private(env: ClinicEnv) -> None:
    """trong NHÓM không sửa được điều học ở chat riêng"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải đang vay tiền ngân hàng", in_group=False)  # học ở chat riêng
    result = await edits.edit_fact_by_snippet(env.clinic_id, GROUP_SCOPE, "vay tiền", "gì đó")
    assert result.ok is False, "trong nhóm mà sửa được chuyện riêng là hỏng"
    assert await _remembered(env, NGUOI) == ["Hải đang vay tiền ngân hàng"]


async def test_memory_edit_store_privacy_group_cannot_delete_a_fact_learned_in_private(
    env: ClinicEnv,
) -> None:
    """trong NHÓM không XÓA được điều học ở chat riêng"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải đang vay tiền ngân hàng", in_group=False)
    result = await edits.delete_fact_by_snippet(env.clinic_id, GROUP_SCOPE, "vay tiền")
    assert result.ok is False
    assert await _remembered(env, NGUOI) == ["Hải đang vay tiền ngân hàng"], "không được mất"


async def test_memory_edit_store_privacy_error_message_in_a_group_does_not_leak_private_facts(
    env: ClinicEnv,
) -> None:
    """câu báo lỗi trong NHÓM KHÔNG được rò điều học ở chat riêng"""
    # Lỗ tinh vi nhất: chặn sửa rồi nhưng danh sách "đang nhớ" trong câu báo lỗi lại liệt kê cả chuyện riêng, và
    # câu đó đi thẳng vào ngữ cảnh của model đang đứng giữa nhóm.
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải đang vay tiền ngân hàng", in_group=False)  # riêng tư
    await _remember(env, NGUOI, "Hải hay đi họp lớp", in_group=True)  # học trong nhóm
    result = await edits.edit_fact_by_snippet(env.clinic_id, GROUP_SCOPE, "không có gì khớp", "gì đó")
    assert result.ok is False
    listed = _existing(result) or []
    assert listed == ["Hải hay đi họp lớp"]
    assert "vay tiền" not in " ".join(listed), "RÒ chuyện riêng ra nhóm"


async def test_memory_edit_store_privacy_group_can_still_edit_a_fact_learned_in_the_group(
    env: ClinicEnv,
) -> None:
    """trong nhóm VẪN sửa được điều học ngay trong nhóm"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải hay đi họp lớp", in_group=True)
    result = await edits.edit_fact_by_snippet(
        env.clinic_id, GROUP_SCOPE, "họp lớp", "Hải hay đi họp lớp hàng tháng"
    )
    assert result.ok is True
    assert await _remembered(env, NGUOI) == ["Hải hay đi họp lớp hàng tháng"]


# ----------------------------------------------------------------- không đụng sang đối tượng khác


async def test_memory_edit_store_isolation_editing_one_person_leaves_another_untouched(
    env: ClinicEnv,
) -> None:
    """sửa điều của người này không chạm điều của người kia"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải thích cà phê đen", in_group=False)
    await _remember(env, "u-nam", "Nam thích cà phê đen", in_group=False)
    result = await edits.edit_fact_by_snippet(env.clinic_id, PRIVATE_SCOPE, "cà phê đen", "Hải thích trà")
    assert result.ok is True
    assert await _remembered(env, NGUOI) == ["Hải thích trà"]
    assert await _remembered(env, "u-nam") == ["Nam thích cà phê đen"], "người khác phải nguyên vẹn"


async def test_memory_edit_store_isolation_different_accounts_do_not_see_each_other(env: ClinicEnv) -> None:
    """khác account thì không thấy nhau"""
    edits = MemoryEditStoreImpl(env.db)
    await _remember(env, NGUOI, "Hải thích cà phê đen", in_group=False)
    result = await edits.delete_fact_by_snippet(
        env.clinic_id,
        FactEditScope(account_id="acc-khac", subject_id=NGUOI, only_group_facts=False),
        "cà phê đen",
    )
    assert result.ok is False
    assert await _remembered(env, NGUOI) == ["Hải thích cà phê đen"]

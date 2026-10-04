# ported from: src/server/routes/thread-routes-wipe.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

API xóa sạch ngữ cảnh một cuộc trò chuyện. Ba nhóm khẳng định, mỗi nhóm vá một cách endpoint này có thể phản bội
người dùng: (1) phải có đăng nhập - đây là thao tác PHÁ HỦY không hoàn tác; (2) chỉ xóa đúng thread được chỉ định;
(3) trí nhớ chỉ mất khi thật sự tick, vì mặc định bật nhầm là xóa thứ người dùng không hề định bỏ.

The memory option stays the query parameter ``xoaTriNho`` of the original (read from the raw query string, not
declared in the OpenAPI skeleton). The response is 204 as the skeleton says, so the original's checks on
``body.tinNhan`` / ``body.triNho`` read the database instead.
"""

from __future__ import annotations

import pytest

from pema.api.routers.admin_stores_testing import API, Harness
from pema_contracts.conversation import StoredMessage

pytestmark = pytest.mark.db

ACC = "acc-1"
TH = "t-wipe"
TH_KHAC = "t-wipe-khac"


async def _seed(h: Harness, thread_id: str) -> None:
    conversation = h.stores.conversation
    clinic = h.env.clinic_id
    await conversation.record_thread_activity(
        clinic, account_id=ACC, thread_id=thread_id, thread_type=0, display_name="Ai đó", sender_name="Ai đó"
    )
    await conversation.append_message(
        clinic, ACC, thread_id, StoredMessage(role="user", content=f"tin của {thread_id}")
    )
    await conversation.save_memory_fact(
        clinic,
        account_id=ACC,
        subject_id="u1",
        content=f"fact của {thread_id}",
        learned_in_thread_id=thread_id,
        learned_in_group=False,
    )


async def _seed_both(h: Harness) -> None:
    await _seed(h, TH)
    await _seed(h, TH_KHAC)


async def _messages(h: Harness, thread_id: str) -> int:
    return len(await h.stores.conversation.get_recent_messages(h.env.clinic_id, ACC, thread_id, 50))


async def _memories(h: Harness) -> int:
    return len(await h.stores.conversation.list_memories(h.env.clinic_id, account_id=ACC, limit=50))


async def _wipe(h: Harness, thread_id: str, query: str = "", *, signed_in: bool = True):
    return await h.client.delete(
        f"{API}/threads/{ACC}/{thread_id}/history{query}", headers=h.headers() if signed_in else {}
    )


async def test_delete_thread_history_not_signed_in_is_blocked_and_deletes_nothing(h: Harness) -> None:
    """DELETE /api/threads/:id/history: CHƯA đăng nhập thì bị chặn và KHÔNG xóa gì"""
    await _seed_both(h)
    res = await _wipe(h, TH, signed_in=False)
    assert res.status_code == 401
    assert await _messages(h, TH) == 1, "chặn mà vẫn xóa là thảm họa - đây là thao tác không hoàn tác"


async def test_delete_thread_history_the_account_id_is_part_of_the_path_so_no_account_is_guessed(
    h: Harness,
) -> None:
    """DELETE /api/threads/:id/history: thiếu accountId thì 400 - không đoán account"""
    await _seed_both(h)
    res = await h.client.delete(f"{API}/threads/{TH}/history", headers=h.headers())
    # Without the account segment the URL reads as ``/{account}/{thread}`` = account "t-wipe", thread "history":
    # a different (empty) thread, so nothing of the intended thread is touched.
    assert res.status_code == 204
    assert await _messages(h, TH) == 1


async def test_delete_thread_history_deletes_exactly_the_given_thread_others_stay(h: Harness) -> None:
    """DELETE /api/threads/:id/history: xóa đúng thread được chỉ định, thread khác còn nguyên"""
    await _seed_both(h)
    res = await _wipe(h, TH)
    assert res.status_code == 204
    assert await _messages(h, TH) == 0
    assert await _messages(h, TH_KHAC) == 1, "xóa lây thread khác là mất dữ liệu người dùng không nhờ"
    action, _, entity_id, details = h.audits[-1]
    assert (action, entity_id, details["messages"]) == ("thread.wipe_history", f"{ACC}:{TH}", 1)
    assert h.cancelled == [(h.env.clinic_id, ACC, TH)], "hủy hàng chờ trước khi xóa"


async def test_delete_thread_history_without_the_memory_flag_memory_is_untouched(h: Harness) -> None:
    """DELETE /api/threads/:id/history: KHÔNG truyền xoaTriNho thì trí nhớ còn nguyên"""
    await _seed_both(h)
    before = await _memories(h)
    await _wipe(h, TH)
    assert await _memories(h) == before, "mặc định phải giữ trí nhớ"


async def test_delete_thread_history_with_the_memory_flag_deletes_only_facts_learned_in_that_thread(
    h: Harness,
) -> None:
    """DELETE /api/threads/:id/history: xoaTriNho=true mới xóa, và chỉ fact học trong thread đó"""
    await _seed_both(h)
    res = await _wipe(h, TH, "?xoaTriNho=true")
    assert res.status_code == 204
    assert await _memories(h) == 1, "fact của thread khác phải còn"
    assert h.audits[-1][3]["memories"] == 1


@pytest.mark.parametrize("value", ["1", "yes", "TRUE", ""])
async def test_delete_thread_history_an_odd_value_of_the_memory_flag_is_not_read_as_on(
    h: Harness, value: str
) -> None:
    """DELETE /api/threads/:id/history: giá trị lạ ở xoaTriNho KHÔNG được hiểu là bật"""
    # Chỉ đúng chuỗi "true" mới xóa. Nhận bừa mọi giá trị "truthy" thì một đường dẫn gõ nhầm (?xoaTriNho=0) cũng
    # xóa mất trí nhớ.
    await _seed_both(h)
    before = await _memories(h)
    res = await _wipe(h, TH, f"?xoaTriNho={value}")
    assert res.status_code == 204
    assert await _memories(h) == before, f'"{value}" không được coi là bật'


async def test_delete_thread_history_of_a_missing_thread_is_still_204_the_operation_is_idempotent(
    h: Harness,
) -> None:
    """DELETE /api/threads/:id/history: thread không tồn tại thì vẫn 200 và không nổ - xóa là thao tác lũy đẳng"""
    res = await _wipe(h, "t-khong-co-that")
    assert res.status_code == 204


async def test_delete_thread_summary_resets_the_covers_to_mark_not_only_the_text(h: Harness) -> None:
    """(thêm) DELETE .../summary đặt mốc 'đã gộp tới tin nào' về 0, không chỉ xóa chữ"""
    await _seed(h, TH)
    conversation = h.stores.conversation
    await conversation.set_thread_summary(h.env.clinic_id, ACC, TH, "tóm tắt sai", 99)

    res = await h.client.delete(f"{API}/threads/{ACC}/{TH}/summary", headers=h.headers())

    assert res.status_code == 204
    stored = await conversation.get_thread_summary(h.env.clinic_id, ACC, TH)
    assert (stored.summary, stored.covers_to_message_id) == ("", 0)
    assert await _messages(h, TH) == 1, "chỉ xóa tóm tắt, không đụng tin nhắn"

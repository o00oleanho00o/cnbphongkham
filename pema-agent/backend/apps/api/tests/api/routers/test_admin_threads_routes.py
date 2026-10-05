# ported from: src/server/routes/thread-routes.ts
"""``thread-routes.ts``, ``contact-routes.ts`` and ``memory-routes.ts`` have no route test of their own in the
original beyond the two ported files (wipe, delete session/contact). These tests (new) cover the read side and the
remaining mutations of the same routes: listing and search, keyset paging, rename / bot switch, memories."""

from __future__ import annotations

import pytest

from pema.api.routers.admin_stores_testing import API, Harness
from pema_contracts.conversation import StoredMessage

pytestmark = pytest.mark.db

ACC = "acc-1"


async def _seed_thread(h: Harness, thread_id: str, name: str, messages: int = 0) -> None:
    conversation = h.stores.conversation
    await conversation.record_thread_activity(
        h.env.clinic_id,
        account_id=ACC,
        thread_id=thread_id,
        thread_type=0,
        display_name=name,
        sender_name="A",
    )
    for i in range(messages):
        await conversation.append_message(
            h.env.clinic_id, ACC, thread_id, StoredMessage(role="user", content=f"tin-{i + 1}")
        )


async def test_threads_list_filters_by_account_and_search_text(h: Harness) -> None:
    """GET /threads: lọc theo account và theo chữ tìm"""
    await _seed_thread(h, "t-a", "Bệnh nhân A")
    await _seed_thread(h, "t-b", "Bệnh nhân B")
    res = await h.client.get(f"{API}/threads", params={"account_id": ACC, "q": "nhân B"}, headers=h.headers())
    assert res.status_code == 200
    assert [t["thread_id"] for t in res.json()] == ["t-b"]
    assert res.json()[0]["last_message_at"].endswith("+07:00")


async def test_threads_list_pages_with_limit_and_offset(h: Harness) -> None:
    """GET /threads: phân trang bằng limit/offset"""
    for i in range(3):
        await _seed_thread(h, f"t-{i}", f"Thread {i}")
    first = (await h.client.get(f"{API}/threads", params={"limit": 2}, headers=h.headers())).json()
    second = (
        await h.client.get(f"{API}/threads", params={"limit": 2, "offset": 2}, headers=h.headers())
    ).json()
    assert len(first) == 2
    assert len(second) == 1


async def test_thread_messages_are_keyset_paged_oldest_first_within_a_page(h: Harness) -> None:
    """GET /threads/{a}/{t}/messages: keyset theo id, mỗi trang theo thứ tự cũ -> mới"""
    await _seed_thread(h, "t-page", "Thread", messages=5)
    page = (
        await h.client.get(f"{API}/threads/{ACC}/t-page/messages", params={"limit": 2}, headers=h.headers())
    ).json()
    assert [m["content"] for m in page] == ["tin-4", "tin-5"]
    older = (
        await h.client.get(
            f"{API}/threads/{ACC}/t-page/messages",
            params={"limit": 2, "before_id": page[0]["id"]},
            headers=h.headers(),
        )
    ).json()
    assert [m["content"] for m in older] == ["tin-2", "tin-3"]
    assert older[0]["created_at"].endswith("+07:00")


async def test_thread_patch_switches_the_bot_and_renames(h: Harness) -> None:
    """PATCH /threads/{a}/{t}: bật/tắt bot và đổi tên"""
    await _seed_thread(h, "t-patch", "Tên cũ")
    res = await h.client.patch(
        f"{API}/threads/{ACC}/t-patch",
        json={"bot_enabled": False, "display_name": "Tên mới"},
        headers=h.headers(),
    )
    assert res.status_code == 200
    assert (res.json()["bot_enabled"], res.json()["display_name"]) == (False, "Tên mới")
    assert await h.stores.conversation.is_bot_enabled(h.env.clinic_id, ACC, "t-patch") is False
    assert h.audits[-1][:3] == ("thread.update", "thread", f"{ACC}:t-patch")


async def test_thread_patch_of_a_missing_thread_is_404(h: Harness) -> None:
    """PATCH /threads/{a}/{t}: thread không tồn tại thì 404"""
    res = await h.client.patch(
        f"{API}/threads/{ACC}/khong-co", json={"bot_enabled": False}, headers=h.headers()
    )
    assert res.status_code == 404


async def test_contacts_list_and_search(h: Harness) -> None:
    """GET /contacts: danh sách + tìm theo tên"""
    await h.stores.conversation.record_contact_activity(h.env.clinic_id, ACC, "u-1", "Nguyễn Văn Tìm")
    await h.stores.conversation.record_contact_activity(h.env.clinic_id, ACC, "u-2", "Trần Thị Mai")
    res = await h.client.get(f"{API}/contacts", params={"q": "Văn Tìm"}, headers=h.headers())
    assert [c["user_id"] for c in res.json()] == ["u-1"]


async def _remember(h: Harness, subject: str, content: str) -> None:
    await h.stores.conversation.save_memory_fact(
        h.env.clinic_id,
        account_id=ACC,
        subject_id=subject,
        content=content,
        learned_in_thread_id=subject,
        learned_in_group=False,
    )


async def test_memories_list_search_and_delete(h: Harness) -> None:
    """GET/DELETE /memories: xem, tìm và xóa fact; xóa fact không có thì 404"""
    await _remember(h, "u-1", "Dị ứng thuốc tê (hư cấu)")
    await _remember(h, "u-2", "Thích gọi buổi sáng")
    listed = (await h.client.get(f"{API}/memories", params={"q": "thuốc tê"}, headers=h.headers())).json()
    assert [f["content"] for f in listed] == ["Dị ứng thuốc tê (hư cấu)"]
    assert listed[0]["created_at"].endswith("+07:00")

    deleted = await h.client.delete(f"{API}/memories/{ACC}/{listed[0]['id']}", headers=h.headers())
    assert deleted.status_code == 204
    assert h.audits[-1][0] == "memory.delete"
    again = await h.client.delete(f"{API}/memories/{ACC}/{listed[0]['id']}", headers=h.headers())
    assert again.status_code == 404
    assert len((await h.client.get(f"{API}/memories", headers=h.headers())).json()) == 1


async def test_thread_data_routes_need_a_session_and_the_admin_agents_permission(h: Harness) -> None:
    """(thêm) tin nhắn và trí nhớ là dữ liệu bệnh nhân: không đăng nhập 401, thiếu quyền 403 (cả route chỉ đọc)"""
    await _seed_thread(h, "t-secret", "Bệnh nhân", messages=1)
    for path in ("/threads", f"/threads/{ACC}/t-secret/messages", "/contacts", "/memories"):
        assert (await h.client.get(f"{API}{path}")).status_code == 401, path
        assert (await h.client.get(f"{API}{path}", headers=h.headers("crm.task.read"))).status_code == 403, (
            path
        )

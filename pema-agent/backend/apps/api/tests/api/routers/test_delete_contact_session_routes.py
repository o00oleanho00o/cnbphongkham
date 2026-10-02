# ported from: src/server/routes/delete-contact-session-routes.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

Hai endpoint XÓA (session, contact) đều KHÔNG hoàn tác. Ba nhóm khẳng định vá ba cách chúng có thể phản bội người
dùng: (1) phải đăng nhập; (2) phải có accountId, không đoán account; (3) xóa đúng phạm vi, không lây sang account
khác.

(1) is played by the fake auth middleware of ``conftest.py`` (no clinic on the request = not signed in; the real
session is package B1's); a missing ``admin.agents`` permission is a 403 and is new. (2) is structural: the account
id is a PATH segment (``/{account_id}/{user_id}``), so it cannot be forgotten: a request without it is a different
route and is 404/405. The responses are 204 as in the OpenAPI skeleton instead of ``{ok, tinNhan}``.
"""

from __future__ import annotations

import pytest

from pema.api.routers.admin_stores_testing import API, Harness
from pema.conversation.pg_testing import ClinicEnv
from pema_contracts.conversation import StoredMessage

pytestmark = pytest.mark.db

ACC = "acc-1"
TH = "1234567890123456789"  # chat riêng: userId == threadId


async def _seed(h: Harness, thread_id: str = TH) -> None:
    conversation = h.stores.conversation
    clinic = h.env.clinic_id
    await conversation.record_thread_activity(
        clinic,
        account_id=ACC,
        thread_id=thread_id,
        thread_type=0,
        display_name="Bệnh nhân A",
        sender_name="A",
    )
    await conversation.append_message(clinic, ACC, thread_id, StoredMessage(role="user", content="tin"))
    await conversation.record_contact_activity(clinic, ACC, thread_id, "Bệnh nhân A")


async def _threads(env: ClinicEnv, thread_id: str) -> int:
    return int(await env.scalar("SELECT COUNT(*) FROM agent.threads WHERE thread_id = :t", t=thread_id))


async def _messages(env: ClinicEnv, thread_id: str) -> int:
    return int(await env.scalar("SELECT COUNT(*) FROM agent.history WHERE thread_id = :t", t=thread_id))


async def _contacts(env: ClinicEnv, user_id: str) -> int:
    return int(await env.scalar("SELECT COUNT(*) FROM agent.contacts WHERE user_id = :u", u=user_id))


# ----------------------------------------------------------------- DELETE /admin/threads/{account}/{thread}


async def test_delete_thread_session_not_signed_in_is_401_and_deletes_nothing(h: Harness) -> None:
    """DELETE /api/threads/:id (xóa hẳn session): CHƯA đăng nhập thì 401 và KHÔNG xóa gì"""
    await _seed(h)
    res = await h.client.delete(f"{API}/threads/{ACC}/{TH}")
    assert res.status_code == 401
    assert await _threads(h.env, TH) == 1, "chặn mà vẫn xóa là thảm họa"


async def test_delete_thread_session_without_the_permission_is_403_and_deletes_nothing(h: Harness) -> None:
    """(thêm) đăng nhập nhưng thiếu quyền admin.agents thì 403 và KHÔNG xóa gì"""
    await _seed(h)
    res = await h.client.delete(f"{API}/threads/{ACC}/{TH}", headers=h.headers("patient.read"))
    assert res.status_code == 403
    assert await _threads(h.env, TH) == 1


async def test_delete_thread_session_without_stores_wired_is_501_not_a_silent_success(h: Harness) -> None:
    """(thêm) chưa nối store (chưa qua composition root) thì 501, không giả vờ thành công"""
    h.app.state.admin_stores = None
    res = await h.client.delete(f"{API}/threads/{ACC}/{TH}", headers=h.headers())
    assert res.status_code == 501


async def test_delete_thread_session_deletes_the_row_and_messages_but_keeps_the_contact(h: Harness) -> None:
    """DELETE /api/threads/:id (xóa hẳn session): xóa dòng session + tin, GIỮ danh bạ"""
    await _seed(h)
    res = await h.client.delete(f"{API}/threads/{ACC}/{TH}", headers=h.headers())
    assert res.status_code == 204
    assert await _threads(h.env, TH) == 0, "session phải biến mất"
    assert await _messages(h.env, TH) == 0
    assert await _contacts(h.env, TH) == 1, "danh bạ phải giữ - Phương án A"


async def test_delete_thread_session_cancels_the_pending_batch_before_deleting_and_audits_it(
    h: Harness,
) -> None:
    """(thêm) hủy hàng chờ TRƯỚC khi xóa (một batch đang đỗ chạy xen vào sẽ dựng lại session vừa xóa) và ghi audit"""
    await _seed(h)
    await h.client.delete(f"{API}/threads/{ACC}/{TH}", headers=h.headers())
    assert h.cancelled == [(h.env.clinic_id, ACC, TH)]
    action, entity_type, entity_id, details = h.audits[-1]
    assert (action, entity_type, entity_id) == ("thread.delete", "thread", f"{ACC}:{TH}")
    assert details["pending_cancelled"] == 2
    assert "tin" not in str(details), "audit chỉ chứa id và số đếm, không chứa nội dung tin"


# ----------------------------------------------------------------- DELETE /admin/contacts/{account}/{user}


async def test_delete_contact_not_signed_in_is_401_and_deletes_nothing(h: Harness) -> None:
    """DELETE /api/contacts/:userId (xóa danh bạ): CHƯA đăng nhập thì 401 và KHÔNG xóa gì"""
    await _seed(h)
    res = await h.client.delete(f"{API}/contacts/{ACC}/{TH}")
    assert res.status_code == 401
    assert await _contacts(h.env, TH) == 1


async def test_delete_contact_the_account_id_is_part_of_the_path_so_it_cannot_be_omitted(h: Harness) -> None:
    """DELETE /api/contacts/:userId (xóa danh bạ): thiếu accountId thì 400 - ở đây nó nằm trong đường dẫn nên không thể thiếu"""
    await _seed(h)
    res = await h.client.delete(f"{API}/contacts/{TH}", headers=h.headers())
    assert res.status_code in (404, 405)
    assert await _contacts(h.env, TH) == 1


async def test_delete_contact_keeps_the_messages_and_the_session(h: Harness) -> None:
    """DELETE /api/contacts/:userId (xóa danh bạ): xóa danh bạ nhưng GIỮ tin nhắn (chỉ xóa dòng contact)"""
    await _seed(h)
    res = await h.client.delete(f"{API}/contacts/{ACC}/{TH}", headers=h.headers())
    assert res.status_code == 204
    assert await _contacts(h.env, TH) == 0, "danh bạ phải mất"
    assert await _messages(h.env, TH) == 1, "tin nhắn phải còn - contact-delete không đụng lịch sử"
    assert await _threads(h.env, TH) == 1, "session cũng còn"


async def test_delete_contact_of_a_missing_contact_is_not_an_error(h: Harness) -> None:
    """(thêm) xóa danh bạ không có thì vẫn 204 và không ghi audit (nguyên bản trả {ok:false})"""
    res = await h.client.delete(f"{API}/contacts/{ACC}/khong-co", headers=h.headers())
    assert res.status_code == 204
    assert h.audits == []

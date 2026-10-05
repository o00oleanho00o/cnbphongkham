# ported from: src/conversation/xoa-han-session.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

XÓA HẲN session khác RESET: nó bỏ luôn dòng ``threads``. Vẫn phải giữ đúng thứ người dùng chốt (Phương án A):
danh bạ và sổ token ở lại, chỉ session + tin + lịch hẹn của thread đó ra đi. Hai kiểu sai đều tệ ngược nhau (sót
bảng / xóa quá tay sang account khác), nên mỗi test dựng sẵn một account thứ hai và khẳng định nó còn nguyên.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pema.conversation.contact_store import ContactStoreImpl
from pema.conversation.history_store import HistoryStoreImpl
from pema.conversation.image_description_store import ImageDescriptionStoreImpl
from pema.conversation.media_store import MediaStore
from pema.conversation.pg_testing import ClinicEnv
from pema.conversation.thread_store import ThreadStoreImpl
from pema.conversation.usage_store import UsageStoreImpl
from pema.conversation.wipe_thread_context import ThreadContextWiper
from pema.conversation.xoa_han_session import delete_thread_session
from pema_contracts.agent_turn import TokenUsage
from pema_contracts.conversation import StoredMessage

pytestmark = pytest.mark.db

ACC = "acc-1"
ACC_KHAC = "acc-2"
TH = "thread-1"
TH_KHAC = "thread-2"


class Rig:
    def __init__(self, env: ClinicEnv, media_root: Path) -> None:
        self.env = env
        self.wiper = ThreadContextWiper(env.db, MediaStore(media_root), ImageDescriptionStoreImpl(env.db))
        self._job = 0

    async def seed(self, account_id: str, thread_id: str) -> None:
        """Dựng một thread đủ: dòng session, tin nhắn, sổ token, danh bạ, lịch hẹn."""
        clinic = self.env.clinic_id
        await ThreadStoreImpl(self.env.db).record_thread_activity(
            clinic,
            account_id=account_id,
            thread_id=thread_id,
            thread_type=0,
            display_name=f"Tên {thread_id}",
            sender_name="Người dùng",
        )
        history = HistoryStoreImpl(self.env.db)
        await history.append_message(
            clinic, account_id, thread_id, StoredMessage(role="user", content="tin người dùng")
        )
        await history.append_message(
            clinic, account_id, thread_id, StoredMessage(role="assistant", content="bot trả lời")
        )
        await ContactStoreImpl(self.env.db).record_contact_activity(
            clinic, account_id, thread_id, "Người dùng"
        )  # chat riêng: userId == threadId
        usage = UsageStoreImpl(self.env.db)
        turn_id = await usage.open_agent_turn(clinic, account_id, thread_id)
        await usage.finish_agent_turn(clinic, turn_id, TokenUsage(total_tokens=100, steps=1))
        self._job += 1
        await self.env.execute(
            "INSERT INTO agent.jobs (clinic_id, id, account_id, thread_id, thread_type, name, kind, payload, "
            "schedule_kind, run_at, max_runs) VALUES (:c, :id, :a, :t, 0, 'nhắc', 'message', '{}', 'once', "
            "'2030-01-01T00:00:00Z', 1)",
            c=clinic,
            id=f"job-{self._job}",
            a=account_id,
            t=thread_id,
        )

    async def count(self, table: str, account_id: str, thread_id: str) -> int:
        sql = {
            "threads": "SELECT COUNT(*) FROM agent.threads WHERE account_id = :a AND thread_id = :t",
            "history": "SELECT COUNT(*) FROM agent.history WHERE account_id = :a AND thread_id = :t",
            "jobs": "SELECT COUNT(*) FROM agent.jobs WHERE account_id = :a AND thread_id = :t",
            "usage": "SELECT COUNT(*) FROM agent.usage WHERE account_id = :a AND thread_id = :t",
            "contacts": "SELECT COUNT(*) FROM agent.contacts WHERE account_id = :a AND user_id = :t",
        }[table]
        return int(await self.env.scalar(sql, a=account_id, t=thread_id))


@pytest.fixture
async def rig(env: ClinicEnv, tmp_path: Path) -> Rig:
    rig = Rig(env, tmp_path / "media-root")
    await rig.seed(ACC, TH)
    await rig.seed(ACC, TH_KHAC)
    await rig.seed(ACC_KHAC, TH)  # cùng threadId, khác account - phải còn nguyên
    return rig


async def _delete(rig: Rig, account_id: str, thread_id: str):
    return await delete_thread_session(rig.env.db, rig.wiper, rig.env.clinic_id, account_id, thread_id)


async def test_xoa_han_session_deletes_the_session_row_messages_and_jobs_of_exactly_that_thread(
    rig: Rig,
) -> None:
    """xóa dòng session + tin nhắn + lịch hẹn của ĐÚNG thread đó"""
    result = await _delete(rig, ACC, TH)
    assert await rig.count("threads", ACC, TH) == 0, "dòng session phải biến mất"
    assert await rig.count("history", ACC, TH) == 0, "tin nhắn phải bị xóa"
    assert await rig.count("jobs", ACC, TH) == 0, "lịch hẹn của thread phải bị xóa"
    assert result.had_row is True
    assert result.messages == 2
    assert result.jobs == 1


async def test_xoa_han_session_keeps_the_address_book_and_the_token_ledger(rig: Rig) -> None:
    """GIỮ danh bạ (Phương án A) và sổ token (agent_turns)"""
    await _delete(rig, ACC, TH)
    assert await rig.count("contacts", ACC, TH) == 1, "danh bạ phải được giữ - có nút xóa riêng"
    assert await rig.count("usage", ACC, TH) == 1, "sổ token phải giữ để thống kê không bị viết lại"


async def test_xoa_han_session_does_not_touch_another_thread_of_the_same_account(rig: Rig) -> None:
    """KHÔNG đụng thread khác cùng account"""
    await _delete(rig, ACC, TH)
    assert await rig.count("threads", ACC, TH_KHAC) == 1
    assert await rig.count("history", ACC, TH_KHAC) == 2
    assert await rig.count("jobs", ACC, TH_KHAC) == 1


async def test_xoa_han_session_does_not_touch_another_account_with_the_same_thread_id(rig: Rig) -> None:
    """KHÔNG đụng account khác cùng threadId"""
    await _delete(rig, ACC, TH)
    assert await rig.count("threads", ACC_KHAC, TH) == 1, "account khác cùng threadId phải còn nguyên"
    assert await rig.count("history", ACC_KHAC, TH) == 2
    assert await rig.count("contacts", ACC_KHAC, TH) == 1


async def test_xoa_han_session_deleting_something_that_does_not_exist_reports_no_row_without_raising(
    rig: Rig,
) -> None:
    """xóa cái không tồn tại thì coDong=false, không ném"""
    result = await _delete(rig, ACC, "thread-khong-co")
    assert result.had_row is False

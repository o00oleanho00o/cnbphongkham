# ported from: src/conversation/xoa-han-session.ts
"""XÓA HẲN một session (cuộc trò chuyện) khỏi dashboard.

The PORT-MAP lists this file as "no port" with the note "expires dashboard sessions"; that note describes a
different file. ``xoa-han-session.ts`` is the "delete session" of the Sessions page (the route
``DELETE /admin/threads/{account_id}/{thread_id}`` is in this package), so it IS ported here.

Khác ``wipe_thread_context`` (RESET - xóa nội dung nhưng GIỮ dòng ``threads`` để giữ tên + công tắc bot): hàm
này còn xóa CHÍNH dòng session, tức nó biến mất khỏi trang Sessions.

GIỮ LẠI có chủ đích:
  - ``contacts``: người dùng chốt Phương án A - xóa session không đụng danh bạ. Có nút xóa contact riêng.
  - ``memories``: có nút xóa riêng ở trang Memory.
  - ``usage``: SỔ CHI TIÊU token (không chứa chữ hội thoại). Giữ nguyên để thống kê token không bị viết lại -
    đúng như ``wipe_thread_context`` làm.

XÓA THÊM so với reset: ``agent.jobs`` của thread (``job_runs`` cascade). Session đã biến mất mà để lại một
lịch nhắc trỏ vào nó thì tới giờ nó bắn ra và DỰNG LẠI session - mâu thuẫn với "đã xóa". Reset thì giữ
session nên mới giữ lịch.

Forced deviation: see ``wipe_thread_context`` (no foreign key links a thread to its history, so ``wipe`` is
reused to empty every table; the jobs table has none either, so its rows are deleted by hand).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from pema.conversation.sql_util import affected_rows
from pema.conversation.wipe_thread_context import ThreadContextWiper
from pema.core.db import ClinicDatabase
from pema.shared.logger import create_logger

_log = create_logger("xoa-session")

_DELETE_THREAD_ROW = text(
    "DELETE FROM agent.threads "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)
_DELETE_THREAD_JOBS = text(
    "DELETE FROM agent.jobs "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)


@dataclass(frozen=True)
class DeleteSessionResult:
    """``KetQuaXoaSession``."""

    messages: int
    """``tinNhan``: số tin nhắn đã xóa (từ bước dọn ngữ cảnh)."""
    jobs: int
    """``lichHen``: số lịch hẹn của thread đã xóa."""
    had_row: bool
    """``coDong``: dòng session có tồn tại để xóa không (False = xóa cái vốn không có)."""


async def delete_thread_session(
    db: ClinicDatabase,
    wiper: ThreadContextWiper,
    clinic_id: UUID,
    account_id: str,
    thread_id: str,
) -> DeleteSessionResult:
    """``xoaHanSession``."""
    # Bước 1: dọn ngữ cảnh (history, trace, media, counters). Nó tự chạy trong giao dịch riêng và xóa file ảnh
    # trên đĩa (ngoài giao dịch, cố ý).
    context = await wiper.wipe_thread_context(clinic_id, account_id, thread_id)

    # Bước 2: xóa CHÍNH dòng session + lịch hẹn trỏ vào nó, trong một giao dịch.
    scope = {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id}
    async with db.session(clinic_id) as session:
        jobs = affected_rows(await session.execute(_DELETE_THREAD_JOBS, scope))
        had_row = affected_rows(await session.execute(_DELETE_THREAD_ROW, scope)) > 0

    _log.info(
        "Đã xóa hẳn session",
        account_id=account_id,
        thread_id=thread_id,
        messages=context.messages,
        jobs=jobs,
        had_row=had_row,
    )
    return DeleteSessionResult(messages=context.messages, jobs=jobs, had_row=had_row)

# ported from: src/conversation/thread-store.ts
"""Threads: one row per (account, thread), the unit of the Sessions page (table ``agent.threads``).

Forced deviations: SQLite sync -> SQLAlchemy async + Postgres (``clinic_id``, no RLS; ``strftime`` becomes
``now()``; ``LIKE`` becomes an escaped ``ILIKE``; ``ORDER BY last_message_at DESC`` gets ``NULLS LAST``
because SQLite sorts NULL last on DESC and Postgres first).

``agent.threads`` has a foreign key to ``agent.accounts`` (the SQLite schema had none): recording activity for
an account that does not exist fails, which is what we want (a thread of a deleted account is an orphan).

Not ported: ``backfillThreadsFromMessages`` (rebuilt the table from an older SQLite file at upgrade time;
Postgres starts clean, the PORT-MAP lists ``startup-backfill`` as "no port").
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import text

from pema.conversation.sql_util import affected_rows, like_pattern
from pema.core.db import ClinicDatabase
from pema_contracts.conversation import ThreadRow, ThreadSummary

_UPSERT = text(
    """
    INSERT INTO agent.threads (clinic_id, account_id, thread_id, thread_type, display_name, message_count,
                               last_message_at, last_sender_name)
    VALUES (:clinic_id, :account_id, :thread_id, :thread_type, :display_name, 1, now(), :sender_name)
    ON CONFLICT (clinic_id, account_id, thread_id) DO UPDATE SET
        message_count = agent.threads.message_count + 1,
        last_message_at = EXCLUDED.last_message_at,
        last_sender_name = EXCLUDED.last_sender_name,
        -- Tên mới chỉ ghi đè khi không rỗng (tin sau có thể thiếu tên)
        display_name = CASE WHEN EXCLUDED.display_name <> '' THEN EXCLUDED.display_name
                            ELSE agent.threads.display_name END
    """
)

_GET = text(
    "SELECT bot_enabled, display_name FROM agent.threads "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)

_SET_ENABLED = text(
    "UPDATE agent.threads SET bot_enabled = :enabled "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)

_SET_NAME = text(
    "UPDATE agent.threads SET display_name = :name "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)

_GET_SUMMARY = text(
    "SELECT summary, summary_covers_to_message_id FROM agent.threads "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)

_SET_SUMMARY = text(
    "UPDATE agent.threads SET summary = :summary, summary_covers_to_message_id = :covers_to "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)

_GET_EPOCH = text(
    "SELECT context_epoch FROM agent.threads "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id"
)

_GET_ROW = text(
    """
    SELECT account_id, thread_id, thread_type, display_name, bot_enabled,
           message_count, last_message_at, last_sender_name
    FROM agent.threads
    WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id
    """
)

_LIST = text(
    """
    SELECT account_id, thread_id, thread_type, display_name, bot_enabled,
           message_count, last_message_at, last_sender_name
    FROM agent.threads
    WHERE clinic_id = :clinic_id
      AND (CAST(:account_id AS text) = '' OR account_id = :account_id)
      AND (display_name ILIKE :like ESCAPE '\\' OR thread_id ILIKE :like ESCAPE '\\')
    ORDER BY last_message_at DESC NULLS LAST, thread_id
    LIMIT :limit OFFSET :offset
    """
)


@dataclass(frozen=True)
class ThreadStatus:
    bot_enabled: bool


class ThreadStoreImpl:
    """``ThreadStore`` of ``pema_contracts.conversation`` on ``agent.threads`` (+ the extra methods the
    scheduler and the channel layer need: ``find_thread_status``, ``has_display_name``,
    ``set_thread_display_name``). ``wipe_thread_context`` is provided by ``PostgresConversationStore`` because
    it also needs the media files."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def record_thread_activity(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        thread_id: str,
        thread_type: int,
        display_name: str,
        sender_name: str,
    ) -> None:
        """Ghi nhận 1 tin đến cho thread (tạo mới nếu chưa có). ``display_name`` rỗng = giữ tên cũ."""
        async with self._db.session() as session:
            await session.execute(
                _UPSERT,
                {
                    "clinic_id": clinic_id,
                    "account_id": account_id,
                    "thread_id": thread_id,
                    "thread_type": thread_type,
                    "display_name": display_name,
                    "sender_name": sender_name,
                },
            )

    async def is_bot_enabled(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool:
        """Bot có được phép trả lời thread này không. Thread chưa từng thấy = có."""
        status = await self.find_thread_status(clinic_id, account_id, thread_id)
        return status is None or status.bot_enabled

    async def find_thread_status(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> ThreadStatus | None:
        """Trạng thái thread cho scheduler (``proactive-send-guard``) - CỐ Ý khác ``is_bot_enabled``: hàm đó
        mặc định permissive cho thread lạ (đúng cho TIN ĐẾN - chưa kịp ghi thread thì vẫn phải trả lời được),
        còn tin CHỦ ĐỘNG không được nhắm vào một thread chưa từng ghi nhận trong hệ thống - trả ``None`` để
        caller coi đó là điều kiện chặn, không phải mặc định cho qua."""
        row = await self._get(clinic_id, account_id, thread_id)
        return ThreadStatus(bot_enabled=bool(row["bot_enabled"])) if row is not None else None

    async def has_display_name(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool:
        """Thread group đã có tên hiển thị chưa - dùng để quyết định có gọi getGroupInfo không."""
        row = await self._get(clinic_id, account_id, thread_id)
        return row is not None and row["display_name"] != ""

    async def set_bot_enabled(self, clinic_id: UUID, account_id: str, thread_id: str, enabled: bool) -> bool:
        async with self._db.session() as session:
            result = await session.execute(
                _SET_ENABLED,
                {
                    "clinic_id": clinic_id,
                    "account_id": account_id,
                    "thread_id": thread_id,
                    "enabled": enabled,
                },
            )
            return affected_rows(result) > 0

    async def set_thread_display_name(
        self, clinic_id: UUID, account_id: str, thread_id: str, name: str
    ) -> None:
        async with self._db.session() as session:
            await session.execute(
                _SET_NAME,
                {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id, "name": name},
            )

    # ===== Memory lớp 2: rolling summary =====

    async def get_thread_summary(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadSummary:
        async with self._db.session() as session:
            row = (
                (
                    await session.execute(
                        _GET_SUMMARY,
                        {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id},
                    )
                )
                .mappings()
                .first()
            )
        if row is None:
            return ThreadSummary(summary="", covers_to_message_id=0)
        return ThreadSummary(
            summary=row["summary"], covers_to_message_id=int(row["summary_covers_to_message_id"])
        )

    async def set_thread_summary(
        self, clinic_id: UUID, account_id: str, thread_id: str, summary: str, covers_to: int
    ) -> None:
        async with self._db.session() as session:
            await session.execute(
                _SET_SUMMARY,
                {
                    "clinic_id": clinic_id,
                    "account_id": account_id,
                    "thread_id": thread_id,
                    "summary": summary,
                    "covers_to": covers_to,
                },
            )

    async def get_thread_context_epoch(self, clinic_id: UUID, account_id: str, thread_id: str) -> int:
        """Số lần ngữ cảnh thread này đã bị xóa sạch. Vào khóa phiên gửi router để mỗi lần xóa mở một phiên
        mới - xem ``cache-session-id`` và cột ``context_epoch``.

        Thread chưa có dòng nào (tin đầu tiên chưa ghi xong) trả 0, cùng giá trị với thread chưa từng bị xóa -
        đúng ý, vì cả hai đều là "chưa có gì để bỏ đi".
        """
        async with self._db.session() as session:
            value = (
                await session.execute(
                    _GET_EPOCH, {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id}
                )
            ).scalar()
        return int(value) if value is not None else 0

    async def get_thread(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadRow | None:
        """One row of the Sessions list (no equivalent in the original: the dashboard re-listed)."""
        async with self._db.session() as session:
            row = (
                (
                    await session.execute(
                        _GET_ROW, {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id}
                    )
                )
                .mappings()
                .first()
            )
        return ThreadRow.model_validate(dict(row)) if row is not None else None

    async def list_threads(
        self,
        clinic_id: UUID,
        *,
        account_id: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[ThreadRow]:
        """``account_id`` bỏ trống = mọi account (dashboard mặc định xem trộn chung)."""
        async with self._db.session() as session:
            rows = (
                (
                    await session.execute(
                        _LIST,
                        {
                            "clinic_id": clinic_id,
                            "account_id": account_id or "",
                            "like": like_pattern(query),
                            "limit": limit,
                            "offset": offset,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return [ThreadRow.model_validate(dict(r)) for r in rows]

    async def _get(self, clinic_id: UUID, account_id: str, thread_id: str) -> dict[str, object] | None:
        async with self._db.session() as session:
            row = (
                (
                    await session.execute(
                        _GET, {"clinic_id": clinic_id, "account_id": account_id, "thread_id": thread_id}
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row is not None else None

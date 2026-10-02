# ported from: src/conversation/contact-store.ts
"""Contacts ("auto-collected" address book, table ``agent.contacts``).

Forced deviations: SQLite sync -> SQLAlchemy async + Postgres with ``clinic_id``, no RLS; ``strftime`` default
and ``LIKE`` become ``now()`` and ``ILIKE`` (with the wildcards of the search text escaped, the original let
a ``%`` typed by the user act as a wildcard).

Not ported: ``backfillContactsFromDirectMessages``. It rebuilt the table from the messages of an OLDER
SQLite file at upgrade time; Postgres starts clean (the PORT-MAP lists ``startup-backfill`` as "no port" for
the same reason).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from pema.conversation.sql_util import affected_rows, like_pattern
from pema.core.db import ClinicDatabase
from pema_contracts.conversation import ContactRow

_UPSERT = text(
    """
    INSERT INTO agent.contacts (clinic_id, account_id, user_id, display_name, message_count)
    VALUES (:clinic_id, :account_id, :user_id, :display_name, 1)
    ON CONFLICT (clinic_id, account_id, user_id) DO UPDATE SET
        message_count = agent.contacts.message_count + 1,
        last_seen = now(),
        display_name = CASE WHEN EXCLUDED.display_name <> '' THEN EXCLUDED.display_name
                            ELSE agent.contacts.display_name END
    """
)

_DELETE = text(
    "DELETE FROM agent.contacts "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND user_id = :user_id"
)

_LIST = text(
    """
    SELECT account_id, user_id, display_name, first_seen, last_seen, message_count
    FROM agent.contacts
    WHERE clinic_id = :clinic_id
      AND (CAST(:account_id AS text) = '' OR account_id = :account_id)
      AND (display_name ILIKE :like ESCAPE '\\' OR user_id ILIKE :like ESCAPE '\\')
    ORDER BY last_seen DESC
    LIMIT :limit OFFSET :offset
    """
)


class ContactStoreImpl:
    """``ContactStore`` of ``pema_contracts.conversation`` on ``agent.contacts``."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def record_contact_activity(
        self, clinic_id: UUID, account_id: str, user_id: str, display_name: str
    ) -> None:
        """Ghi nhận 1 tin đến từ người này ("auto-collected" như GoClaw - ghi cả người bị allowlist chặn để
        thấy ai đã từng nhắn tới bot)."""
        if not user_id:
            return  # payload thiếu uidFrom - không có gì để ghi
        async with self._db.session() as session:
            await session.execute(
                _UPSERT,
                {
                    "clinic_id": clinic_id,
                    "account_id": account_id,
                    "user_id": user_id,
                    "display_name": display_name,
                },
            )

    async def delete_contact(self, clinic_id: UUID, account_id: str, user_id: str) -> bool:
        """Xóa MỘT dòng danh bạ (``xoaContact``). Chỉ đụng bảng ``contacts`` - KHÔNG xóa tin nhắn.

        Danh bạ là "auto-collected" từ tin đến (``record_contact_activity``), nên xóa xong mà người đó nhắn
        lại thì dòng tự hiện lại (đếm lại từ đầu; tin nhắn cũ trong DB vẫn nguyên). Đó là hành vi đúng của
        một danh bạ tự thu thập, không phải bug.
        """
        async with self._db.session() as session:
            result = await session.execute(
                _DELETE, {"clinic_id": clinic_id, "account_id": account_id, "user_id": user_id}
            )
            return affected_rows(result) > 0

    async def list_contacts(
        self,
        clinic_id: UUID,
        *,
        account_id: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContactRow]:
        """``account_id`` bỏ trống = mọi account."""
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
        return [ContactRow.model_validate(dict(r)) for r in rows]

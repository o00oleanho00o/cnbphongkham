# ported from: src/conversation/history-store.ts
"""History: the LLM context store (table ``agent.history``, the ``messages`` table of zalo-agent).

It is NOT the Inbox of record (``clinic.message`` is): the channel layer writes both.

Forced deviations:

* ``node:sqlite`` (sync) becomes SQLAlchemy async over Postgres; every method takes ``clinic_id`` first and
  opens its unit of work with ``ClinicDatabase.session(clinic_id)`` (row level security);
* ``created_at`` is ``timestamptz``: an explicit value is an aware ``datetime`` and the read side returns
  it normalised to +07:00 (``VnDatetime``); the id is a ``bigint`` identity column;
* the ``images`` column is ``jsonb`` instead of a JSON string.

Kept from the original: two separate INSERT statements (with and without an explicit ``created_at``; writing
``COALESCE(:created_at, now())`` would copy the schema default into a second place and one of the two write
paths would drift), prune of the thread right after each write, keyset pagination by id, and reading order
by id and NOT by ``created_at`` (a burst of old messages delivered after a listener reconnect must not be
shuffled into the middle of the live conversation).
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any
from uuid import UUID

from sqlalchemy import text

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.core.db import ClinicDatabase
from pema_contracts.conversation import StoredMessage

_INSERT = text(
    """
    INSERT INTO agent.history (clinic_id, account_id, thread_id, role, sender_name, sender_id, content,
    images) VALUES (:clinic_id, :account_id, :thread_id, :role, :sender_name, :sender_id, :content,
    CAST(:images AS jsonb)) RETURNING id
    """
)

# Bản có `created_at` tường minh. Two statements instead of one with COALESCE: see module docstring.
_INSERT_WITH_CREATED_AT = text(
    """
    INSERT INTO agent.history (clinic_id, account_id, thread_id, role, sender_name, sender_id, content,
    images, created_at) VALUES (:clinic_id, :account_id, :thread_id, :role, :sender_name, :sender_id,
    :content, CAST(:images AS jsonb), :created_at) RETURNING id
    """
)

# Giữ N tin mới nhất của thread, xóa phần cũ hơn. The subquery takes the id of the (N+1)th newest message; a
# thread with fewer than N+1 messages yields NULL and nothing is deleted. Both the DELETE and the subquery
# run on the index (clinic_id, account_id, thread_id, id).
_PRUNE = text(
    """
    DELETE FROM agent.history
    WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id
      AND id <= (SELECT id FROM agent.history
                 WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id
                 ORDER BY id DESC LIMIT 1 OFFSET :keep)
    """
)

_SET_IMAGES = text(
    "UPDATE agent.history SET images = CAST(:images AS jsonb) WHERE clinic_id = :clinic_id AND id = :id"
)

_RECENT = text(
    """
    SELECT id, role, sender_name, sender_id, content, images, created_at FROM agent.history
    WHERE clinic_id = :clinic_id AND account_id = :account_id AND thread_id = :thread_id
    ORDER BY id DESC LIMIT :limit
    """
)

_PAGED = text(
    """
    SELECT id, role, sender_name, sender_id, content, images, created_at FROM agent.history WHERE clinic_id
    = :clinic_id AND account_id = :account_id AND thread_id = :thread_id AND id < :before_id ORDER BY id
    DESC LIMIT :limit
    """
)

_MAX_ID = 9_223_372_036_854_775_807  # bigint max: "from the newest message" when ``before_id`` is omitted


def parse_images(raw: object) -> list[str]:
    """The ``images`` column is a JSON array; NULL or anything that is not a non-empty list means no image
    (``parseImages`` returned ``undefined``; the DTO uses an empty list)."""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return []
    if not isinstance(raw, list) or not raw:
        return []
    items: list[Any] = list(raw)  # pyright: ignore[reportUnknownArgumentType]
    return [str(item) for item in items]


def _to_message(row: Any) -> StoredMessage:
    return StoredMessage(
        id=row["id"],
        role=row["role"],
        content=row["content"],
        sender_name=row["sender_name"],
        sender_id=row["sender_id"],
        images=parse_images(row["images"]),
        created_at=row["created_at"],
    )


class HistoryStoreImpl:
    """``HistoryStore`` of ``pema_contracts.conversation`` on ``agent.history``."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def append_message(
        self, clinic_id: UUID, account_id: str, thread_id: str, message: StoredMessage
    ) -> int:
        """Ghi 1 tin, trả về id của row để cập nhật bổ sung sau (vd gắn ảnh tải xong muộn)."""
        params: dict[str, Any] = {
            "clinic_id": clinic_id,
            "account_id": account_id,
            "thread_id": thread_id,
            "role": message.role,
            "sender_name": message.sender_name,
            "sender_id": message.sender_id,
            "content": message.content,
            "images": json.dumps(message.images) if message.images else None,
        }
        async with self._db.session(clinic_id) as session:
            if message.created_at is not None:
                row_id = (
                    await session.execute(
                        _INSERT_WITH_CREATED_AT, {**params, "created_at": message.created_at}
                    )
                ).scalar_one()
            else:
                row_id = (await session.execute(_INSERT, params)).scalar_one()
            # Dọn ngay thread vừa ghi: không cần cron, và thread im lặng thì không tốn gì.
            await session.execute(
                _PRUNE,
                {
                    "clinic_id": clinic_id,
                    "account_id": account_id,
                    "thread_id": thread_id,
                    "keep": get_tuning_int("HISTORY_MAX_MESSAGES_PER_THREAD"),
                },
            )
        return int(row_id)

    async def set_message_images(self, clinic_id: UUID, message_id: int, images: Sequence[str]) -> None:
        """Gắn ảnh vào tin đã ghi - dùng cho passive listen (ghi tin ngay, ảnh tải xong sau)."""
        if len(images) == 0:
            return
        async with self._db.session(clinic_id) as session:
            await session.execute(
                _SET_IMAGES, {"clinic_id": clinic_id, "id": message_id, "images": json.dumps(list(images))}
            )

    async def get_recent_messages(
        self, clinic_id: UUID, account_id: str, thread_id: str, limit: int | None = None
    ) -> list[StoredMessage]:
        """Oldest first, the N newest (``limit`` defaults to ``HISTORY_CONTEXT_LIMIT``)."""
        effective = limit if limit is not None else get_tuning_int("HISTORY_CONTEXT_LIMIT")
        async with self._db.session(clinic_id) as session:
            rows = (
                (
                    await session.execute(
                        _RECENT,
                        {
                            "clinic_id": clinic_id,
                            "account_id": account_id,
                            "thread_id": thread_id,
                            "limit": effective,
                        },
                    )
                )
                .mappings()
                .all()
            )
        # DESC để lấy N tin mới nhất, đảo lại thành thứ tự thời gian cho LLM.
        return [_to_message(r) for r in reversed(rows)]

    async def list_messages_paged(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[StoredMessage]:
        """Đọc tin nhắn phân trang cho dashboard - keyset theo id (ổn định khi có tin mới chen vào, không lệch
        trang như OFFSET). ``before_id`` bỏ trống = từ tin mới nhất."""
        async with self._db.session(clinic_id) as session:
            rows = (
                (
                    await session.execute(
                        _PAGED,
                        {
                            "clinic_id": clinic_id,
                            "account_id": account_id,
                            "thread_id": thread_id,
                            "before_id": before_id if before_id is not None else _MAX_ID,
                            "limit": limit,
                        },
                    )
                )
                .mappings()
                .all()
            )
        return [_to_message(r) for r in reversed(rows)]

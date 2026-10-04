# ported from: src/conversation/memory-store.ts
"""Durable memory facts (``save_memory``; table ``agent.memories``).

Forced deviations:

* ``node:sqlite`` sync -> SQLAlchemy async + Postgres (``clinic_id`` + RLS, ``LIKE`` -> escaped ``ILIKE``);
* the "check duplicate, then insert, then cap" sequence of ``saveMemoryFact`` ran inside ONE synchronous
  process, so no other writer could slip in between. With several workers that no longer holds, and there is
  no unique constraint on ``content`` (a fact may be edited into a duplicate on purpose, see
  ``memory_edit_store``). The three statements therefore run in one transaction guarded by a transaction
  scoped advisory lock keyed on (clinic, account, subject): two concurrent saves of the same fact cannot
  both pass the duplicate check.

Clinic note: the store is policy-agnostic. In ``patient_channel`` the ``save_memory`` tool asks
``PolicyHooks.allow_memory_write`` BEFORE it calls this store (CONTRACTS-AI01 section 3).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.conversation.sql_util import affected_rows, like_pattern
from pema.core.db import ClinicDatabase
from pema_contracts.conversation import MemoryContextItem, MemoryFact, SaveMemoryResult

_LOCK = text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))")

_DUPLICATE = text(
    "SELECT id FROM agent.memories "
    "WHERE clinic_id = :clinic_id AND account_id = :account_id AND subject_id = :subject_id "
    "AND content = :content "
    "LIMIT 1"
)

_INSERT = text(
    """
    INSERT INTO agent.memories (clinic_id, account_id, subject_id, content, learned_in_thread_id,
    learned_in_group) VALUES (:clinic_id, :account_id, :subject_id, :content, :thread_id, :in_group)
    """
)

# Giữ N fact mới nhất mỗi subject - cùng pattern prune của history-store.
_CAP = text(
    """
    DELETE FROM agent.memories
    WHERE clinic_id = :clinic_id AND account_id = :account_id AND subject_id = :subject_id
      AND id <= (SELECT id FROM agent.memories
                 WHERE clinic_id = :clinic_id AND account_id = :account_id AND subject_id = :subject_id
                 ORDER BY id DESC LIMIT 1 OFFSET :keep)
    """
)

# Quy tắc inject BẤT ĐỐI XỨNG (user đã chốt): private không bao giờ chảy ra public.
# - Chat riêng với A: mọi fact về A (kể cả học trong group - chuyện nói trước nhóm không còn là bí mật) +
#   fact về chính thread DM.
# - Group X, A đang nói: fact về group X + fact về A NHƯNG CHỈ fact học trong group. Fact học ở DM tuyệt đối
#   không xuất hiện trong prompt ở group.
_DIRECT = text(
    """
    SELECT id, subject_id, content FROM agent.memories WHERE clinic_id = :clinic_id AND account_id =
    :account_id AND (subject_id = :sender_id OR subject_id = :thread_id) ORDER BY id
    """
)
_GROUP = text(
    """
    SELECT id, subject_id, content FROM agent.memories
    WHERE clinic_id = :clinic_id AND account_id = :account_id
      AND (subject_id = :thread_id OR (subject_id = :sender_id AND learned_in_group))
    ORDER BY id
    """
)

# ===== Cho dashboard: xem + xóa fact =====  Trước đây ghi "xóa là quyền của user, bot không tự xóa". Đã
# đổi: bot sửa và xóa được qua ``memory_edit_store``, nhưng CHỈ trong tập fact nó đang nhìn thấy. Lý do đổi
# là bằng chứng mới chứ không phải đổi ý: không có đường sửa thì một lời đính chính của người dùng ("mình
# chuyển ra Hà Nội rồi") chỉ đẻ thêm fact mới nằm cạnh fact cũ, để lại hai điều mâu thuẫn - tệ hơn hẳn so
# với không nhớ gì. Đường xóa của dashboard vẫn giữ, không phụ thuộc vào bot.
_LIST = text(
    """
    SELECT id, account_id, subject_id, content, learned_in_thread_id, learned_in_group, created_at FROM
    agent.memories WHERE clinic_id = :clinic_id AND (CAST(:account_id AS text) = '' OR account_id =
    :account_id) AND (subject_id ILIKE :like ESCAPE '\\' OR content ILIKE :like ESCAPE '\\') ORDER BY id
    DESC LIMIT :limit OFFSET :offset
    """
)

_DELETE = text(
    "DELETE FROM agent.memories WHERE clinic_id = :clinic_id AND account_id = :account_id AND id = :id"
)


class MemoryStoreImpl:
    """``MemoryStore`` of ``pema_contracts.conversation`` on ``agent.memories``."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def save_memory_fact(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        subject_id: str,
        content: str,
        learned_in_thread_id: str,
        learned_in_group: bool,
    ) -> SaveMemoryResult:
        """So khớp TRÙNG KHÍT (sau khi cắt khoảng trắng hai đầu), không chuẩn hóa gì thêm. Học Hermes
        (``memory_tool.py``: ``if content in entries`` -> "Entry already exists"). Cố ý không bỏ dấu hay hạ
        chữ thường để so: hai câu chỉ khác dấu trong tiếng Việt thường là hai câu khác nghĩa, mà chặn nhầm ở
        đây
        nghĩa là người dùng dặn một điều mới và bot im lặng không nhớ."""
        trimmed = content.strip()
        scope = {"clinic_id": clinic_id, "account_id": account_id, "subject_id": subject_id}
        async with self._db.session(clinic_id) as session:
            await session.execute(_LOCK, {"key": f"memory:{clinic_id}:{account_id}:{subject_id}"})
            duplicate = (await session.execute(_DUPLICATE, {**scope, "content": trimmed})).first()
            if duplicate is not None:
                return SaveMemoryResult(saved=False, reason="duplicate")

            await session.execute(
                _INSERT,
                {
                    **scope,
                    "content": trimmed,
                    "thread_id": learned_in_thread_id,
                    "in_group": learned_in_group,
                },
            )
            await session.execute(_CAP, {**scope, "keep": get_tuning_int("MEMORY_MAX_FACTS_PER_SUBJECT")})
        return SaveMemoryResult(saved=True)

    async def get_memories_for_context(
        self, clinic_id: UUID, *, account_id: str, thread_id: str, sender_id: str, is_group: bool
    ) -> list[MemoryContextItem]:
        """Asymmetric rule: a fact learned in private never surfaces in a group."""
        params = {
            "clinic_id": clinic_id,
            "account_id": account_id,
            "thread_id": thread_id,
            "sender_id": sender_id,
        }
        async with self._db.session(clinic_id) as session:
            rows = (await session.execute(_GROUP if is_group else _DIRECT, params)).mappings().all()

        # DM: senderId và threadId trùng nhau -> dedupe theo id (the SQL ``OR`` already returns a row once,
        # the filter is kept as the original's safety net).
        seen: set[int] = set()
        items: list[MemoryContextItem] = []
        for row in rows:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            items.append(MemoryContextItem(subject_id=row["subject_id"], content=row["content"]))
        return items

    async def list_memories(
        self,
        clinic_id: UUID,
        *,
        account_id: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryFact]:
        """``account_id`` bỏ trống = mọi account."""
        async with self._db.session(clinic_id) as session:
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
        return [MemoryFact.model_validate(dict(r)) for r in rows]

    async def delete_memory_fact(self, clinic_id: UUID, account_id: str, fact_id: int) -> bool:
        async with self._db.session(clinic_id) as session:
            result = await session.execute(
                _DELETE, {"clinic_id": clinic_id, "account_id": account_id, "id": fact_id}
            )
            return affected_rows(result) > 0

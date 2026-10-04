# ported from: src/conversation/image-description-store.ts
"""Cache of the vision sidecar's image descriptions (table ``agent.image_descriptions``).

Each image in the media store is described ONCE: later turns (also when reloaded from history) read the
cache, do not call the sidecar again and cost no quota. Learned from Hermes' sha256 cache; keyed by
``rel_path`` here because every media file already has a unique path.

Forced deviations: SQLite sync -> SQLAlchemy async; the table is keyed ``(clinic_id, rel_path)`` (a path is
unique inside one clinic's media root); the loop of ``xoaMoTaAnhTheoDuongDan`` (one DELETE per path) becomes a
single ``DELETE ... WHERE rel_path = ANY(:paths)``.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from pema.conversation.sql_util import affected_rows
from pema.core.db import ClinicDatabase

_GET = text(
    "SELECT description FROM agent.image_descriptions WHERE clinic_id = :clinic_id AND rel_path = :rel_path"
)
_SET = text(
    """
    INSERT INTO agent.image_descriptions (clinic_id, rel_path, description, model)
    VALUES (:clinic_id, :rel_path, :description, :model)
    ON CONFLICT (clinic_id, rel_path) DO UPDATE SET description = EXCLUDED.description, model = EXCLUDED.model
    """
)
_PRUNE = text("DELETE FROM agent.image_descriptions WHERE clinic_id = :clinic_id AND created_at < :cutoff")
_DELETE_BY_PATHS = text(
    "DELETE FROM agent.image_descriptions WHERE clinic_id = :clinic_id AND rel_path = ANY(:paths)"
)


class ImageDescriptionStoreImpl:
    """``ImageDescriptionStore`` of ``pema_contracts.conversation`` on ``agent.image_descriptions``."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def get_image_description(self, clinic_id: UUID, rel_path: str) -> str | None:
        async with self._db.session(clinic_id) as session:
            row = (await session.execute(_GET, {"clinic_id": clinic_id, "rel_path": rel_path})).first()
        return str(row[0]) if row is not None else None

    async def save_image_description(
        self, clinic_id: UUID, rel_path: str, description: str, model: str
    ) -> None:
        async with self._db.session(clinic_id) as session:
            await session.execute(
                _SET,
                {"clinic_id": clinic_id, "rel_path": rel_path, "description": description, "model": model},
            )

    async def delete_descriptions_by_paths(self, clinic_id: UUID, rel_paths: Sequence[str]) -> int:
        """Xóa mô tả của đúng những ảnh này (``xoaMoTaAnhTheoDuongDan``). Nhận danh sách đường dẫn vì bảng chỉ
        khóa theo ``rel_path`` - không có cột account/thread để lọc, nên caller phải lấy danh sách từ
        ``MediaStore.delete_thread_media`` rồi truyền vào."""
        if len(rel_paths) == 0:
            return 0
        async with self._db.session(clinic_id) as session:
            result = await session.execute(
                _DELETE_BY_PATHS, {"clinic_id": clinic_id, "paths": list(rel_paths)}
            )
            return affected_rows(result)

    async def prune_expired_image_descriptions(
        self, clinic_id: UUID, retention_days: int, now: datetime | None = None
    ) -> int:
        """Dọn mô tả cũ hơn N ngày - cùng nhịp với dọn file media để hai bên kể cùng một câu chuyện: quá hạn
        thì cả pixel lẫn mô tả đều rơi về text "[gửi kèm N ảnh]". Trả về số row đã xóa."""
        cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
        async with self._db.session(clinic_id) as session:
            result = await session.execute(_PRUNE, {"clinic_id": clinic_id, "cutoff": cutoff})
            return affected_rows(result)

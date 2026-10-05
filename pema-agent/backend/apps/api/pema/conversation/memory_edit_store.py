# ported from: src/conversation/memory-edit-store.ts
"""Sửa và xóa fact đã nhớ, khớp theo ĐOẠN CHỮ NGẮN thay vì id.

Forced deviations: SQLite sync -> SQLAlchemy async + Postgres (``clinic_id``, no RLS). The Vietnamese result
shapes of the original (``{ok, loai: "khong_khop" | "khop_nhieu", factHienCo, factKhop, noiDungCu}``) become a
small dataclass with English names (``kind``: ``"no_match"`` / ``"ambiguous"``), like ``SaveMemoryResult``
did for ``KetQuaGhiNho``. The tool that calls this (D4's ``save_memory``) formats the Vietnamese text.

Vì sao không dùng id: model không thấy id trong prompt - fact được nhét vào dưới dạng gạch đầu dòng trần. Bắt
nó nhớ id là bắt nhớ thứ nó chưa từng đọc. Hermes gặp đúng bài toán này và chọn khớp chuỗi con
(``tools/memory_tool.py``, ``replace``/``remove`` nhận ``old_text``), mình theo cùng ngữ nghĩa:

  - không khớp gì  -> trả về danh sách fact hiện có để model thử lại cho đúng
  - khớp nhiều fact KHÁC nhau -> từ chối, bắt model nói cụ thể hơn
  - khớp nhiều fact TRÙNG KHÍT -> làm trên cái đầu tiên, an toàn

Không bao giờ đoán bừa: sửa nhầm một fact còn tệ hơn không sửa được.

ĐIỂM KHÁC HERMES, và là chỗ dễ hỏng nhất ở đây: Hermes chỉ phục vụ một người dùng nên fact nào cũng thấy
được. Bot này đọc tin trong nhóm, mà luật inject là BẤT ĐỐI XỨNG (fact học ở chat riêng không bao giờ hiện
trong nhóm
- xem ``memory_store``). Nên tập fact được phép khớp PHẢI hẹp đúng bằng tập model đang nhìn thấy. Không siết
  chỗ này thì có hai lỗ cùng lúc:

  1. người trong nhóm sửa hoặc XÓA được fact học ở chat riêng
  2. câu báo "không khớp, đây là các fact hiện có" RÒ luôn fact riêng ra nhóm

The same asymmetry is a clinic safety property: a fact a patient gave in a private chat must not be readable
or editable from a group.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema_contracts.conversation import (
    MemoryEditFailed,
    MemoryEditOk,
    MemoryEditResult,
    MemoryEditScope,
)

# Fact model ĐANG NHÌN THẤY về subject này, đúng luật inject. ``only_group_facts`` (chiFactHocTrongNhom) =
# true khi đang ở nhóm và subject là một NGƯỜI: lúc đó chỉ fact học trong nhóm mới được đụng tới.
_VISIBLE = text(
    """
    SELECT id, content FROM agent.memories
    WHERE clinic_id = :clinic_id AND account_id = :account_id AND subject_id = :subject_id
    ORDER BY id
    """
)
_VISIBLE_IN_GROUP = text(
    """
    SELECT id, content FROM agent.memories WHERE clinic_id = :clinic_id AND account_id = :account_id AND
    subject_id = :subject_id AND learned_in_group ORDER BY id
    """
)
_UPDATE = text("UPDATE agent.memories SET content = :content WHERE clinic_id = :clinic_id AND id = :id")
_DELETE = text("DELETE FROM agent.memories WHERE clinic_id = :clinic_id AND id = :id")


@dataclass(frozen=True)
class FactEditScope:
    """``PhamViSuaFact``."""

    account_id: str
    subject_id: str
    only_group_facts: bool
    """True = chỉ được đụng fact học trong nhóm (đang ở nhóm, subject là một người)."""


@dataclass(frozen=True)
class FactEditResult:
    """``KetQuaSuaFact``."""

    ok: bool
    kind: Literal["no_match", "ambiguous"] | None = None
    old_content: str | None = None
    """``noiDungCu``: set when ``ok``."""
    existing_facts: list[str] = field(default_factory=list[str])
    """``factHienCo``: set for ``no_match`` so the model can retry with the right words."""
    matched_facts: list[str] = field(default_factory=list[str])
    """``factKhop``: set for ``ambiguous``."""


@dataclass(frozen=True)
class _Row:
    id: int
    content: str


async def _visible_facts(session: AsyncSession, clinic_id: UUID, scope: FactEditScope) -> list[_Row]:
    rows = (
        (
            await session.execute(
                _VISIBLE_IN_GROUP if scope.only_group_facts else _VISIBLE,
                {"clinic_id": clinic_id, "account_id": scope.account_id, "subject_id": scope.subject_id},
            )
        )
        .mappings()
        .all()
    )
    return [_Row(id=int(r["id"]), content=str(r["content"])) for r in rows]


def _find_matching_fact(visible: list[_Row], snippet: str) -> _Row | FactEditResult:
    needle = snippet.strip().lower()
    matches = [r for r in visible if needle in r.content.lower()]

    if len(matches) == 0:
        return FactEditResult(ok=False, kind="no_match", existing_facts=[r.content for r in visible])
    # Trùng khít nhau thì làm trên cái đầu - không có gì để chọn nhầm.
    # Học từ Hermes: ``if len(unique_texts) > 1`` mới báo lỗi.
    if len(matches) > 1 and len({r.content for r in matches}) > 1:
        return FactEditResult(ok=False, kind="ambiguous", matched_facts=[r.content for r in matches])
    return matches[0]


def _to_port_result(result: FactEditResult) -> MemoryEditResult:
    """The contract result (``MemoryEditPort``): the Vietnamese ``kind`` codes of the original."""
    if result.ok:
        return MemoryEditOk(old_content=result.old_content or "")
    if result.kind == "ambiguous":
        return MemoryEditFailed(kind="khop_nhieu", matching_facts=list(result.matched_facts))
    return MemoryEditFailed(kind="khong_khop", existing_facts=list(result.existing_facts))


class MemoryEditStoreImpl:
    """Implements ``pema_contracts.conversation.MemoryEditPort`` (``edit_fact_by_fragment`` /
    ``delete_fact_by_fragment``) over the snippet methods below."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def edit_fact_by_fragment(
        self, clinic_id: UUID, scope: MemoryEditScope, fragment: str, new_content: str
    ) -> MemoryEditResult:
        result = await self.edit_fact_by_snippet(
            clinic_id,
            FactEditScope(scope.account_id, scope.subject_id, scope.only_group_learned),
            fragment,
            new_content,
        )
        return _to_port_result(result)

    async def delete_fact_by_fragment(
        self, clinic_id: UUID, scope: MemoryEditScope, fragment: str
    ) -> MemoryEditResult:
        result = await self.delete_fact_by_snippet(
            clinic_id, FactEditScope(scope.account_id, scope.subject_id, scope.only_group_learned), fragment
        )
        return _to_port_result(result)

    async def edit_fact_by_snippet(
        self, clinic_id: UUID, scope: FactEditScope, snippet: str, new_content: str
    ) -> FactEditResult:
        """Thay nội dung fact đang chứa ``snippet`` bằng ``new_content`` (``suaFactTheoDoanChu``)."""
        async with self._db.session() as session:
            found = _find_matching_fact(await _visible_facts(session, clinic_id, scope), snippet)
            if isinstance(found, FactEditResult):
                return found
            await session.execute(_UPDATE, {"clinic_id": clinic_id, "id": found.id, "content": new_content})
            return FactEditResult(ok=True, old_content=found.content)

    async def delete_fact_by_snippet(
        self, clinic_id: UUID, scope: FactEditScope, snippet: str
    ) -> FactEditResult:
        """Xóa fact đang chứa ``snippet`` (``xoaFactTheoDoanChu``)."""
        async with self._db.session() as session:
            found = _find_matching_fact(await _visible_facts(session, clinic_id, scope), snippet)
            if isinstance(found, FactEditResult):
                return found
            await session.execute(_DELETE, {"clinic_id": clinic_id, "id": found.id})
            return FactEditResult(ok=True, old_content=found.content)

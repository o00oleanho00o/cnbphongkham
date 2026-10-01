"""``KnowledgeStore`` (``pema_contracts.knowledge``) on Postgres: the object the ``kb_search`` tool (D4), the
admin routes and the ingest worker share.

NEW module (the original had module-level functions bound to one global SQLite connection). It only
COMPOSES the ported modules - ``kb_source_store``, ``kb_source_queries``, ``kb_chunk_store``,
``kb_agent_binding``, ``kb_search``, ``kb_file_store`` - each unit of work in ``ClinicDatabase.session(
clinic_id)`` so row level security applies, and turns their dataclasses into the contract DTOs.

Rules this class keeps (the contract's normative list):
* DEFAULT-DENY: an agent with no source bound reads nothing (``search``);
* a source's raw text is NEVER returned (``raw_text`` is always empty in a ``KbSource`` DTO) - the same rule
  as ``bo_noi_dung_goc`` of the original;
* size and signature of an upload are checked BEFORE anything is written (the route checks them too, at the
  ASGI level, before the body is read; this is the defence in depth for any other caller);
* the doctor's sign-off: ``set_approved`` records WHO and WHEN; a ``patient_channel`` agent cites only
  approved sources (``kb_search``).

Errors are ``DomainError`` with Vietnamese text without PII; the API turns them into ``ErrorResponse``.
"""

from __future__ import annotations

import asyncio
import secrets
from pathlib import Path
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.core.db import ClinicDatabase
from pema.knowledge.chu_ky_file import khop_chu_ky_that
from pema.knowledge.doc_text_extract import DINH_DANG_HO_TRO, la_dinh_dang_ho_tro
from pema.knowledge.kb_agent_binding import (
    agent_cua_nguon,
    agent_ton_tai,
    dat_agent_cho_nguon,
    dat_nguon_cho_agent,
    dem_agent_theo_nguon,
    nguon_cua_agent,
    ton_tai_cac_agent,
)
from pema.knowledge.kb_chunk_store import dem_doan, lay_doan_cua_nguon
from pema.knowledge.kb_file_store import luu_file, xoa_file
from pema.knowledge.kb_search import nhung_cau_hoi, tim_trong_kho_tri_thuc
from pema.knowledge.kb_source_queries import danh_sach_nguon_gon, loc_id_ton_tai
from pema.knowledge.kb_source_store import (
    KbSourceTomTat,
    dat_trang_thai,
    lay_nguon,
    tao_nguon,
    xoa_nguon,
)
from pema.shared.logger import create_logger
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.knowledge import (
    EmbeddingClient,
    KbChunk,
    KbHit,
    KbSource,
    KbSourceKind,
    KbSourceStatus,
)

log = create_logger("knowledge.store")

TEN_NGUON_TOI_DA = 200
"""``tenNguonSchema``: the name enters EVERY ``kb_search`` result, so this is a real system boundary."""
SO_NGUON_TOI_DA_MOI_AGENT = 500
SO_AGENT_TOI_DA_MOI_NGUON = 200
DO_DAI_ID_TOI_DA = 64


def _dto(n: KbSourceTomTat) -> KbSource:
    return KbSource(
        id=n.id,
        name=n.ten,
        kind=KbSourceKind(n.loai),
        format=n.dinh_dang,
        path=n.duong_dan,
        raw_text="",
        status=KbSourceStatus(n.trang_thai),
        error=n.loi,
        chunk_count=n.so_doan,
        byte_size=n.so_byte,
        attempts=n.so_lan_thu,
        approved_by_clinical_owner=n.da_duyet,
        created_at=n.created_at,
        updated_at=n.updated_at,
    )


def _khong_tim_thay() -> DomainError:
    return DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy nguồn")


def kiem_tra_ten_nguon(ten: str) -> str:
    ten = ten.strip()
    if not ten or len(ten) > TEN_NGUON_TOI_DA:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED, f"Tên nguồn không hợp lệ (bắt buộc, tối đa {TEN_NGUON_TOI_DA} ký tự)"
        )
    return ten


def kiem_tra_danh_sach_id(ids: list[str], *, toi_da: int, ten: str) -> list[str]:
    """Bounds of the binding bodies (``putAgentSourcesSchema`` / ``putSourceAgentsSchema``): a list with no
    ceiling is an unbounded loop (and a huge SQL parameter), and one enormous element alone could swallow
    the memory before any lookup."""
    if len(ids) > toi_da or any(len(i) > DO_DAI_ID_TOI_DA for i in ids):
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            f"Danh sách {ten} không hợp lệ (tối đa {toi_da} phần tử, mỗi id tối đa {DO_DAI_ID_TOI_DA} ký tự)",
        )
    return ids


class PostgresKnowledgeStore:
    def __init__(
        self,
        db: ClinicDatabase,
        *,
        embedder: EmbeddingClient | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._db = db
        self._embedder = embedder
        self._data_dir = data_dir

    # ------------------------------------------------------------------ sources

    async def create_text_source(self, clinic_id: UUID, *, name: str, text: str) -> KbSource:
        ten = kiem_tra_ten_nguon(name)
        if not text.strip():
            raise DomainError(ErrorCode.VALIDATION_FAILED, "Nội dung không được để trống")
        so_byte = len(text.encode("utf-8"))
        async with self._db.session(clinic_id) as session:
            nguon = await tao_nguon(
                session, clinic_id, ten=ten, loai="text", noi_dung_goc=text, so_byte=so_byte
            )
        log.info("tạo nguồn kho tri thức (gõ tay)", source_id=nguon.id)
        return _dto(nguon)

    async def create_file_source(self, clinic_id: UUID, *, name: str, format: str, data: bytes) -> KbSource:
        ten = kiem_tra_ten_nguon(name)
        dinh_dang = format.lower()
        if not la_dinh_dang_ho_tro(dinh_dang):
            raise DomainError(
                ErrorCode.KB_SOURCE_INVALID,
                f'Định dạng ".{dinh_dang or "?"}" chưa hỗ trợ - dùng {", ".join(DINH_DANG_HO_TRO)}',
            )
        tran_mb = get_tuning_int("KB_MAX_FILE_MB")
        if len(data) > tran_mb * 1024 * 1024:
            raise DomainError(ErrorCode.PAYLOAD_TOO_LARGE, f"Nội dung vượt quá {tran_mb}MB")
        if not khop_chu_ky_that(data, dinh_dang):
            raise DomainError(
                ErrorCode.KB_SOURCE_INVALID, "Nội dung file không khớp với định dạng khai báo trong tên file"
            )
        # The id of the stored file is NOT the id of the database row (``tao_nguon`` makes its own) - only a
        # random string for the file name, absolutely never the original file name.
        file_id = secrets.token_hex(8)
        duong_dan = await asyncio.to_thread(luu_file, file_id, dinh_dang, data, data_dir=self._data_dir)
        try:
            async with self._db.session(clinic_id) as session:
                nguon = await tao_nguon(
                    session,
                    clinic_id,
                    ten=ten,
                    loai="file",
                    dinh_dang=dinh_dang,
                    duong_dan=duong_dan,
                    so_byte=len(data),
                )
        except BaseException:
            await asyncio.to_thread(xoa_file, duong_dan, data_dir=self._data_dir)
            raise
        log.info(
            "tạo nguồn kho tri thức (upload file)", source_id=nguon.id, dinh_dang=dinh_dang, so_byte=len(data)
        )
        return _dto(nguon)

    async def get_source(self, clinic_id: UUID, source_id: str) -> KbSource | None:
        async with self._db.session(clinic_id) as session:
            nguon = await lay_nguon(session, clinic_id, source_id)
        return _dto(nguon) if nguon is not None else None

    async def list_sources(self, clinic_id: UUID) -> list[KbSource]:
        async with self._db.session(clinic_id) as session:
            return [_dto(n) for n in await danh_sach_nguon_gon(session, clinic_id)]

    async def count_agents_by_source(self, clinic_id: UUID) -> dict[str, int]:
        """``soAgent`` of the list screen: ``0`` (no key) is the only thing that tells "chunked and ready"
        from "usable by the bot". Not in the contract DTO yet (open item)."""
        async with self._db.session(clinic_id) as session:
            return await dem_agent_theo_nguon(session, clinic_id)

    async def set_status(
        self,
        clinic_id: UUID,
        source_id: str,
        status: KbSourceStatus,
        *,
        error: str = "",
        chunk_count: int | None = None,
    ) -> None:
        async with self._db.session(clinic_id) as session:
            await dat_trang_thai(session, clinic_id, source_id, status.value, loi=error, so_doan=chunk_count)

    async def delete_source(self, clinic_id: UUID, source_id: str) -> int:
        # Read ``storage_key`` BEFORE deleting the row - deleting the row first loses the way to the file and
        # the disk swells forever with orphan files nothing can clean any more.
        async with self._db.session(clinic_id) as session:
            nguon = await lay_nguon(session, clinic_id, source_id)
            if nguon is None:
                raise _khong_tim_thay()
            so_doan_da_xoa = await xoa_nguon(session, clinic_id, source_id)
        await asyncio.to_thread(xoa_file, nguon.duong_dan, data_dir=self._data_dir)
        log.info("xóa nguồn kho tri thức", source_id=source_id)
        return so_doan_da_xoa

    async def reindex_source(self, clinic_id: UUID, source_id: str) -> None:
        async with self._db.session(clinic_id) as session:
            nguon = await lay_nguon(session, clinic_id, source_id)
            if nguon is None:
                raise _khong_tim_thay()
            # I6: pressing "Xử lý lại" EXACTLY while the source is dang_xu_ly (a worker really processing it,
            # or stuck waiting for ``go_nguon_ket_dau_tick`` to judge it) used to be SWALLOWED silently - the
            # route set cho_xu_ly at once, then the round already running wrote its final state on top and
            # erased the decision just taken. Refuse clearly instead of fighting for the state quietly.
            #
            # This conflict is TEMPORARY, not a dead end: ``go_nguon_ket_dau_tick`` runs again EVERY tick, so
            # a source stuck in dang_xu_ly by a worker past its deadline also leaves this state in the end -
            # but the upper bound is NOT one TICK_MS: a source really running keeps dang_xu_ly until the end
            # of KB_EXTRACT_TIMEOUT_MS of its own round, so the real upper bound is TICK_MS +
            # KB_EXTRACT_TIMEOUT_MS (at most 605s with the two default ceilings). "Thử lại sau ít phút" stays
            # right.
            if nguon.trang_thai == "dang_xu_ly":
                raise DomainError(ErrorCode.INVALID_STATE, "Nguồn đang được xử lý, thử lại sau ít phút")
            # Grant a fresh attempts budget: this is a DELIBERATE action of the operator, not an automatic
            # retry - give the source a full chance, do not add up attempts spent last time.
            await dat_trang_thai(session, clinic_id, source_id, "cho_xu_ly", so_lan_thu=0)

    async def list_chunks(self, clinic_id: UUID, source_id: str, *, offset: int, limit: int) -> list[KbChunk]:
        async with self._db.session(clinic_id) as session:
            if await lay_nguon(session, clinic_id, source_id) is None:
                raise _khong_tim_thay()
            doan = await lay_doan_cua_nguon(session, clinic_id, source_id, offset, limit)
        return [KbChunk(order=d.thu_tu, title=d.tieu_de, content=d.noi_dung) for d in doan]

    async def count_chunks(self, clinic_id: UUID, source_id: str) -> int:
        async with self._db.session(clinic_id) as session:
            return await dem_doan(session, clinic_id, source_id)

    async def set_approved(self, clinic_id: UUID, source_id: str, approved: bool, *, by_user: UUID) -> None:
        async with self._db.session(clinic_id) as session:
            result = await session.execute(
                text(
                    "UPDATE agent.kb_document SET approved_by_clinical_owner = :a, "
                    "approved_by = CASE WHEN :a THEN CAST(:u AS uuid) ELSE NULL END, "
                    "approved_at = CASE WHEN :a THEN now() ELSE NULL END "
                    "WHERE clinic_id = :c AND id = :id RETURNING id"
                ),
                {"c": clinic_id, "id": source_id, "a": approved, "u": str(by_user)},
            )
            if result.first() is None:
                raise _khong_tim_thay()
        log.info("duyệt nguồn kho tri thức", source_id=source_id, approved=approved)

    # ------------------------------------------------------------------ bindings

    async def sources_of_agent(self, clinic_id: UUID, agent_id: str) -> list[str]:
        async with self._db.session(clinic_id) as session:
            return await nguon_cua_agent(session, clinic_id, agent_id)

    async def agents_of_source(self, clinic_id: UUID, source_id: str) -> list[str]:
        async with self._db.session(clinic_id) as session:
            if await lay_nguon(session, clinic_id, source_id) is None:
                raise _khong_tim_thay()
            return await agent_cua_nguon(session, clinic_id, source_id)

    async def set_sources_for_agent(self, clinic_id: UUID, agent_id: str, source_ids: list[str]) -> None:
        kiem_tra_danh_sach_id(source_ids, toi_da=SO_NGUON_TOI_DA_MOI_AGENT, ten="nguồn")
        try:
            async with self._db.session(clinic_id) as session:
                # I9 (TOCTOU): the existence checks and the write are in ONE transaction and the table has
                # foreign keys, so an agent/source deleted in between makes the INSERT fail instead of
                # leaving an orphan binding (the original had to read the body BEFORE checking for this).
                if not await agent_ton_tai(session, clinic_id, agent_id):
                    raise DomainError(ErrorCode.VALIDATION_FAILED, "Agent không tồn tại")
                ton_tai = await loc_id_ton_tai(session, clinic_id, source_ids)
                khong_ton_tai = [i for i in source_ids if i not in ton_tai]
                if khong_ton_tai:
                    # Without this the binding table accumulates junk ids, and the agent page shows a
                    # checkbox that points at a source that no longer exists.
                    raise DomainError(
                        ErrorCode.VALIDATION_FAILED, f"Nguồn không tồn tại: {', '.join(khong_ton_tai)}"
                    )
                await dat_nguon_cho_agent(session, clinic_id, agent_id, source_ids)
        except IntegrityError as err:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, "Agent hoặc nguồn vừa bị xóa, hãy tải lại trang"
            ) from err
        log.info("đặt lại nguồn kho tri thức cho agent", agent_id=agent_id, so_nguon=len(set(source_ids)))

    async def set_agents_for_source(self, clinic_id: UUID, source_id: str, agent_ids: list[str]) -> None:
        kiem_tra_danh_sach_id(agent_ids, toi_da=SO_AGENT_TOI_DA_MOI_NGUON, ten="agent")
        try:
            async with self._db.session(clinic_id) as session:
                if await lay_nguon(session, clinic_id, source_id) is None:
                    raise _khong_tim_thay()
                ton_tai = await ton_tai_cac_agent(session, clinic_id, agent_ids)
                khong_ton_tai = [i for i in agent_ids if i not in ton_tai]
                if khong_ton_tai:
                    # Reject the WHOLE request, never write the valid part and drop the rest: writing half
                    # shows the user "saved" while the real list differs from what they just ticked.
                    raise DomainError(
                        ErrorCode.VALIDATION_FAILED, f"Agent không tồn tại: {', '.join(khong_ton_tai)}"
                    )
                await dat_agent_cho_nguon(session, clinic_id, source_id, agent_ids)
        except IntegrityError as err:
            raise DomainError(
                ErrorCode.VALIDATION_FAILED, "Agent hoặc nguồn vừa bị xóa, hãy tải lại trang"
            ) from err
        log.info("đặt lại agent đọc được nguồn", source_id=source_id, so_agent=len(set(agent_ids)))

    # ------------------------------------------------------------------ search

    async def search(
        self,
        clinic_id: UUID,
        *,
        question: str,
        agent_id: str,
        limit: int = 5,
        chi_da_duyet: bool | None = None,
    ) -> list[KbHit]:
        """Hybrid keyword + vector search with RRF over the sources bound to ``agent_id`` (default-deny).

        ``chi_da_duyet=None`` derives "only doctor-approved sources" from the agent's own profile
        (``patient_channel`` -> True). A caller that knows the effective profile of the account (the more
        restrictive of agent and account) should pass it - this keyword is beyond the Protocol, which has no
        way to carry the account (open item for D4)."""
        # Embed BEFORE opening the database transaction: no connection is held while a model is called.
        vector = await nhung_cau_hoi(self._embedder, question)
        async with self._db.session(clinic_id) as session:
            ket_qua = await tim_trong_kho_tri_thuc(
                session,
                clinic_id,
                cau_hoi=question,
                agent_id=agent_id,
                so_luong=limit,
                vector_cau_hoi=vector,
                chi_da_duyet=chi_da_duyet,
            )
        return [
            KbHit(
                source_id=k.source_id,
                source_name=k.ten_nguon,
                title=k.tieu_de,
                content=k.noi_dung,
                score=k.diem,
            )
            for k in ket_qua
        ]

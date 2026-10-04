# ported from: src/knowledge/kb-ingest-worker.ts
"""Background processing loop of the knowledge base: read the text of a ``cho_xu_ly`` source -> cut chunks
-> embed -> save -> ``san_sang``. RUNS IN THE BACKGROUND, never inside the upload request - reading a 200
page PDF inside the handler would block the whole bot (no messages received, no turn run).

Extraction + chunking run in an isolated child process (see ``chay_trich_xuat_tach_luong``) - THIS file only
claims the source, calls the worker, then WRITES the database (the extraction process never opens a
connection).

Forced deviations:
* SQLite -> Postgres, sync -> async: the worker is a class bound to a ``ClinicDatabase`` (role
  ``agent_worker``) and every pass is for ONE clinic (``clinic_id``); the process that loops over
  ``ctx.list_active_clinic_ids()`` is ``pema.workers.kb_ingest_worker``. Each step uses its OWN short
  transaction: the claim COMMITS before the (possibly minutes long) extraction, so no database transaction
  is held open while a document is parsed;
* "one process, one ``dangChayVong`` flag" -> a Postgres advisory lock per clinic held for the whole pass
  (``_khoa_vong``): two worker processes cannot run a pass for the same clinic at the same time, which is
  the assumption ``go_nguon_ket_dau_tick`` relies on (it resets EVERY ``dang_xu_ly`` source, so it must
  never run while another process is really processing one). The in-process flag stays too;
* NEW step: after extraction the chunks are embedded (bge-m3) when an embedding client is configured. A
  failing embedding endpoint does NOT fail the source: the chunks are stored without vectors and found by
  the keyword side (``reindex`` fills them later).
* the I4 race (source deleted while the worker awaits extraction) is closed twice: the existence check kept
  from the original, and the foreign key ``ON DELETE CASCADE`` that makes an orphan chunk impossible.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import UUID

from sqlalchemy import text

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.core.db import ClinicDatabase
from pema.knowledge.chay_trich_xuat_tach_luong import (
    LoiTrichXuatBiNgatGiuaChung,
    trich_xuat_tach_luong,
)
from pema.knowledge.chunk_text import ThamSoCat
from pema.knowledge.doc_text_extract import DinhDangKb, la_dinh_dang_ho_tro
from pema.knowledge.don_doan_mo_coi import don_doan_mo_coi
from pema.knowledge.kb_chunk_store import luu_doan, van_ban_de_nhung
from pema.knowledge.kb_file_store import doc_file
from pema.knowledge.kb_source_queries import (
    KbSourceTomTat,
    gianh_nguon_cho_xu_ly,
    lay_nguon_theo_trang_thai,
)
from pema.knowledge.kb_source_store import dat_trang_thai, lay_nguon
from pema.shared.logger import create_logger
from pema_contracts.knowledge import EmbeddingClient

log = create_logger("kb-ingest-worker")

# Scan every 5s: the source table is tiny so scanning often costs nothing noticeable and only affects the
# maximum delay before a freshly uploaded source is picked up. Not a tuning parameter (not something an
# operator needs to change live, unlike SCHEDULER_TICK_MS which directly affects the delay of a customer
# message).
TICK_MS: Final = 5000


@dataclass(frozen=True, slots=True)
class CaiDatIngest:
    """The tuning values one pass needs, read at the START of each source (the original read
    ``getTuning`` each
    time: changing a value on the dashboard takes effect without a restart). ``tu_tuning`` reads them; tests
    build one by hand to reach values below the operator-facing floor (the "real timeout branch" test)."""

    tran_lan_thu: int
    co_doan_toi_da: int
    chong_lan: int
    han_ms: int
    tran_ram_mb: int

    @classmethod
    def tu_tuning(cls) -> CaiDatIngest:
        return cls(
            tran_lan_thu=get_tuning_int("KB_MAX_INGEST_ATTEMPTS"),
            co_doan_toi_da=get_tuning_int("KB_CHUNK_CHARS"),
            chong_lan=get_tuning_int("KB_CHUNK_OVERLAP_PERCENT"),
            han_ms=get_tuning_int("KB_EXTRACT_TIMEOUT_MS"),
            tran_ram_mb=get_tuning_int("KB_EXTRACT_MAX_RAM_MB"),
        )


def khoa_advisory(clinic_id: UUID) -> int:
    digest = hashlib.blake2b(f"kb-ingest:{clinic_id}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


class KbIngestWorker:
    def __init__(
        self,
        db: ClinicDatabase,
        *,
        embedder: EmbeddingClient | None = None,
        data_dir: Path | None = None,
        cai_dat: CaiDatIngest | None = None,
    ) -> None:
        self._db = db
        self._embedder = embedder
        self._data_dir = data_dir
        self._cai_dat = cai_dat
        self._dang_chay_vong: set[UUID] = set()

    def _cai_dat_hien_tai(self) -> CaiDatIngest:
        return self._cai_dat if self._cai_dat is not None else CaiDatIngest.tu_tuning()

    async def _danh_hong(self, clinic_id: UUID, source_id: str, loi: str) -> None:
        try:
            async with self._db.session(clinic_id) as session:
                await dat_trang_thai(session, clinic_id, source_id, "hong", loi=loi)
        except Exception as err:
            log.error("không ghi được trạng thái hong của nguồn", err=err, source_id=source_id)

    async def _nhung_cac_doan(self, doan_noi_dung: list[str]) -> list[list[float]] | None:
        if self._embedder is None or not doan_noi_dung:
            return None
        try:
            return await self._embedder.embed(doan_noi_dung)
        except Exception as err:
            log.warning("embedding đoạn thất bại, lưu đoạn không có vector", err=err)
            return None

    async def xu_ly_mot_nguon(self, clinic_id: UUID, n: KbSourceTomTat) -> None:
        cai_dat = self._cai_dat_hien_tai()
        try:
            # Claim CONDITIONALLY (compare-then-change atomic, raising ``attempts``) - see
            # ``gianh_nguon_cho_xu_ly``. A failed claim (``False``) SKIPS the source entirely: it was
            # claimed/processed by another round, or has run out of attempts.
            #
            # INSIDE the try (I8) - must NOT sit before it: the claim is a real UPDATE that can RAISE for an
            # SQL reason (not the ordinary "claim failed"). Raised outside the try it would leave
            # ``xu_ly_mot_vong`` and abandon the WHOLE scan - the sources processed AFTER the faulty one
            # would never be examined.
            async with self._db.session(clinic_id) as session:
                gianh_duoc = await gianh_nguon_cho_xu_ly(session, clinic_id, n.id, cai_dat.tran_lan_thu)
            if not gianh_duoc:
                return

            dinh_dang: DinhDangKb
            if n.loai == "text":
                # ``noi_dung_goc`` is read back ONLY AFTER claiming, for EXACTLY ONE source at a time - the
                # "cho_xu_ly" list does NOT pull this column (I5: 8 sources x 5 million characters = +30 MB
                # for one call if the snapshot pulled the full text of EVERY waiting source into RAM at once).
                async with self._db.session(clinic_id) as session:
                    day = await lay_nguon(session, clinic_id, n.id)
                if day is None:
                    return  # deleted between the claim and the re-read - rare but safe
                buf = day.noi_dung_goc.encode("utf-8")
                dinh_dang = "txt"  # typed content is already plain text: the "txt" meaning of doc_chu_tu_file
            else:
                if not la_dinh_dang_ho_tro(n.dinh_dang):
                    raise ValueError(f'Định dạng "{n.dinh_dang}" chưa được hỗ trợ')
                buf = await asyncio.to_thread(doc_file, n.duong_dan, data_dir=self._data_dir)
                dinh_dang = n.dinh_dang

            ket = await trich_xuat_tach_luong(
                buf=buf,
                dinh_dang=dinh_dang,
                tham_so_cat=ThamSoCat(co_doan_toi_da=cai_dat.co_doan_toi_da, chong_lan=cai_dat.chong_lan),
                han_ms=cai_dat.han_ms,
                tran_ram_mb=cai_dat.tran_ram_mb,
            )
            doan = ket.doan

            vectors = await self._nhung_cac_doan([van_ban_de_nhung(n.ten, d) for d in doan])

            async with self._db.session(clinic_id) as session:
                # I4: a DELETE can slip in EXACTLY while the worker is awaiting extraction - the source is
                # gone then the chunks must NOT be written (they would be orphans forever; here the foreign
                # key would also refuse the insert).
                if await lay_nguon(session, clinic_id, n.id) is None:
                    return

                # I7: extracting TEXT does not mean being able to cut CHUNKS - a document of headings only
                # (no body) or an empty .txt/.md returns valid text (not empty, or no raise in the
                # extractor) while ``cat_thanh_doan()`` gives an EMPTY list. Without this guard the source
                # becomes "Sẵn sàng, 0 đoạn" - ``kb_search`` never returns anything for it and nobody knows
                # why. Raising here falls into the "ordinary extraction error" branch below ("hong" at
                # once, not waiting for ``attempts`` to run out - empty content stays empty however many
                # times it is retried).
                if not doan:
                    raise ValueError(
                        "Tài liệu không có nội dung để cắt đoạn (có thể chỉ chứa tiêu đề hoặc trống)"
                    )

                await luu_doan(session, clinic_id, n.id, doan, n.ten, vectors)
                # Just processed DONE - grant a fresh attempts budget, exactly the reason for the reset in
                # ``dat_trang_thai``: ``attempts`` does not go back by itself with the state, it must be
                # passed explicitly.
                await dat_trang_thai(
                    session, clinic_id, n.id, "san_sang", loi="", so_doan=len(doan), so_lan_thu=0
                )
        except LoiTrichXuatBiNgatGiuaChung as err:
            # The worker was forced to stop (past the deadline or died abnormally) - we do NOT KNOW whether
            # the document is truly broken or the machine was just slow/short of memory, so we do NOT mark
            # "hong" at once: leave "dang_xu_ly" (set by ``gianh_nguon_cho_xu_ly``) and wait for
            # ``go_nguon_ket_dau_tick`` (reads ``attempts``, runs AT THE START OF EVERY TICK - not only on a
            # restart, see the docstring of that function) to decide to retry or give up.
            log.warning("worker trích xuất kho tri thức bị dừng giữa chừng", source_id=n.id, loi=str(err))
        except Exception as err:
            # An ORDINARY extraction error (broken file, unknown format, no text at all) - mark "hong" AT
            # ONCE, not waiting for ``attempts`` to run out: broken content stays broken however many times
            # it is retried, same behaviour as before this phase.
            loi = str(err) or type(err).__name__
            log.warning("xử lý nguồn kho tri thức thất bại", source_id=n.id)
            await self._danh_hong(clinic_id, n.id, loi)

    async def xu_ly_mot_vong(self, clinic_id: UUID) -> None:
        """Process every source in ``cho_xu_ly``; one broken source does not stop the round."""
        async with self._db.session(clinic_id) as session:
            dang_cho = await lay_nguon_theo_trang_thai(session, clinic_id, "cho_xu_ly")
        for n in dang_cho:
            await self.xu_ly_mot_nguon(clinic_id, n)
            # Yield the event loop between EVERY source - extraction runs in its own process (no longer
            # blocks the main loop when the CPU is heavy) but claiming/reading the file/writing the
            # database is still on the main loop, and yielding between sources is cheap.
            await asyncio.sleep(0)

    async def go_nguon_ket_dau_tick(self, clinic_id: UUID) -> None:
        """Called AT THE START OF EVERY TICK (through ``chay_mot_vong_an_toan`` below), NOT only at boot:
        every ``dang_xu_ly`` left behind - from the previous start (worker killed midway) OR from the tick
        right before (the worker killed by its deadline - the catch in ``xu_ly_mot_nguon`` deliberately LEAVES
        ``dang_xu_ly``) - is judged by ``attempts``: under the ceiling it goes back to ``cho_xu_ly`` and
        ``xu_ly_mot_vong()`` (called RIGHT AFTER in the SAME ``chay_mot_vong_an_toan``, not on the next tick)
        queries ``cho_xu_ly`` again, so it claims and retries IN THIS VERY TICK; at the ceiling it goes
        straight to ``hong`` - no ENDLESS retry (C3).

        BEFORE the fix that called it only at boot: a source past its deadline AFTER boot stayed
        ``dang_xu_ly`` FOREVER (the reindex route refuses every ``dang_xu_ly`` with 409 - only deleting the
        source or restarting the bot was left). Calling it every tick makes that 409 TEMPORARY, BUT the upper
        bound is NOT one ``TICK_MS``: a source REALLY running keeps ``dang_xu_ly`` until the end of
        ``KB_EXTRACT_TIMEOUT_MS`` of its own round, so the real upper bound is ``TICK_MS +
        KB_EXTRACT_TIMEOUT_MS`` (at most 605s with the two default ceilings)."""
        tran_lan_thu = self._cai_dat_hien_tai().tran_lan_thu
        async with self._db.session(clinic_id) as session:
            ket = await lay_nguon_theo_trang_thai(session, clinic_id, "dang_xu_ly")
            for n in ket:
                if n.so_lan_thu >= tran_lan_thu:
                    await dat_trang_thai(
                        session,
                        clinic_id,
                        n.id,
                        "hong",
                        loi=(
                            "Nguồn này làm worker treo hoặc dừng bất thường liên tiếp - "
                            f"đã thử {n.so_lan_thu} lần, dừng xử lý."
                        ),
                    )
                else:
                    await dat_trang_thai(session, clinic_id, n.id, "cho_xu_ly")

    @contextlib.asynccontextmanager
    async def _khoa_vong(self, clinic_id: UUID) -> AsyncGenerator[bool]:
        """A Postgres advisory lock for the pass of ONE clinic, on a dedicated connection held for the whole
        pass; yields ``False`` when another process already holds it."""
        async with self._db.engine.connect() as conn:
            khoa = khoa_advisory(clinic_id)
            lay_duoc = bool(
                (await conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": khoa})).scalar()
            )
            try:
                yield lay_duoc
            finally:
                if lay_duoc:
                    await conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": khoa})
                await conn.rollback()

    async def chay_mot_vong_an_toan(self, clinic_id: UUID) -> None:
        """A complete tick: release the sources left stuck in ``dang_xu_ly`` by the previous tick/start FIRST,
        only then process the ``cho_xu_ly`` sources - public so a test can call it directly instead of waiting
        for the real ``TICK_MS``.

        Prevents two rounds overlapping: a big source (a PDF of hundreds of pages) can take longer than
        ``TICK_MS``, and the next tick firing while the previous round is still unfinished is skipped - the
        conditional claim above is already SAFE without this flag (no source processed twice), but without
        it scanning is duplicated every 5s. The SAME guard makes sure ``go_nguon_ket_dau_tick()`` NEVER runs
        while another source is REALLY being processed in THIS very tick (a new tick only starts after the
        previous one is completely done) - it only releases exactly the sources stuck from the previous
        tick/start. ACROSS processes the advisory lock gives the same guarantee."""
        if clinic_id in self._dang_chay_vong:
            return
        self._dang_chay_vong.add(clinic_id)
        try:
            async with self._khoa_vong(clinic_id) as lay_duoc:
                if not lay_duoc:
                    return
                await self.go_nguon_ket_dau_tick(clinic_id)
                await self.xu_ly_mot_vong(clinic_id)
        finally:
            self._dang_chay_vong.discard(clinic_id)

    async def don_luc_khoi_dong(self, clinic_id: UUID) -> None:
        async with self._db.session(clinic_id) as session:
            ket = await don_doan_mo_coi(session, clinic_id)
        if ket.so_doan > 0:
            log.info(
                "đã dọn đoạn mồ côi (nguồn gốc đã bị xóa) lúc khởi động",
                so_doan=ket.so_doan,
                so_hang_fts=ket.so_hang_fts,
            )

    async def bat_dau_worker(self, clinic_ids: list[UUID]) -> None:
        """Boot work of the original ``batDauWorker`` for the given clinics: sweep the orphan chunks, then
        run one pass at once (a source uploaded while the bot was restarting does not wait for the first
        ``TICK_MS``; that first pass ALSO releases every ``dang_xu_ly`` stuck from the previous run). The
        loop itself - repeating every ``TICK_MS`` over ``ctx.list_active_clinic_ids()`` and stopping on a
        signal - is ``pema.workers.kb_ingest_worker``."""
        for clinic_id in clinic_ids:
            await self.don_luc_khoi_dong(clinic_id)
            await self.chay_mot_vong_an_toan(clinic_id)

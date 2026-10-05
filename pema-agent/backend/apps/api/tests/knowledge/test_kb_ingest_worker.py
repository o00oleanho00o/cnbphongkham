# ported from: src/knowledge/kb-ingest-worker.test.ts
"""Forced deviations: SQLite -> Postgres (a database per test module, ``kb`` fixture); the worker thread ->
a child process (every test that processes a source starts a real one); ``data_dir`` is a ``tmp_path``."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from sqlalchemy import text

from pema.knowledge.chunk_text import DoanMoi
from pema.knowledge.kb_chunk_store import luu_doan
from pema.knowledge.kb_file_store import luu_file
from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_slow_docx_test_fixture import bom_quay_cpu_docx
from pema.knowledge.kb_source_store import KbSource, dat_trang_thai, lay_nguon, tao_nguon, xoa_nguon
from pema.knowledge.kb_test_support import KbHarness
from pema.shared.bo_dau_tieng_viet import bo_dau_tieng_viet
from pema.shared.doi_cho_den_khi import WaitOptions, doi_cho_den_khi

pytestmark = pytest.mark.db


def cai_dat(**ghi_de: int) -> CaiDatIngest:
    mac_dinh = {
        "tran_lan_thu": 2,
        "co_doan_toi_da": 1200,
        "chong_lan": 10,
        "han_ms": 60_000,
        "tran_ram_mb": 192,
    }
    return CaiDatIngest(**{**mac_dinh, **ghi_de})


def tao_worker(kb: KbHarness, tmp_path: Path) -> KbIngestWorker:
    return KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=cai_dat())


async def lay(kb: KbHarness, id_: str) -> KbSource:
    async with kb.session() as s:
        n = await lay_nguon(s, kb.clinic_id, id_)
    assert n is not None
    return n


async def noi_dung_doan_cua_nguon(kb: KbHarness, source_id: str) -> list[str]:
    with kb.kb_database.admin_engine.connect() as conn:
        result = conn.execute(
            text("SELECT content FROM agent.kb_chunk WHERE source_id = :s ORDER BY ord"), {"s": source_id}
        )
        return [r[0] for r in result]


async def test_kb_ingest_worker_process_a_pending_source_is_chunked_then_becomes_ready(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nguồn cho_xu_ly được cắt đoạn rồi chuyển sang san_sang"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="# Bảo hành\n\n12 tháng.")
    await tao_worker(kb, tmp_path).xu_ly_mot_vong()
    sau = await lay(kb, n.id)
    assert sau.trang_thai == "san_sang"
    assert sau.so_doan > 0


async def test_kb_ingest_worker_process_a_broken_file_is_marked_hong_with_a_readable_sentence_not_stuck(
    kb: KbHarness, tmp_path: Path
) -> None:
    """file hỏng thì trạng thái hong kèm câu tiếng Việt đọc được, KHÔNG kẹt ở dang_xu_ly"""
    async with kb.session() as s:
        n = await tao_nguon(
            s,
            kb.clinic_id,
            ten="hỏng",
            loai="file",
            dinh_dang="pdf",
            duong_dan=luu_file("h", "pdf", b"khong phai pdf", data_dir=tmp_path),
        )
    await tao_worker(kb, tmp_path).xu_ly_mot_vong()
    sau = await lay(kb, n.id)
    assert sau.trang_thai == "hong"
    assert "không đọc được" in sau.loi.lower()


async def test_kb_ingest_worker_process_one_broken_source_does_not_block_the_others_in_the_same_round(
    kb: KbHarness, tmp_path: Path
) -> None:
    """một nguồn hỏng KHÔNG chặn các nguồn còn lại trong cùng vòng"""
    async with kb.session() as s:
        hong = await tao_nguon(
            s,
            kb.clinic_id,
            ten="hỏng",
            loai="file",
            dinh_dang="pdf",
            duong_dan=luu_file("h2", "pdf", b"rac", data_dir=tmp_path),
        )
        tot = await tao_nguon(s, kb.clinic_id, ten="tốt", loai="text", noi_dung_goc="# Giá\n\n25.000đ")
    await tao_worker(kb, tmp_path).xu_ly_mot_vong()
    assert (await lay(kb, hong.id)).trang_thai == "hong"
    assert (await lay(kb, tot.id)).trang_thai == "san_sang", "một nguồn hỏng không được kéo cả vòng chết theo"


async def test_kb_ingest_worker_process_a_source_not_pending_is_left_alone_ready_stays_ready(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nguồn không nằm ở cho_xu_ly thì KHÔNG bị đụng vào (san_sang giữ nguyên)"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="đã xong", loai="text", noi_dung_goc="abc")
        await dat_trang_thai(s, kb.clinic_id, n.id, "san_sang", so_doan=3)
    await tao_worker(kb, tmp_path).xu_ly_mot_vong()
    sau = await lay(kb, n.id)
    assert sau.trang_thai == "san_sang"
    assert sau.so_doan == 3


async def test_kb_ingest_worker_process_a_source_stuck_in_dang_xu_ly_from_a_previous_run_is_reset(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nguồn kẹt ở dang_xu_ly từ lần chạy trước được đặt lại lúc khởi động"""
    # A worker that died midway (process killed) leaves the source in ``dang_xu_ly`` for ever and it is
    # never processed again - it must release itself at the start.
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="kẹt", loai="text", noi_dung_goc="x")
        await dat_trang_thai(s, kb.clinic_id, n.id, "dang_xu_ly")
    await tao_worker(kb, tmp_path).go_nguon_ket_dau_tick()
    assert (await lay(kb, n.id)).trang_thai == "cho_xu_ly"


async def test_kb_ingest_worker_process_go_nguon_ket_dau_tick_does_not_touch_other_states(
    kb: KbHarness, tmp_path: Path
) -> None:
    """goNguonKetDauTick KHÔNG đụng nguồn đang ở trạng thái khác"""
    async with kb.session() as s:
        san_sang = await tao_nguon(s, kb.clinic_id, ten="a", loai="text", noi_dung_goc="x")
        await dat_trang_thai(s, kb.clinic_id, san_sang.id, "san_sang", so_doan=1)
    await tao_worker(kb, tmp_path).go_nguon_ket_dau_tick()
    assert (await lay(kb, san_sang.id)).trang_thai == "san_sang"


async def test_kb_ingest_worker_orphan_race_the_worker_does_not_write_chunks_for_a_source_deleted_midway(
    kb: KbHarness, tmp_path: Path
) -> None:
    """worker KHÔNG ghi đoạn cho nguồn đã bị xóa giữa chừng"""
    # The real window: the worker is awaiting extraction (a real child process, a real await) and the
    # DELETE route slips in BEFORE the result comes back. A slow-ish docx keeps the window open.
    async with kb.session() as s:
        n = await tao_nguon(
            s,
            kb.clinic_id,
            ten="x",
            loai="file",
            dinh_dang="docx",
            duong_dan=luu_file("cham", "docx", bom_quay_cpu_docx(60_000), data_dir=tmp_path),
        )
    chay = asyncio.create_task(tao_worker(kb, tmp_path).xu_ly_mot_vong())
    await doi_cho_den_khi(
        lambda: (
            kb.kb_database.scalar("SELECT status FROM agent.kb_document WHERE id = :id", {"id": n.id})
            == "dang_xu_ly"
        ),
        WaitOptions(mo_ta="nguồn được giành"),
    )
    async with kb.session() as s:
        await xoa_nguon(s, kb.clinic_id, n.id)
    await chay
    assert kb.kb_database.scalar("SELECT count(*) FROM agent.kb_chunk") == 0, (
        "nguồn bị xóa giữa chừng thì KHÔNG được ghi đoạn - đoạn ghi xong sẽ mồ côi vĩnh viễn"
    )


async def test_kb_ingest_worker_claim_error_an_error_while_claiming_does_not_abandon_the_whole_scan(
    kb: KbHarness, tmp_path: Path
) -> None:
    """giaNguonChoXuLy ném lỗi cho MỘT nguồn: nguồn đó được đánh hong, nguồn còn lại vẫn xử lý bình thường"""
    async with kb.session() as s:
        khoe_manh = await tao_nguon(
            s, kb.clinic_id, ten="khỏe mạnh", loai="text", noi_dung_goc="# Tiêu đề\n\nabc"
        )
        loi = await tao_nguon(s, kb.clinic_id, ten="sẽ lỗi lúc giành", loai="text", noi_dung_goc="def")

    # The trigger blocks ONLY the claim (the move to dang_xu_ly) of ONE source - not the "hong" write the
    # catch uses to recover. A real SQL error at exactly the claim step: before fix I8 the claim sat OUTSIDE
    # the try and the error abandoned the whole scan, the sources processed AFTER were never examined.
    kb.kb_database.execute(
        "CREATE FUNCTION agent.gia_lap_loi_gianh() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN "
        "RAISE EXCEPTION 'gia lap loi gianh nguon'; END $$"
    )
    kb.kb_database.execute(
        "CREATE TRIGGER gia_lap_loi_gianh BEFORE UPDATE OF status ON agent.kb_document "
        "FOR EACH ROW WHEN (NEW.status = 'dang_xu_ly' AND NEW.id = '" + loi.id + "') "
        "EXECUTE FUNCTION agent.gia_lap_loi_gianh()"
    )
    try:
        await tao_worker(kb, tmp_path).xu_ly_mot_vong()  # must not raise
    finally:
        kb.kb_database.execute("DROP TRIGGER gia_lap_loi_gianh ON agent.kb_document")
        kb.kb_database.execute("DROP FUNCTION agent.gia_lap_loi_gianh()")

    assert (await lay(kb, khoe_manh.id)).trang_thai == "san_sang", "nguồn khỏe mạnh bị nguồn lỗi kéo theo"
    assert (await lay(kb, loi.id)).trang_thai == "hong", "nguồn lỗi giành phải được đánh hong"


async def test_kb_ingest_worker_overlapping_rounds_a_round_with_an_old_snapshot_does_not_overwrite_what_another_round_finished(
    kb: KbHarness, tmp_path: Path
) -> None:
    """vòng A giữ snapshot cũ không được ghi đè nguồn mà vòng B đã xử lý xong trong lúc A còn dở"""
    # y is created BEFORE x, then ``created_at`` is forced so x ALWAYS heads the snapshot (ORDER BY created_at
    # DESC) and y comes after. Round A stays "stuck" at x (a real await on the slow extraction) while we
    # simulate round B having already finished y.
    async with kb.session() as s:
        y = await tao_nguon(s, kb.clinic_id, ten="y", loai="text", noi_dung_goc="# Giờ làm việc\n\n8h - 21h")
        x = await tao_nguon(
            s,
            kb.clinic_id,
            ten="x",
            loai="file",
            dinh_dang="docx",
            duong_dan=luu_file("cham", "docx", bom_quay_cpu_docx(60_000), data_dir=tmp_path),
        )
    kb.kb_database.execute(
        "UPDATE agent.kb_document SET created_at = '2020-01-01T00:00:00.000Z' WHERE id = :id", {"id": y.id}
    )
    kb.kb_database.execute(
        "UPDATE agent.kb_document SET created_at = '2020-01-01T00:00:00.001Z' WHERE id = :id", {"id": x.id}
    )

    luot_a = asyncio.create_task(tao_worker(kb, tmp_path).xu_ly_mot_vong())
    await doi_cho_den_khi(
        lambda: (
            kb.kb_database.scalar("SELECT status FROM agent.kb_document WHERE id = :id", {"id": x.id})
            == "dang_xu_ly"
        ),
        WaitOptions(mo_ta="x được giành"),
    )

    # Simulate round B: it claimed and finished y.
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, y.id, [DoanMoi(0, "", "đã xử lý bởi lượt B")])
        await dat_trang_thai(s, kb.clinic_id, y.id, "san_sang", so_doan=1)

    await luot_a

    # Round A finally reached y (from the OLD snapshot, when y was cho_xu_ly). If it could claim again it
    # would overwrite it with its own re-cut. Measure the CONTENT, not just the count: both branches give
    # exactly 1 chunk.
    assert await noi_dung_doan_cua_nguon(kb, y.id) == ["đã xử lý bởi lượt B"], (
        "vòng A giành lại và xử lý CHỒNG lên y dù vòng B đã xong"
    )
    assert (await lay(kb, y.id)).trang_thai == "san_sang"


async def test_kb_ingest_worker_source_name_enters_the_index_through_the_real_production_junction(
    kb: KbHarness, tmp_path: Path
) -> None:
    """worker thật (loai: text) ghi tên nguồn vào cột phang, không phải chỉ test tự mô phỏng lại thao tác"""
    # The source name shares no word with the content - if the folded column matched only through an
    # accidental overlap this test would measure nothing.
    ten = "Chính sách vận hành xưởng ABC"
    async with kb.session() as s:
        n = await tao_nguon(
            s,
            kb.clinic_id,
            ten=ten,
            loai="text",
            noi_dung_goc="Điều khoản riêng tư không liên quan chuyện khác.",
        )

    await tao_worker(kb, tmp_path).xu_ly_mot_vong()

    assert (await lay(kb, n.id)).trang_thai == "san_sang"
    with kb.kb_database.admin_engine.connect() as conn:
        rows = [
            r[0]
            for r in conn.execute(text("SELECT folded FROM agent.kb_chunk WHERE source_id = :s"), {"s": n.id})
        ]
    assert rows, "phải có ít nhất một đoạn được ghi"
    ten_da_bo_dau = bo_dau_tieng_viet(ten)
    assert all(ten_da_bo_dau in r for r in rows), (
        f'folded phải chứa tên nguồn đã bỏ dấu "{ten_da_bo_dau}": {rows}'
    )

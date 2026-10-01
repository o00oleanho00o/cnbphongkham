# ported from: src/knowledge/kb-ingest-worker-empty-chunks.test.ts
"""The case "extraction gives TEXT but chunking gives an EMPTY list" (I7) - three different shapes must all
end "hong" with a readable Vietnamese sentence, never leak as "san_sang, 0 chunks" (a source that looks ready
but ``kb_search`` never returns anything for).

All three go through ``doc_chu_tu_file`` WITHOUT raising (text not empty, or not empty in the extractor's
sense) - only ``cat_thanh_doan`` sees 0 chunks. The test pins the INVARIANT "empty chunks are always
blocked", not one specific input.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pema.knowledge.kb_file_store import luu_file
from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_source_store import KbSource, lay_nguon, tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db

CAI_DAT = CaiDatIngest(tran_lan_thu=2, co_doan_toi_da=1200, chong_lan=10, han_ms=60_000, tran_ram_mb=192)


async def xu_ly(kb: KbHarness, tmp_path: Path, id_: str) -> KbSource:
    await KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CAI_DAT).xu_ly_mot_vong(kb.clinic_id)
    async with kb.session() as s:
        n = await lay_nguon(s, kb.clinic_id, id_)
    assert n is not None
    return n


async def test_tai_lieu_trich_ra_rong_typed_text_with_only_a_heading_and_no_body_is_hong(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nội dung gõ tay CHỈ có heading, không thân bài ("# Chính sách bảo hành") -> hong"""
    async with kb.session() as s:
        n = await tao_nguon(
            s, kb.clinic_id, ten="chỉ tiêu đề", loai="text", noi_dung_goc="# Chính sách bảo hành"
        )
    sau = await xu_ly(kb, tmp_path, n.id)
    assert sau.trang_thai == "hong", "chữ trích ra KHÔNG rỗng nhưng cắt đoạn ra 0 - phải bị chặn"
    assert "không có nội dung để cắt đoạn" in sau.loi.lower()


async def test_tai_lieu_trich_ra_rong_an_empty_txt_file_is_hong_not_ready_with_0_chunks(
    kb: KbHarness, tmp_path: Path
) -> None:
    """file .txt RỖNG -> hong, không phải san_sang 0 đoạn"""
    async with kb.session() as s:
        n = await tao_nguon(
            s,
            kb.clinic_id,
            ten="txt rỗng",
            loai="file",
            dinh_dang="txt",
            duong_dan=luu_file("rong", "txt", b"", data_dir=tmp_path),
        )
    sau = await xu_ly(kb, tmp_path, n.id)
    assert sau.trang_thai == "hong"
    assert "không có nội dung để cắt đoạn" in sau.loi.lower()


async def test_tai_lieu_trich_ra_rong_typed_text_of_headings_only_is_hong(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nội dung gõ tay TOÀN heading, không mục nào có thân ("# A\\n\\n## B\\n\\n### C") -> hong"""
    async with kb.session() as s:
        n = await tao_nguon(
            s, kb.clinic_id, ten="toàn tiêu đề", loai="text", noi_dung_goc="# A\n\n## B\n\n### C"
        )
    sau = await xu_ly(kb, tmp_path, n.id)
    assert sau.trang_thai == "hong"
    assert "không có nội dung để cắt đoạn" in sau.loi.lower()


async def test_tai_lieu_trich_ra_rong_content_with_a_real_body_is_still_ready_the_guard_is_not_overzealous(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nội dung CÓ thân bài thật thì vẫn san_sang bình thường - phép chặn không quá tay"""
    async with kb.session() as s:
        n = await tao_nguon(
            s,
            kb.clinic_id,
            ten="có thân bài",
            loai="text",
            noi_dung_goc="# Bảo hành\n\n12 tháng kể từ ngày mua",
        )
    sau = await xu_ly(kb, tmp_path, n.id)
    assert sau.trang_thai == "san_sang"
    assert sau.so_doan > 0

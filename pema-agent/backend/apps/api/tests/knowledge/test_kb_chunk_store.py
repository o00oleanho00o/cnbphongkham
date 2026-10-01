# ported from: src/knowledge/kb-chunk-store.test.ts
"""Forced deviation (SQLite -> Postgres): chunk and full-text index are one table, so the "FTS row has the
rowid of the chunk" and "no orphan FTS row" tests become "the full-text column is in step with the chunk"."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from pema.knowledge.chunk_text import DoanMoi
from pema.knowledge.kb_chunk_store import dem_doan, lay_doan_cua_nguon, lay_doan_theo_id, luu_doan
from pema.knowledge.kb_source_store import tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db


async def _nguon(kb: KbHarness, ten: str = "nguồn test") -> str:
    async with kb.session() as s:
        return (await tao_nguon(s, kb.clinic_id, ten=ten, loai="text", noi_dung_goc="x")).id


async def test_kb_chunk_store_save_replaces_the_first_save_not_accumulating(kb: KbHarness) -> None:
    """lưu đoạn lần hai THAY THẾ lần đầu, không cộng dồn"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "bản cũ")])
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "bản mới")])
    async with kb.session() as s:
        assert await dem_doan(s, kb.clinic_id, id_) == 1


async def test_kb_chunk_store_save_twice_leaves_no_stale_full_text_entry(kb: KbHarness) -> None:
    """lưu đoạn lần hai KHÔNG để lại hàng FTS mồ côi"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "bản cũ")])
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "bản mới")])
    # The full-text vector is a generated column of the chunk row: the old text cannot still be searchable.
    cu = kb.kb_database.scalar("SELECT count(*) FROM agent.kb_chunk WHERE tsv @@ to_tsquery('simple', 'cu')")
    moi = kb.kb_database.scalar(
        "SELECT count(*) FROM agent.kb_chunk WHERE tsv @@ to_tsquery('simple', 'moi')"
    )
    assert (cu, moi) == (0, 1), "chỉ mục toàn văn của lần lưu đầu phải biến mất khi lưu đè lần hai"


async def test_kb_chunk_store_folded_column_has_folded_text_content_keeps_diacritics(kb: KbHarness) -> None:
    """cột phang chứa chữ đã bỏ dấu, noi_dung giữ nguyên dấu"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "Bảo hành 12 tháng")])
        row = (await s.execute(text("SELECT folded, content FROM agent.kb_chunk"))).one()
    assert row[0] == "Bao hanh 12 thang"
    assert row[1] == "Bảo hành 12 tháng", "bản gửi cho model phải còn dấu"


async def test_kb_chunk_store_the_heading_also_enters_the_folded_column(kb: KbHarness) -> None:
    """tiêu đề cũng vào cột phang - khách hỏi bằng chữ trong tiêu đề phải tìm ra"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "Chính sách đổi trả", "Trong vòng 7 ngày")])
        folded = (await s.execute(text("SELECT folded FROM agent.kb_chunk"))).scalar_one()
    assert "Chinh sach doi tra" in folded


async def test_kb_chunk_store_folded_column_is_tokenised_punctuation_never_glues_numbers(
    kb: KbHarness,
) -> None:
    """(thêm) cột phang tách từ như unicode61: '20.000đ' ra hai từ '20' và '000d'"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "Phí 20.000đ, miễn phí-ship.")])
        folded = (await s.execute(text("SELECT folded FROM agent.kb_chunk"))).scalar_one()
    assert folded == "Phi 20 000d mien phi ship"


async def test_kb_chunk_store_count_source_without_chunks_counts_0(kb: KbHarness) -> None:
    """nguồn chưa có đoạn nào đếm ra 0"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        assert await dem_doan(s, kb.clinic_id, id_) == 0


async def test_kb_chunk_store_count_counts_the_chunks_saved(kb: KbHarness) -> None:
    """đếm đúng số đoạn đã lưu"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(i, "", f"đoạn {i + 1}") for i in range(3)])
        assert await dem_doan(s, kb.clinic_id, id_) == 3


async def test_kb_chunk_store_embeddings_must_match_the_chunk_count(kb: KbHarness) -> None:
    """(thêm) số vector phải bằng số đoạn; có vector thì lưu vào cột embedding"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        with pytest.raises(ValueError, match="Số vector"):
            await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "a")], embeddings=[])
        vec = [0.0] * 1024
        vec[3] = 1.0
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "a")], embeddings=[vec])
        co_vector = (await s.execute(text("SELECT embedding IS NOT NULL FROM agent.kb_chunk"))).scalar_one()
    assert co_vector is True


async def test_lay_doan_theo_id_returns_in_the_order_of_the_ids_passed_not_the_sql_order(
    kb: KbHarness,
) -> None:
    """trả về đúng thứ tự của ids truyền vào, không theo thứ tự SQL"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(
            s,
            kb.clinic_id,
            id_,
            [DoanMoi(0, "", "đoạn A"), DoanMoi(1, "", "đoạn B"), DoanMoi(2, "", "đoạn C")],
        )
        ids = [r[0] for r in (await s.execute(text("SELECT id FROM agent.kb_chunk ORDER BY id"))).all()]
        a, b, c = ids
        ket_qua = await lay_doan_theo_id(s, kb.clinic_id, [c, a, b])
    assert [r.noi_dung for r in ket_qua] == ["đoạn C", "đoạn A", "đoạn B"]


async def test_lay_doan_theo_id_comes_with_the_source_name_through_a_join(kb: KbHarness) -> None:
    """kèm tên nguồn qua JOIN"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "nội dung")])
        doan_id = (await s.execute(text("SELECT id FROM agent.kb_chunk"))).scalar_one()
        ket_qua = await lay_doan_theo_id(s, kb.clinic_id, [doan_id])
    assert ket_qua[0].ten_nguon == "nguồn test"


async def test_lay_doan_theo_id_a_missing_id_is_skipped_without_raising(kb: KbHarness) -> None:
    """id không tồn tại thì bị bỏ qua, không throw"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "nội dung")])
        doan_id = (await s.execute(text("SELECT id FROM agent.kb_chunk"))).scalar_one()
        ket_qua = await lay_doan_theo_id(s, kb.clinic_id, [999999, doan_id])
    assert len(ket_qua) == 1
    assert ket_qua[0].id == doan_id


async def test_lay_doan_theo_id_empty_ids_return_an_empty_list(kb: KbHarness) -> None:
    """mảng ids rỗng trả về mảng rỗng"""
    async with kb.session() as s:
        assert await lay_doan_theo_id(s, kb.clinic_id, []) == []


async def test_lay_doan_cua_nguon_returns_the_right_page_by_offset_and_limit_ordered_by_order(
    kb: KbHarness,
) -> None:
    """trả đúng trang theo offset/limit, thứ tự theo thuTu"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(i, "", f"đoạn {i}") for i in range(4)])
        trang1 = await lay_doan_cua_nguon(s, kb.clinic_id, id_, 0, 2)
        trang2 = await lay_doan_cua_nguon(s, kb.clinic_id, id_, 2, 2)
    assert [d.noi_dung for d in trang1] == ["đoạn 0", "đoạn 1"]
    assert [d.noi_dung for d in trang2] == ["đoạn 2", "đoạn 3"]


async def test_lay_doan_cua_nguon_comes_with_the_heading_breadcrumb(kb: KbHarness) -> None:
    """kèm tiêu đề (breadcrumb) - đây là cách duy nhất người vận hành tự phát hiện lỗi đọc file"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "Chính sách > Đổi trả", "Trong vòng 7 ngày")])
        [doan] = await lay_doan_cua_nguon(s, kb.clinic_id, id_, 0, 20)
    assert doan.tieu_de == "Chính sách > Đổi trả"


async def test_lay_doan_cua_nguon_another_source_does_not_mix_chunks(kb: KbHarness) -> None:
    """nguồn khác không lẫn đoạn vào nhau"""
    id_ = await _nguon(kb)
    id_khac = await _nguon(kb, "nguồn khác")
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "của nguồn 1")])
        await luu_doan(s, kb.clinic_id, id_khac, [DoanMoi(0, "", "của nguồn khác")])
        ket_qua = await lay_doan_cua_nguon(s, kb.clinic_id, id_, 0, 20)
    assert [d.noi_dung for d in ket_qua] == ["của nguồn 1"]


async def test_lay_doan_cua_nguon_offset_past_the_total_returns_an_empty_list(kb: KbHarness) -> None:
    """offset vượt quá tổng số đoạn trả về mảng rỗng, không throw"""
    id_ = await _nguon(kb)
    async with kb.session() as s:
        await luu_doan(s, kb.clinic_id, id_, [DoanMoi(0, "", "đoạn duy nhất")])
        assert await lay_doan_cua_nguon(s, kb.clinic_id, id_, 100, 20) == []

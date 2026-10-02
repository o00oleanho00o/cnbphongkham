# ported from: src/knowledge/kb-source-store.test.ts
"""Forced deviation (SQLite -> Postgres): the four tables cleaned in the original (``kb_sources``,
``kb_chunks``, ``kb_chunks_fts``, ``agent_kb_sources``) are three here (``agent.kb_document``,
``agent.kb_chunk`` with the full-text column inside it, ``agent.agent_kb_document``)."""

from __future__ import annotations

import pytest

from pema.knowledge.chunk_text import DoanMoi
from pema.knowledge.kb_agent_binding import dat_nguon_cho_agent
from pema.knowledge.kb_chunk_store import dem_doan, luu_doan
from pema.knowledge.kb_source_store import danh_sach_nguon, dat_trang_thai, lay_nguon, tao_nguon, xoa_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db


async def test_kb_source_store_create_and_read_create_a_source_then_read_it_back_default_state_is_pending(
    kb: KbHarness,
) -> None:
    """tạo nguồn rồi đọc lại thấy đúng, trạng thái mặc định là chờ xử lý"""
    async with kb.session() as s:
        n = await tao_nguon(
            s, kb.clinic_id, ten="Chính sách đổi trả", loai="text", noi_dung_goc="Đổi trả trong 7 ngày."
        )
    async with kb.session() as s:
        doc = await lay_nguon(s, kb.clinic_id, n.id)
    assert doc is not None
    assert doc.ten == "Chính sách đổi trả"
    assert doc.trang_thai == "cho_xu_ly"
    assert doc.so_doan == 0


async def test_kb_source_store_create_and_read_reading_a_missing_source_returns_none(kb: KbHarness) -> None:
    """đọc nguồn không tồn tại trả về null"""
    async with kb.session() as s:
        assert await lay_nguon(s, kb.clinic_id, "khong-ton-tai") is None


async def test_kb_source_store_create_and_read_the_list_shows_the_source_just_created(kb: KbHarness) -> None:
    """danh sách nguồn thấy nguồn vừa tạo"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="Nguồn liệt kê", loai="text", noi_dung_goc="x")
    async with kb.session() as s:
        lst = await danh_sach_nguon(s, kb.clinic_id)
    assert any(x.id == n.id for x in lst)


async def test_kb_source_store_create_and_read_set_state_updates_the_right_columns(kb: KbHarness) -> None:
    """đặt trạng thái cập nhật đúng cột"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="Đặt trạng thái", loai="file", dinh_dang="pdf")
        await dat_trang_thai(s, kb.clinic_id, n.id, "hong", loi="Không đọc được file")
    async with kb.session() as s:
        doc = await lay_nguon(s, kb.clinic_id, n.id)
    assert doc is not None
    assert doc.trang_thai == "hong"
    assert doc.loi == "Không đọc được file"


async def test_kb_source_store_create_and_read_set_state_without_values_keeps_the_old_error_count_and_attempts(
    kb: KbHarness,
) -> None:
    """(thêm) bỏ trống loi/soDoan/soLanThu thì GIỮ NGUYÊN giá trị cũ"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="giữ giá trị", loai="text", noi_dung_goc="x")
        await dat_trang_thai(s, kb.clinic_id, n.id, "san_sang", loi="ghi chú", so_doan=7, so_lan_thu=3)
        await dat_trang_thai(s, kb.clinic_id, n.id, "cho_xu_ly")
    async with kb.session() as s:
        doc = await lay_nguon(s, kb.clinic_id, n.id)
    assert doc is not None
    assert (doc.trang_thai, doc.loi, doc.so_doan, doc.so_lan_thu) == ("cho_xu_ly", "ghi chú", 7, 3)


async def test_kb_source_store_delete_removes_every_place_no_orphan_left(kb: KbHarness) -> None:
    """xóa nguồn dọn sạch CẢ BỐN nơi, không để lại mồ côi"""
    kb.kb_database.add_agent("agent-1")
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="abc")
        await luu_doan(s, kb.clinic_id, n.id, [DoanMoi(0, "", "nội dung abc")])
        await dat_nguon_cho_agent(s, kb.clinic_id, "agent-1", [n.id])

    async with kb.session() as s:
        await xoa_nguon(s, kb.clinic_id, n.id)

    def dem(sql: str) -> int:
        return int(kb.kb_database.scalar(sql))

    assert dem("SELECT COUNT(*) FROM agent.kb_document") == 0, "nguồn"
    assert dem("SELECT COUNT(*) FROM agent.kb_chunk") == 0, "đoạn (kèm chỉ mục toàn văn trong cùng hàng)"
    assert dem("SELECT COUNT(*) FROM agent.agent_kb_document") == 0, "gán cho agent"


async def test_kb_source_store_delete_returns_the_number_of_chunks_deleted(kb: KbHarness) -> None:
    """xóa nguồn trả về đúng số đoạn đã xóa"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="đếm đoạn", loai="text", noi_dung_goc="abc")
        await luu_doan(s, kb.clinic_id, n.id, [DoanMoi(0, "", "đoạn 1"), DoanMoi(1, "", "đoạn 2")])
    async with kb.session() as s:
        so_doan_da_xoa = await xoa_nguon(s, kb.clinic_id, n.id)
    assert so_doan_da_xoa == 2


async def test_kb_source_store_delete_does_not_touch_another_source(kb: KbHarness) -> None:
    """xóa nguồn KHÔNG đụng nguồn khác"""
    async with kb.session() as s:
        a = await tao_nguon(s, kb.clinic_id, ten="a", loai="text", noi_dung_goc="1")
        b = await tao_nguon(s, kb.clinic_id, ten="b", loai="text", noi_dung_goc="2")
        await luu_doan(s, kb.clinic_id, a.id, [DoanMoi(0, "", "của a")])
        await luu_doan(s, kb.clinic_id, b.id, [DoanMoi(0, "", "của b")])
    async with kb.session() as s:
        await xoa_nguon(s, kb.clinic_id, a.id)
    async with kb.session() as s:
        assert await dem_doan(s, kb.clinic_id, b.id) == 1

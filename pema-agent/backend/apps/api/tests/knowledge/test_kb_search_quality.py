# ported from: src/knowledge/kb-search-quality.test.ts
"""Retrieval quality through the REAL ingest path (``cat_thanh_doan`` -> ``luu_doan``, exactly what
``kb_ingest_worker`` does with a ``kind='text'`` source) - NOT fixtures built with ``luu_doan`` directly: the
junction between chunking and storage had no test before and that is how I1 (looking up the exact DOCUMENT
NAME returns nothing) slipped through two review rounds."""

from __future__ import annotations

import re

import pytest

from pema.knowledge.chunk_text import ThamSoCat, cat_thanh_doan
from pema.knowledge.kb_agent_binding import dat_nguon_cho_agent, nguon_cua_agent
from pema.knowledge.kb_chunk_store import luu_doan
from pema.knowledge.kb_search import KetQuaKb, tim_trong_kho_tri_thuc
from pema.knowledge.kb_source_store import KbSource, tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db

AGENT = "agent-a"
THAM_SO_CAT_MAC_DINH = ThamSoCat(co_doan_toi_da=2000, chong_lan=0)


async def nap_qua_worker(kb: KbHarness, ten: str, chu: str) -> KbSource:
    kb.kb_database.add_agent(AGENT)
    async with kb.session() as s:
        nguon = await tao_nguon(s, kb.clinic_id, ten=ten, loai="text", noi_dung_goc=chu)
        doan = cat_thanh_doan(chu, THAM_SO_CAT_MAC_DINH)
        await luu_doan(s, kb.clinic_id, nguon.id, doan, nguon.ten)
        cu = await nguon_cua_agent(s, kb.clinic_id, AGENT)
        await dat_nguon_cho_agent(s, kb.clinic_id, AGENT, [*cu, nguon.id])
    return nguon


async def tim(kb: KbHarness, cau_hoi: str, so_luong: int | None = None) -> list[KetQuaKb]:
    async with kb.session() as s:
        return await tim_trong_kho_tri_thuc(
            s, kb.clinic_id, cau_hoi=cau_hoi, agent_id=AGENT, so_luong=so_luong
        )


async def test_tra_bang_ten_tai_lieu_the_document_h1_title_finds_the_right_chunk(kb: KbHarness) -> None:
    """tra bằng chính tiêu đề H1 của tài liệu ra đúng đoạn"""
    # The case measured as broken: the H1 had no body right below it and was overwritten by the H2 - "chính
    # sách đổi trả" (the document name) found 0 rows although the content was in the store. The SOURCE name
    # deliberately shares no word with the question ("Tài liệu vận hành"), otherwise the folded column would
    # match through the source name and not through the breadcrumb under test.
    await nap_qua_worker(
        kb,
        "Tài liệu vận hành",
        "# Chính sách đổi trả\n\n## Điều kiện\n\nHàng còn nguyên tem.\n\n## Thời hạn\n\nTrong vòng 7 ngày.",
    )
    kq = await tim(kb, "chính sách đổi trả")
    assert kq, "tra đúng tên tài liệu (H1) mà ra rỗng"
    assert re.search("Chính sách đổi trả", kq[0].tieu_de), (
        f'breadcrumb phải mang tên tài liệu (H1), thực tế: "{kq[0].tieu_de}"'
    )


async def test_tra_bang_ten_tai_lieu_the_source_name_finds_the_right_chunk(kb: KbHarness) -> None:
    """tra bằng TÊN NGUỒN ra đúng đoạn"""
    await nap_qua_worker(kb, "Bảng giá quán", "Cà phê 25.000đ.")
    kq = await tim(kb, "bảng giá quán")
    assert kq, "tra đúng tên nguồn mà ra rỗng"


async def test_khu_trung_two_sources_with_identical_content_take_only_one_slot(kb: KbHarness) -> None:
    """hai nguồn nội dung y hệt chỉ chiếm MỘT slot"""
    nguon_a = await nap_qua_worker(kb, "Nguồn A", "Cà phê 25.000đ.")
    nguon_b = await nap_qua_worker(kb, "Nguồn B", "Cà phê 25.000đ.")
    kq = await tim(kb, "cà phê", so_luong=5)
    assert len(kq) == 1, f"phải khử còn 1, ra: {[x.source_id for x in kq]}"
    assert kq[0].source_id in (nguon_a.id, nguon_b.id)


async def test_khu_trung_dedup_does_not_come_up_short_still_so_luong_different_chunks(kb: KbHarness) -> None:
    """khử trùng KHÔNG làm thiếu: vẫn đủ soLuong đoạn khác nhau"""
    # The SQL LIMITs exactly, so dedup AFTER it comes up short unless we over-fetch first: 2 duplicates + 5
    # different ones, ask 5, expect all 5.
    await nap_qua_worker(kb, "Nguồn A", "Cà phê 25.000đ.")
    await nap_qua_worker(kb, "Nguồn B", "Cà phê 25.000đ.")
    for i in range(5):
        await nap_qua_worker(kb, f"Khác {i}", f"Cà phê loại {i} giá {i}0.000đ.")
    kq = await tim(kb, "cà phê", so_luong=5)
    assert len(kq) == 5, f"khử trùng xong bị hụt: {[x.noi_dung for x in kq]}"


async def test_khu_trung_different_content_even_if_similar_is_not_deduped_by_mistake(kb: KbHarness) -> None:
    """nội dung KHÁC nhau (dù tương tự) không bị khử oan"""
    await nap_qua_worker(kb, "Nguồn A", "Cà phê 25.000đ.")
    await nap_qua_worker(kb, "Nguồn B", "Cà phê 30.000đ.")
    kq = await tim(kb, "cà phê", so_luong=5)
    assert len(kq) == 2, "hai đoạn giá khác nhau bị khử nhầm thành một"


async def test_mot_tai_lieu_lon_a_big_document_does_not_take_every_slot_of_a_generic_question(
    kb: KbHarness,
) -> None:
    """tài liệu nhiều mục (breadcrumb+tên nguồn lặp lại mỗi đoạn) không đẩy hết tài liệu khác ra khỏi top-k"""
    tieu_de_lon = "Sổ tay vận hành cửa hàng"
    noi_dung_lon = (
        f"# {tieu_de_lon}\n\n"
        "## Chính sách mở cửa\n\nMở cửa 8h, đóng cửa 21h các ngày trong tuần.\n\n"
        "## Chính sách nhân sự\n\nCa làm việc chia 2 ca sáng chiều, nghỉ luân phiên.\n\n"
        "## Chính sách kho\n\nKiểm kho mỗi tuần một lần vào sáng thứ Hai.\n\n"
        "## Chính sách vệ sinh\n\nDọn dẹp quầy kệ cuối mỗi ca làm việc.\n\n"
        "## Chính sách an toàn\n\nKiểm tra bình cứu hỏa mỗi tháng một lần.\n\n"
        "## Chính sách đào tạo\n\nNhân viên mới được đào tạo trong 3 ngày đầu."
    )
    await nap_qua_worker(kb, tieu_de_lon, noi_dung_lon)
    await nap_qua_worker(kb, "Chính sách bảo hành A", "Bảo hành 12 tháng cho sản phẩm điện tử.")
    await nap_qua_worker(kb, "Chính sách bảo hành B", "Bảo hành 24 tháng cho đồ gia dụng.")
    await nap_qua_worker(kb, "Chính sách bảo hành C", "Bảo hành 6 tháng cho phụ kiện.")

    kq = await tim(kb, "chính sách bảo hành", so_luong=5)
    so_nguon_khac_nhau = len({x.source_id for x in kq})
    # Real number recorded - the threshold is not tuned to keep the test green (3 of 4 sources must remain).
    assert so_nguon_khac_nhau >= 3, (
        "tài liệu lớn có dấu hiệu CHIẾM TRỌN top-k - chỉ còn "
        f"{so_nguon_khac_nhau} nguồn khác nhau trong {len(kq)} kết quả: "
        f"{[(x.ten_nguon, x.tieu_de, x.diem) for x in kq]}"
    )

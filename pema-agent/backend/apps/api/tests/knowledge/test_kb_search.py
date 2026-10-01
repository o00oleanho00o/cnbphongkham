# ported from: src/knowledge/kb-search.test.ts
"""Keyword side of the search on real Vietnamese data (the vector side has its own tests,
``test_kb_search_hybrid.py``). Forced deviation: ``bm25()`` -> ``ts_rank_cd`` (see ``kb_fts_query``), so the
ranking is a little blunter; the fixture questions are the original's and every one still ranks first."""

from __future__ import annotations

import re

import pytest

from pema.knowledge.chunk_text import DoanMoi
from pema.knowledge.kb_agent_binding import dat_nguon_cho_agent
from pema.knowledge.kb_chunk_store import luu_doan
from pema.knowledge.kb_search import KetQuaKb, tim_trong_kho_tri_thuc
from pema.knowledge.kb_source_store import KbSource, tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db

AGENT = "agent-a"

# Fixture: 4 chunks of the kind of real customer-care document.
TAI_LIEU = [
    "# Phí vận chuyển\n\nNội thành 20.000 đồng, ngoại thành 35.000 đồng. Đơn trên 500.000 đồng được miễn phí ship.",
    "# Bảo hành\n\nBảo hành 12 tháng cho mọi sản phẩm. Đổi mới trong 30 ngày đầu nếu lỗi nhà sản xuất.",
    "# Chính sách đổi trả\n\nĐổi trả trong vòng 7 ngày kể từ ngày nhận hàng, sản phẩm còn nguyên tem.",
    "# Giờ làm việc\n\nCửa hàng mở cửa 8h00, đóng cửa 21h00 tất cả các ngày trong tuần.",
]


async def nap_nguon(kb: KbHarness, ten: str, noi_dungs: list[str], agent: str = AGENT) -> KbSource:
    """Load 1 source, each entry of ``noi_dungs`` becomes its own chunk (NOT through ``cat_thanh_doan``)."""
    async with kb.session() as s:
        nguon = await tao_nguon(s, kb.clinic_id, ten=ten, loai="text", noi_dung_goc="\n\n".join(noi_dungs))
        await luu_doan(
            s,
            kb.clinic_id,
            nguon.id,
            [DoanMoi(thu_tu=i, tieu_de="", noi_dung=nd) for i, nd in enumerate(noi_dungs)],
        )
    return nguon


async def gan(kb: KbHarness, agent: str, source_ids: list[str]) -> None:
    kb.kb_database.add_agent(agent)
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, agent, source_ids)


async def tim(kb: KbHarness, cau_hoi: str, agent: str = AGENT, so_luong: int | None = None) -> list[KetQuaKb]:
    async with kb.session() as s:
        return await tim_trong_kho_tri_thuc(
            s, kb.clinic_id, cau_hoi=cau_hoi, agent_id=agent, so_luong=so_luong
        )


async def test_tim_trong_kho_tri_thuc_keyword_three_customer_style_questions_rank_the_right_chunk_first(
    kb: KbHarness,
) -> None:
    """ba câu hỏi kiểu khách hàng ra đúng đoạn ở hạng 1"""
    nguon = await nap_nguon(kb, "chăm sóc khách hàng", TAI_LIEU)
    await gan(kb, AGENT, [nguon.id])
    for cau, mong in (
        ("phi ship noi thanh bao nhieu", "vận chuyển"),
        ("bảo hành bao lâu vậy shop", "Bảo hành"),
        ("đổi trả được không", "đổi trả"),
    ):
        kq = await tim(kb, cau, so_luong=1)
        assert re.search(mong, kq[0].noi_dung), f'câu "{cau}"'


async def test_tim_trong_kho_tri_thuc_keyword_opening_hours_question_ranks_the_right_chunk_first(
    kb: KbHarness,
) -> None:
    """câu hỏi giờ mở cửa cũng ra đúng đoạn ở hạng 1 (đã đo, không phải suy luận)"""
    # "đồng" (money) and "đóng" (close) both fold to "dong": a REAL risk of keyword search.
    nguon = await nap_nguon(kb, "chăm sóc khách hàng", TAI_LIEU)
    await gan(kb, AGENT, [nguon.id])
    kq = await tim(kb, "mấy giờ đóng cửa", so_luong=2)
    assert re.search("Giờ làm việc", kq[0].noi_dung), f"top 2 thực tế: {[x.noi_dung[:30] for x in kq]}"


async def test_tim_trong_kho_tri_thuc_keyword_a_question_of_words_with_d_stroke_still_finds_the_right_chunk(
    kb: KbHarness,
) -> None:
    """câu hỏi chỉ có từ mang chữ 'đ' vẫn ra đúng đoạn - chứng minh boDauTiengViet có tác dụng thật"""
    # "đ" is a letter of its own, not a base letter plus a combining mark: only folding makes "đổi" = "doi".
    nguon = await nap_nguon(kb, "chăm sóc khách hàng", TAI_LIEU)
    await gan(kb, AGENT, [nguon.id])
    kq = await tim(kb, "đổi", so_luong=1)
    assert re.search("Chính sách đổi trả", kq[0].noi_dung), "câu hỏi 'đổi' một mình"


async def test_tim_trong_kho_tri_thuc_isolation_only_searches_the_sources_enabled_for_that_agent(
    kb: KbHarness,
) -> None:
    """chỉ tìm trong nguồn ĐÃ BẬT cho agent đó"""
    nguon_a = await nap_nguon(kb, "nguồn A", ["Bảo hành 12 tháng cho mọi sản phẩm."])
    nguon_b = await nap_nguon(kb, "nguồn B", ["Bảo hành 24 tháng cho sản phẩm cao cấp."])
    await gan(kb, "agent-a", [nguon_a.id])
    await gan(kb, "agent-b", [nguon_b.id])

    kq = await tim(kb, "bảo hành", "agent-a")
    assert kq
    assert all(x.source_id == nguon_a.id for x in kq), "rò nguồn của agent khác"


async def test_tim_trong_kho_tri_thuc_isolation_an_agent_with_no_source_gets_empty_not_everything(
    kb: KbHarness,
) -> None:
    """agent chưa gán nguồn nào thì trả RỖNG, không phải trả tất cả"""
    await nap_nguon(kb, "nguồn A", ["Bảo hành 12 tháng cho mọi sản phẩm."])
    kb.kb_database.add_agent("agent-chua-gan")
    assert await tim(kb, "bảo hành", "agent-chua-gan") == []


async def test_tim_trong_kho_tri_thuc_isolation_the_source_filter_is_in_the_sql_not_after_taking_the_top(
    kb: KbHarness,
) -> None:
    """lọc nguồn nằm TRONG SQL, không lọc sau khi lấy top"""
    # 30 SHORT chunks matching almost perfectly in the source that is NOT enabled, plus 1 matching but
    # LONGER chunk in the enabled one. Filtering after taking the top-5 would push the right chunk out.
    await nap_nguon(kb, "nguồn nhiễu", ["Bảo hành."] * 30)
    nguon_dung = await nap_nguon(
        kb,
        "nguồn đúng",
        ["Bảo hành 12 tháng cho mọi sản phẩm, đổi mới trong 30 ngày đầu nếu lỗi nhà sản xuất."],
    )
    await gan(kb, AGENT, [nguon_dung.id])

    kq = await tim(kb, "bảo hành", so_luong=5)
    assert len(kq) == 1
    assert kq[0].source_id == nguon_dung.id

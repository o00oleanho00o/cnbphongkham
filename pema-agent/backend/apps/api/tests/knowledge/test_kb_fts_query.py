# ported from: src/knowledge/kb-fts-query.test.ts
"""Forced deviation (SQLite FTS5 -> Postgres ``to_tsquery``): the query string is ``'phi' | 'ship' | ...``
(each token a quoted literal lexeme, joined by OR) instead of ``"phi" OR "ship"``."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from pema.knowledge.kb_fts_query import diem_bm25, dung_truy_van_fts, idf_bm25
from pema.knowledge.kb_test_support import KbHarness


def test_dung_truy_van_fts_wraps_each_word_in_quotes_and_joins_with_or() -> None:
    """bọc từng từ trong nháy kép và nối bằng OR"""
    assert dung_truy_van_fts("phí ship nội thành") == "'phi' | 'ship' | 'noi' | 'thanh'"


def test_dung_truy_van_fts_a_question_with_no_usable_word_returns_empty_not_an_empty_query() -> None:
    """câu hỏi không còn từ nào dùng được thì trả rỗng, KHÔNG dựng MATCH rỗng"""
    assert dung_truy_van_fts("!!! ??? ...") == ""


def test_dung_truy_van_fts_guards_drop_absurdly_long_tokens_and_cap_the_token_count() -> None:
    """(thêm) bỏ từ dài vô lý, giới hạn số từ"""
    assert dung_truy_van_fts("a" * 500 + " ok") == "'ok'"
    assert len(dung_truy_van_fts(" ".join(f"t{i}" for i in range(200))).split(" | ")) == 64


@pytest.mark.db
async def test_dung_truy_van_fts_fts_syntax_characters_in_the_question_do_not_raise(kb: KbHarness) -> None:
    """ký tự cú pháp FTS5 trong câu hỏi KHÔNG làm ném lỗi"""
    # Text of a stranger goes straight in here - "-", "*", '"', "(", "'", "&", "|", "!" are all tsquery syntax
    async with kb.session() as s:
        for cau in (
            'giá "combo" bao nhiêu',
            "shop ơi - còn hàng *không*",
            "a( b) c",
            "it's & that | !not :* ^",
        ):
            q = dung_truy_van_fts(cau)
            await s.execute(text("SELECT to_tsquery('simple', :q)"), {"q": q})


def test_bm25_a_rare_word_outweighs_a_repeated_common_word_the_idf_part_ts_rank_lacks() -> None:
    """(thêm) BM25: nhiều từ hiếm khác nhau thắng một từ phổ biến lặp lại - phần IDF mà ts_rank không có"""
    # "dong" (money / close) is in 3 of 4 chunks; "gio" and "cua" in 1 each: the chunk with two distinct rare
    # words must beat the one that repeats the common word.
    idf = {"gio": idf_bm25(4, 1), "dong": idf_bm25(4, 3), "cua": idf_bm25(4, 1)}
    gio_lam_viec = "Gio lam viec cua hang mo cua dong cua".lower().split()
    phi_van_chuyen = "Noi thanh 20 000 dong ngoai thanh 35 000 dong mien phi".lower().split()
    cau_hoi = ["gio", "dong", "cua"]
    assert diem_bm25(cau_hoi, gio_lam_viec, idf, 9.0) > diem_bm25(cau_hoi, phi_van_chuyen, idf, 9.0)


def test_bm25_idf_never_goes_negative_and_a_word_in_no_chunk_scores_nothing() -> None:
    """(thêm) IDF không âm (sàn 1e-6); chunk không chứa từ nào thì 0 điểm"""
    assert idf_bm25(4, 4) == pytest.approx(1e-6)
    assert diem_bm25(["a"], ["b", "c"], {"a": 1.0}, 2.0) == 0.0
    assert diem_bm25(["a"], [], {"a": 1.0}, 2.0) == 0.0

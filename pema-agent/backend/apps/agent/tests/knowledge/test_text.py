"""Reading a document for the knowledge store: folding Vietnamese, the YAML head, chunks at headings, warnings."""

from __future__ import annotations

from datetime import date

from plugins.knowledge.text import (
    MAX_CHUNK_CHARS,
    chunk,
    content_warnings,
    fold,
    outline,
    query_terms,
    split_head,
    terms,
)

DOC = """---
doc_id: "DEMO-PEMA-D07"
tenant_id: "DEMO-PEMA"
title: "Bảng giá hiện hành"
version: "2.0"
status: active
effective_from: 2026-10-01
effective_to: null
audience: patient
ingest_role: kb
---
# Bảng giá hiện hành

Giá áp dụng tại cả hai chi nhánh từ ngày 01/10/2026, đã gồm thuế. Giá có thể thay đổi theo từng đợt.

## Điều trị nám

### Buổi lẻ
Một buổi laser điều trị nám có giá 4.000.000 đồng, gồm thăm khám trước buổi và chăm sóc sau buổi tại phòng khám.

### Gói 10 buổi
Gói 10 buổi điều trị nám có giá 25.000.000 đồng, dùng trong 12 tháng kể từ buổi đầu tiên.

## Ghi chú
Ngắn.
"""


def test_folding_drops_marks_and_d_with_stroke() -> None:
    assert fold("Điều trị NÁM, bớt Hori") == "dieu tri nam, bot hori"


def test_terms_add_neighbour_pairs_and_questions_drop_common_words() -> None:
    assert terms("trị nám") == ["tri", "nam", "trinam"]
    assert "bao" not in query_terms("trị nám bao nhiêu tiền")
    assert "trinam" in query_terms("trị nám bao nhiêu tiền")


def test_the_yaml_head_becomes_the_documents_facts() -> None:
    head, body = split_head(DOC)

    assert (head.doc_code, head.title, head.version, head.lifecycle) == (
        "DEMO-PEMA-D07",
        "Bảng giá hiện hành",
        "2.0",
        "active",
    )
    assert (head.effective_from, head.effective_to, head.audience) == (date(2026, 10, 1), None, "patient")
    assert body.startswith("# Bảng giá hiện hành")


def test_a_document_without_a_head_keeps_all_its_text() -> None:
    head, body = split_head("# Giờ mở cửa\n\nTừ 8h đến 20h.")

    assert head.doc_code is None
    assert body == "# Giờ mở cửa\n\nTừ 8h đến 20h."


def test_chunks_follow_the_headings_and_carry_their_path() -> None:
    _, body = split_head(DOC)

    pieces = chunk(body, "Bảng giá")

    assert [p.path for p in pieces] == [
        "Bảng giá hiện hành",
        "Bảng giá hiện hành > Điều trị nám > Buổi lẻ",
        "Bảng giá hiện hành > Điều trị nám > Gói 10 buổi",
    ]
    assert "Ghi chú\nNgắn." in pieces[-1].text


def test_a_long_section_is_cut_at_paragraphs() -> None:
    paragraph = "Một đoạn dài về chăm sóc da sau điều trị. " * 20
    body = "## Chăm sóc\n\n" + "\n\n".join([paragraph] * 4)

    pieces = chunk(body, "T")

    assert len(pieces) > 1
    assert all(len(p.text) <= MAX_CHUNK_CHARS for p in pieces)


def test_the_outline_counts_the_chunks_of_each_heading() -> None:
    _, body = split_head(DOC)

    nodes = outline(body)

    assert [(n.level, n.title, n.chunks) for n in nodes] == [
        (1, "Bảng giá hiện hành", 1),
        (2, "Điều trị nám", 0),
        (3, "Buổi lẻ", 1),
        (3, "Gói 10 buổi", 1),
        (2, "Ghi chú", 0),
    ]


def test_text_without_headings_and_with_a_phone_number_is_flagged() -> None:
    body = "Gọi 0912 345 678 để đặt lịch."

    codes = [w.code for w in content_warnings(body, outline(body))]

    assert codes == ["no_headings", "personal_data"]

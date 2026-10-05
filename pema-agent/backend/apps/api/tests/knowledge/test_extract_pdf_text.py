# ported from: src/knowledge/extract-pdf-text.test.ts
"""Forced deviation: ``unpdf`` -> ``pypdf``."""

from __future__ import annotations

import re

import pytest

from pema.knowledge.doc_text_extract import doc_chu_tu_file


def pdf_mot_trang(chu: str) -> bytes:
    """A minimal one-page PDF with ASCII text. An empty string gives a page with NO text-drawing operator -
    exactly the shape of a scanned-image PDF as the reader sees it. The xref table holds BYTE OFFSETS so they
    must be accumulated while assembling, never hard-coded."""
    noi_dung_trang = f"BT /F1 12 Tf 72 720 Td ({chu}) Tj ET\n" if chu else ""
    obj = [
        "<</Type/Catalog/Pages 2 0 R>>",
        "<</Type/Pages/Kids[3 0 R]/Count 1>>",
        "<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Resources<</Font<</F1 4 0 R>>>>/Contents 5 0 R>>",
        "<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
        f"<</Length {len(noi_dung_trang)}>>\nstream\n{noi_dung_trang}endstream",
    ]

    pdf = "%PDF-1.4\n"
    lech: list[int] = []
    for i, than in enumerate(obj):
        lech.append(len(pdf))
        pdf += f"{i + 1} 0 obj\n{than}\nendobj\n"

    lech_xref = len(pdf)
    pdf += f"xref\n0 {len(obj) + 1}\n0000000000 65535 f \n"
    for v in lech:
        pdf += f"{v:010d} 00000 n \n"
    pdf += f"trailer\n<</Size {len(obj) + 1}/Root 1 0 R>>\nstartxref\n{lech_xref}\n%%EOF\n"

    return pdf.encode("latin-1")  # latin-1: 1 character = 1 byte, so the xref offsets are right


def test_extract_pdf_text_via_doc_chu_tu_file_reads_text_from_a_pdf() -> None:
    """đọc được chữ từ PDF"""
    ra = doc_chu_tu_file(pdf_mot_trang("Bao hanh 12 thang"), "pdf")
    assert re.search(r"Bao hanh 12 thang", ra)


def test_extract_pdf_text_via_doc_chu_tu_file_broken_pdf_raises_a_readable_vietnamese_error_not_a_raw_library_error() -> (
    None
):
    """PDF hỏng thì ném lỗi có câu tiếng Việt đọc được, không ném lỗi thư viện thô"""
    with pytest.raises(ValueError, match=r"(?i)không đọc được"):
        doc_chu_tu_file(b"khong phai pdf", "pdf")


def test_extract_pdf_text_via_doc_chu_tu_file_pdf_without_a_text_layer_reports_the_right_disease_not_a_generic_one() -> (
    None
):
    """PDF không có lớp chữ (ảnh quét) báo ĐÚNG BỆNH, không báo chung chung"""
    # The library returns an empty string and does not raise - this branch must recognise it itself
    with pytest.raises(ValueError, match=r"(?i)ảnh quét"):
        doc_chu_tu_file(pdf_mot_trang(""), "pdf")

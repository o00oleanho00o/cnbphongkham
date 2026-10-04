# ported from: src/knowledge/doc-text-extract.test.ts
"""Pure module - no environment or database."""

from __future__ import annotations

from pema.knowledge.doc_text_extract import DINH_DANG_HO_TRO, doc_chu_tu_file, la_dinh_dang_ho_tro


def test_la_dinh_dang_ho_tro_recognises_exactly_the_5_supported_formats() -> None:
    """nhận đúng 5 định dạng hỗ trợ"""
    assert list(DINH_DANG_HO_TRO) == ["txt", "md", "docx", "xlsx", "pdf"]
    for d in DINH_DANG_HO_TRO:
        assert la_dinh_dang_ho_tro(d) is True


def test_la_dinh_dang_ho_tro_rejects_an_unknown_format() -> None:
    """từ chối định dạng lạ"""
    for x in ("doc", "png", "csv", ""):
        assert la_dinh_dang_ho_tro(x) is False


def test_doc_chu_tu_file_txt_is_read_directly_as_utf8_keeping_vietnamese_diacritics() -> None:
    """txt đọc thẳng UTF-8, giữ nguyên dấu tiếng Việt"""
    chu = doc_chu_tu_file("Xin chào, đây là tài liệu.".encode(), "txt")
    assert chu == "Xin chào, đây là tài liệu."


def test_doc_chu_tu_file_md_is_read_directly_with_no_markdown_processing_at_the_file_reading_layer() -> None:
    """md đọc thẳng UTF-8, không xử lý markdown gì thêm ở tầng đọc file"""
    chu = doc_chu_tu_file("# Tiêu đề\n\nNội dung".encode(), "md")
    assert chu == "# Tiêu đề\n\nNội dung"

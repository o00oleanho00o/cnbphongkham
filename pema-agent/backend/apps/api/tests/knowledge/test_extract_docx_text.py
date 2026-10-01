# ported from: src/knowledge/extract-docx-text.test.ts
"""Forced deviation: the original builds its Word files with ``renderDocx`` (the document tool of the bot,
package D4 here). This test builds them with ``python-docx`` directly, the same library D4's renderer sits
on, so it does not import a module of another package."""

from __future__ import annotations

import io
import re
import time
from pathlib import Path

import pytest
from docx import Document

from pema.knowledge.doc_text_extract import doc_chu_tu_file
from pema.knowledge.ooxml_zip_test_helper import (
    ZipEntryInput,
    build_zip_buffer,
    chu_kho_nen,
    docx_chi_co_anh,
    docx_tu_xml,
    zip_entry_qua_tran,
)

FIXTURES = Path(__file__).parent / "fixtures"


def word_table() -> bytes:
    return (FIXTURES / "word-table.docx").read_bytes()


def word_tabstop() -> bytes:
    return (FIXTURES / "word-tabstop.docx").read_bytes()


def render_docx(blocks: list[tuple[str, str, int]]) -> bytes:
    """``(kind, text, level)``: a paragraph or a heading, written with ``python-docx``."""
    document = Document()
    for kind, text, level in blocks:
        if kind == "heading":
            document.add_heading(text, level=level)
        else:
            document.add_paragraph(text)
    out = io.BytesIO()
    document.save(out)
    return out.getvalue()


def test_extract_docx_text_via_doc_chu_tu_file_reads_back_the_text_of_a_docx_the_bot_wrote() -> None:
    """đọc lại được chữ từ chính file docx do bot sinh ra"""
    buf = render_docx([("paragraph", "Đổi trả trong 7 ngày", 0)])
    chu = doc_chu_tu_file(buf, "docx")
    assert "Đổi trả trong 7 ngày" in chu


def test_extract_docx_text_via_doc_chu_tu_file_heading_and_body_both_read_out() -> None:
    """tiêu đề văn bản (title) và heading đều đọc ra được"""
    buf = render_docx([("heading", "Bảo hành", 1), ("paragraph", "12 tháng kể từ ngày mua", 0)])
    chu = doc_chu_tu_file(buf, "docx")
    assert "Bảo hành" in chu
    assert "12 tháng kể từ ngày mua" in chu


def test_extract_docx_text_via_doc_chu_tu_file_heading_becomes_markdown_hash_so_chunk_text_recognises_the_title() -> (
    None
):
    """heading dịch sang markdown '#' để chunk-text nhận diện được tiêu đề"""
    buf = render_docx([("heading", "Chính sách đổi trả", 2), ("paragraph", "Trong vòng 7 ngày.", 0)])
    chu = doc_chu_tu_file(buf, "docx")
    assert re.search(r"^##?\s+Chính sách đổi trả$", chu, re.MULTILINE)


def test_extract_docx_text_via_doc_chu_tu_file_several_paragraphs_keep_order_and_content() -> None:
    """nhiều đoạn văn giữ đúng thứ tự và nội dung"""
    buf = render_docx([("paragraph", "Đoạn một", 0), ("paragraph", "Đoạn hai", 0)])
    chu = doc_chu_tu_file(buf, "docx")
    assert chu.index("Đoạn một") < chu.index("Đoạn hai")


def test_extract_docx_text_via_doc_chu_tu_file_broken_docx_not_a_zip_raises_a_readable_vietnamese_error() -> (
    None
):
    """file docx hỏng (không phải zip) ném lỗi tiếng Việt đọc được"""
    with pytest.raises(ValueError, match=r"(?i)không phải file zip"):
        doc_chu_tu_file(b"khong phai file zip", "docx")


def test_extract_docx_text_via_doc_chu_tu_file_a_zip_renamed_to_docx_reports_a_sentence_the_operator_can_read() -> (
    None
):
    """file .zip đổi đuôi thành .docx (qua lọt kiểm chữ ký PK, thiếu word/document.xml) báo câu người vận hành đọc được"""
    # A valid zip (so the "PK" check of kb_route_guards still matches) with NO word/document.xml entry -
    # exactly the shape of a .zip/.xlsx renamed to .docx.
    zip_khong_phai_docx = build_zip_buffer([ZipEntryInput("readme.txt", b"khong lien quan")])
    with pytest.raises(ValueError, match=r"(?i)không phải .docx hợp lệ") as excinfo:
        doc_chu_tu_file(zip_khong_phai_docx, "docx")
    # The sentence must NOT mention "word/document.xml" (an internal OOXML term) - the operator reading the
    # dashboard does not know what it is.
    assert "word/document.xml" not in str(excinfo.value)


def test_extract_docx_text_real_word_fixture_reads_a_docx_written_by_real_word_without_a_scrap_of_xml() -> (
    None
):
    """đọc file .docx do Word THẬT ghi, không lẫn một mẩu XML nào"""
    chu = doc_chu_tu_file(word_table(), "docx")
    assert "<w:" not in chu, "XML thô lọt vào chữ trích ra"
    assert "chữ có khoảng trắng đầu dòng" in chu


def test_extract_docx_text_real_word_fixture_tab_stop_does_not_become_raw_xml_a_real_tab_stays_a_tab_character() -> (
    None
):
    """tab stop trong Word không biến thành XML thô, tab thật vẫn ra ký tự tab"""
    # The case MEASURED as broken in the old regex version: <w:tab w:val="left" w:pos="2880"/> wrongly
    # matched /<w:t[^>]*>/ - the whole tab stop definition leaked into the result.
    chu = doc_chu_tu_file(word_tabstop(), "docx")
    assert not re.search(r"w:val|w:pos|w:tabs", chu)
    # Match EXACTLY the whole text (not a substring): the fixture has EXACTLY 2 tab stop definitions in
    # <w:pPr><w:tabs> (w:pos=2880 and 5760) BEFORE 2 REAL tabs in <w:r> - if a tab DEFINITION were counted
    # as a tab character the result would have EXTRA tabs at the START, which a substring match cannot catch.
    assert chu == "Ca phe\tGia 25000\tBao hanh 12 thang"


def test_extract_docx_text_real_word_fixture_word_table_keeps_row_structure_self_closing_p_in_an_empty_cell_does_not_merge_paragraph_boundaries() -> (
    None
):
    """bảng Word giữ cấu trúc hàng; <w:p/> tự đóng trong ô rỗng không gộp sai ranh giới đoạn"""
    # The case MEASURED as broken: PARAGRAPH_RE treated <w:p/> as an OPENING tag (swallowing the "/") and
    # scanned to the next </w:p> - the fixture has 2 self-closing <w:p/> in the empty table cells (row 2)
    # and 1 more at the end of the body.
    chu = doc_chu_tu_file(word_table(), "docx")
    assert re.search(r"Tên \| Số", chu), f"không thấy hàng bảng, đọc ra: {chu!r}"
    # Row 2 is all empty cells -> dropped (same rule "drop a row with no cell holding text" as xlsx) - no
    # stray "| " or empty line may be left behind.
    assert not re.search(r"Tên \| Số\n\|", chu)


def test_extract_docx_text_real_word_fixture_self_closing_p_between_two_real_paragraphs_does_not_merge_their_content() -> (
    None
):
    """<w:p/> tự đóng NẰM GIỮA hai đoạn văn thật không gộp lẫn nội dung (chốt HỒI QUY, không phải bằng chứng B10-8)"""
    chu = doc_chu_tu_file(
        docx_tu_xml(
            "<w:p><w:r><w:t>Truoc tu dong</w:t></w:r></w:p>"
            '<w:p w:rsidR="1"/>'
            "<w:p><w:r><w:t>Sau tu dong</w:t></w:r></w:p>"
        ),
        "docx",
    )
    assert chu == "Truoc tu dong\n\nSau tu dong"


def test_extract_docx_text_real_word_fixture_content_inside_ppr_does_not_leak_without_relying_on_trim() -> (
    None
):
    """nội dung KHÔNG-KHOẢNG-TRẮNG trong pPr (bỏ qua nội dung) không lọt ra, không cần .trim() che"""
    # <w:noBreakHyphen/> makes "-" - NOT whitespace - so if it leaked from pPr, strip() would not remove it
    # and this test really measures the skip-content mechanism. Putting it in <w:pPr> is deliberately
    # INVALID-SCHEMA data (simulating hostile input), not a file Word writes.
    chu = doc_chu_tu_file(
        docx_tu_xml("<w:p><w:pPr><w:noBreakHyphen/></w:pPr><w:r><w:t>Noi dung that</w:t></w:r></w:p>"),
        "docx",
    )
    assert chu == "Noi dung that", f'dấu "-" không được lọt ra: {chu!r}'


def test_extract_docx_text_real_word_fixture_instr_text_and_del_text_between_two_runs_do_not_leak_not_hidden_by_trim() -> (
    None
):
    """<w:instrText>/<w:delText> NẰM GIỮA hai run có chữ không lọt vào kết quả (không phải nhờ trim che)"""
    chu = doc_chu_tu_file(
        docx_tu_xml(
            "<w:p>"
            "<w:r><w:t>Truoc</w:t></w:r>"
            '<w:r><w:instrText> HYPERLINK "http://evil.example/x" </w:instrText></w:r>'
            "<w:del><w:r><w:delText>chu da xoa</w:delText></w:r></w:del>"
            "<w:r><w:t>Sau</w:t></w:r>"
            "</w:p>"
        ),
        "docx",
    )
    assert chu == "TruocSau", f"mã field/chữ đã xoá không được lọt vào giữa: {chu!r}"


def test_extract_docx_text_real_word_fixture_outline_lvl_1_valid_still_gives_a_heading_of_the_right_level() -> (
    None
):
    """outlineLvl=1 (hợp lệ, trong khoảng 0-8) VẪN ra heading đúng cấp - chốt DƯƠNG cho tầng 1"""
    # outlineLvl is 0-based (0 = Heading1), so val="1" must give "## " (Heading2).
    chu = doc_chu_tu_file(
        docx_tu_xml('<w:p><w:pPr><w:outlineLvl w:val="1"/></w:pPr><w:r><w:t>Tieu de</w:t></w:r></w:p>'),
        "docx",
    )
    assert chu == "## Tieu de"


def test_extract_docx_text_real_word_fixture_outline_lvl_9_body_text_does_not_turn_a_paragraph_into_a_title() -> (
    None
):
    """outlineLvl=9 (Body Text theo ECMA-376, KHÔNG phải heading) không biến đoạn văn thành tiêu đề"""
    chu = doc_chu_tu_file(
        docx_tu_xml('<w:p><w:pPr><w:outlineLvl w:val="9"/></w:pPr><w:r><w:t>Doan thuong</w:t></w:r></w:p>'),
        "docx",
    )
    assert chu == "Doan thuong", f'không được có tiền tố "#": {chu!r}'


def test_extract_docx_text_real_word_fixture_nested_table_keeps_the_outer_row_and_the_cell_text() -> None:
    """bảng LỒNG trong ô không làm mất hàng bảng ngoài, không mất chữ trong ô"""

    def o_tc(chu: str) -> str:
        return f"<w:tc><w:p><w:r><w:t>{chu}</w:t></w:r></w:p></w:tc>"

    chu = doc_chu_tu_file(
        docx_tu_xml(
            "<w:tbl>"
            f"<w:tr>{o_tc('A1')}{o_tc('A2')}</w:tr>"
            "<w:tr>"
            "<w:tc>"
            "<w:p><w:r><w:t>B1</w:t></w:r></w:p>"
            f"<w:tbl><w:tr>{o_tc('n1')}{o_tc('n2')}</w:tr></w:tbl>"
            "<w:p><w:r><w:t>B1duoi</w:t></w:r></w:p>"
            "</w:tc>"
            f"{o_tc('B2')}"
            "</w:tr>"
            "</w:tbl>"
        ),
        "docx",
    )
    assert re.search(r"A1 \| A2", chu), f"mất hàng bảng ngoài: {chu!r}"
    assert re.search(r"\bB1\b", chu), f"mất chữ trong ô trước bảng lồng: {chu!r}"
    assert re.search(r"n1 \| n2", chu), f"mất nội dung bảng lồng: {chu!r}"
    assert re.search(r"B1duoi", chu), f"mất chữ trong ô sau bảng lồng: {chu!r}"
    assert re.search(r"B2", chu), f"mất ô còn lại của hàng ngoài: {chu!r}"
    # The outer row A1|A2 must come BEFORE the content of the B cell (not thrown out as a detached
    # "paragraph" in the wrong place by the nested table).
    assert chu.index("A1 | A2") < chu.index("n1 | n2")
    # Invariant "1 row = 1 line" (chunk_text cuts paragraphs by line): the outer row that holds the nested
    # table ("B1"/"n1 | n2"/"B1duoi"/"B2") MUST be on exactly ONE line.
    dong_chua_n1 = next((d for d in chu.split("\n") if "n1 | n2" in d), None)
    assert dong_chua_n1 is not None, f'không tìm thấy dòng chứa "n1 | n2" trong: {chu!r}'
    assert re.search(r"B1.*n1 \| n2.*B1duoi.*B2", dong_chua_n1), (
        f"hàng chứa bảng lồng phải nằm chung 1 dòng với B1/B1duoi/B2: {dong_chua_n1!r}"
    )


def test_extract_docx_text_bomb_and_ceilings_xml_missing_closing_tags_is_refused_in_under_a_second_without_spinning_the_cpu() -> (
    None
):
    """XML thiếu thẻ đóng bị từ chối trong dưới 1 giây, không quay CPU"""
    bom = docx_tu_xml("<w:p>" * 200_000)  # no closing tag at all
    t0 = time.perf_counter()
    with pytest.raises(Exception):  # noqa: B017, PT011 - any readable error; the point is the time
        doc_chu_tu_file(bom, "docx")
    ton_ms = (time.perf_counter() - t0) * 1000
    assert ton_ms < 1000, f"tốn {ton_ms}ms - phải dưới 1 giây (bản regex cũ tốn 38 090ms)"


def test_extract_docx_text_bomb_and_ceilings_entry_inflating_over_the_ceiling_is_refused_without_allocating_it_all() -> (
    None
):
    """entry giải nén vượt trần bị từ chối, KHÔNG cấp phát hết"""
    with pytest.raises(Exception, match=r"(?i)vượt quá giới hạn"):
        doc_chu_tu_file(zip_entry_qua_tran(), "docx")


def test_extract_docx_text_bomb_and_ceilings_deeply_nested_xml_over_the_ceiling_is_refused() -> None:
    """XML lồng sâu quá trần bị từ chối"""
    with pytest.raises(Exception, match=r"(?i)lồng quá sâu"):
        doc_chu_tu_file(docx_tu_xml("<w:p>" * 300 + "x"), "docx")


def test_extract_docx_text_bomb_and_ceilings_docx_with_only_images_raises_a_readable_vietnamese_error() -> (
    None
):
    """docx chỉ có ảnh (không có chữ nào) NÉM lỗi tiếng Việt đọc được"""
    # Returning an empty string would let the worker mark "Sẵn sàng, 0 đoạn" - a poisoned source looking
    # healthy. This is how a process-killing source gets past the "hong" branch.
    with pytest.raises(ValueError, match=r"(?i)không đọc được chữ nào"):
        doc_chu_tu_file(docx_chi_co_anh(), "docx")


def test_extract_docx_text_bomb_and_ceilings_text_over_the_8_mb_ceiling_is_refused_with_the_right_message_not_mislabelled_invalid_xml() -> (
    None
):
    """chữ trích ra vượt trần 8 MB bị từ chối với thông báo ĐÚNG NGHĨA, KHÔNG bị dán nhãn sai 'XML không hợp lệ'"""
    # The error of TRAN_TONG_KY_TU_TRICH is raised SYNCHRONOUSLY inside parse events, so it goes through
    # exactly the error-translation branch of xml_sax_scan. Hard-to-compress text (not repeated "x") so the
    # compression ratio ceiling is not hit first.
    buf = docx_tu_xml(f"<w:p><w:r><w:t>{chu_kho_nen(int(8.5 * 1024 * 1024))}</w:t></w:r></w:p>")
    with pytest.raises(Exception, match=r"(?i)vượt quá giới hạn 8 MB") as excinfo:
        doc_chu_tu_file(buf, "docx")
    assert not re.search("(?i)XML không hợp lệ", str(excinfo.value)), (
        "không được dán nhãn sai là lỗi cú pháp XML"
    )

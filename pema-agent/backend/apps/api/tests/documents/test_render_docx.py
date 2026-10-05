# ported from: src/documents/render-docx.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original unzipped the file and read the XML back (``readZipEntryText``); the same is done here with
``zipfile``. Where the original asserted on the XML, so does this port; two EXTRA tests re-open the bytes with
python-docx to check the file as a Word library sees it (marked EXTRA).
"""

from __future__ import annotations

import io
import re
import zipfile

from docx import Document

from pema.documents.document_content_schema import DocumentBlock, ParseOk, parse_document_blocks
from pema.documents.docx_text_runs import TextRunSpec, parse_text_runs
from pema.documents.render_docx import DocxMeta, render_docx
from pema.documents.render_docx_styles import CONTENT_WIDTH_DXA


def _blocks(raw: list[dict[str, object]]) -> list[DocumentBlock]:
    result = parse_document_blocks(raw)
    assert isinstance(result, ParseOk), result
    return result.value


def _entry(data: bytes, name: str) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return archive.read(name).decode("utf-8")


def _document_xml(raw: list[dict[str, object]], title: str | None = None) -> str:
    return _entry(render_docx(_blocks(raw), DocxMeta(title=title)), "word/document.xml")


def test_render_docx_creates_a_valid_docx_zip_with_the_required_parts() -> None:
    """tạo file .docx hợp lệ (zip có đủ phần bắt buộc)"""
    buf = render_docx(_blocks([{"type": "paragraph", "text": "xin chào"}]))
    assert buf[:2] == b"PK", "file zip phải bắt đầu bằng PK"
    with zipfile.ZipFile(io.BytesIO(buf)) as archive:
        entries = archive.namelist()
    assert "word/document.xml" in entries, "thiếu document.xml"
    assert "[Content_Types].xml" in entries, "thiếu Content_Types"


def test_render_docx_keeps_vietnamese_diacritics() -> None:
    """giữ nguyên tiếng Việt có dấu"""
    xml = _document_xml([{"type": "paragraph", "text": "Báo giá dịch vụ tháng 7"}])
    assert "Báo giá dịch vụ tháng 7" in xml


def test_render_docx_title_and_3_heading_levels_all_reach_the_file() -> None:
    """tiêu đề tài liệu + heading 3 cấp đều vào file"""
    xml = _document_xml(
        [
            {"type": "heading", "text": "Phần một", "level": 1},
            {"type": "heading", "text": "Phần hai", "level": 2},
            {"type": "heading", "text": "Phần ba", "level": 3},
        ],
        "Tiêu đề chính",
    )
    for text in ["Tiêu đề chính", "Phần một", "Phần hai", "Phần ba"]:
        assert text in xml, f'thiếu "{text}"'
    # Assert ALL THREE levels: checking only Heading1 and Heading2 would stay green if the lookup mapped level
    # 3 to the wrong place, and since ``level`` is a number range that lookup is a hand-written function, no
    # longer a table guarded by the compiler.
    for cap in [1, 2, 3]:
        assert re.search(f"Heading{cap}", xml), f"thiếu Heading{cap}"


def test_render_docx_bullets_use_numbering_and_never_insert_the_bullet_character() -> None:
    """bullets dùng numbering, KHÔNG chèn ký tự • vào text"""
    xml = _document_xml([{"type": "bullets", "items": ["Giao trong 3 ngày", "Bảo hành 12 tháng"]}])
    assert "numPr" in xml, "phải khai numbering để Word nhận là danh sách"
    assert "Giao trong 3 ngày" in xml
    # Regression of the gotcha: a raw bullet in <w:t> leaves Word without indent or numbering continuation
    assert not re.search(r"<w:t[^>]*>•", xml), "không được chèn • thẳng vào text"


def test_render_docx_table_dual_width_dxa_shading_clear_and_repeating_header() -> None:
    """bảng: dual width DXA + shading CLEAR + header lặp lại"""
    xml = _document_xml(
        [
            {
                "type": "table",
                "headers": ["Sản phẩm", "Số lượng"],
                "rows": [["Bàn phím", "2"], ["Chuột", "3"]],
            }
        ]
    )
    assert "Bàn phím" in xml
    assert "Chuột" in xml
    assert 'w:type="dxa"' in xml, "chiều rộng phải là DXA (PERCENTAGE vỡ ở Google Docs)"
    assert 'w:val="clear"' in xml, "shading phải CLEAR - SOLID render nền đen"
    assert 'w:val="solid"' not in xml, "không được dùng shading SOLID"
    assert "tblHeader" in xml, "header nên lặp lại khi bảng tràn trang"


def test_render_docx_column_widths_add_up_to_the_content_width() -> None:
    """tổng bề rộng các cột khớp bề rộng vùng nội dung (lệch là Word render méo)"""
    # 5 columns split CONTENT_WIDTH with a remainder -> check the remainder is piled on correctly
    for col_count in (3, 5, 7):
        headers = [f"Cột {i + 1}" for i in range(col_count)]
        xml = _document_xml([{"type": "table", "headers": headers, "rows": [["x" for _ in headers]]}])
        grid = re.findall(r'<w:gridCol w:w="(\d+)"\s*/>', xml)
        assert sum(int(w) for w in grid) == CONTENT_WIDTH_DXA, (
            f"{col_count} cột: tổng phải khớp vùng nội dung"
        )


def test_render_docx_vietnamese_typography_times_new_roman_and_black_headings_not_theme_blue() -> None:
    """typography chuẩn văn bản VN: Times New Roman, heading ĐEN không phải xanh theme"""
    buf = render_docx(
        _blocks([{"type": "heading", "text": "Mục một", "level": 1}]), DocxMeta(title="KẾ HOẠCH")
    )
    styles = _entry(buf, "word/styles.xml")
    assert "Times New Roman" in styles, "font phải là Times New Roman"
    # The default theme paints headings accent blue (2E74B5/1F4E79...) - overridden to black
    assert not re.search(r"(2E74B5|1F4E79|2F5496|4472C4)", styles, re.IGNORECASE), (
        "heading không được dính màu xanh theme"
    )
    doc = _entry(buf, "word/document.xml")
    assert "KẾ HOẠCH" in doc
    assert "Mục một" in doc


def test_render_docx_page_margins_follow_the_administrative_standard() -> None:
    """lề trang chuẩn văn bản hành chính: trái 3cm (1701), phải 1.5cm (850)"""
    xml = _document_xml([{"type": "paragraph", "text": "x"}])
    assert re.search(r'w:left="1701"', xml)
    assert re.search(r'w:right="850"', xml)


def test_render_docx_bold_marker_becomes_a_bold_run_and_asterisks_never_reach_the_text() -> None:
    """marker **đậm** thành run bold, dấu sao không lọt vào text"""
    xml = _document_xml([{"type": "paragraph", "text": "**Thời gian:** từ 07h00 ngày 10/8"}])
    assert "**" not in xml, "dấu ** không được xuất hiện trong file"
    assert "Thời gian:" in xml, "phần đậm phải còn nguyên chữ"
    assert "từ 07h00 ngày 10/8" in xml
    # The run holding "Thời gian:" must be bold: <w:b/> before that text in the same run
    assert re.search(r"<w:b/>.*?Thời gian:", xml, re.DOTALL), "phần trong ** phải in đậm"


def test_render_docx_right_aligned_paragraph_has_no_first_line_indent() -> None:
    """paragraph align right: canh phải và KHÔNG thụt đầu dòng (dòng lạc khoản)"""
    xml = _document_xml(
        [
            {"type": "paragraph", "text": "Hà Nội, ngày 10 tháng 8 năm 2026", "align": "right"},
            {"type": "paragraph", "text": "Đoạn văn xuôi bình thường trong văn bản."},
        ]
    )
    assert re.search(r'w:val="right"', xml)
    # A justified paragraph has a first-line indent, a closing line does not
    assert re.search(r'w:firstLine="567"', xml)
    at = xml.index("Hà Nội")
    right_para = xml[max(0, at - 700) : at]
    assert "w:firstLine" not in right_para, "dòng canh phải không được thụt đầu dòng"


def test_render_docx_two_columns_is_a_borderless_2_column_table_for_motto_and_signature_block() -> None:
    """two_columns: bảng 2 cột KHÔNG viền cho quốc hiệu / khối ký tên"""
    xml = _document_xml(
        [
            {
                "type": "two_columns",
                "left": ["UBND XÃ A", "**TRẠM Y TẾ**"],
                "right": ["**CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM**", "**Độc lập - Tự do - Hạnh phúc**"],
            }
        ]
    )
    assert "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM" in xml
    assert "TRẠM Y TẾ" in xml
    # The table must hide its borders: every side declared none
    assert re.search(r'w:val="none"', xml), "viền bảng two_columns phải là none"
    assert "**" not in xml, "marker đậm phải được parse, không lọt vào file"


def test_render_docx_table_has_cell_padding_so_text_does_not_stick_to_the_border() -> None:
    """bảng có đệm trong ô - chữ không dính sát viền"""
    xml = _document_xml([{"type": "table", "headers": ["A"], "rows": [["x"]]}])
    # tblCellMar with left/right margin 108 twips
    assert re.search(r"w:tblCellMar", xml), "bảng phải khai cell margin"
    assert re.search(r'w:w="108"', xml)


def test_render_docx_paragraph_with_newlines_is_split_into_several_paragraphs() -> None:
    """đoạn văn có "\\n" bị tách thành nhiều Paragraph (docx bỏ qua ký tự xuống dòng)"""
    xml = _document_xml([{"type": "paragraph", "text": "Dòng một\nDòng hai\n\nDòng ba"}])
    for line in ("Dòng một", "Dòng hai", "Dòng ba"):
        assert line in xml
    # 3 lines with text -> at least 3 <w:p>, and no "\n" leaks into the text
    assert xml.count("<w:p>") >= 3
    assert not re.search(r"<w:t[^>]*>[^<]*\n", xml), "không được để ký tự xuống dòng trong text"


def test_render_docx_mixed_blocks_come_out_in_the_order_sent() -> None:
    """nhiều block trộn lẫn vẫn ra đúng thứ tự"""
    xml = _document_xml(
        [
            {"type": "heading", "text": "Mở đầu", "level": 1},
            {"type": "paragraph", "text": "Nội dung mở đầu"},
            {"type": "bullets", "items": ["Ý một"]},
            {"type": "table", "headers": ["A"], "rows": [["B"]]},
        ]
    )
    order = [xml.find(t) for t in ["Mở đầu", "Nội dung mở đầu", "Ý một", "B"]]
    assert all(pos > 0 and (i == 0 or pos > order[i - 1]) for i, pos in enumerate(order)), (
        "các block phải xuất hiện đúng thứ tự model gửi"
    )


# ------------------------------------------------------------------ EXTRA: as python-docx reads it


def test_extra_render_docx_reopens_with_python_docx_in_order_with_tables_and_styles() -> None:
    buf = render_docx(
        _blocks(
            [
                {"type": "heading", "text": "Mở đầu", "level": 1},
                {"type": "paragraph", "text": "Nội dung **đậm** thường"},
                {"type": "table", "headers": ["A", "B"], "rows": [["1", "2"]]},
            ]
        ),
        DocxMeta(title="  Tiêu đề  "),
    )
    doc = Document(io.BytesIO(buf))
    texts = [p.text for p in doc.paragraphs if p.text]
    assert texts == ["Tiêu đề", "Mở đầu", "Nội dung đậm thường"]
    title_style = doc.paragraphs[0].style
    assert title_style is not None
    assert title_style.name == "Title"
    assert [c.text for c in doc.tables[0].rows[1].cells] == ["1", "2"]
    section = doc.sections[0]
    assert (section.page_width, section.page_height) == (
        (11906 * 635),
        (16838 * 635),
    ), "A4"


def test_extra_render_docx_blank_or_missing_title_adds_no_title_paragraph() -> None:
    blocks = _blocks([{"type": "paragraph", "text": "x"}])
    for meta in (None, DocxMeta(), DocxMeta(title="   ")):
        doc = Document(io.BytesIO(render_docx(blocks, meta)))
        assert [p.text for p in doc.paragraphs] == ["x"]


def test_extra_parse_text_runs_alternates_plain_and_bold_and_never_returns_empty() -> None:
    assert parse_text_runs("a **b** c") == [
        TextRunSpec("a ", False),
        TextRunSpec("b", True),
        TextRunSpec(" c", False),
    ]
    assert parse_text_runs("**x**", base_bold=False) == [TextRunSpec("x", True)]
    assert parse_text_runs("a", base_bold=True) == [TextRunSpec("a", True)]
    assert parse_text_runs("") == [TextRunSpec("", False)]
    assert parse_text_runs("****", base_bold=True) == [TextRunSpec("****", True)]

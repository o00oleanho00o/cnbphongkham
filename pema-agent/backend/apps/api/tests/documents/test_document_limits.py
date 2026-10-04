# ported from: src/documents/document-limits.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original booted a temp env with ``DOCUMENT_MAX_*`` overrides; here the same values come from a static
tuning provider installed per test (``install_tuning_provider``) and removed afterwards.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pytest

from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.documents.document_content_schema import (
    BulletsBlock,
    DocumentBlock,
    ParagraphBlock,
    Sheet,
    TableBlock,
)
from pema.documents.document_limits import (
    LimitCheck,
    check_document_limits,
    check_spreadsheet_limits,
    safe_file_name,
)


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    install_tuning_provider(
        StaticTuningProvider(
            {
                "DOCUMENT_MAX_BLOCKS": 5,
                "DOCUMENT_MAX_ROWS": 4,
                # 500 is the lower bound of the tuning spec - set lower and it is ignored
                "DOCUMENT_MAX_CHARS": 500,
                "DOCUMENT_MAX_SHEETS": 2,
            }
        )
    )
    yield
    reset_tuning_provider()


def para(text: str) -> DocumentBlock:
    return ParagraphBlock(type="paragraph", text=text)


# ------------------------------------------------------------------ checkDocumentLimits


def test_check_document_limits_moderate_content_passes() -> None:
    """nội dung vừa phải thì cho qua"""
    assert check_document_limits([para("chào"), para("bạn")]) == LimitCheck(ok=True)


def test_check_document_limits_too_many_blocks_reports_current_count_and_ceiling() -> None:
    """quá nhiều block -> báo rõ số hiện tại và trần"""
    result = check_document_limits([para("x") for _ in range(6)])
    assert result.ok is False
    assert re.search(r"6 phần.*trần 5", result.reason)


def test_check_document_limits_table_with_too_many_rows_is_blocked() -> None:
    """bảng quá nhiều dòng -> chặn"""
    result = check_document_limits([TableBlock(type="table", headers=["A"], rows=[["x"] for _ in range(5)])])
    assert result.ok is False
    assert re.search(r"5 dòng.*trần 4", result.reason)


def test_check_document_limits_row_with_wrong_column_count_is_blocked_naming_the_row() -> None:
    """dòng bảng lệch số cột -> chặn, chỉ đúng dòng nào sai"""
    result = check_document_limits([TableBlock(type="table", headers=["A", "B"], rows=[["1", "2"], ["3"]])])
    assert result.ok is False
    assert re.search(r"Dòng 2.*1 ô.*2 cột", result.reason)


def test_check_document_limits_total_characters_over_the_ceiling_is_blocked() -> None:
    """tổng ký tự vượt trần -> chặn"""
    result = check_document_limits([para("x" * 501)])
    assert result.ok is False
    assert re.search(r"501 ký tự.*trần 500", result.reason)


def test_check_document_limits_character_count_includes_bullets_and_tables() -> None:
    """đếm ký tự gộp cả bullets và bảng, không chỉ đoạn văn"""
    result = check_document_limits(
        [
            BulletsBlock(type="bullets", items=["y" * 400]),
            TableBlock(type="table", headers=["z" * 150], rows=[["w"]]),
        ]
    )
    assert result.ok is False, "400 + 150 + 1 > 500 nên phải chặn"


# ------------------------------------------------------------------ checkSpreadsheetLimits


def _sheet(name: str, rows: list[list[Any]]) -> Sheet:
    return Sheet.model_validate({"name": name, "headers": ["Cột"], "rows": rows})


def test_check_spreadsheet_limits_valid_spreadsheet_passes() -> None:
    """bảng tính hợp lệ thì cho qua"""
    assert check_spreadsheet_limits([_sheet("S1", [[{"kind": "text", "value": "a"}]])]) == LimitCheck(ok=True)


def test_check_spreadsheet_limits_too_many_sheets_is_blocked() -> None:
    """quá nhiều sheet -> chặn"""
    sheets = [_sheet(f"S{i}", [[{"kind": "text", "value": "a"}]]) for i in range(3)]
    result = check_spreadsheet_limits(sheets)
    assert result.ok is False
    assert re.search(r"3 sheet.*trần 2", result.reason)


def test_check_spreadsheet_limits_row_with_wrong_column_count_is_blocked_with_sheet_name() -> None:
    """dòng lệch số cột -> chặn kèm tên sheet"""
    result = check_spreadsheet_limits(
        [
            Sheet.model_validate(
                {"name": "Báo giá", "headers": ["A", "B"], "rows": [[{"kind": "text", "value": "x"}]]}
            )
        ]
    )
    assert result.ok is False
    assert re.search(r"Báo giá.*dòng 1", result.reason)


# ------------------------------------------------------------------ safeFileName


def test_safe_file_name_keeps_vietnamese_diacritics_and_forces_the_right_extension() -> None:
    """giữ tên tiếng Việt có dấu, ép đúng đuôi"""
    assert safe_file_name("Báo giá tháng 7", "docx") == "Báo giá tháng 7.docx"
    assert safe_file_name("bang-luong.xlsx", "xlsx") == "bang-luong.xlsx"


def test_safe_file_name_blocks_path_traversal() -> None:
    """chặn path traversal"""
    name = safe_file_name("../../data/accounts/credentials", "docx")
    assert ".." not in name, f'vẫn còn .. trong "{name}"'
    assert "/" not in name
    assert "\\" not in name
    assert name.endswith(".docx")


def test_safe_file_name_dangerous_extension_is_replaced_by_the_real_one() -> None:
    """đuôi nguy hiểm bị thay bằng đuôi thật"""
    assert safe_file_name("virus.exe", "docx") == "virus.docx"
    assert safe_file_name("script.bat", "xlsx") == "script.xlsx"


def test_safe_file_name_empty_or_all_odd_characters_uses_the_default_name() -> None:
    """tên rỗng hoặc toàn ký tự lạ -> dùng tên mặc định"""
    assert safe_file_name("", "docx") == "tai-lieu.docx"
    assert safe_file_name("***", "xlsx") == "tai-lieu.xlsx"


def test_safe_file_name_too_long_name_is_cut_short() -> None:
    """tên quá dài bị cắt ngắn"""
    name = safe_file_name("a" * 200, "docx")
    assert len(name) <= 85, f"tên dài {len(name)} ký tự"

# ported from: src/documents/document-content-schema.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Tests the REAL schema PARSE - the layer that was once left empty: the tool tests called ``execute`` directly
(bypassing validation), the render tests used plain objects, so the "Duplicate discriminator value" bug in the
Excel cell schema killed ``create_excel_file`` 100% on real Zalo while 423 tests stayed green.

Translation notes: ``safeParse`` -> ``TypeAdapter.validate_python`` inside ``_parses``; "must not throw" means
"may only raise ``ValidationError``" (any other exception is the regression this test guards).
The last section holds EXTRA tests for the parse / JSON-Schema API of the Python port (not in the original).
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest
from pydantic import ValidationError

from pema.documents.document_content_schema import (
    HeadingBlock,
    NumberCell,
    ParseFail,
    ParseOk,
    Sheet,
    SumFormulaCell,
    TextCell,
    document_block_schema,
    document_blocks_json_schema,
    parse_document_blocks,
    parse_sheets,
    sheets_json_schema,
    spreadsheet_cell_schema,
)


def _parses(adapter: Any, value: object) -> bool:
    """``safeParse(...).success``; ONLY a ``ValidationError`` is an acceptable failure."""
    try:
        adapter.validate_python(value)
    except ValidationError:
        return False
    return True


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(by_alias=True)


# ------------------------------------------------------------------ spreadsheetCellSchema


def test_spreadsheet_cell_schema_regression_zalo_crash_parsing_object_cells_must_not_throw() -> None:
    """HỒI QUY vụ chết trên Zalo: parse ô object KHÔNG được throw"""
    # A discriminated union with 2 schemas of the same kind="formula" threw right inside safeParse
    for cell in [
        {"kind": "text", "value": "x"},
        {"kind": "number", "value": 1},
        {"kind": "formula", "op": "multiply", "columns": ["B", "C"]},
        {"kind": "formula", "op": "sum", "column": "D", "fromRow": 2, "toRow": 9},
        {"kind": "kind-la", "value": "x"},
    ]:
        _parses(spreadsheet_cell_schema, cell)  # any exception other than ValidationError fails the test


def test_spreadsheet_cell_schema_every_valid_object_form_parses() -> None:
    """mọi dạng object hợp lệ đều parse được"""
    assert _dump(spreadsheet_cell_schema.validate_python({"kind": "text", "value": "Vụ A"})) == {
        "kind": "text",
        "value": "Vụ A",
    }
    assert _dump(spreadsheet_cell_schema.validate_python({"kind": "number", "value": 5})) == {
        "kind": "number",
        "value": 5,
        "format": "plain",
    }
    assert _dump(
        spreadsheet_cell_schema.validate_python({"kind": "formula", "op": "multiply", "columns": ["b", "c"]})
    ) == {"kind": "formula", "op": "multiply", "columns": ["B", "C"]}


def test_spreadsheet_cell_schema_multiply_cell_needs_exactly_2_columns() -> None:
    """ô nhân phải có ĐÚNG 2 cột - thiếu hay thừa đều bị chối

    ``columns`` was a ``z.tuple()`` so the TYPE held the length. It is now a length-2 list (so providers that
    inspect the schema strictly accept it), the length became a RUNTIME constraint and needs a guard. Without
    it ``columns[1]`` is undefined and the formula is written to the file as "B5*undefined5"."""
    for columns in ([], ["B"], ["B", "C", "D"]):
        ket = _parses(spreadsheet_cell_schema, {"kind": "formula", "op": "multiply", "columns": columns})
        assert ket is False, f"columns={json.dumps(columns)} lẽ ra phải bị chối"


def test_spreadsheet_cell_schema_plain_string_and_number_are_accepted_and_normalised() -> None:
    """chuỗi thường và số thuần - cách model gửi TỰ NHIÊN - được nhận và chuẩn hóa"""
    assert _dump(spreadsheet_cell_schema.validate_python("Vụ kim cương A")) == {
        "kind": "text",
        "value": "Vụ kim cương A",
    }
    assert _dump(spreadsheet_cell_schema.validate_python(123)) == {
        "kind": "number",
        "value": 123,
        "format": "plain",
    }


def test_spreadsheet_cell_schema_string_formulas_parse_into_objects() -> None:
    """công thức dạng chuỗi "=B2*C2" và "=SUM(D2:D9)" được parse thành object"""
    assert _dump(spreadsheet_cell_schema.validate_python("=B2*C2")) == {
        "kind": "formula",
        "op": "multiply",
        "columns": ["B", "C"],
    }
    assert _dump(spreadsheet_cell_schema.validate_python("=SUM(D2:D9)")) == {
        "kind": "formula",
        "op": "sum",
        "column": "D",
        "fromRow": 2,
        "toRow": 9,
    }
    # Lower case + spaces are still understood
    assert _dump(spreadsheet_cell_schema.validate_python("= b2 * c2")) == {
        "kind": "formula",
        "op": "multiply",
        "columns": ["B", "C"],
    }


def test_spreadsheet_cell_schema_unsupported_formulas_are_rejected_with_guidance() -> None:
    """công thức ngoài 2 dạng hỗ trợ bị TỪ CHỐI kèm hướng dẫn, không âm thầm thành chữ"""
    for bad in ["=XLOOKUP(A1,B:B,C:C)", "=SUMIFS(D:D,A:A,1)", "=A2+B2", "=SUM(A2:B9)"]:
        with pytest.raises(ValidationError) as caught:
            spreadsheet_cell_schema.validate_python(bad)
        messages = json.dumps(
            caught.value.errors(include_url=False, include_context=False), ensure_ascii=False
        )
        assert "Chỉ hỗ trợ công thức" in messages, f'"{bad}" phải kèm hướng dẫn tiếng Việt'


def test_spreadsheet_cell_schema_full_sheet_with_mixed_rows_parses() -> None:
    """sheet đầy đủ với rows trộn chuỗi + số + công thức chuỗi parse được"""
    parsed = Sheet.model_validate(
        {
            "name": "Tổng quan",
            "headers": ["Vụ việc", "Số nạn nhân", "Thiệt hại (tỷ)", "Ghi chú"],
            "rows": [
                ["Vụ A", 12, 5.5, "đang xét xử"],
                ["Tổng", {"kind": "number", "value": 12}, "=SUM(C2:C2)", ""],
            ],
        }
    )
    assert parsed.rows[0][1].kind == "number"
    assert parsed.rows[1][2].kind == "formula"


# ------------------------------------------------------------------ documentBlockSchema


def test_document_block_schema_all_5_block_types_parse_and_none_makes_it_throw() -> None:
    """cả 5 loại block parse được, không loại nào làm safeParse throw"""
    blocks = [
        {"type": "heading", "text": "Mục", "level": 1},
        {"type": "paragraph", "text": "Đoạn văn"},
        {"type": "paragraph", "text": "Lạc khoản", "align": "right"},
        {"type": "bullets", "items": ["a"]},
        {"type": "table", "headers": ["A"], "rows": [["x"]]},
        {"type": "two_columns", "left": ["trái"], "right": ["phải"]},
    ]
    for block in blocks:
        assert _parses(document_block_schema, block) is True, json.dumps(block, ensure_ascii=False)


# `level` was a union of literals (1|2|3) so the range was held by the TYPE. It is now a number range - changed
# so Google accepts the schema - so the constraint is a RUNTIME matter and needs a guard. If level 0 or 4 slips
# through, the lookup in render_docx returns the nearest level, i.e. the file comes out with the wrong level
# and nobody is told.


def test_heading_block_level_accepts_exactly_1_2_3() -> None:
    """nhận đúng 1, 2, 3"""
    for level in (1, 2, 3):
        ket = _parses(document_block_schema, {"type": "heading", "text": "M", "level": level})
        assert ket is True, f"cấp {level} lẽ ra phải nhận"


def test_heading_block_level_rejects_out_of_range_and_fractions() -> None:
    """chối cấp ngoài khoảng và số lẻ"""
    for level in (0, 4, 1.5, -1):
        ket = _parses(document_block_schema, {"type": "heading", "text": "M", "level": level})
        assert ket is False, f"cấp {level} lẽ ra phải bị chối"


def test_heading_block_level_defaults_to_2_when_omitted() -> None:
    """bỏ trống thì mặc định cấp 2"""
    ket = document_block_schema.validate_python({"type": "heading", "text": "M"})
    assert _dump(ket) == {"type": "heading", "text": "M", "level": 2}


# ------------------------------------------------------------------ EXTRA: parse API + JSON Schema


def test_extra_parse_document_blocks_ok_returns_typed_blocks() -> None:
    result = parse_document_blocks([{"type": "heading", "text": "Mục", "level": 1}])
    assert isinstance(result, ParseOk)
    assert isinstance(result.value[0], HeadingBlock)


def test_extra_parse_document_blocks_empty_or_garbage_returns_a_vietnamese_reason() -> None:
    for raw in ([], "không phải danh sách", [{"type": "heading", "text": "M", "level": 4}], [{"type": "lạ"}]):
        result = parse_document_blocks(raw)
        assert isinstance(result, ParseFail)
        assert result.reason.startswith("Nội dung không hợp lệ")
        assert result.reason.endswith("Hãy sửa rồi gọi lại.")


def test_extra_parse_reason_never_echoes_the_offending_value() -> None:
    """The reason goes to the model AND to logs; it must name the path and the rule, never the content."""
    secret = "CONTENT-THAT-MUST-NOT-LEAK"
    result = parse_document_blocks([{"type": "heading", "text": secret, "level": 9}])
    assert isinstance(result, ParseFail)
    assert secret not in result.reason


def test_extra_parse_sheets_ok_returns_typed_cells() -> None:
    result = parse_sheets([{"name": "S", "headers": ["A", "B"], "rows": [["x", 1]]}])
    assert isinstance(result, ParseOk)
    cells = result.value[0].rows[0]
    assert isinstance(cells[0], TextCell)
    assert isinstance(cells[1], NumberCell)


def test_extra_parse_sheets_unsupported_formula_reason_carries_the_guidance() -> None:
    result = parse_sheets([{"name": "S", "headers": ["A"], "rows": [["=A2+B2"]]}])
    assert isinstance(result, ParseFail)
    assert "Chỉ hỗ trợ công thức" in result.reason
    assert "sheets[0].rows[0][0]" in result.reason


def test_extra_sum_cell_exposes_snake_case_attributes_and_camel_case_wire_names() -> None:
    cell = spreadsheet_cell_schema.validate_python("=SUM(D2:D9)")
    assert isinstance(cell, SumFormulaCell)
    assert (cell.from_row, cell.to_row) == (2, 9)
    assert _dump(cell)["fromRow"] == 2


def _walk(node: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        mapping = cast("dict[str, Any]", node)
        found.append(mapping)
        for value in mapping.values():
            found.extend(_walk(value))
    elif isinstance(node, list):
        for item in cast("list[Any]", node):
            found.extend(_walk(item))
    return found


@pytest.mark.parametrize("build", [document_blocks_json_schema, sheets_json_schema])
def test_extra_tool_json_schema_is_provider_safe(build: Any) -> None:
    """The two bugs of 2026-08-06 that muted the bot on a provider: a numeric ``enum`` and tuple ``items``."""
    schema = build()
    for node in _walk(schema):
        assert "$ref" not in node, "must be self-contained"
        assert "$defs" not in node, "must be self-contained"
        assert "prefixItems" not in node, "no tuple"
        assert not isinstance(node.get("items"), list), "``items`` must be an object"
        enum = node.get("enum")
        if enum is not None:
            assert all(isinstance(value, str) for value in enum), "no numeric enum"
        assert {"type": "null"} not in node.get("anyOf", []), "optional means absent, not null"
    assert schema["type"] == "array"
    assert schema["minItems"] == 1


def test_extra_heading_level_json_schema_is_an_integer_range() -> None:
    blocks = document_blocks_json_schema()["items"]["oneOf"]
    heading = next(b for b in blocks if b["properties"]["type"]["const"] == "heading")
    assert heading["properties"]["level"] == {"type": "integer", "minimum": 1, "maximum": 3, "default": 2}


def test_extra_sheet_json_schema_keeps_the_model_facing_vietnamese_descriptions() -> None:
    sheet = sheets_json_schema()["items"]
    assert "GIỮ NGUYÊN dấu tiếng Việt" in sheet["properties"]["name"]["description"]
    assert "navy" in sheet["properties"]["theme"]["description"]
    assert sheet["properties"]["theme"]["enum"] == ["navy", "blue", "green", "burgundy", "slate", "teal"]
    # A PROPERTY called "title" must survive the clean-up of the cosmetic ``title`` keyword
    assert "title" in sheet["properties"]

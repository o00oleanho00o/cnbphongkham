# ported from: src/config/parse-disabled-tools.ts
"""``parse-disabled-tools.ts`` has no test file in the original; the behaviour is its docstring: defensive reading,
a corrupt column yields an EMPTY list (fail-open, accepted and documented), never an exception."""

from __future__ import annotations

import pytest

from pema.config.parse_disabled_tools import parse_disabled_tools


def test_parse_disabled_tools_reads_a_json_array_of_tool_keys() -> None:
    """đọc mảng JSON key tool"""
    assert parse_disabled_tools('["web_search","create_image"]') == ["web_search", "create_image"]


def test_parse_disabled_tools_accepts_the_list_a_jsonb_column_already_decoded() -> None:
    """(thêm) cột jsonb của Postgres đã là list"""
    assert parse_disabled_tools(["web_search", "create_image"]) == ["web_search", "create_image"]


def test_parse_disabled_tools_keeps_only_strings() -> None:
    """chỉ giữ phần tử là chuỗi"""
    assert parse_disabled_tools('["a", 1, null, {"b": 2}, "c"]') == ["a", "c"]


@pytest.mark.parametrize("raw", ["", "không phải json", "{bad", '{"a": 1}', '"chuoi"', "42", "null", None, 7])
def test_parse_disabled_tools_corrupt_or_wrong_shape_yields_an_empty_list_never_raises(raw: object) -> None:
    """hỏng thì trả mảng RỖNG (= không tắt gì) chứ không ném: cột hỏng không được phép làm chết cả lượt trả lời"""
    assert parse_disabled_tools(raw) == []

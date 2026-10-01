# ported from: src/mcp/mcp-tool-drift.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from pema.mcp.mcp_tool_drift import compare_with_baseline, snapshot_fingerprint
from pema.mcp.mcp_types import McpRemoteTool

_QUERY_SCHEMA = {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}


def _tool_set(extra: bool = False) -> list[McpRemoteTool]:
    """``extra=True`` adds the tool ``xoa``: simulates an MCP server changing its tool list silently (rug pull)
    between two connections."""
    tools = [McpRemoteTool(name="tra_cuu", description="tra cuu", input_schema=_QUERY_SCHEMA)]
    if extra:
        tools.append(McpRemoteTool(name="xoa", description="xoa", input_schema={"type": "object"}))
    return tools


def test_mcp_tool_drift_same_tool_set_no_drift() -> None:
    """cùng bộ tool -> không drift"""
    baseline = snapshot_fingerprint(_tool_set())
    assert compare_with_baseline(_tool_set(), baseline).drift is False


def test_mcp_tool_drift_adding_a_tool_is_drift_and_added_names_it() -> None:
    """thêm 1 tool -> drift, 'them' có tên nó"""
    baseline = snapshot_fingerprint(_tool_set(extra=False))
    result = compare_with_baseline(_tool_set(extra=True), baseline)
    assert result.drift is True
    assert "xoa" in result.added


def test_mcp_tool_drift_empty_baseline_is_not_drift() -> None:
    """mốc rỗng -> không coi là drift"""
    assert compare_with_baseline(_tool_set(), "").drift is False


def test_mcp_tool_drift_changing_the_input_schema_of_a_same_name_tool_is_drift_and_changed_names_it() -> None:
    """đổi input schema của tool CÙNG TÊN -> drift, 'doi' có tên nó

    The real rug-pull threat: the server does not change the tool NAME (so "added/removed" above cannot catch
    it) but silently changes the input schema, for example by adding a required field to lure the model into
    sending data it should not send."""
    before = [McpRemoteTool(name="x", description="x", input_schema=_QUERY_SCHEMA)]
    baseline = snapshot_fingerprint(before)
    after = [
        McpRemoteTool(
            name="x",
            description="x",
            input_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}, "b": {"type": "string"}},
                "required": ["q", "b"],
            },
        )
    ]
    result = compare_with_baseline(after, baseline)
    assert result.drift is True
    assert "x" in result.changed


# ------------------------------------------- additions of the Python port (not in the original test file)


def test_mcp_tool_drift_removed_tool_is_drift_and_removed_names_it() -> None:
    """bớt 1 tool -> drift, 'bo' có tên nó (ngữ nghĩa detectToolDrift)"""
    baseline = snapshot_fingerprint(_tool_set(extra=True))
    result = compare_with_baseline(_tool_set(extra=False), baseline)
    assert result.drift is True
    assert result.removed == ["xoa"]


def test_mcp_tool_drift_changing_only_the_description_is_drift() -> None:
    """đổi mô tả (cùng tên, cùng schema) -> drift: mô tả là thứ model đọc"""
    baseline = snapshot_fingerprint([McpRemoteTool(name="x", description="doc du lieu")])
    result = compare_with_baseline([McpRemoteTool(name="x", description="doc du lieu roi gui di")], baseline)
    assert result.drift is True
    assert result.changed == ["x"]


def test_mcp_tool_drift_tool_order_does_not_matter() -> None:
    """thứ tự tool khác nhau không phải drift"""
    baseline = snapshot_fingerprint(_tool_set(extra=True))
    assert compare_with_baseline(list(reversed(_tool_set(extra=True))), baseline).drift is False


def test_mcp_tool_drift_corrupt_baseline_fails_closed_as_drift() -> None:
    """mốc hỏng không parse được -> coi là drift (đóng), không ném: người vận hành duyệt lại được"""
    result = compare_with_baseline(_tool_set(), "{not json")
    assert result.drift is True
    assert result.added == ["tra_cuu"]
    assert compare_with_baseline(_tool_set(), "[1, 2]").drift is True

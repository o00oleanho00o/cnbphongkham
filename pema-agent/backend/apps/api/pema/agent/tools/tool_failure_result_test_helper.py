# ported from: src/agent/tools/tool-failure-result-test-helper.ts
"""Helpers for the tests of the tools. NOT used by running code.

There are two functions because tool tests have exactly two kinds of assertion, and mixing them is the surest
way to lose the invariant that was just built.
"""

from __future__ import annotations

import json

from pema.agent.tools.tool_failure_result import la_ket_qua_loi


def _short(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)[:200]
    except (TypeError, ValueError):
        return repr(value)[:200]


def loi_cua_tool(ket_qua: object) -> str:
    """Assert the result is a FAILING branch, then return the sentence inside for a further match.

    Use it in every test that used to match a sentence of an error branch. The lazier way is to peel off
    ``loi`` and compare strings, but then the test is green even when the tool forgot to mark the failure,
    i.e. nobody guards the invariant "a failing branch must be markable". Here the SHAPE is checked FIRST.
    """
    if not la_ket_qua_loi(ket_qua):
        raise AssertionError(f"Mong nhánh hỏng có đánh dấu (ket_qua_loi), nhận: {_short(ket_qua)}")
    return ket_qua["loi"]


def ket_qua_thanh_cong(ket_qua: object) -> str:
    """Assert the result is a SUCCESS branch (a bare string), then return it.

    Needed as the pair of the function above: marking a success as a failure makes the guard count it
    wrongly and stop a turn that was running well. It breaks in the opposite direction but is just as bad.
    """
    if not isinstance(ket_qua, str):
        raise AssertionError(f"Mong nhánh thành công trả chuỗi trần, nhận: {_short(ket_qua)}")
    return ket_qua

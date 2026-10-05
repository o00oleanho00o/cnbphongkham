# ported from: src/knowledge/docx-sax-table-tracker.ts
"""Track Word tables (``<w:tbl>``) through a STACK, split from ``docx_sax_paragraph_builder`` so that file
does not grow past 200 lines.

Why a stack and not a single variable: a table nested in a cell is a valid and common structure (forms and
invoices in Word). A single variable (``hang_cua_bang`` / ``o_cua_hang`` shared by EVERY table level) makes a
nested table, the moment it opens, OVERWRITE the state of the OUTER table still in progress - measured in
the original: a row of the outer table vanished entirely, the text in the cell before the nested table was
lost too, and the nested table came out as a "paragraph" in the WRONG place instead of inside its own cell.
A stack gives EACH table level its own state, nested correctly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(slots=True)
class _BangFrame:
    hang_cua_bang: list[str] = field(default_factory=lambda: [])
    o_cua_hang: list[str] = field(default_factory=lambda: [])
    bo_dem_o: str = ""


class DocxTableTracker:
    def __init__(self) -> None:
        self._bang_stack: list[_BangFrame] = []  # top = the INNERMOST table currently open
        self._do_sau_o = 0  # depth of open <w:tc>, counted over EVERY table level

    def mo_bang(self) -> None:
        """``<w:tbl>`` opens - push a new table state on the top of the stack."""
        self._bang_stack.append(_BangFrame())

    def dong_bang(self, them_doan: Callable[[str], None]) -> None:
        """``<w:tbl>`` closes - pop the state, pour the result into the CELL of the OUTER table (if any,
        i.e. a nested table) or emit it as an independent "paragraph" (root table)."""
        xong = self._bang_stack.pop() if self._bang_stack else None
        if xong is None or not xong.hang_cua_bang:
            return
        ngoai = self._bang_stack[-1] if self._bang_stack else None
        if ngoai is not None:
            # NESTED table: join rows with "; " (NOT "\n") to embed in the cell of the outer table while
            # STILL staying on one line. "1 row = 1 line" is the invariant of this whole builder and of
            # ``xlsx_sax_sheet_builder`` - ``cat_thanh_doan`` (chunk_text) cuts paragraphs by LINE, joining
            # with "\n" here would make the OUTER row (holding the nested table) span several lines and be
            # split in half between 2 chunks.
            ngoai.bo_dem_o += (" " if ngoai.bo_dem_o else "") + "; ".join(xong.hang_cua_bang)
        else:
            them_doan("\n".join(xong.hang_cua_bang))  # ROOT table: keep "1 row = 1 line"

    def mo_hang(self) -> None:
        """``<w:tr>`` opens - reset the cell list of the current row (INNERMOST table)."""
        dinh = self._bang_stack[-1] if self._bang_stack else None
        if dinh is not None:
            dinh.o_cua_hang = []

    def dong_hang(self) -> None:
        """``<w:tr>`` closes - close the row if any cell is non-empty."""
        dinh = self._bang_stack[-1] if self._bang_stack else None
        if dinh is not None and any(o.strip() for o in dinh.o_cua_hang):
            dinh.hang_cua_bang.append(" | ".join(dinh.o_cua_hang))

    def mo_o(self) -> None:
        """``<w:tc>`` opens - reset the text buffer of the open cell (INNERMOST table)."""
        self._do_sau_o += 1
        dinh = self._bang_stack[-1] if self._bang_stack else None
        if dinh is not None:
            dinh.bo_dem_o = ""

    def dong_o(self) -> None:
        """``<w:tc>`` closes - put the cell into the cell list of the current row."""
        self._do_sau_o -= 1
        dinh = self._bang_stack[-1] if self._bang_stack else None
        if dinh is not None:
            dinh.o_cua_hang.append(dinh.bo_dem_o.strip())

    def dang_trong_o(self) -> bool:
        """Inside SOME cell (at any table level) or not."""
        return self._do_sau_o > 0

    def them_vao_o_dang_mo(self, van_ban: str) -> None:
        """Pour more text (a paragraph that just ended) into the OPEN cell of the INNERMOST table - called
        when ``dang_trong_o()`` is true."""
        if not van_ban:
            return
        dinh = self._bang_stack[-1] if self._bang_stack else None
        if dinh is not None:
            dinh.bo_dem_o += (" " if dinh.bo_dem_o else "") + van_ban


def tao_docx_table_tracker() -> DocxTableTracker:
    return DocxTableTracker()

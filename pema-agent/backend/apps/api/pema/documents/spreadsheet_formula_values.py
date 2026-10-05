# ported from: src/documents/spreadsheet-formula-values.ts
"""Pre-compute the RESULT of every formula cell.

Why it must be computed here: an .xlsx stores the formula in ``<f>`` and the computed result in ``<v>``. Excel
recomputes on open so it does not need ``<v>``, but EVERY preview tool (Zalo, Google Drive, Outlook)
reads only ``<v>`` - without it the cell shows empty. Anthropic's skill solves it by running a
LibreOffice recalc; the bot can compute it itself because it generated the data and needs no extra
software.

No forced deviation (the module is pure computation).
"""

from __future__ import annotations

from pema.documents.document_content_schema import (
    MultiplyFormulaCell,
    NumberCell,
    Sheet,
    SpreadsheetCellOutput,
    SumFormulaCell,
    TextCell,
)


def column_letter_to_index(letter: str) -> int:
    """ "A" -> 0, "B" -> 1, "AA" -> 26."""
    index = 0
    for ch in letter.upper():
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def column_index_to_letter(index: int) -> str:
    """0 -> "A", 25 -> "Z", 26 -> "AA"."""
    n = index + 1
    out = ""
    while n > 0:
        rem = (n - 1) % 26
        out = chr(65 + rem) + out
        n = (n - rem) // 26
    return out


def formula_text(cell: SpreadsheetCellOutput) -> str | None:
    """Excel formula string (WITHOUT the "=" sign - the writer adds it)."""
    if isinstance(cell, MultiplyFormulaCell):
        # The real row in Excel is filled in when the table is built, here only the columns are kept
        return f"{cell.columns[0]}{{row}}*{cell.columns[1]}{{row}}"
    if isinstance(cell, SumFormulaCell):
        return f"SUM({cell.column}{cell.from_row}:{cell.column}{cell.to_row})"
    return None


def _at(values: list[float | None], index: int) -> float | None:
    return values[index] if 0 <= index < len(values) else None


def compute_sheet_values(sheet: Sheet) -> list[list[float | None]]:
    """Matrix of numeric values of the sheet, indexed ``[data row][column]``.
    A text cell or a cell that could not be computed is ``None``.

    Computed top to bottom so a SUM cell on the last row can add the multiply cells above it (the most common
    case: a "total price" column and then a total row)."""
    values: list[list[float | None]] = []

    for row_index, row in enumerate(sheet.rows):
        computed: list[float | None] = []
        for cell in row:
            computed.append(_evaluate_cell(cell, row_index, values, computed))
        values.append(computed)

    return values


def _evaluate_cell(
    cell: SpreadsheetCellOutput,
    row_index: int,
    done_rows: list[list[float | None]],
    current_row: list[float | None],
) -> float | None:
    if isinstance(cell, NumberCell):
        return cell.value
    if isinstance(cell, TextCell):
        return None

    if isinstance(cell, MultiplyFormulaCell):
        a = _at(current_row, column_letter_to_index(cell.columns[0]))
        b = _at(current_row, column_letter_to_index(cell.columns[1]))
        return a * b if a is not None and b is not None else None

    # SUM: from_row/to_row are row numbers as shown in Excel (row 1 is the header), so data row i sits on
    # Excel row i + 2
    col_index = column_letter_to_index(cell.column)
    total = 0.0
    counted = 0
    for excel_row in range(cell.from_row, cell.to_row + 1):
        data_index = excel_row - 2
        if data_index < 0:
            continue
        # Only add rows already computed (above); a row below has no value yet
        if data_index == row_index:
            value = _at(current_row, col_index)
        else:
            value = _at(done_rows[data_index], col_index) if data_index < len(done_rows) else None
        if value is not None:
            total += value
            counted += 1
    return total if counted > 0 else None

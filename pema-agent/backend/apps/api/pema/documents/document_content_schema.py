# ported from: src/documents/document-content-schema.ts
"""Document content schema: the contract between the MODEL and the renderer.

Deliberately NOT the API of ``python-docx`` / ``openpyxl``: the model only has to understand a few familiar
concepts (heading, paragraph, bullets, table), not DXA, WidthType or numFmt. Swapping the library later only
changes the renderer; this schema and the way the model calls the tool stay the same.

The tools take DATA only, never code (prompt-injection rule): everything that arrives from the model goes
through this module first.

Forced deviations:
* zod -> pydantic v2. ``z.infer`` / ``z.output`` -> the model classes below (the OUTPUT of the cell schema is
  the four ``*Cell`` models, after the string / number shorthands were normalised).
* ``safeParse`` -> ``parse_document_blocks`` / ``parse_sheets`` returning ``ParseOk`` or ``ParseFail`` with a
  Vietnamese reason, so the tool can hand the sentence to the model unchanged (same rule as the limits).
* ``z.discriminatedUnion`` over ``kind`` cannot be used for the cell (see ``SpreadsheetCell``); pydantic's
  callable ``Discriminator`` routes by (``kind``, ``op``) instead, and ``z.transform`` became a
  ``BeforeValidator`` that rewrites the shorthands into the object form.
* Wire names stay camelCase (``fromRow`` / ``toRow``, what the model sends); the Python attributes are
  snake_case (``from_row`` / ``to_row``).
* ``document_blocks_json_schema`` / ``sheets_json_schema`` replace the zod -> JSON-Schema conversion done by
  the Vercel AI SDK: the tool layer uses them to build the tool parameter schema.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Final, Literal, cast

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Discriminator,
    Field,
    StringConstraints,
    Tag,
    TypeAdapter,
    ValidationError,
)

from pema.documents.xlsx_themes import XlsxThemeName

# ===== Text documents (.docx) =====

_STRICT = ConfigDict(strict=True, populate_by_name=True)
"""Strict: a JSON ``1.5`` is not an int and ``123`` is not a string, as in zod (no silent coercion)."""


class HeadingBlock(BaseModel):
    model_config = _STRICT

    type: Literal["heading"]
    text: Annotated[str, Field(min_length=1)]
    level: Annotated[int, Field(ge=1, le=3)] = 2
    """Heading level 1-3. DELIBERATELY a number range and NOT a union of literals, although the union says it
    better: this schema flies straight to the LLM provider, and a union of numeric literals becomes
    ``enum: [1]`` while Google's ``Schema.enum`` is ``repeated string`` and only takes strings. It rejects the
    whole request with a 400 ("(TYPE_STRING), 1"), and because the tool set rides every turn the bot goes
    completely mute (hit for real on 2026-08-06, same family as the ``z.tuple()`` of the Excel formula cell).
    A range becomes ``{"type":"integer","minimum":1,"maximum":3}``: no ``enum`` so no clash, and it
    still blocks 0, 4 and fractions exactly like the union."""


class ParagraphBlock(BaseModel):
    model_config = _STRICT

    type: Literal["paragraph"]
    text: Annotated[str, Field(min_length=1, description="Bôi đậm giữa dòng bằng **chữ đậm**")]
    align: Annotated[
        Literal["left", "center", "right", "justify"] | None,
        Field(
            description="center/right cho dòng lạc khoản (địa danh, ngày tháng); bỏ trống = justify",
        ),
    ] = None


class BulletsBlock(BaseModel):
    model_config = _STRICT

    type: Literal["bullets"]
    items: Annotated[list[Annotated[str, Field(min_length=1)]], Field(min_length=1)]


class TableBlock(BaseModel):
    model_config = _STRICT

    type: Literal["table"]
    headers: Annotated[list[str], Field(min_length=1, max_length=8)]
    rows: Annotated[list[list[str]], Field(min_length=1)]


class TwoColumnsBlock(BaseModel):
    """Two columns side by side, no border: the layout Vietnamese documents use most, the head of an
    administrative document (agency name on the left, national motto on the right) and the signature block
    at the end (recipients on the left, position + signer on the right). Without this block the model has to
    fake it with spaces and the layout breaks as soon as the file is opened."""

    model_config = _STRICT

    type: Literal["two_columns"]
    left: Annotated[list[str], Field(min_length=1, description="Các dòng cột trái, canh giữa trong cột")]
    right: Annotated[list[str], Field(min_length=1, description="Các dòng cột phải, canh giữa trong cột")]


DocumentBlock = Annotated[
    HeadingBlock | ParagraphBlock | BulletsBlock | TableBlock | TwoColumnsBlock,
    Field(discriminator="type"),
]
"""``documentBlockSchema``: discriminated by ``type``."""

# ===== Spreadsheets (.xlsx) =====

# A formula cell only accepts BUILT-IN OPERATIONS, never a free formula.
#
# Reason: the file must carry the computed value (``<v>``) so that preview tools show a number instead of an
# empty cell. The bot can only compute the result when it knows exactly which operation it is doing - letting
# the model type "=SUMIFS(...)" cannot be computed.

ColumnLetter = Annotated[
    str,
    StringConstraints(pattern=r"^[A-Za-z]{1,2}$"),
    AfterValidator(lambda s: s.upper()),
]


class TextCell(BaseModel):
    model_config = _STRICT

    kind: Literal["text"]
    value: str


class NumberCell(BaseModel):
    model_config = _STRICT

    kind: Literal["number"]
    value: Annotated[float, Field(allow_inf_nan=False)]
    format: Literal["plain", "money", "percent"] = "plain"
    """money = #,##0 (the unit is written in the header) - percent = 0.0% (stored as a fraction)."""


class MultiplyFormulaCell(BaseModel):
    model_config = _STRICT

    kind: Literal["formula"]
    op: Literal["multiply"]
    columns: Annotated[list[ColumnLetter], Field(min_length=2, max_length=2)]
    """Letters of the 2 same-row columns to multiply, e.g. ["B", "C"].

    DELIBERATELY ``list`` with length 2 and NOT a tuple, although the tuple says it better: this schema flies
    straight to the LLM provider, and a tuple becomes draft-07 JSON Schema with ``items`` as an ARRAY
    (``prefixItems`` in 2020-12). Google's OpenAI-compatible layer only takes 2020-12 where ``items``
    must be an object or boolean, so it rejects the WHOLE REQUEST with a 400 - and because the tool set
    rides every turn the bot goes mute, not only on the turn that asked for Excel (hit for real on
    2026-08-06). The runtime constraint is identical to the tuple: exactly 2 elements, each one a column
    letter."""


class SumFormulaCell(BaseModel):
    model_config = _STRICT

    kind: Literal["formula"]
    op: Literal["sum"]
    column: ColumnLetter
    """Column to add up, e.g. "D"."""
    from_row: Annotated[int, Field(ge=1, alias="fromRow")]
    to_row: Annotated[int, Field(ge=1, alias="toRow")]
    """Add from which row to which row (row numbers as Excel shows them, header counted)."""


type FormulaCell = MultiplyFormulaCell | SumFormulaCell

MULTIPLY_RE: Final = re.compile(r"^=\s*([A-Za-z]{1,2})\d+\s*\*\s*([A-Za-z]{1,2})\d+\s*$", re.ASCII)
SUM_RE: Final = re.compile(
    r"^=\s*SUM\(\s*([A-Za-z]{1,2})(\d+)\s*:\s*([A-Za-z]{1,2})(\d+)\s*\)\s*$", re.ASCII | re.IGNORECASE
)

FORMULA_UNSUPPORTED_MESSAGE: Final = (
    'Chỉ hỗ trợ công thức "=B2*C2" (nhân 2 ô cùng dòng) hoặc "=SUM(D2:D9)" (cộng 1 cột). '
    "Công thức khác hãy tự tính rồi gửi số."
)


def _formula_string_to_object(raw: str) -> dict[str, Any]:
    """``formulaString``: a formula written as the string "=B2*C2" / "=SUM(D2:D9)" - the way the model writes
    it most NATURALLY (DeepSeek did exactly that in testing), so it must be accepted instead of forcing the
    model to learn a dedicated object structure. An "=" string that is neither of these forms is rejected with
    guidance so that the model switches to a pre-computed number."""
    mul = MULTIPLY_RE.match(raw)
    if mul:
        return {
            "kind": "formula",
            "op": "multiply",
            "columns": [mul.group(1).upper(), mul.group(2).upper()],
        }
    total = SUM_RE.match(raw)
    if total and total.group(1).upper() == total.group(3).upper():
        return {
            "kind": "formula",
            "op": "sum",
            "column": total.group(1).upper(),
            "fromRow": int(total.group(2)),
            "toRow": int(total.group(4)),
        }
    raise ValueError(FORMULA_UNSUPPORTED_MESSAGE)


def _normalise_cell(raw: object) -> object:
    """The shorthands a cell accepts besides the object form: plain strings and plain numbers are the way the
    model sends them most naturally (like the table of a Word document); the object is the full form when a
    format is needed."""
    if isinstance(raw, str):
        # An "=" string must land in the formula branch: letting it fall through as text is a wrong formula
        # silently turned into words, and the user never finds out
        if raw.startswith("="):
            return _formula_string_to_object(raw)
        return {"kind": "text", "value": raw}
    if isinstance(raw, int | float) and not isinstance(raw, bool):
        return {"kind": "number", "value": raw, "format": "plain"}
    return raw


def _cell_tag(raw: object) -> str | None:
    """Route an object cell to its model by (kind, op). ``z.discriminatedUnion("kind")`` threw "Duplicate
    discriminator value" on EVERY parse because both formula schemas share kind="formula" - it killed
    ``create_excel_file`` 100% on real Zalo while every test stayed green (the tests called ``execute``
    directly, never the validation layer). A callable discriminator has no such trap: an unknown cell gives a
    normal validation error, never an exception."""
    if isinstance(raw, Mapping):
        mapping = cast("Mapping[str, object]", raw)
        kind: object = mapping.get("kind")
        op: object = mapping.get("op")
    else:
        kind = getattr(raw, "kind", None)
        op = getattr(raw, "op", None)
    if kind == "text":
        return "text"
    if kind == "number":
        return "number"
    if kind == "formula" and op == "multiply":
        return "formula_multiply"
    if kind == "formula" and op == "sum":
        return "formula_sum"
    return None


type SpreadsheetCellInput = str | float | TextCell | NumberCell | MultiplyFormulaCell | SumFormulaCell
"""What the model may send for one cell (the JSON-Schema INPUT type)."""

type SpreadsheetCellOutput = TextCell | NumberCell | MultiplyFormulaCell | SumFormulaCell
"""What a validated cell is (``z.output<typeof spreadsheetCellSchema>``); the renderers work on this."""

SpreadsheetCell = Annotated[
    Annotated[TextCell, Tag("text")]
    | Annotated[NumberCell, Tag("number")]
    | Annotated[MultiplyFormulaCell, Tag("formula_multiply")]
    | Annotated[SumFormulaCell, Tag("formula_sum")],
    Discriminator(_cell_tag),
    BeforeValidator(_normalise_cell, json_schema_input_type=SpreadsheetCellInput),
]
"""``spreadsheetCellSchema``: one cell takes MANY forms - a plain string / number is the most natural
way for a model to send it (like the table of a Word document), the object is the full form when a
format is needed. The OUTPUT is always one of the four models: text, number, multiply formula, sum formula."""


class Sheet(BaseModel):
    """``sheetSchema``."""

    model_config = _STRICT

    name: Annotated[
        str,
        Field(
            min_length=1,
            description='Tên sheet GIỮ NGUYÊN dấu tiếng Việt, vd "Tổng quan" (không viết "Tong quan")',
        ),
    ]
    theme: Annotated[
        XlsxThemeName | None,
        Field(
            description=(
                "Tông màu hợp nội dung: navy (trang trọng, mặc định) · blue (tài chính, báo giá) · "
                "green (tăng trưởng, nông nghiệp, môi trường) · burgundy (rủi ro, pháp lý, sự cố) · "
                "slate (kỹ thuật, vận hành) · teal (y tế, giáo dục, dịch vụ)"
            ),
        ),
    ] = None
    """Colour theme - the model picks by document context, never a free hex."""
    title: Annotated[str | None, Field(description='Tiêu đề lớn đầu sheet, vd "BÁO CÁO TỔNG HỢP..."')] = None
    """Prominent title banner at the top of the sheet - recommended for reports."""
    subtitle: Annotated[
        str | None, Field(description="Dòng phụ đề nhỏ dưới tiêu đề (phạm vi, khoảng thời gian)")
    ] = None
    headers: Annotated[list[str], Field(min_length=1, max_length=20)]
    rows: Annotated[list[list[SpreadsheetCell]], Field(min_length=1)]
    note: Annotated[str | None, Field(description="Ghi chú/lưu ý quan trọng hiện cuối bảng")] = None
    """Red italic note at the end of the table - for important caveats, data sources."""


# ===== Public parse API (what the tool layer calls) =====

document_block_schema: Final[TypeAdapter[DocumentBlock]] = TypeAdapter(DocumentBlock)
spreadsheet_cell_schema: Final[TypeAdapter[SpreadsheetCell]] = TypeAdapter(SpreadsheetCell)
sheet_schema: Final[TypeAdapter[Sheet]] = TypeAdapter(Sheet)

_blocks_adapter: Final[TypeAdapter[list[DocumentBlock]]] = TypeAdapter(
    Annotated[list[DocumentBlock], Field(min_length=1)]
)
_sheets_adapter: Final[TypeAdapter[list[Sheet]]] = TypeAdapter(Annotated[list[Sheet], Field(min_length=1)])


@dataclass(frozen=True)
class ParseOk[T]:
    value: T
    ok: Literal[True] = True


@dataclass(frozen=True)
class ParseFail:
    reason: str
    """Vietnamese sentence the tool hands to the model so it can fix its call."""
    ok: Literal[False] = False


_MAX_REPORTED_ERRORS = 5

_TYPE_MESSAGES_VI: Final[dict[str, str]] = {
    "missing": "thiếu trường bắt buộc",
    "string_too_short": "không được để trống",
    "too_short": "thiếu phần tử (không đủ số lượng tối thiểu)",
    "too_long": "quá nhiều phần tử (vượt số lượng tối đa)",
    "string_type": "phải là chuỗi",
    "int_type": "phải là số nguyên",
    "float_type": "phải là số",
    "list_type": "phải là danh sách",
    "literal_error": "giá trị không nằm trong các lựa chọn cho phép",
    "greater_than_equal": "nhỏ hơn mức tối thiểu cho phép",
    "less_than_equal": "lớn hơn mức tối đa cho phép",
    "string_pattern_mismatch": "sai định dạng (cột phải là 1-2 chữ cái, vd B hoặc AA)",
    "union_tag_not_found": "thiếu hoặc sai trường phân loại (type/kind/op)",
    "union_tag_invalid": "loại (type) không hợp lệ",
    "model_type": "phải là một đối tượng",
}


def _location(loc: tuple[int | str, ...], root: str) -> str:
    out = root
    for part in loc:
        out += f"[{part}]" if isinstance(part, int) else f".{part}"
    return out


def format_validation_error(error: ValidationError, root: str) -> str:
    """Vietnamese, model-readable summary of a validation error (at most 5 problems, never PII: only the
    path and the rule, never the offending value)."""
    problems: list[str] = []
    errors = error.errors(include_url=False, include_context=False, include_input=False)
    for item in errors[:_MAX_REPORTED_ERRORS]:
        where = _location(item["loc"], root)
        if item["type"] == "value_error":
            # The message is OUR Vietnamese sentence (the formula guidance); drop pydantic's prefix
            problems.append(f"{where}: {item['msg'].removeprefix('Value error, ')}")
            continue
        problems.append(f"{where}: {_TYPE_MESSAGES_VI.get(item['type'], item['msg'])}")
    more = len(errors) - _MAX_REPORTED_ERRORS
    suffix = f" (còn {more} lỗi nữa)" if more > 0 else ""
    body = "; ".join(problems).rstrip(".")
    return f"Nội dung không hợp lệ - {body}{suffix}. Hãy sửa rồi gọi lại."


def parse_document_blocks(raw: object) -> ParseOk[list[DocumentBlock]] | ParseFail:
    """Validate UNTRUSTED ``blocks`` (a list of dicts from the model) for the Word tool: at least 1 block."""
    try:
        return ParseOk(_blocks_adapter.validate_python(raw))
    except ValidationError as error:
        return ParseFail(format_validation_error(error, "blocks"))


def parse_sheets(raw: object) -> ParseOk[list[Sheet]] | ParseFail:
    """Validate UNTRUSTED ``sheets`` (a list of dicts from the model) for the Excel tool: at least 1 sheet."""
    try:
        return ParseOk(_sheets_adapter.validate_python(raw))
    except ValidationError as error:
        return ParseFail(format_validation_error(error, "sheets"))


# ===== JSON Schema for the tool parameters =====


def _inline_refs(node: Any, defs: Mapping[str, Any]) -> Any:
    """Make the schema what zod used to emit: self-contained and without pydantic's extras.

    * every ``$ref`` is resolved in place and ``discriminator`` is dropped (its ``mapping`` points at the
      removed ``$defs``): providers differ in how they treat ``$ref``, a self-contained schema suits all;
    * ``anyOf: [X, {"type": "null"}]`` collapses to ``X`` and ``"default": null`` goes away: zod's
      ``.optional()`` means "property may be absent", not "may be null", and a ``null`` branch is another
      construct some providers refuse;
    * the cosmetic ``title`` of each schema node is dropped (a PROPERTY called ``title`` is kept).

    The models are not recursive, so this terminates."""
    if isinstance(node, list):
        return [_inline_refs(item, defs) for item in cast("list[Any]", node)]
    if not isinstance(node, dict):
        return node
    mapping = cast("dict[str, Any]", node)
    ref = mapping.get("$ref")
    if isinstance(ref, str):
        target = defs[ref.rsplit("/", 1)[-1]]
        rest = {k: v for k, v in mapping.items() if k != "$ref"}
        return _inline_refs({**target, **rest}, defs)
    out: dict[str, Any] = {}
    for key, value in mapping.items():
        if key in ("$defs", "discriminator"):
            continue
        if key == "title" and isinstance(value, str):
            continue
        if key == "default" and value is None:
            continue
        if key == "properties" and isinstance(value, dict):
            props = cast("dict[str, Any]", value)
            out[key] = {name: _inline_refs(schema, defs) for name, schema in props.items()}
            continue
        out[key] = _inline_refs(value, defs)
    any_of = out.get("anyOf")
    if isinstance(any_of, list):
        branches = [b for b in cast("list[Any]", any_of) if b != {"type": "null"}]
        if len(branches) == 1 and len(branches) != len(cast("list[Any]", any_of)):
            merged = {k: v for k, v in out.items() if k != "anyOf"}
            return {**cast("dict[str, Any]", branches[0]), **merged}
    return out


def _self_contained_schema(adapter: TypeAdapter[Any]) -> dict[str, Any]:
    schema = adapter.json_schema(mode="validation")
    defs = cast("Mapping[str, Any]", schema.get("$defs", {}))
    return _inline_refs(schema, defs)


def document_blocks_json_schema() -> dict[str, Any]:
    """JSON Schema (2020-12, no ``$ref``, no numeric ``enum``, no tuple ``items``) of the Word tool's
    ``blocks`` parameter: an array of at least 1 block."""
    return _self_contained_schema(_blocks_adapter)


def sheets_json_schema() -> dict[str, Any]:
    """JSON Schema of the Excel tool's ``sheets`` parameter: an array of at least 1 sheet."""
    return _self_contained_schema(_sheets_adapter)

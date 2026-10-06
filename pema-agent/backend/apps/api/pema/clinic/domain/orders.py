# ported from: prototype/shared/order-data.js (validateItems, orderPrintData, routeForProduct),
# prototype/shared/product-catalog-runtime.js (normalize, find) and prototype/import-product-catalog.py
# (read_catalog: code upper-cased, integer price >= 0, outputType)
"""Order rules that need no database: line validation for an approval, the split of the lines into sheets,
the accent-insensitive catalog search and the canonical form (and hash) of a catalog import.

Forced deviations from the JavaScript:

* the prototype validated with ``Number.isSafeInteger``; the contract bounds (``quantity`` 1 to 9999, price an
  ``int`` >= 0) are enforced by pydantic and the database, so ``validate_lines_for_approval`` keeps only the
  checks the contract cannot express (route, usage, an order that prints nothing);
* ``vat`` and ``price_before_tax`` are rounded to 4 decimals (the width of the database columns), so a second
  import of the same file compares equal;
* messages are the prototype's Vietnamese sentences, raised as ``DomainError(VALIDATION_FAILED)``.

This module is pure: it imports no database code.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.orders import OrderRoute

PRESCRIPTION = OrderRoute.PRESCRIPTION.value
CONSULTATION = OrderRoute.CONSULTATION.value
NONE = OrderRoute.NONE.value
UNRESOLVED = OrderRoute.UNRESOLVED.value
ROUTES = frozenset({PRESCRIPTION, CONSULTATION, NONE, UNRESOLVED})

NO_DIAGNOSIS_MESSAGE = "Cần nội dung tư vấn / chẩn đoán trước khi duyệt."
NOTHING_TO_ISSUE_MESSAGE = "Đơn không có sản phẩm để phát hành."
DRAFT_NOT_APPROVED_MESSAGE = "Đơn nháp cần bác sĩ duyệt trước khi in."


class LineLike(Protocol):
    @property
    def route(self) -> str: ...
    @property
    def usage(self) -> str: ...


def validation_error(message: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, message)


def validate_lines_for_approval(lines: Sequence[LineLike]) -> None:
    """``validateItems(items, final = true)``: every line classified, every printed line with its usage, and
    at least one line that is printed. Raises on the first problem, like the prototype."""
    if not lines:
        raise validation_error("Chọn ít nhất một sản phẩm.")
    for index, line in enumerate(lines, start=1):
        if line.route not in ROUTES:
            raise validation_error(f"Dòng {index}: phân loại không hợp lệ.")
        if line.route == UNRESOLVED:
            raise validation_error(f"Dòng {index}: cần phân loại trước khi duyệt hoặc in.")
        if line.route != NONE and not line.usage.strip():
            raise validation_error(f"Dòng {index}: cần cách dùng trước khi duyệt.")
    if all(line.route == NONE for line in lines):
        raise validation_error(NOTHING_TO_ISSUE_MESSAGE)


def lines_are_complete(lines: Sequence[LineLike]) -> bool:
    """True when ``validate_lines_for_approval`` would pass."""
    try:
        validate_lines_for_approval(lines)
    except DomainError:
        return False
    return True


@dataclass(frozen=True)
class SheetSplit[T: LineLike]:
    prescription: list[T]
    consultation: list[T]
    excluded: list[T]
    unresolved: list[T]


def split_by_route[T: LineLike](lines: Iterable[T]) -> SheetSplit[T]:
    """``orderPrintData``: Đơn thuốc, Phiếu tư vấn, "Không in" and "Cần phân loại"."""
    items = list(lines)
    return SheetSplit(
        prescription=[x for x in items if x.route == PRESCRIPTION],
        consultation=[x for x in items if x.route == CONSULTATION],
        excluded=[x for x in items if x.route == NONE],
        unresolved=[x for x in items if x.route not in ROUTES or x.route == UNRESOLVED],
    )


# ---------------------------------------------------------------------------------------------- search
_SPACES = re.compile(r"\s+")


def normalize(value: object) -> str:
    """``normalize`` of the catalog runtime: no accents, ``đ`` as ``d``, lower case, single spaces."""
    text = str(value if value is not None else "")
    folded = unicodedata.normalize("NFD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.replace("đ", "d").replace("Đ", "D").lower()
    return _SPACES.sub(" ", folded).strip()


class Searchable(Protocol):
    @property
    def code(self) -> str: ...
    @property
    def name(self) -> str: ...
    @property
    def source_type(self) -> str: ...


def find_products[T: Searchable](records: Iterable[T], query: str) -> list[T]:
    """``find``: a record matches when its code, name or type contains the query; an exact code comes first
    (stable for the rest, in the order of the catalog)."""
    q = normalize(query)
    hits = [r for r in records if not q or any(q in normalize(v) for v in (r.code, r.name, r.source_type))]
    return sorted(hits, key=lambda r: 0 if q and normalize(r.code) == q else 1)


# ----------------------------------------------------------------------------------------------- import
@dataclass(frozen=True)
class CatalogRow:
    code: str
    name: str
    unit: str
    source_type: str
    route: str
    price_vnd: int
    vat: float
    price_before_tax: float
    row_number: int
    batch: str
    serial: str


def _import_error(message: str) -> DomainError:
    return DomainError(ErrorCode.VALIDATION_FAILED, message)


def parse_catalog_rows(raw: object) -> list[CatalogRow]:
    """Validate the rows of ``product-catalog.json`` the way ``import-product-catalog.py`` did when it wrote
    them: non-empty list, a code and a name on every row, no duplicate code, an integer price >= 0 and an
    ``outputType`` the order rules know. The code is the key (upper-cased, as the importer stored it)."""
    if not isinstance(raw, list) or not raw:
        raise _import_error("Catalog trống.")
    entries = cast("list[object]", raw)
    rows: list[CatalogRow] = []
    seen: set[str] = set()
    for position, entry in enumerate(entries, start=1):
        if not isinstance(entry, Mapping):
            raise _import_error(f"Dòng {position}: không phải một đối tượng.")
        item = cast("Mapping[str, Any]", entry)
        code = str(item.get("code", "")).strip().upper()
        name = str(item.get("name", "")).strip()
        if not code or not name or code in seen:
            raise _import_error(f"Dòng {position}: thiếu dữ liệu hoặc trùng mã {code}.")
        price = item.get("price")
        if (
            isinstance(price, bool)
            or not isinstance(price, int | float)
            or float(price) != int(price)
            or price < 0
        ):
            raise _import_error(f"Giá không hợp lệ: {code}.")
        route = str(item.get("outputType", ""))
        if route not in {PRESCRIPTION, CONSULTATION, UNRESOLVED}:
            raise _import_error(f"Phân loại không hợp lệ: {code}.")
        seen.add(code)
        rows.append(
            CatalogRow(
                code=code,
                name=name,
                unit=str(item.get("unit", "")),
                source_type=str(item.get("sourceType", "")),
                route=route,
                price_vnd=int(price),
                vat=round(float(item.get("vat") or 0), 4),
                price_before_tax=round(float(item.get("priceBeforeTax") or 0), 4),
                row_number=int(item.get("rowNumber") or 0),
                batch=str(item.get("batch", "")),
                serial=str(item.get("serial", "")),
            )
        )
    return rows


def catalog_hash(rows: Iterable[CatalogRow]) -> str:
    """SHA-256 of the canonical rows: independent of line endings, key order and whitespace of the file, so
    the same catalog gives the same hash on every machine."""
    payload = [
        {
            "code": r.code,
            "name": r.name,
            "unit": r.unit,
            "source_type": r.source_type,
            "route": r.route,
            "price_vnd": r.price_vnd,
            "vat": r.vat,
            "price_before_tax": r.price_before_tax,
            "row_number": r.row_number,
            "batch": r.batch,
            "serial": r.serial,
        }
        for r in rows
    ]
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

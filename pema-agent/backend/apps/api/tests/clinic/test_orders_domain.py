# new tests (package U, step U5; translated from prototype/order-test.cjs and product-catalog-test.cjs)
"""Order rules without a database: approval validation, the split into sheets, accent-insensitive search and
the canonical hash of the real catalog (``prototype/shared/product-catalog.json``, the clinic's own price list:
real data, not synthetic)."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pytest

from pema.clinic.domain.orders import (
    CatalogRow,
    catalog_hash,
    find_products,
    lines_are_complete,
    normalize,
    parse_catalog_rows,
    split_by_route,
    validate_lines_for_approval,
)
from pema_contracts.errors import DomainError, ErrorCode

CATALOG_JSON = Path(__file__).resolve().parents[6] / "prototype" / "shared" / "product-catalog.json"
REAL_CATALOG_SHA256 = "b26a734c46cede169862b771e8110b5420c97d8cdad850be0b892f7e7d00df7b"


@dataclass(frozen=True)
class Line:
    route: str
    usage: str = "Bôi mỏng sáng tối"


@dataclass(frozen=True)
class Rec:
    code: str
    name: str
    source_type: str = ""


def _fails(lines: list[Line]) -> str:
    with pytest.raises(DomainError) as caught:
        validate_lines_for_approval(lines)
    assert caught.value.code is ErrorCode.VALIDATION_FAILED
    return caught.value.message


def test_approval_needs_a_line_a_class_and_a_usage_on_every_printed_line() -> None:
    assert _fails([]) == "Chọn ít nhất một sản phẩm."
    assert (
        _fails([Line("PRESCRIPTION"), Line("UNRESOLVED")]) == "Dòng 2: cần phân loại trước khi duyệt hoặc in."
    )
    assert (
        _fails([Line("PRESCRIPTION"), Line("CONSULTATION", usage="  ")])
        == "Dòng 2: cần cách dùng trước khi duyệt."
    )
    assert _fails([Line("bad")]) == "Dòng 1: phân loại không hợp lệ."
    assert _fails([Line("NONE", usage=""), Line("NONE")]) == "Đơn không có sản phẩm để phát hành."


def test_a_line_that_is_not_printed_needs_no_usage_but_another_line_must_be_printed() -> None:
    lines = [Line("NONE", usage=""), Line("PRESCRIPTION")]
    validate_lines_for_approval(lines)
    assert lines_are_complete(lines)
    assert not lines_are_complete([Line("UNRESOLVED")])


def test_the_sheets_split_by_route_and_unresolved_lines_are_listed_apart() -> None:
    lines = [
        Line("PRESCRIPTION"),
        Line("CONSULTATION"),
        Line("NONE"),
        Line("UNRESOLVED"),
        Line("CONSULTATION"),
    ]
    split = split_by_route(lines)
    assert [len(split.prescription), len(split.consultation), len(split.excluded), len(split.unresolved)] == [
        1,
        2,
        1,
        1,
    ]


def test_search_ignores_accents_case_and_the_letter_d_with_stroke() -> None:
    assert normalize("  Đơn   THUỐC ") == "don thuoc"
    records = [
        Rec("H002", "Desloratadine 5 mg", "Thuốc"),
        Rec("H005", "Cicaderm Cream 40ml", "Mỹ Phẩm"),
        Rec("H0020", "Kem dưỡng", "TPCN"),
    ]
    assert [r.code for r in find_products(records, "thuoc")] == ["H002"]
    assert [r.code for r in find_products(records, "MY PHAM")] == ["H005"]
    assert [r.code for r in find_products(records, "dưỡng")] == ["H0020"]
    # an exact code comes first, whatever the catalog order
    assert [r.code for r in find_products(records, "h002")] == ["H002", "H0020"]
    assert len(find_products(records, "")) == 3


def _rows(*overrides: dict[str, object]) -> list[dict[str, object]]:
    base: dict[str, object] = {
        "code": "h1",
        "name": "Mẫu",
        "unit": "Hộp",
        "sourceType": "Thuốc",
        "price": 1000,
        "outputType": "PRESCRIPTION",
    }
    return [{**base, **o} for o in overrides]


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ([], "Catalog trống."),
        ("x", "Catalog trống."),
        (_rows({"code": ""}), "Dòng 1: thiếu dữ liệu hoặc trùng mã ."),
        (_rows({}, {}), "Dòng 2: thiếu dữ liệu hoặc trùng mã H1."),
        (_rows({"price": 1.5}), "Giá không hợp lệ: H1."),
        (_rows({"price": -1}), "Giá không hợp lệ: H1."),
        (_rows({"outputType": "NONE"}), "Phân loại không hợp lệ: H1."),
    ],
)
def test_the_importer_refuses_what_the_excel_importer_refused(raw: object, message: str) -> None:
    with pytest.raises(DomainError) as caught:
        parse_catalog_rows(raw)
    assert caught.value.message == message


def test_the_hash_does_not_depend_on_key_order_or_float_noise() -> None:
    first = parse_catalog_rows(_rows({"priceBeforeTax": 5238.095238095238}))
    second = parse_catalog_rows(
        [dict(reversed(list(r.items()))) for r in _rows({"priceBeforeTax": 5238.0952381})]
    )
    assert catalog_hash(first) == catalog_hash(second)
    changed = parse_catalog_rows(_rows({"price": 1001}))
    assert catalog_hash(first) != catalog_hash(changed)


@pytest.mark.skipif(not CATALOG_JSON.exists(), reason="prototype catalog not in this checkout")
def test_the_real_catalog_has_115_rows_with_the_known_type_counts_and_hash() -> None:
    rows: list[CatalogRow] = parse_catalog_rows(json.loads(CATALOG_JSON.read_text(encoding="utf-8")))
    assert len(rows) == 115
    assert Counter(r.source_type for r in rows) == {"Thuốc": 30, "Mỹ Phẩm": 64, "TPCN": 14, "": 7}
    assert Counter(r.route for r in rows) == {"PRESCRIPTION": 30, "CONSULTATION": 78, "UNRESOLVED": 7}
    h095 = next(r for r in rows if r.code == "H095")
    assert h095.route == "UNRESOLVED"  # seven rows without an Excel type are never classified by guess
    assert sum(1 for r in rows if r.price_vnd == 0) == 2  # a price of 0 stays 0
    assert catalog_hash(rows) == REAL_CATALOG_SHA256

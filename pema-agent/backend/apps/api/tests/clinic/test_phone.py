"""Phones said in a chat, as the agent gateway stores them. Pure: no database."""

from __future__ import annotations

import pytest

from pema.clinic.domain.phone import normalize_vn_phone


@pytest.mark.parametrize(
    ("raw", "stored"),
    [
        ("0912345678", "0912345678"),
        ("0912 345 678", "0912345678"),
        ("0912.345.678", "0912345678"),
        ("+84 912-345-678", "0912345678"),
        ("84912345678", "0912345678"),
        ("0388 123 456", "0388123456"),
        ("(028) 3822 1234", "02838221234"),
        ("+84 28 3822 1234", "02838221234"),
    ],
)
def test_a_vietnamese_number_is_kept_as_digits_from_zero(raw: str, stored: str) -> None:
    assert normalize_vn_phone(raw) == stored


@pytest.mark.parametrize(
    "raw", ["", "abc", "912345678", "00912345678", "091234567", "0112345678", "+1 415 555 0100"]
)
def test_anything_else_is_refused(raw: str) -> None:
    assert normalize_vn_phone(raw) is None

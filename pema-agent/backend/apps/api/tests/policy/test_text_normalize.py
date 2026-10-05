"""Vietnamese folding used by the red-flag detector and the PII mask (new module, no original)."""

from __future__ import annotations

import unicodedata

from pema.policy.text_normalize import fold_char, fold_text, normalize_for_flags, to_nfc


def test_fold_removes_diacritics_and_maps_d_stroke() -> None:
    """bỏ dấu tiếng Việt, đ -> d, hạ chữ thường"""
    assert fold_text("Nguyễn Thị Hoa Đặng") == "nguyen thi hoa dang"
    assert fold_text("ƯỚC MƠ") == "uoc mo"


def test_fold_keeps_the_length_of_an_nfc_string() -> None:
    """fold giữ nguyên độ dài để cắt đúng vị trí trong văn bản gốc"""
    text = to_nfc("Chảy máu ở số 12 đường Lê Lợi, phường Bến Nghé ☺ 0901")
    assert len(fold_text(text)) == len(text)


def test_fold_char_leaves_symbols_digits_and_emoji() -> None:
    """ký hiệu, chữ số, emoji không đổi"""
    assert [fold_char(c) for c in "7,😀"] == ["7", ",", "😀"]


def test_normalize_collapses_stretched_letters_and_inner_separators() -> None:
    """chữ kéo dài và dấu chấm giữa chữ bị gộp; số 0 giữa chữ thành o"""
    assert normalize_for_flags("chayyy maauu").folded == "chay mau"
    assert normalize_for_flags("ch.ảy m-áu").folded == "chay mau"
    assert normalize_for_flags("S0T cao").folded == "sot cao"
    assert normalize_for_flags("khoooo thở").folded == "kho tho"


def test_normalize_keeps_digits_and_decimal_points() -> None:
    """chữ số và dấu thập phân không bị đụng: 38.5 vẫn là 38.5"""
    assert normalize_for_flags("sốt 38.5 độ").folded == "sot 38.5 do"
    assert normalize_for_flags("sdt 0901").folded == "sdt 0901"


def test_original_span_returns_the_diacritics_the_patient_typed() -> None:
    """truy ngược về chữ gốc có dấu để phân biệt "sốt" với "sót\""""
    n = normalize_for_flags("còn sót lại và bị sốtt")
    first = n.folded.index("sot")
    assert n.original_span(first, first + 3) == "sót"
    second = n.folded.index("sot", first + 1)
    assert n.original_span(second, second + 3).startswith("sốt")


def test_normalize_accepts_decomposed_input() -> None:
    """đầu vào dạng tổ hợp (NFD) được đưa về NFC trước khi so khớp"""
    decomposed = unicodedata.normalize("NFD", "khó thở")
    assert normalize_for_flags(decomposed).folded == "kho tho"


def test_empty_text() -> None:
    """chuỗi rỗng không lỗi"""
    n = normalize_for_flags("")
    assert n.folded == ""
    assert n.original_span(0, 0) == ""

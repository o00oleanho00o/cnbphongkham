# ported from: src/shared/html-entities.ts
"""Giải mã HTML entity về ký tự thật. Trang tiếng Việt (minhngoc, xoso...) trộn entity SỐ (&#225; = á)
với entity TÊN (&Ecirc; = Ê, &agrave; = à) - chỉ decode số thì text ra "CHUY&Ecirc;N TRANG" thay vì
"CHUYÊN TRANG", model đọc rất khổ.

Forced deviations: none in behaviour, except that a numeric entity whose code point is not a valid scalar
value (above U+10FFFF or a lone surrogate) is left untouched. ``String.fromCodePoint`` throws ``RangeError``
for the first and the original had no guard; a lone surrogate would later fail to encode as UTF-8. Leaving
the entity as text keeps the "unknown entity stays as it is, never throws" rule of the original. Numeric
classes are ASCII (``[0-9]``): Python's ``\\d`` would also accept non-ASCII numerals.
"""

from __future__ import annotations

import re

NAMED_ENTITIES: dict[str, str] = {
    # Ký hiệu hay gặp
    "amp": "&",
    "lt": "<",
    "gt": ">",
    "quot": '"',
    "apos": "'",
    "nbsp": " ",
    "hellip": "...",
    "ndash": "-",
    "mdash": "-",
    "lsquo": "'",
    "rsquo": "'",
    "ldquo": '"',
    "rdquo": '"',
    "laquo": "<<",
    "raquo": ">>",
    "middot": "-",
    "bull": "-",
    "trade": "(TM)",
    "copy": "(c)",
    "reg": "(R)",
    "deg": "°",
    # Chữ Latin-1 có dấu (bản thường; "Ecirc" tự tra "ecirc" rồi viết hoa kết quả)
    "agrave": "à",
    "aacute": "á",
    "acirc": "â",
    "atilde": "ã",
    "auml": "ä",
    "aring": "å",
    "aelig": "æ",
    "ccedil": "ç",
    "egrave": "è",
    "eacute": "é",
    "ecirc": "ê",
    "euml": "ë",
    "igrave": "ì",
    "iacute": "í",
    "icirc": "î",
    "iuml": "ï",
    "eth": "ð",
    "ntilde": "ñ",
    "ograve": "ò",
    "oacute": "ó",
    "ocirc": "ô",
    "otilde": "õ",
    "ouml": "ö",
    "oslash": "ø",
    "ugrave": "ù",
    "uacute": "ú",
    "ucirc": "û",
    "uuml": "ü",
    "yacute": "ý",
    "thorn": "þ",
    "yuml": "ÿ",
    "szlig": "ß",
}
"""Entity tên -> ký tự. Chữ Latin-1 chỉ cần bản thường - bản hoa suy ra tự động."""

_HEX = re.compile(r"&#x([0-9a-fA-F]+);")
_DEC = re.compile(r"&#([0-9]+);")
_NAMED = re.compile(r"&([a-zA-Z]+);")
_UPPER_START = re.compile(r"[A-Z]")


def _decode_named(name: str) -> str | None:
    direct = NAMED_ENTITIES.get(name)
    if direct is not None:
        return direct
    # "Ecirc" / "ECIRC" -> tra "ecirc" rồi viết hoa: khỏi liệt kê gấp đôi bảng
    lower = NAMED_ENTITIES.get(name.lower())
    if lower is not None and _UPPER_START.match(name):
        return lower.upper()
    return None


def _from_code_point(code: int) -> str | None:
    if code > 0x10FFFF or 0xD800 <= code <= 0xDFFF:
        return None
    return chr(code)


def decode_html_entities(text: str) -> str:
    def hex_sub(match: re.Match[str]) -> str:
        decoded = _from_code_point(int(match.group(1), 16))
        return match.group(0) if decoded is None else decoded

    def dec_sub(match: re.Match[str]) -> str:
        decoded = _from_code_point(int(match.group(1)))
        return match.group(0) if decoded is None else decoded

    def named_sub(match: re.Match[str]) -> str:
        decoded = _decode_named(match.group(1))
        return match.group(0) if decoded is None else decoded

    text = _HEX.sub(hex_sub, text)
    text = _DEC.sub(dec_sub, text)
    return _NAMED.sub(named_sub, text)

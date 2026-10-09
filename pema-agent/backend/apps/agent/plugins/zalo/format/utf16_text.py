"""UTF-16 and JavaScript string semantics for the text pipeline (no TS original: a forced-deviation helper).

Why this module exists: the TypeScript text pipeline runs on JS strings, whose ``length``, ``slice`` and
regex indices count UTF-16 code units, and zca-js packs ``Style.start`` / ``Style.len`` into
``textProperties`` untouched, so Zalo counts the same way. An emoji is a surrogate pair, 2 units. Python
``str`` counts code points. "Fixing" the offsets to code points would shift every span after the first
emoji of a real message (see the docstring of ``markdown_to_zalo_styles``).

The approach: a *unit string* is a ``str`` holding one char per UTF-16 code unit (an astral character
becomes its two surrogate halves, which Python strings can hold). Every algorithm that the original wrote
against JS strings runs unchanged on a unit string, so every length, slice, index and offset is a UTF-16
unit by construction. ``to_units`` / ``from_units`` convert at the public boundary only:

* texts coming IN from callers (real ``str``) are converted with ``to_units``;
* texts going OUT (message parts, stripped text) are converted back with ``from_units``;
* every ``start`` / ``length`` that crosses a module boundary (``TextStyle``, ``DoanDaCat``) is in UTF-16
  units relative to the text it belongs to.

A cut must never split a surrogate pair (the original could, a latent bug on a 2000-char window): see
``khong_cat_giua_cap_thay_the``.

JS whitespace: ``String.prototype.trim`` and the regex class ``\\s`` match WhiteSpace + LineTerminator, which
is NOT the same set as Python's ``str.strip()`` / ``\\s`` (JS includes U+FEFF; Python also matches
U+001C..U+001F and U+0085). ``JS_WS_CHARS`` is the exact ECMAScript set; the ``js_*`` helpers and the
``JS_S`` / ``JS_NOT_S`` regex fragments use it.
"""

from __future__ import annotations

import struct

from .js_whitespace import JS_NOT_S, JS_S, JS_WS_CHARS, js_trim, js_trim_end, js_trim_start

__all__ = [
    "JS_LINE_END",
    "JS_LINE_START",
    "JS_NOT_S",
    "JS_S",
    "JS_WS_CHARS",
    "from_units",
    "index_to_utf16",
    "js_trim",
    "js_trim_end",
    "js_trim_start",
    "khong_cat_giua_cap_thay_the",
    "to_units",
    "utf16_len",
    "utf16_slice",
    "utf16_to_index",
]

# JS multiline ``^`` / ``$`` also treat CR, LS and PS as line terminators (Python's ``re.M`` only knows LF).
JS_LINE_START = "(?<![^\\n\\r\\u2028\\u2029])"
JS_LINE_END = "(?![^\\n\\r\\u2028\\u2029])"


def _is_bmp(text: str) -> bool:
    return all(ord(ch) < 0x10000 for ch in text)


def _has_surrogate_unit(text: str) -> bool:
    return any(0xD800 <= ord(ch) <= 0xDFFF for ch in text)


def to_units(text: str) -> str:
    """Real string -> unit string (one char per UTF-16 code unit). Identity for BMP-only text."""
    if text.isascii() or _is_bmp(text):
        return text
    data = text.encode("utf-16-le", "surrogatepass")
    units = struct.unpack(f"<{len(data) // 2}H", data)
    return "".join(map(chr, units))


def from_units(units: str) -> str:
    """Unit string -> real string (surrogate pairs recombined). Lone surrogates are kept as they are."""
    if units.isascii() or not _has_surrogate_unit(units):
        return units
    return units.encode("utf-16-le", "surrogatepass").decode("utf-16-le", "surrogatepass")


def utf16_len(text: str) -> int:
    """JS ``String.length`` of a real string."""
    if text.isascii():
        return len(text)
    return sum(2 if ord(ch) >= 0x10000 else 1 for ch in text)


def utf16_slice(text: str, start: int, length: int) -> str:
    """JS ``text.slice(start, start + length)`` of a real string, offsets in UTF-16 units."""
    return from_units(to_units(text)[start : start + length])


def utf16_to_index(text: str, offset: int) -> int:
    """UTF-16 offset -> code point index of a real string (``offset`` must not fall inside a pair)."""
    return len(from_units(to_units(text)[:offset]))


def index_to_utf16(text: str, index: int) -> int:
    """Code point index -> UTF-16 offset of a real string."""
    return utf16_len(text[:index])


def _is_high_surrogate(ch: str) -> bool:
    return 0xD800 <= ord(ch) <= 0xDBFF


def _is_low_surrogate(ch: str) -> bool:
    return 0xDC00 <= ord(ch) <= 0xDFFF


def khong_cat_giua_cap_thay_the(units: str, cut: int) -> int:
    """Move ``cut`` (an index in a unit string) off the middle of a surrogate pair.

    Backs up by one unit; when that would leave an empty head (``cut == 1``) moves forward instead so the
    caller still makes progress.
    """
    if 0 < cut < len(units) and _is_high_surrogate(units[cut - 1]) and _is_low_surrogate(units[cut]):
        return cut - 1 if cut > 1 else cut + 1
    return cut

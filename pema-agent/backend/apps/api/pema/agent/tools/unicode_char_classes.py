# ported from: (no TS counterpart) regex character classes used by wrap-untrusted-content.ts,
# khu-dai-phan-cach-gia.ts and khu-gia-mao-nhan-nguon.ts
"""Character-class strings for the ``\\p{Cf}`` / ``\\p{Mn}`` / JS ``\\s`` of the original regexes.

Forced deviation: the TypeScript sources use the Unicode property escapes ``\\p{Cf}`` (format characters:
ZWSP, ZWJ, BOM, RTL override ...) and ``\\p{Mn}`` (combining marks) and JavaScript's ``\\s``. The stdlib
``re`` has no ``\\p{..}``, and the third-party ``regex`` package is not a dependency of this project, so the
classes are generated ONCE at import from ``unicodedata`` (general category) and spliced into a bracket
expression. Behaviour stays the same; only the Unicode database version of the interpreter may differ from
the Node one.

Only the planes that can hold a character of those categories are scanned: planes 0-3 (BMP, SMP, SIP, TIP)
and the plane 14 (tags, variation selectors supplement). Planes 4-13 are unassigned and 15-16 are private
use.

``JS_WHITESPACE`` is spelled out instead of using Python's ``\\s``: Python's ``\\s`` also matches
U+001C-U+001F and U+0085, JavaScript's ``\\s`` does not (and JavaScript's includes U+FEFF, Python's does
not).

PURE module: no log, no env, no DB.
"""

from __future__ import annotations

import unicodedata

_SCANNED = (range(0x0, 0x40000), range(0xE0000, 0xF0000))


def _range(first: int, last: int) -> str:
    if first == last:
        return f"\\U{first:08x}"
    return f"\\U{first:08x}-\\U{last:08x}"


def _ranges_of(category: str) -> str:
    """Bracket-expression body (no brackets) of every code point whose general category is ``category``."""
    out: list[str] = []
    start = -1
    prev = -2
    for span in _SCANNED:
        for cp in span:
            if unicodedata.category(chr(cp)) != category:
                continue
            if cp != prev + 1:
                if start >= 0:
                    out.append(_range(start, prev))
                start = cp
            prev = cp
    if start >= 0:
        out.append(_range(start, prev))
    return "".join(out)


CF = _ranges_of("Cf")
"""Body of ``\\p{Cf}`` (put it inside ``[...]``)."""

MN = _ranges_of("Mn")
"""Body of ``\\p{Mn}`` (put it inside ``[...]``)."""

JS_WHITESPACE = "\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff"
"""Body of JavaScript's ``\\s`` (put it inside ``[...]``)."""

BRAILLE_BLANK = "\\u2800"
"""U+2800 BRAILLE PATTERN BLANK: neither ``\\s`` nor ``\\p{Zs}``, the space of Braille."""

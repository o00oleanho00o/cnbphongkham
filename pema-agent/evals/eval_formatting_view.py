# ported from: evals/eval-formatting-view.ts
"""How the evals SEE the formatting of an answer.

WHY THIS FILE EXISTS - a gap paid for on 2026-08-05. ``kiem_tra_text`` only receives the BARE text after the
markdown was translated, when the ``**`` markers are already gone. So every case could assert "no markdown
character leaked into the text" and could NEVER measure whether anything was bold. A machine had no way to
catch a formatting fault, every ugly output was found by a user, and the persona rules grew case by case
instead of being checked against many message shapes.

Each span carries the TEXT it covers, not only the style code: "there are 5 bold spans" is almost meaningless,
"the bold spans cover the first words of each item" is what a reader perceives.

Pure module. Forced deviation: the original slices JavaScript strings, whose ``start``/``len`` are UTF-16 code
units (an emoji is a surrogate pair = 2 units). Python strings index code points, so the slice goes through
UTF-16 explicitly; slicing by code points would shift every span after the first emoji.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ZaloStyle:
    """One style range of a sent message (zca-js ``Style``): ``start``/``len`` in UTF-16 units."""

    start: int
    len: int
    st: str


@dataclass(frozen=True)
class SentMessage:
    """One message exactly as it went into ``sendMessage``: the text and its style ranges."""

    msg: str
    styles: list[ZaloStyle] = field(default_factory=list[ZaloStyle])


@dataclass(frozen=True)
class SpanDaGui:
    """A styled region together with the exact text inside it."""

    st: str
    """Zalo style code: ``b``, ``i``, ``u``, ``s``, ``f_18``, ``c_f27806``..."""
    chu: str
    """The text this span covers: what the reader really sees styled."""
    tin: int
    """Which message (counted from 1): a long answer is split into several."""


@dataclass(frozen=True)
class DinhDangDaGui:
    span: list[SpanDaGui]
    """Every span of every message, in the order sent."""
    so_tin: int
    """How many messages Zalo really received."""


def doan_theo_kieu(dd: DinhDangDaGui, st: str) -> list[str]:
    """Every piece of text styled with one given style."""
    return [s.chu for s in dd.span if s.st == st]


def dem_kieu(dd: DinhDangDaGui, st: str) -> int:
    """How many spans have this style."""
    return sum(1 for s in dd.span if s.st == st)


@dataclass(frozen=True)
class _Kieu:
    """The style codes (``KIEU.dam``...). ``do`` is a legal attribute name in Python."""

    dam: str = "b"
    nghieng: str = "i"
    gach_chan: str = "u"
    to: str = "f_18"
    do: str = "c_db342e"
    cam: str = "c_f27806"
    vang: str = "c_f7b503"
    xanh: str = "c_15a85f"


KIEU = _Kieu()
"""The style codes used in assertions, so the cases do not scatter magic strings."""


def utf16_len(text: str) -> int:
    """Length of ``text`` in UTF-16 code units (JavaScript ``string.length``)."""
    return len(text.encode("utf-16-le")) // 2


def utf16_index(text: str, needle: str) -> int:
    """JavaScript ``text.indexOf(needle)`` in UTF-16 units; -1 when absent."""
    at = text.find(needle)
    return -1 if at < 0 else utf16_len(text[:at])


def _slice_utf16(text: str, start: int, length: int) -> str:
    """JavaScript ``text.slice(start, start + length)`` with UTF-16 offsets."""
    raw = text.encode("utf-16-le")
    return raw[2 * start : 2 * (start + length)].decode("utf-16-le", errors="replace")


def dung_goc_nhin_dinh_dang(tin: list[SentMessage]) -> DinhDangDaGui:
    """Build the formatting view from what the fake API recorded.

    ``chu`` is cut RIGHT HERE instead of letting each case cut it: ``start``/``len`` are UTF-16 units, and
    cutting wrong once would make every later assertion lie while staying green.
    """
    span: list[SpanDaGui] = []
    for i, t in enumerate(tin):
        for s in t.styles:
            span.append(SpanDaGui(st=s.st, chu=_slice_utf16(t.msg, s.start, s.len), tin=i + 1))
    return DinhDangDaGui(span=span, so_tin=len(tin))

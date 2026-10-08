# ported from: src/knowledge/chunk-text.ts
"""Cut raw text into chunks to store in ``agent.kb_chunk`` (through ``luu_doan``).

Cut at NATURAL boundaries, not by a hard character count: cutting mid-sentence loses the meaning, and a
chunk without meaning is useless even if the ranker finds it. Boundary priority: markdown heading (``#``) >
blank line > newline > sentence (``. ``) > character (only when no other boundary is left).

Keep the NEAREST markdown HEADING above in each chunk - the cheapest trick to compensate for retrieval that
cannot see the whole document: the chunk "trong vòng 7 ngày" alone means nothing, with the heading
"Chính sách đổi trả" the model reads it at once.

Pure function (no environment, no database, no file read) - imports only the invisible-character filter
(also pure). This is the INGEST layer: the Tags range (ASCII smuggling, see ``loc_ky_tu_an``) is filtered
HERE and not in the wrapping layer: a document that enters the store is already clean, no need to filter
again at each lookup.

Forced deviation: JavaScript string lengths count UTF-16 code units, Python counts code points; the two
differ only for characters outside the Basic Multilingual Plane (emoji), where Python's chunks are a hair
longer in code units. Irrelevant for Vietnamese text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from pema.knowledge.tag_ky_tu_an import loc_ky_tu_an


@dataclass(frozen=True, slots=True)
class ThamSoCat:
    co_doan_toi_da: int
    chong_lan: int


@dataclass(frozen=True, slots=True)
class DoanMoi:
    """A chunk to store: ``thu_tu`` (order), ``tieu_de`` (heading breadcrumb), ``noi_dung`` (body)."""

    thu_tu: int
    tieu_de: str
    noi_dung: str


@dataclass(frozen=True, slots=True)
class _DoanChuaGanSo:
    tieu_de: str
    noi_dung: str


HEADING_RE: Final = re.compile(r"^(#{1,6})\s+(.+)$")
"""Markdown heading: 1-6 ``#``, a space, then text. Group 1 = the ``#`` run (level), group 2 = the title."""

CAP_TOI_DA: Final = 6
"""Maximum heading level markdown supports (matches ``#{1,6}`` above)."""


def _trim(s: str) -> str:
    """``String.prototype.trim``: whitespace and the byte order mark."""
    return s.strip().strip("﻿").strip()


def _vi_tri_cat_tot_nhat(text: str, max_len: int) -> int:
    """Best cut position in ``text[:max_len]``: prefer the newline nearest the end, then the sentence
    punctuation nearest the end, finally a hard cut at exactly ``max_len``. Only a position > 0 is accepted
    so every iteration of the loop that calls this advances at least one character - otherwise the cutting
    loop of ``cat_thanh_doan`` could stand still."""
    doan_dau = text[:max_len]

    vi_tri_xuong_dong = doan_dau.rfind("\n")
    if vi_tri_xuong_dong > 0:
        return vi_tri_xuong_dong + 1

    vi_tri_cau_cham = doan_dau.rfind(". ")
    if vi_tri_cau_cham > 0:
        return vi_tri_cau_cham + 1  # keep the period, drop the space after it

    return max_len


def _cat_van_ban_phang(text: str, max_len: int) -> list[str]:
    """Cut text that has NO blank-line boundary left (already split in ``cat_thanh_doan``) into pieces
    <= ``max_len`` using the newline, then sentence, then character boundary."""
    ra: list[str] = []
    con = text
    while len(con) > max_len:
        vi_tri_cat = _vi_tri_cat_tot_nhat(con, max_len)
        manh = _trim(con[:vi_tri_cat])
        if manh:
            ra.append(manh)
        con = con[vi_tri_cat:]
    cuoi = _trim(con)
    if cuoi:
        ra.append(cuoi)
    return ra


def _chen_chong_lan(doan: list[_DoanChuaGanSo], overlap_chars: int) -> list[_DoanChuaGanSo]:
    """Insert the overlap: the next chunk carries the last ``overlap_chars`` characters of the chunk right
    before it - ONLY when both chunks have the same heading (a different heading means we moved to another
    section, and carrying old content over would be the wrong context). The start of the overlap is moved
    forward to the nearest space so the next chunk does not begin with half a word."""
    if overlap_chars <= 0 or len(doan) < 2:
        return doan

    ra: list[_DoanChuaGanSo] = [doan[0]]
    for i in range(1, len(doan)):
        truoc = doan[i - 1]
        hien_tai = doan[i]
        if truoc.tieu_de != hien_tai.tieu_de:
            ra.append(hien_tai)
            continue

        duoi = truoc.noi_dung[max(0, len(truoc.noi_dung) - overlap_chars) :]
        vi_tri_khoang_trang = duoi.find(" ")
        phan_chong_lan = duoi if vi_tri_khoang_trang == -1 else duoi[vi_tri_khoang_trang + 1 :]
        ra.append(
            _DoanChuaGanSo(
                tieu_de=hien_tai.tieu_de,
                noi_dung=f"{phan_chong_lan} {hien_tai.noi_dung}" if phan_chong_lan else hien_tai.noi_dung,
            )
        )
    return ra


def cat_thanh_doan(chu: str, p: ThamSoCat) -> list[DoanMoi]:
    # Normalise line endings ONCE at the door - all the logic below (splitting on blank lines, looking for a
    # heading on the first line) relies on a bare "\n". A .txt/.md saved by Windows Notepad/Word has CRLF
    # ("\r\n\r\n" for a blank line): there are no 2 "\n" side by side so ``re.split(r"\n{2,}")`` splits
    # nothing, the whole document falls into ONE chunk and the "keep the nearest heading" feature breaks
    # silently (only a heading on the first line of the document is found). ``\r\n?`` catches CRLF and a
    # lone CR (old Mac).
    #
    # Filter the Tags range RIGHT HERE - the single choke point every KB document goes through before it is
    # cut, so filtering once at the door is clean enough for the whole store.
    chu = loc_ky_tu_an(re.sub(r"\r\n?", "\n", chu))

    max_len = max(1, p.co_doan_toi_da)
    overlap_chars = max(0, int(max_len * (p.chong_lan / 100)))

    ket_qua: list[_DoanChuaGanSo] = []
    # Stack of headings by LEVEL (index 1..6, index 0 is always empty and unused) - fixes bug I1: the old
    # version kept ONE ``tieu_de_hien_tai``, overwritten by an H2 before any chunk was closed under the H1,
    # so the H1 (usually the SAME as the document name) never reached the index when an H2 followed. On a
    # heading of level N, CLEAR every level DEEPER than N (a new section invalidates the old child
    # headings), then join the remaining levels (shallow -> deep) into a breadcrumb "H1 > H2 > H3".
    ngan_xep_tieu_de: list[str] = [""] * (CAP_TOI_DA + 1)
    tieu_de_hien_tai = ""
    buffer = ""

    def chot_buffer() -> None:
        """Close the buffer being gathered into one (or several, if the buffer exceeds ``max_len``) chunk."""
        nonlocal buffer
        noi_dung = _trim(buffer)
        buffer = ""
        if not noi_dung:
            return
        for manh in _cat_van_ban_phang(noi_dung, max_len):
            ket_qua.append(_DoanChuaGanSo(tieu_de=tieu_de_hien_tai, noi_dung=manh))

    for doan_tho in re.split(r"\n{2,}", chu):
        doan_van = _trim(doan_tho)
        if not doan_van:
            continue

        dong = doan_van.split("\n")
        khop_tieu_de = HEADING_RE.match(_trim(dong[0]))
        than = doan_van
        if khop_tieu_de:
            # New section: close everything gathered under the OLD breadcrumb before changing it
            chot_buffer()
            cap = len(khop_tieu_de.group(1))
            ngan_xep_tieu_de[cap] = _trim(khop_tieu_de.group(2))
            for lv in range(cap + 1, CAP_TOI_DA + 1):
                ngan_xep_tieu_de[lv] = ""
            tieu_de_hien_tai = " > ".join(t for t in ngan_xep_tieu_de if t)
            than = _trim("\n".join(dong[1:]))
        # A heading with no body RIGHT below it (e.g. "# Document title" alone and then "## Subsection") is
        # NOT skipped from the breadcrumb: the stack above has recorded it; there is just nothing to CLOSE
        # into a chunk in this round.
        if not than:
            continue

        ghep = f"{buffer}\n\n{than}" if buffer else than
        if len(ghep) <= max_len:
            buffer = ghep
        else:
            chot_buffer()
            buffer = than
    chot_buffer()

    return [
        DoanMoi(thu_tu=i, tieu_de=d.tieu_de, noi_dung=d.noi_dung)
        for i, d in enumerate(_chen_chong_lan(ket_qua, overlap_chars))
    ]

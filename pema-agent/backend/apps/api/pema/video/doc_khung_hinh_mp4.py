# ported from: src/video/doc-khung-hinh-mp4.ts
"""Read the REAL FRAME SIZE and DURATION from the MP4 file itself, instead of trusting source metadata.

WHY IT MUST EXIST (frame size): a real case a user hit: a 1280x720 LANDSCAPE Facebook video was declared as
576x1024 PORTRAIT, and the Zalo app on a PHONE CRASHED when opening the chat. Zalo builds the play surface
from the numbers we declare and then receives a completely different frame.

WHY DURATION TOO: Instagram (yt-dlp) returns ``duration: null``, so if we only trusted the source the video
card shows 0:00. The duration sits ready in the file's ``mvhd`` box (2 fields ``timescale`` + ``duration``),
reading straight from there is exact. Read in the SAME walk of the box tree as the frame size: no extra cost
(the buffer is already in RAM).

Why not trust the source (frame size):

    TikWM   returns NO width/height at all (the whole response key set was dumped)
    yt-dlp  Facebook's ``hd`` format carries no width/height anywhere, even inside itself; and the
            ``formats`` array declares 2560x1440 while the stream sent measures 1280x720 with ffprobe

Reading from the file depends on no source's claim. Checked on real videos, matching ffprobe number by
number: TikTok landscape/portrait, Facebook landscape, Instagram 720x1280 + 67s.

SAFETY: this is a byte reader for strangers' data, so it is deliberately very narrow: it only follows the MP4
box tree to find ``tkhd``/``mvhd``, decodes no frame, allocates nothing by a size the file declares, has a
ceiling on box count and on depth. Every read checks the bounds first. When broken it returns ``None``, it
does not raise.

Forced deviation: Node ``Buffer`` reads (``readUInt32BE`` ...) become ``struct.unpack_from``; a read past the
buffer raises ``struct.error`` where Node raised ``RangeError``, and both are swallowed by the same
``try``/``except`` as in the original. JS ``Math.round`` (half rounds up) is ``_math_round``.
"""

from __future__ import annotations

import contextlib
import math
import struct
from dataclasses import dataclass

TRAN_HOP = 300
"""Ceiling on boxes walked: blocks a file stuffed with tens of thousands of empty boxes."""

TRAN_SAU = 3
"""Maximum depth when entering nested boxes (``moov`` -> ``trak`` -> ...)."""

VI_TRI_MA_TRAN = 40
VI_TRI_KHUNG = 76
DICH_KHI_VERSION_1 = 12
"""Positions of the fields in the ``tkhd`` box, counted from the start of the box BODY.

MEASURED on a TikTok file and checked against ffprobe, not copied from memory: my first version miscounted
4 bytes and read a height of 16384 (the last element of the transform matrix, ``0x40000000``).

Version 1 uses an 8-byte timestamp instead of 4, in three fields, so everything after shifts by 12 bytes."""

CAN_TOI_THIEU = VI_TRI_KHUNG + 8
"""A ``tkhd`` box must be long enough to reach the end of the height before it can be read."""

MVHD_V0_TIMESCALE = 12
MVHD_V0_DURATION = 16
MVHD_V1_TIMESCALE = 20
MVHD_V1_DURATION = 24
MVHD_CAN_V0 = MVHD_V0_DURATION + 4
MVHD_CAN_V1 = MVHD_V1_DURATION + 8
"""Position of ``timescale`` + ``duration`` in the ``mvhd`` box, counted from the start of the BODY.

``mvhd`` body: version(1) + flags(3), then
  version 0: creation(4) modification(4) timescale(4)@12 duration(4)@16
  version 1: creation(8) modification(8) timescale(4)@20 duration(8)@24"""

THOI_LUONG_TRAN_MS = 24 * 60 * 60 * 1000
"""Sane duration ceiling: catches a ``duration`` declared as the "unknown" sentinel (0xFFFFFFFF)."""


@dataclass(frozen=True)
class KhungHinh:
    width: int
    height: int


@dataclass(frozen=True)
class ThongTinMp4:
    khung: KhungHinh | None
    thoi_luong_ms: int | None


def _math_round(x: float) -> int:
    """JS ``Math.round`` (half rounds UP), not Python's banker's rounding."""
    return math.floor(x + 0.5)


def tinh_thoi_luong_ms(timescale: int, duration: int) -> int | None:
    """timescale + duration -> milliseconds, or ``None`` if absurd (including the "unknown" sentinel)."""
    if not timescale > 0 or not duration > 0:
        return None
    ms = _math_round((duration / timescale) * 1000)
    return ms if 0 < ms < THOI_LUONG_TRAN_MS else None


def doc_thong_tin_mp4(b: bytes) -> ThongTinMp4:
    """Read BOTH the frame size (from ``tkhd``) and the DURATION (from ``mvhd``) in ONE walk.

    Does not return early at the first ``tkhd`` like the old version: it goes on until it has BOTH (or runs
    out of boxes / hits the ceiling). ``mvhd`` is a direct child of ``moov``, ``tkhd`` sits in ``trak``: the
    same area, so both are met almost at once.
    """
    dem_hop = 0
    khung: KhungHinh | None = None
    thoi_luong_ms: int | None = None

    def xong() -> bool:
        return khung is not None and thoi_luong_ms is not None

    def doc_tkhd(than: int, het: int) -> KhungHinh | None:
        if than >= len(b):
            return None
        ver = b[than]
        dich = DICH_KHI_VERSION_1 if ver == 1 else 0
        if than + CAN_TOI_THIEU + dich > het:
            return None

        mt = than + VI_TRI_MA_TRAN + dich
        ok = than + VI_TRI_KHUNG + dich
        w = struct.unpack_from(">I", b, ok)[0] / 65536
        h = struct.unpack_from(">I", b, ok + 4)[0] / 65536
        if not (w > 0 and h > 0):
            return None  # an audio track declares 0x0

        # Transform matrix: ``a === 0 && b !== 0`` means a 90 or 270 degree rotation, i.e. the DISPLAY frame
        # is swapped against the stored frame. A video shot portrait on a phone is often stored landscape
        # with a rotation flag: not handling it declares the wrong orientation again, exactly the error that
        # just crashed the phone.
        a = struct.unpack_from(">i", b, mt)[0]
        bb = struct.unpack_from(">i", b, mt + 4)[0]
        xoay = a == 0 and bb != 0

        if xoay:
            return KhungHinh(width=_math_round(h), height=_math_round(w))
        return KhungHinh(width=_math_round(w), height=_math_round(h))

    def doc_mvhd(than: int, het: int) -> int | None:
        if than >= len(b):
            return None
        ver = b[than]
        if ver == 1:
            if than + MVHD_CAN_V1 > het:
                return None
            ts = struct.unpack_from(">I", b, than + MVHD_V1_TIMESCALE)[0]
            dur = struct.unpack_from(">Q", b, than + MVHD_V1_DURATION)[0]
            return tinh_thoi_luong_ms(ts, dur)
        if than + MVHD_CAN_V0 > het:
            return None
        ts = struct.unpack_from(">I", b, than + MVHD_V0_TIMESCALE)[0]
        dur = struct.unpack_from(">I", b, than + MVHD_V0_DURATION)[0]
        return tinh_thoi_luong_ms(ts, dur)

    def duyet(dau: int, cuoi: int, sau: int) -> None:
        nonlocal dem_hop, khung, thoi_luong_ms
        i = dau
        while i + 8 <= cuoi and not xong():
            dem = dem_hop
            dem_hop += 1
            if dem >= TRAN_HOP:
                return
            co: int = struct.unpack_from(">I", b, i)[0]
            ten = b[i + 4 : i + 8].decode("latin1")
            than = i + 8

            if co == 1:
                # 64-bit size sits right after the box name
                if than + 8 > cuoi:
                    return
                co = struct.unpack_from(">Q", b, than)[0]
                than += 8
            if co == 0:
                co = cuoi - i  # last box, stretches to the end
            if co < 8:
                return

            # Do NOT give up when the box is longer than the part we have: ``moov`` is usually bigger than
            # the head of the file we downloaded, while ``tkhd``/``mvhd`` sit right in the start of it.
            het = min(i + co, cuoi)

            if ten == "tkhd":
                if khung is None:
                    r = doc_tkhd(than, het)
                    if r is not None:
                        khung = r
            elif ten == "mvhd":
                if thoi_luong_ms is None:
                    r2 = doc_mvhd(than, het)
                    if r2 is not None:
                        thoi_luong_ms = r2
            elif ten in ("moov", "trak") and sau < TRAN_SAU:
                duyet(than, het, sau + 1)

            i += co

    # A stranger's bytes: a read past the bounds is dropped, do not break the whole send.
    with contextlib.suppress(struct.error, IndexError):
        duyet(0, len(b), 0)
    return ThongTinMp4(khung=khung, thoi_luong_ms=thoi_luong_ms)


def doc_khung_hinh_mp4(b: bytes) -> KhungHinh | None:
    """Frame size only. Keeps the old signature for the places that only need the size.

    Finds the ``tkhd`` of the FIRST track whose size is non-zero. The audio track also has a ``tkhd`` but
    declares 0x0: measured, and my first version read exactly that wrong track.
    """
    return doc_thong_tin_mp4(b).khung

# ported from: src/video/kiem-url-video-truoc-khi-gui.ts
"""Probe whether the video link returned by a SOURCE can really be sent.

WHY IT MUST EXIST: this is a mistake that was paid for, do not remove it.

The previous version assumed "a broken URL makes ``sendVideo`` raise, we catch it and fall back to the
download path". That assumption is WRONG. Reading the zca-js source (``sendVideo.ts:69-77``):

    const headResponse = await utils.request(options.videoUrl, { method: "HEAD" }, true);
    if (headResponse.ok) { fileSize = parseInt(...); }

``sendVideo`` only RAISES when the HEAD request itself raises (network error, DNS). With HTTP 403 or 404
``headResponse.ok`` is ``false``, ``fileSize`` stays 0, and it STILL sends the message containing that dead
URL. That means the ``catch`` branch never runs, the download path is dead code, and the bot charges the
slot, writes "video sent" into the history and reports success to the model, while the recipient sees a
video card that does not open.

Measured on a TikTok link: yt-dlp's URL returns **403 right on the machine that just ran yt-dlp** (it is tied
to yt-dlp's session). That is not a rare case.

PROBE WITH GET PLUS ``Range: bytes=0-0``, NOT WITH HEAD: measured and paid for: ``v16m.tiktokcdn-us.com``
returns **503 for HEAD** while returning **206 for GET with Range** on the SAME URL, whereas
``v19.tiktokcdn-us.com`` answers HEAD normally. So a failing HEAD does NOT mean a broken video: the
recipient's machine downloads with GET and can still watch. Probing with HEAD wrongly pushes a living video
to the most expensive fallback. Range 0-0 costs one byte yet measures what will really happen.

SECURITY: goes through ``open_guarded_request`` so ``videoUrl``, a string returned by a third party
(TikWM/yt-dlp), is blocked if it points at an internal address, and every redirect hop is checked again.
Without this step ``videoUrl`` goes straight into ``sendVideo``, and zca-js follows ``location`` RECURSIVELY
without counting hops, without checking the address (``utils.ts:320-331``).

Forced deviations: Node ``URL`` is ``parse_public_url`` / ``httpx.URL`` of ``safe_remote_download``; the Node
response object (``statusCode``, ``headers``, ``destroy``) is ``GuardedResponse`` (``status_code``,
``headers``, ``aclose``). The optional ``transport`` / ``resolver`` keyword arguments are the test seams of
``open_guarded_request`` (no real network in tests).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

import httpx

from pema.shared.safe_remote_download import (
    MAX_REDIRECTS,
    HostResolver,
    open_guarded_request,
    parse_public_url,
)

TRAN_DO_MS = 15_000
"""Time ceiling for one probe. Only asks for 1 byte so it need not be wide."""

TRAN_HOP = MAX_REDIRECTS
"""Maximum redirect hops when probing.

IMPORTED, not copied by hand: the previous version wrote ``3`` with a comment "keep it equal to the download
version so both sides have the same rule", a promise nobody watches. An import is watched by the compiler."""


def do_co_that(status: int, day_du: str | None, dai_phan: float) -> int | None:
    """The REAL size of the whole file, from whichever header tells the truth.

    With a 206, ``content-length`` is the length of the PART just asked for (1 byte), not the file size:
    reading it wrongly makes every video "1 byte" and the size ceiling meaningless. The real size is at the
    tail of ``content-range: bytes 0-0/6667679``.

    A server that does not support Range returns 200 with ``content-length`` being the full size. When
    nothing is trustworthy return ``None``: better not to know than to know wrong.
    """
    if status == 206:
        m = re.search(r"/([0-9]+)\s*$", day_du or "")
        n = float(m.group(1)) if m else math.nan
        return int(n) if math.isfinite(n) and n > 0 else None
    return int(dai_phan) if math.isfinite(dai_phan) and dai_phan > 0 else None


@dataclass(frozen=True)
class KetQuaDoOk:
    so_byte: int | None
    kieu_noi_dung: str
    url_cuoi: str
    """The FINAL URL that was verified (after following every redirect).

    The caller MUST use this one, not the original string: the previous version probed one thing and gave
    ``sendVideo`` another, while zca-js follows ``location`` recursively without counting hops and without
    checking the address."""
    ok: Literal[True] = True


@dataclass(frozen=True)
class KetQuaDoLoi:
    ly: str
    ok: Literal[False] = False


KetQuaDo = KetQuaDoOk | KetQuaDoLoi


def la_kieu_video(kieu: str) -> bool:
    """Is the content type regarded as video.

    Strict: ONLY ``video/*`` and ``application/octet-stream``. The case to catch is a CDN returning **200
    with ``text/html``**: an "expired link" page or a bot-block page. That case does not raise, ``bytes > 0``
    so it also passes the "empty content" gate, then the HTML is written to ``<name>.mp4`` and sent as a
    video. The recipient gets a 2KB file that does not open, and the bot reports success.

    ``application/octet-stream`` is accepted because some CDNs return that type for mp4; it is "unknown" and
    not "known to be HTML", so blocking it is blocking unjustly.
    """
    g = kieu.lower().split(";")[0].strip()
    return g.startswith("video/") or g == "application/octet-stream"


def quyet_dinh_tu_header(
    status: int, kieu: str, day_du: str | None, dai_phan: float, url_cuoi: str = ""
) -> KetQuaDo:
    """The final decision from the headers. PURE, split out so it can be tested.

    Without the split the DECISION part of the probe has nothing watching it: measured, dropping the
    ``la_kieu_video`` gate or the status gate kept the whole suite green, because every network case is
    blocked by ``open_guarded_request`` before a connection opens, so no case reaches here. So
    ``la_kieu_video`` is proven right, but "the probe CALLS it" was proven by nobody, and that second one is
    exactly the bug to stop.

    Same way ``ghi_stream_ra_file_co_tran`` is split from the network part, and for the same reason.
    """
    if status < 200 or status >= 300:
        return KetQuaDoLoi(ly=f"HTTP {status}")
    if not la_kieu_video(kieu):
        return KetQuaDoLoi(ly=f"Kiểu nội dung không phải video: {kieu or '(trống)'}")
    return KetQuaDoOk(so_byte=do_co_that(status, day_du, dai_phan), kieu_noi_dung=kieu, url_cuoi=url_cuoi)


def _number(value: str | None) -> float:
    """JS ``Number(value)``: ``NaN`` when missing or junk."""
    if value is None:
        return math.nan
    try:
        return float(value.strip())
    except ValueError:
        return math.nan


async def kiem_url_video_con_song(
    raw_url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: HostResolver | None = None,
) -> KetQuaDo:
    """Probe once. Does NOT raise: every failing path returns ``ok=False`` with a short reason for the log,
    because the caller needs to know "cannot be sent by URL" and does not need an exception to catch."""
    try:
        url = parse_public_url(raw_url)
    except Exception:
        return KetQuaDoLoi(ly="URL không hợp lệ")

    for _hop in range(TRAN_HOP + 1):
        try:
            # ``identity`` for the same reason as the download path: if the CDN compresses, then
            # ``content-length`` and ``content-range`` speak about the COMPRESSED size, and the size
            # ceiling reads a wrong number.
            res = await open_guarded_request(
                url,
                TRAN_DO_MS,
                "GET",
                {"range": "bytes=0-0", "Accept-Encoding": "identity"},
                None,
                transport=transport,
                resolver=resolver,
            )
        except Exception as err:
            return KetQuaDoLoi(ly=str(err))

        status = res.status_code
        location = res.headers.get("location")
        kieu = res.headers.get("content-type", "")
        day_du = res.headers.get("content-range")
        dai_phan = _number(res.headers.get("content-length"))
        # Cancel RIGHT after the headers: a server that ignores ``Range`` returns 200 with the WHOLE file,
        # and we have no business pulling tens of MB just to probe.
        await res.aclose()

        if 300 <= status < 400 and location:
            try:
                url = url.join(location)  # the new hop goes through the guard in the next round
            except Exception:
                return KetQuaDoLoi(ly="Chuyển hướng tới URL không hợp lệ")
            continue

        return quyet_dinh_tu_header(status, kieu, day_du, dai_phan, str(url))

    return KetQuaDoLoi(ly=f"Quá {TRAN_HOP} lần chuyển hướng")

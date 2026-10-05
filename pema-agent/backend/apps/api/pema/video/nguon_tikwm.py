# ported from: src/video/nguon-tikwm.ts
"""MAIN source for TikTok: the public API of tikwm.com.

WHY IT STANDS BEFORE yt-dlp: measured numbers, same IP, same time window (2026-08-22):

    TikWM   12/12 (100%)   1.04 seconds   returns h264
    yt-dlp   3/7  (~43%)   3.94 seconds   returns h265 (default)

yt-dlp fails because TikTok returns an anti-bot challenge page. 4 remedies were tried (``--impersonate``,
``api_hostname``, ``device_id``, retry) and none lifted the rate. TikWM stands outside that since it handles
the anti-bot part itself.

IN RETURN: this is a FREE third-party service. It can go down, start charging or tighten limits at any time,
so yt-dlp must stay as tier 2. And the link the user sends goes through their server (they know who looked
up which video, the message content is not exposed).

Does NOT support Facebook: measured ``Url parsing is failed``. Facebook goes to yt-dlp.

Forced deviation: Node ``fetch`` + ``AbortSignal.timeout`` become an ``httpx.AsyncClient`` with a timeout.
The only seam is the optional ``transport`` argument (an ``httpx.MockTransport`` in tests, the equivalent of
the original test replacing ``globalThis.fetch``). The endpoint is a FIXED trusted host (the user's URL only
travels as an encoded query parameter), so this call does not go through the safe-download guard.
"""

from __future__ import annotations

import math
from typing import Any, cast
from urllib.parse import quote

import httpx

from pema.video.thong_tin_video import CO_MAC_DINH, KetQuaNguon, KetQuaNguonLoi, KetQuaNguonOk, ThongTinVideo

API = "https://www.tikwm.com/api/"

TRAN_MS = 20_000
"""Time ceiling of one call.

Measured 1.04 seconds, so 20 seconds is generous. There is a ceiling because a request does not give up by
itself: a hung service without a timeout makes this call hold one slot of the parallel queue (only 2 slots)
until the agent turn ends."""


def _so_hoac_null(v: Any) -> float | None:
    """A positive finite number, or ``None``. A numeric string is accepted (``Number(v)``)."""
    if isinstance(v, bool):
        return None
    n: Any = v
    if isinstance(v, str):
        try:
            n = float(v)
        except ValueError:
            return None
    if isinstance(n, int | float) and math.isfinite(n) and n > 0:
        return n
    return None


def _chuoi_hoac_null(v: Any) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() != "" else None


def _math_round(x: float) -> int:
    """JS ``Math.round`` (half rounds UP), not Python's banker's rounding."""
    return math.floor(x + 0.5)


def _encode_uri_component(s: str) -> str:
    return quote(s, safe="!*'()")


async def lay_video_tu_tikwm(url: str, *, transport: httpx.AsyncBaseTransport | None = None) -> KetQuaNguon:
    json_body: Any
    try:
        async with httpx.AsyncClient(transport=transport, timeout=TRAN_MS / 1000) as client:
            res = await client.get(
                f"{API}?url={_encode_uri_component(url)}", headers={"accept": "application/json"}
            )
            if not res.is_success:
                # 5xx is on their side, retrying makes sense. 4xx is us sending wrong, retrying is useless.
                return KetQuaNguonLoi(
                    loi=f"TikWM trả HTTP {res.status_code}", thu_lai_duoc=res.status_code >= 500
                )
            json_body = res.json()
    except Exception as e:
        return KetQuaNguonLoi(loi=f"Không gọi được TikWM: {e}", thu_lai_duoc=True)

    if not isinstance(json_body, dict):
        return KetQuaNguonLoi(loi="TikWM trả dữ liệu không đọc được", thu_lai_duoc=True)
    goc = cast("dict[str, Any]", json_body)

    code = goc.get("code")
    if isinstance(code, bool) or code != 0:
        msg = _chuoi_hoac_null(goc.get("msg")) or "không rõ lý do"
        # "Free Api Limit: 1 request/second": measured when calling back-to-back without a pause. This is a
        # RETRYABLE case, quite unlike "wrong url" which gives the same result however long you retry.
        cham_toc = "limit" in msg.lower()
        return KetQuaNguonLoi(loi=f"TikWM từ chối: {msg}", thu_lai_duoc=cham_toc)

    raw_data = goc.get("data")
    d = cast("dict[str, Any]", raw_data) if isinstance(raw_data, dict) else {}

    # ``play`` is the version WITHOUT watermark, ``wmplay`` the one WITH. Checked by eye on the frames at
    # second 5 and second 20 of the same video: ``wmplay`` has the TikTok logo + @username and the logo MOVES
    # over time, ``play`` is clean. The two files differ by 833,225 bytes. Taking the wrong field breaks
    # exactly what the user needs.
    video_url = _chuoi_hoac_null(d.get("play"))
    if not video_url:
        return KetQuaNguonLoi(loi="TikWM không trả đường dẫn video", thu_lai_duoc=True)

    giay = _so_hoac_null(d.get("duration"))
    kich_thuoc = _so_hoac_null(d.get("size"))
    author = d.get("author")
    unique_id = (
        _chuoi_hoac_null(cast("dict[str, Any]", author).get("unique_id"))
        if isinstance(author, dict)
        else None
    )

    return KetQuaNguonOk(
        video=ThongTinVideo(
            video_url=video_url,
            # ``cover`` missing -> ``origin_cover``; still missing -> empty and the layer above decides:
            # ``sendVideo`` demands this field but an empty string beats throwing the whole turn away over a
            # missing cover image.
            thumbnail_url=_chuoi_hoac_null(d.get("cover")) or _chuoi_hoac_null(d.get("origin_cover")) or "",
            # TikWM returns SECONDS, ``sendVideo`` needs MILLISECONDS.
            duration_ms=0 if giay is None else _math_round(giay * 1000),
            # TikWM returns no frame size. Measured: their video is 576x1024, exactly the portrait default.
            width=CO_MAC_DINH["width"],
            height=CO_MAC_DINH["height"],
            file_size=None if kich_thuoc is None else _math_round(kich_thuoc),
            # Cut right at the source: see the comment in the same place of ``nguon_yt_dlp``.
            tac_gia=None if unique_id is None else unique_id[:64],
            nguon="tikwm",
            nen_tang="tiktok",
        )
    )

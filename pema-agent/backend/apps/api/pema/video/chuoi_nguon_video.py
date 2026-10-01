# ported from: src/video/chuoi-nguon-video.ts
"""Source chain: try the main source, if it fails fall to the fallback source.

ORDER and REASON (measured 2026-08-22, same IP, same time window):

    TikTok:    TikWM (12/12, 1.0s) -> yt-dlp (3/7, 3.9s)
    Facebook:  yt-dlp (5/5)         -> end, TikWM does not accept Facebook

The two TikTok sources are TRULY INDEPENDENT: one calls a third-party API, the other scrapes the page
itself. If TikWM goes down yt-dlp still runs and vice versa. A fallback chain whose two tiers rely on the same
mechanism is not a fallback.

Facebook has only ONE tier: that is a known limit, not an omission. Measured 5/5 so acceptable.

Forced deviations: ``Promise`` becomes ``async``; the injectable ``doi`` (sleep) and ``chuoi`` (chain) options
are kept as optional fields of ``TuyChonChuoi``; the TypeScript union ``KetQuaChuoi`` becomes two dataclasses
with a ``Literal`` ``ok``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from pema.video.nguon_tikwm import lay_video_tu_tikwm
from pema.video.nguon_yt_dlp import lay_video_tu_yt_dlp
from pema.video.thong_tin_video import KetQuaNguon, KetQuaNguonOk, TenNguonVideo, ThongTinVideo
from pema.video.whitelist_nguon_video import NenTangVideo


@dataclass(frozen=True)
class MatXich:
    """One link of the chain: a name for the log, and the function to call."""

    ten: TenNguonVideo
    chay: Callable[[str], Awaitable[KetQuaNguon]]


def chuoi_nguon_cho(nen_tang: NenTangVideo) -> list[MatXich]:
    if nen_tang == "tiktok":
        return [
            MatXich("tikwm", lambda u: lay_video_tu_tikwm(u)),
            MatXich("yt-dlp", lambda u: lay_video_tu_yt_dlp(u, "tiktok")),
        ]
    # Facebook AND Instagram: only yt-dlp (TikWM accepts neither: measured ``Url parsing is failed``). Pass
    # ``nen_tang`` STRAIGHT down, not the constant "facebook" like the old version: that constant made
    # Instagram videos get their frame read with Facebook's default.
    return [MatXich("yt-dlp", lambda u: lay_video_tu_yt_dlp(u, nen_tang))]


@dataclass(frozen=True)
class TuyChonChuoi:
    so_lan_thu: int
    """Number of tries PER link. Measured: 4 tries -> 5/6 sessions succeed with yt-dlp."""
    nghi_ms: int
    """Pause between two tries, milliseconds.

    TikWM limits **1 request/second** (measured, they say so straight in the error:
    ``Free Api Limit: 1 request/second``). The pause must be >= 1000ms, otherwise the retry runs into the
    limit itself and we think the source is broken."""
    doi: Callable[[int], Awaitable[None]] | None = None
    """Only for tests to inject a fake clock: production uses the default."""
    chuoi: list[MatXich] | None = field(default=None)
    """The chain of links. Leave empty to take it by platform.

    Injectable from outside because otherwise the test of the fall-through rule has to MAKE REAL NETWORK
    CALLS (TikWM) and RUN A REAL CHILD PROCESS (yt-dlp): such a test is both slow and flaky with the network,
    and does not even measure what needs measuring. The alternative is copying the algorithm into the test,
    but a copy never goes red when the real one is wrong."""


async def _nghi_mac_dinh(ms: int) -> None:
    await asyncio.sleep(ms / 1000)


@dataclass(frozen=True)
class DaThu:
    nguon: TenNguonVideo
    loi: str


@dataclass(frozen=True)
class KetQuaChuoiOk:
    video: ThongTinVideo
    ok: Literal[True] = True


@dataclass(frozen=True)
class KetQuaChuoiLoi:
    loi_cho_log: str
    """Joined errors of every link, ONLY FOR THE LOG.

    The ``ChoLog`` suffix is deliberate: it joins yt-dlp's stderr with TikWM's error body, i.e. text produced
    by a THIRD PARTY. That text must not flow into the sentence the tool returns to the model: the model
    often copies it verbatim to the person who messaged. The tool reads the ``loi_cau_hinh`` flag to choose
    the sentence, not this string."""
    da_thu: list[DaThu]
    loi_cau_hinh: bool
    """Did ANY link fail because the server lacks configuration.

    Merged with OR rather than taking the last link's: the TikTok chain is TikWM -> yt-dlp, so the case
    "TikWM down + machine without yt-dlp" has the last link carrying the flag, but the opposite case must
    also be caught. A single link reporting a config error is enough for the operator to have work to do."""
    can_dang_nhap: bool
    """Did any link report content that demands login: see ``KetQuaNguonLoi.can_dang_nhap``."""
    tam_thoi: bool
    """Did any link fail in a RETRYABLE way (``KetQuaNguonLoi.thu_lai_duoc``).

    On when at least one try returned a temporary error: typically TikTok returning the anti-bot page
    (yt-dlp "Unable to extract"), or a source returning 5xx. Quite unlike a PERMANENT error (private /
    deleted / wrong url) which gives the same result however long you retry.

    The tool reads this flag to give the RIGHT advice: the temporary case "retrying in a few minutes usually
    works", the permanent case "do not promise a retry". Merging the two leads the user around in circles
    (change the link, retry in vain, or give up unjustly when it only needed waiting for the source to stop
    blocking)."""
    ok: Literal[False] = False


KetQuaChuoi = KetQuaChuoiOk | KetQuaChuoiLoi


async def lay_video_qua_chuoi(url: str, nen_tang: NenTangVideo, tuy_chon: TuyChonChuoi) -> KetQuaChuoi:
    """Run the whole chain until there is a result.

    Fall-through rule: an error with ``thu_lai_duoc=False`` (wrong URL, private video, deleted video) SKIPS
    that link's retry part and goes to the next link at once: retrying a permanent error only wastes the time
    of the person waiting.
    """
    doi = tuy_chon.doi or _nghi_mac_dinh
    da_thu: list[DaThu] = []

    loi_cau_hinh = False
    can_dang_nhap = False
    tam_thoi = False

    for mat in tuy_chon.chuoi if tuy_chon.chuoi is not None else chuoi_nguon_cho(nen_tang):
        loi_cuoi = "không rõ"
        for lan in range(1, max(1, tuy_chon.so_lan_thu) + 1):
            ket = await mat.chay(url)
            if isinstance(ket, KetQuaNguonOk):
                return KetQuaChuoiOk(video=ket.video)

            loi_cuoi = ket.loi
            if ket.loi_cau_hinh:
                loi_cau_hinh = True
            if ket.can_dang_nhap:
                can_dang_nhap = True
            if ket.thu_lai_duoc:
                tam_thoi = True
            if not ket.thu_lai_duoc:
                break
            # No pause after the LAST try: pausing and then leaving wastes the time of the person waiting,
            # and it occupies a slot in the parallel queue.
            if lan < tuy_chon.so_lan_thu:
                await doi(tuy_chon.nghi_ms)
        da_thu.append(DaThu(nguon=mat.ten, loi=loi_cuoi))

    return KetQuaChuoiLoi(
        loi_cho_log=" | ".join(f"{t.nguon}: {t.loi}" for t in da_thu),
        da_thu=da_thu,
        loi_cau_hinh=loi_cau_hinh,
        can_dang_nhap=can_dang_nhap,
        tam_thoi=tam_thoi,
    )

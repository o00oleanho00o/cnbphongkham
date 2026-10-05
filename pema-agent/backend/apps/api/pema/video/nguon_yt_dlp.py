# ported from: src/video/nguon-yt-dlp.ts
"""yt-dlp source: FALLBACK for TikTok, ONLY source for Facebook.

Only runs ``--dump-single-json --skip-download``: reads metadata, does NOT download the video. Measured:
3.94 seconds, 72.8 MB peak RAM, 1.44 seconds CPU. RAM barely changes with a real download (75.6 MB) because
yt-dlp writes straight to disk, so ~73 MB is Python itself, and that cost is FIXED per process, not by video
size. That is why the parallel ceiling is set at 2.

WHY NOT A JS (here: Python) LIBRARY: yt-dlp is a child process, it exits fully when done and returns its RAM.
No server to keep alive, no port to open.

UPDATING: ``pip install -U yt-dlp`` is enough, NO code change. Reading the official 2025-2026 Changelog: every
breaking change is about minimum Python/Node versions, the ``--exec`` syntax, aria2c, ``--netrc-cmd``, NONE
touches the JSON schema of ``--dump-single-json``. The fields used here are the core inherited from
youtube-dl, stable for many years.

Forced deviation: ``JSON.parse`` is ``json.loads`` (rejecting ``NaN``/``Infinity`` like JS does); JS
``Math.round`` (half rounds up) is ``_math_round``; TypeScript object types are dataclasses/dicts.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any, cast

from pema.video import chay_yt_dlp as chay
from pema.video.chon_format_video import args_chon_format
from pema.video.thong_tin_video import (
    CO_MAC_DINH,
    CO_MAC_DINH_NGANG,
    KetQuaNguon,
    KetQuaNguonLoi,
    KetQuaNguonOk,
    ThongTinVideo,
)
from pema.video.whitelist_nguon_video import NenTangVideo

TRAN_MS = 45_000
"""Time ceiling. Measured 3.94 seconds; set to 45 seconds because Facebook sometimes goes through several
redirect hops. Exceeding it KILLS the process: letting it hang makes it hold one of the two parallel slots."""

_InfoDict = dict[str, Any]


def _math_round(x: float) -> int:
    """JS ``Math.round`` (half rounds UP), not Python's banker's rounding."""
    return math.floor(x + 0.5)


def _so(v: Any) -> int | float | None:
    if isinstance(v, bool):
        return None
    return v if isinstance(v, int | float) and math.isfinite(v) and v > 0 else None


def _chu(v: Any) -> str | None:
    return v.strip() if isinstance(v, str) and v.strip() != "" else None


LOI_CAN_DANG_NHAP = (
    "Nội dung này bắt đăng nhập mới xem được (story Facebook, bài trong nhóm/tài khoản kín, hoặc nội "
    "dung Instagram hạn chế) nên bot không tải được - bot không có tài khoản mạng xã hội để xem. Nói "
    "rõ với người dùng là loại link này không tải được, và gợi ý họ gửi link bài đăng hoặc reel công "
    "khai thay thế. Đừng bảo họ thử lại."
)
"""Sentence for the case CONTENT DEMANDS LOGIN (Facebook Stories, closed-group posts).

MEASURED on a user's story, a control run with the same tool and conditions:

    share/v/  -> generic -> redirect to /reel/... -> facebook:reel -> DOWNLOADABLE
    /stories/ -> generic -> redirect to login.php -> dead end

Facebook's own server returns ``302 -> login.php?next=<original url>``. The user can open it because THEIR
BROWSER sends a session cookie: the right to view lives in the cookie, not in the URL. The bot's server has
no Facebook session.

A second, independent block: sweeping all 1751 yt-dlp extractors, the URL ``/stories/<id>/<code>/`` matches
NONE, so it must fall to ``generic``. (``story.php``/``story_fbid`` in the Facebook pattern is the old-style
POST, not the 24-hour Stories: same name, two completely different things.)

So this is NOT an error fixable on our side. What can be fixed is telling the TRUE disease: the old version
returned "the video may be private or deleted" which made users retry in vain."""

CANH_DAI_CHUAN = 1280
"""Long side after normalisation: see ``chuan_hoa_theo_ti_le``."""


def chuan_hoa_theo_ti_le(co: dict[str, int | float]) -> dict[str, int | float]:
    """Keep the RATIO, bring the long side to ``CANH_DAI_CHUAN``.

    Used when only the ratio is known and not the real resolution of the stream about to be sent. Made even
    because odd sizes are something video decoders dislike.
    """
    dai = max(co["width"], co["height"])
    if dai <= CANH_DAI_CHUAN:
        return co
    ty = CANH_DAI_CHUAN / dai

    def chan(n: int | float) -> int:
        return max(2, _math_round((n * ty) / 2) * 2)

    return {"width": chan(co["width"]), "height": chan(co["height"])}


def khung_hinh(d: _InfoDict, nen_tang: NenTangVideo) -> dict[str, int]:
    """The REAL frame size of the video. This is where the Zalo app on phones was crashed.

    A FAILURE THAT REALLY HAPPENED (a 1280x720 LANDSCAPE Facebook video): yt-dlp chose format ``hd``, and that
    format carries NO ``width``/``height``: both at the top level and inside it they are ``null``. The old
    version read nothing and fell straight back to the PORTRAIT default 576x1024. Zalo was told "portrait
    video" and received a landscape frame: a desktop can stretch it so it was watchable, while the phone app
    builds the play surface from the declared numbers and CRASHED. The user saw a black card, portrait frame.

    The real size IS in the JSON, just in the ``formats`` array (the DASH streams all say 1280x720): the old
    version simply did not read that far. Confirmed with ffprobe on the very stream that was sent:
    1280x720, h264.

    Order: top level (TikTok has it, measured 1080x1920) -> biggest format in ``formats`` -> default BY
    PLATFORM. Guessing the frame is dangerous, so guess only when there is really nothing left to read.
    """
    w = _so(d.get("width"))
    h = _so(d.get("height"))
    if w is not None and h is not None:
        return {"width": _math_round(w), "height": _math_round(h)}

    # Every format of the same video has the same RATIO but a different RESOLUTION, and the format that gets
    # sent (Facebook's ``hd``) is the one that does NOT declare a size. So only the RATIO can be had, not the
    # real resolution.
    #
    # MEASURED on a user's video: the formats array reaches 2560x1440 while ffprobe on the very stream that
    # was sent gives 1280x720. Declaring 2560x1440 keeps the ratio right (16:9) so the picture is not
    # distorted, but it is still a false declaration, and a false size declaration is what just crashed the
    # Zalo phone app.
    #
    # Keep the RATIO, normalise the long side to 1280: what Zalo needs to build the frame is the ratio, and
    # better to state a common size with the right ratio than a specific one we have no way to know. For this
    # video it comes out exactly 1280x720.
    raw_formats = d.get("formats")
    fs = cast("list[object]", raw_formats) if isinstance(raw_formats, list) else []
    tot: dict[str, int | float] | None = None
    for f in fs:
        if not isinstance(f, dict):
            continue
        fmt = cast("dict[str, Any]", f)
        fw = _so(fmt.get("width"))
        fh = _so(fmt.get("height"))
        if fw is None or fh is None:
            continue
        if tot is None or fw * fh > tot["width"] * tot["height"]:
            tot = {"width": fw, "height": fh}
    if tot is not None:
        norm = chuan_hoa_theo_ti_le(tot)
        return {"width": _math_round(norm["width"]), "height": _math_round(norm["height"])}

    # Nothing left to read. Default BY PLATFORM instead of one shared constant: TikTok and Instagram (reels)
    # are almost always portrait, Facebook is mostly landscape (and zca-js ``sendVideo`` also defaults to
    # 1280x720 when nothing is passed). The send layer re-reads the frame from the buffer itself
    # (``doc_khung_hinh_mp4``) anyway, so this number is only a safety net for when reading the file fails.
    return dict(CO_MAC_DINH_NGANG) if nen_tang == "facebook" else dict(CO_MAC_DINH)


def cat_ten(v: str | None) -> str | None:
    """Cut the author name to a sane length: see the comment at the call site."""
    return None if v is None else v[:64]


def phan_loai_loi_yt_dlp(loi: str, loi_cau_hinh: bool) -> KetQuaNguon:
    """Classify a yt-dlp error into a typed result. PURE, testable.

    Three very different kinds, and saying the wrong kind makes the user do the wrong thing:

    * NEEDS LOGIN (story, closed group): can never be downloaded. Saying "retry later" lets them retry in
      vain. Recognised by yt-dlp's own error string, which contains the final URL it was led to
      (``login.php?next=...``).
    * MISSING TOOL: the disease is on the server, the operator must fix it.
    * The rest: about the video or the source. Only this group has retry-worthy cases.
    """
    if re.search(r"login\.php|checkpoint/|/login/\?next=", loi, re.IGNORECASE):
        return KetQuaNguonLoi(loi=LOI_CAN_DANG_NHAP, thu_lai_duoc=False, can_dang_nhap=True)
    if loi_cau_hinh:
        return KetQuaNguonLoi(loi=loi, thu_lai_duoc=False, loi_cau_hinh=True)

    # "Unable to extract" / "Unexpected response" is TikTok returning a challenge page: an intermittent case,
    # retrying makes sense (measured: 4 tries -> 5/6 sessions succeed). "Video unavailable" / "Private" gives
    # the same result however long you retry.
    #
    # Instagram returns "empty media response" (measured 2026-08) for EVERY case it cannot fetch:
    # rate-limit, private video, deleted: yt-dlp does NOT tell them apart. Put in the retryable group: the
    # most common case (rate-limit) passes after a few minutes, and the tool sentence says "try again later"
    # instead of making the user give up unjustly. A truly private video gets retried once and then dropped;
    # in exchange the common case is not misreported.
    #
    # A process timeout comes out as "đã dừng" and NOT "timed out": when the process is killed the error
    # message only says "Command failed", with no word to catch by regex (measured).
    chap_chon = (
        re.search(
            r"unable to extract|unexpected response|challenge|đã dừng|HTTP Error 5"
            r"|empty media response|rate.?limit",
            loi,
            re.IGNORECASE,
        )
        is not None
    )
    return KetQuaNguonLoi(loi=loi, thu_lai_duoc=chap_chon)


def doi_so_metadata_yt_dlp(url: str) -> list[str]:
    """Arguments for reading metadata. Split PURE so a test can watch the SHARED format selector
    (``args_chon_format``) being the same as on the download path (``doi_so_tai_yt_dlp``): two separate
    yt-dlp calls, and if the selectors drift it declares the size of one format but sends the bytes of
    another."""
    return [
        "--dump-single-json",
        "--skip-download",
        "--no-warnings",
        "--no-playlist",
        *args_chon_format(),
        url,
    ]


async def lay_video_tu_yt_dlp(url: str, nen_tang: NenTangVideo) -> KetQuaNguon:
    # The hardening flags (``--ignore-config``, ``--no-plugin-dirs``) live in ``chay_yt_dlp`` so every yt-dlp
    # run gets them: see the comment block at the top of ``chay_yt_dlp``.
    ket = await chay.chay_yt_dlp(doi_so_metadata_yt_dlp(url), TRAN_MS)

    if not ket.ok:
        return phan_loai_loi_yt_dlp(ket.loi, ket.loi_cau_hinh is True)

    return doc_stdout_yt_dlp(ket.stdout, nen_tang)


def _khong_nan(ten: str) -> Any:
    raise ValueError(ten)


def doc_stdout_yt_dlp(stdout: str, nen_tang: NenTangVideo) -> KetQuaNguon:
    """Read yt-dlp's JSON into a ``KetQuaNguon``. PURE, never touches the child process.

    Split from ``lay_video_tu_yt_dlp`` so it can be tested: every SILENT MISREAD lives here (seconds vs
    milliseconds, cover image, Facebook not returning a frame size), and checking them through the other
    function means running the real yt-dlp, i.e. needing a network, a binary and a real video still alive.
    A test like that goes red for reasons unrelated to what it checks.
    """
    try:
        parsed: Any = json.loads(stdout, parse_constant=_khong_nan)
    except ValueError:
        return KetQuaNguonLoi(loi="yt-dlp trả JSON không đọc được", thu_lai_duoc=True)
    d: _InfoDict = cast("_InfoDict", parsed) if isinstance(parsed, dict) else {}

    video_url = _chu(d.get("url"))
    if not video_url:
        # No flat ``url`` means the chosen format must merge sound + picture: that case must download and
        # remux, and remuxing is exactly what we avoid (ffmpeg parsing a stranger's content). Return a
        # failure so the chain falls to another source.
        return KetQuaNguonLoi(
            loi="Video này không có luồng phát sẵn (phải ghép hình và tiếng)", thu_lai_duoc=False
        )

    giay = _so(d.get("duration"))

    # ``thumbnail`` missing -> take the last image in ``thumbnails`` (yt-dlp orders small to large).
    # MEASURED: Facebook returns NEITHER: ``thumbnail: null`` and ``thumbnails: null``. So this path only
    # rescues other platforms; Facebook still yields an empty string, and the tool layer logs a warning
    # for that case.
    raw_anh = d.get("thumbnails")
    ds_anh = cast("list[object]", raw_anh) if isinstance(raw_anh, list) else []
    anh_cuoi: str | None = None
    if ds_anh:
        cuoi = ds_anh[-1]
        anh_cuoi = _chu(cast("dict[str, Any]", cuoi).get("url")) if isinstance(cuoi, dict) else None

    kich_thuoc = _so(d.get("filesize")) or _so(d.get("filesize_approx"))
    frame = khung_hinh(d, nen_tang)
    return KetQuaNguonOk(
        video=ThongTinVideo(
            video_url=video_url,
            thumbnail_url=_chu(d.get("thumbnail")) or anh_cuoi or "",
            duration_ms=0 if giay is None else _math_round(giay * 1000),
            width=frame["width"],
            height=frame["height"],
            file_size=None if kich_thuoc is None else _math_round(kich_thuoc),
            # Cut right at the source: this is the poster's free string, and a source declaring a 200,000
            # character name was measured, which the old version swallowed in full: burning tokens, bloating
            # the log, bloating the DB. 64 characters is plenty for a real account name.
            tac_gia=cat_ten(_chu(d.get("uploader_id")) or _chu(d.get("uploader")) or _chu(d.get("channel"))),
            nguon="yt-dlp",
            nen_tang=nen_tang,
        )
    )

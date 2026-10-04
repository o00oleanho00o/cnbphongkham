# ported from: src/video/chon-format-video.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The format selector lives INSIDE yt-dlp, not in our code. A pure function that copies the selection algorithm
would NEVER go red when yt-dlp changes behaviour: exactly how the ``^=avc`` bug slipped through, it "looked
right" but matched empty because yt-dlp relabelled h264.

So these tests run the REAL yt-dlp, but OFFLINE and DETERMINISTIC: ``--load-info-json`` loads a hand-built
list of formats and applies ``-f``/``-S`` to it. It touches NO network and hits NO TikTok anti-bot page (the
thing that makes real network calls flaky). A machine without yt-dlp skips every behaviour case (like a
minimal CI environment), exactly as the original does. The fixture is hand-built minimally but its fields
come from a real capture.
"""

from __future__ import annotations

import itertools
import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from pema.video import chon_format_video as chon
from pema.video.chay_yt_dlp import chay_yt_dlp

_dem = itertools.count()
_SpecFormat = dict[str, Any]
"""``{format_id, vcodec, acodec?, width?, height?, note?}``.

``vcodec: "progressive"`` = muxed mp4 but yt-dlp can NOT parse the codec (the exact shape of an Instagram
progressive format, ``video_versions``). ``acodec: "none"`` = a picture-only stream (DASH video-only). These
two are for the Instagram case."""


def _dung_format(f: _SpecFormat) -> dict[str, Any]:
    """Build a minimal format enough for yt-dlp to sort; the URL is a dummy (offline, no download)."""
    dims: dict[str, Any] = {}
    if f.get("width"):
        dims["width"] = f["width"]
    if f.get("height"):
        dims["height"] = f["height"]
    # Progressive: the mp4 carries no vcodec/acodec fields, yet yt-dlp still treats it as pre-muxed.
    if f["vcodec"] == "progressive":
        return {
            "format_id": f["format_id"],
            "ext": "mp4",
            **dims,
            "url": f"https://example.invalid/{f['format_id']}.mp4",
            "protocol": "https",
        }
    chi_tieng_noi = f["vcodec"] == "none"
    ext = "mp3" if chi_tieng_noi else "mp4"
    return {
        "format_id": f["format_id"],
        "vcodec": f["vcodec"],
        "acodec": f.get("acodec") or ("mp3" if chi_tieng_noi else "aac"),
        "ext": ext,
        **dims,
        **({"format_note": f["note"]} if f.get("note") else {}),
        "url": f"https://example.invalid/{f['format_id']}.{ext}",
        "protocol": "https",
    }


def _dung_info_json(formats: list[_SpecFormat]) -> str:
    return json.dumps(
        {
            "id": "7",
            "title": "video test co dau tieng viet",
            "ext": "mp4",
            "extractor": "TikTok",
            "extractor_key": "TikTok",
            "webpage_url": "https://www.tiktok.com/@x/video/7",
            "_type": "video",
            "formats": [_dung_format(f) for f in formats],
        }
    )


_ChonTren = Callable[[list[_SpecFormat], list[str]], Awaitable[tuple[str, str] | None]]


@pytest.fixture
async def chon_tren(tmp_path: Path) -> _ChonTren:
    """Let yt-dlp apply the selector ``args_sel`` on the format list (offline), return the format it CHOSE
    as ``(id, vcodec)``, ``None`` when nothing is chosen. Skips the test when yt-dlp is not installed."""
    if not (await chay_yt_dlp(["--version"], 15_000)).ok:
        pytest.skip("yt-dlp chưa cài trên máy test")

    async def _chon(formats: list[_SpecFormat], args_sel: list[str]) -> tuple[str, str] | None:
        duong = tmp_path / f"fx-{next(_dem)}.json"
        duong.write_text(_dung_info_json(formats), encoding="utf-8")
        r = await chay_yt_dlp(
            [
                "--load-info-json",
                str(duong),
                "--skip-download",
                "--no-warnings",
                *args_sel,
                "--print",
                "%(format_id)s|%(vcodec)s",
            ],
            30_000,
        )
        if not r.ok:
            return None
        dong = [s.strip() for s in r.stdout.split("\n") if "|" in s.strip()]
        if not dong:
            return None
        id_, _, vcodec = dong[-1].partition("|")
        return (id_, vcodec) if id_ else None

    return _chon


# Main fixture: has h264 540p AND h265 1080p. The h265 with HIGHER resolution is deliberate: a selector that
# does not know codec priority would wrongly take h265 (the yt-dlp default prefers resolution). Picking h264
# only happens when ``-S vcodec:h264`` really has an effect.
TIKTOK: list[_SpecFormat] = [
    {"format_id": "audio", "vcodec": "none"},
    {"format_id": "download", "vcodec": "h264", "note": "watermarked"},
    {"format_id": "h264_540p", "vcodec": "h264", "width": 768, "height": 576},
    {"format_id": "bytevc1_1080p", "vcodec": "h265", "width": 1440, "height": 1080},
]


# ------------------------------------------------------------------ yt-dlp chọn đúng codec (offline)


async def test_chon_format_video_uu_tien_h264_du_h265_nhan_cao_hon_va_khong_lay_watermark(
    chon_tren: _ChonTren,
) -> None:
    """ưu tiên h264 dù h265 phân giải cao hơn, và KHÔNG lấy bản watermark"""
    ch = await chon_tren(TIKTOK, chon.args_chon_format())
    assert ch is not None, "yt-dlp phải chọn được một format"
    assert ch[1] == "h264", "phải là h264 cho máy cũ, không phải h265"
    assert ch[0] != "bytevc1_1080p", "không được chọn h265 dù nó nét hơn"
    assert ch[0] != "download", "không được chọn bản đóng logo"


async def test_chon_format_video_bo_chon_cu_avc_lay_nham_h265_canh_de_khong_quay_lai(
    chon_tren: _ChonTren,
) -> None:
    """bộ chọn CŨ `^=avc` lấy nhầm h265 - đây là bug đang sửa, canh để không quay lại"""
    # Records explicitly why we moved to ``-S``: on the same format list the old selector matched empty
    # (yt-dlp reports ``vcodec="h264"`` not ``"avc1"``) then fell back to h265. If this goes red someone
    # brought ``^=avc`` back, OR yt-dlp relabelled again: both need the decision re-read.
    ch = await chon_tren(TIKTOK, ["-f", "b[vcodec^=avc][ext=mp4]/b[ext=mp4]/b"])
    assert ch is not None
    assert ch[1] == "h265", "bộ chọn cũ khớp rỗng rồi lấy h265 - chính là bug"


async def test_chon_format_video_nguon_khai_codec_avc1_van_chon_duoc_lay_net_cao_nhat(
    chon_tren: _ChonTren,
) -> None:
    """nguồn khai codec kiểu `avc1.*` (Facebook / nguồn cũ) vẫn chọn được, lấy nét cao nhất"""
    ch = await chon_tren(
        [
            {"format_id": "audio", "vcodec": "none"},
            {"format_id": "sd", "vcodec": "avc1.4d401f", "width": 640, "height": 360},
            {"format_id": "hd", "vcodec": "avc1.640028", "width": 1280, "height": 720},
        ],
        chon.args_chon_format(),
    )
    assert ch is not None
    assert ch[1].startswith("avc1"), "`-S vcodec:h264` phải nhận avc1 là h264"
    assert ch[0] == "hd", "cùng codec thì lấy phân giải cao nhất"


async def test_chon_format_video_chi_co_h265_van_lay_h265_lui_mem(chon_tren: _ChonTren) -> None:
    """chỉ có h265 thì vẫn lấy h265 (lùi mềm, không rỗng, không lỗi)"""
    ch = await chon_tren(
        [
            {"format_id": "audio", "vcodec": "none"},
            {"format_id": "h265_540p", "vcodec": "h265", "width": 768, "height": 576},
            {"format_id": "h265_1080p", "vcodec": "h265", "width": 1440, "height": 1080},
        ],
        chon.args_chon_format(),
    )
    assert ch is not None
    assert ch[1] == "h265", "không có h264 thì h265 còn hơn không gửi được"
    assert ch[0] == "h265_1080p"


async def test_chon_format_video_h264_duy_nhat_la_watermark_co_h265_sach_chon_h265_sach(
    chon_tren: _ChonTren,
) -> None:
    """bản h264 duy nhất là watermark + có h265 sạch -> chọn h265 sạch"""
    ch = await chon_tren(
        [
            {"format_id": "audio", "vcodec": "none"},
            {"format_id": "download", "vcodec": "h264", "note": "watermarked"},
            {"format_id": "bytevc1_1080p", "vcodec": "h265", "width": 1440, "height": 1080},
        ],
        chon.args_chon_format(),
    )
    assert ch is not None
    assert ch[0] == "bytevc1_1080p", "thà h265 sạch còn hơn h264 đóng logo"


async def test_chon_format_video_instagram_dash_chon_progressive_khong_chon_dash_video_only(
    chon_tren: _ChonTren,
) -> None:
    """Instagram DASH: chọn PROGRESSIVE muxed, KHÔNG chọn dash video-only (tránh video câm / cần ghép)"""
    # IG returns DASH (picture and sound separate) PLUS a pre-muxed progressive mp4. The design deliberately
    # does not install ffmpeg so a picture-only stream (silent or needing a merge) must NOT be chosen.
    # ``b``/best only takes a stream that has both picture and sound, so it must fall to progressive even
    # though the dash video-only has a higher resolution (720x1280). Measured: yt-dlp picks correctly.
    ch = await chon_tren(
        [
            {"format_id": "dash-audio", "vcodec": "none"},
            {"format_id": "prog", "vcodec": "progressive"},
            {
                "format_id": "dash-video",
                "vcodec": "avc1.64001F",
                "acodec": "none",
                "width": 720,
                "height": 1280,
            },
        ],
        chon.args_chon_format(),
    )
    assert ch is not None
    assert ch[0] == "prog", "phải chọn progressive muxed, KHÔNG chọn dash video-only 720x1280"


# ------------------------------------------------------------------ bất biến hằng số (không cần yt-dlp)
# A floor that does NOT need yt-dlp. The behaviour cases above skip themselves on a machine without
# yt-dlp, and then they no longer guard the selector, so a wrong constant could slip through a green suite.
# These pin three design invariants as plain strings, on EVERY machine.


def test_chon_format_video_bat_bien_hang_so_chon_sort_uu_tien_h264_cho_may_cu() -> None:
    """CHON_SORT ưu tiên h264 cho máy cũ"""
    assert "vcodec:h264" in chon.CHON_SORT, f"phải ưu tiên h264: {chon.CHON_SORT}"


def test_chon_format_video_bat_bien_hang_so_chon_format_loai_watermark_khong_ghep_uu_tien_mp4() -> None:
    """CHON_FORMAT loại bản watermark, không có nhánh ghép (cần ffmpeg), ưu tiên mp4"""
    assert "format_id!=download" in chon.CHON_FORMAT, "phải loại bản watermark `download`"
    assert "+" not in chon.CHON_FORMAT, "không được có nhánh ghép hình+tiếng - image không cài ffmpeg"
    assert "mp4" in chon.CHON_FORMAT, "phải ưu tiên mp4 để Zalo phát được"

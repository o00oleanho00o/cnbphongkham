# ported from: src/video/tai-video-vao-ram.ts
"""Get the video bytes into MEMORY, never touching the disk.

WHY THE BYTES ARE NEEDED: measured by a real send to the user's phone:

    videoUrl is a TikTok/Facebook URL -> a computer can watch it, THE PHONE CANNOT
    videoUrl is a Zalo URL            -> the phone plays it smoothly

Sweeping all 140 zca-js APIs: there is no way to hand Zalo a URL and have Zalo download and host it itself.
So for the phone to play it the bytes must pass through here.

WHY NO DISK WRITE: the user settled that bandwidth is not a worry, but constant download-delete cycles grind
the SSD and leave junk. zca-js ``uploadAttachment`` takes ``{ data: Buffer, filename, metadata }`` and does
not require a file path (every branch was checked, including where the checksum is computed). So the whole
path is network -> RAM -> Zalo, with no temp file to delete.

IN RETURN: peak RAM equals the size ceiling times the number of parallel runs. That is why the default size
ceiling must be modest.

Forced deviations: ``Buffer`` is ``bytes``; ``PhuThuocTai`` (the external touch points, replaceable ONLY for
tests) is a dataclass of two async callables defaulting to ``download_from_public_url`` and ``chay_yt_dlp``
(the Python names of ``downloadFromPublicUrl`` / ``chayYtDlp``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Literal

from pema.shared.safe_remote_download import DownloadOptions, RemoteFile, download_from_public_url
from pema.video.chay_yt_dlp import KetQuaChayYtDlp, TuyChonChay, chay_yt_dlp
from pema.video.chon_format_video import args_chon_format

TRAN_TAI_MS = 5 * 60_000
"""Time ceiling for the yt-dlp self-download run. Wider than the metadata read since this is a real download;
it still needs a ceiling, and past the deadline the process is killed."""


@dataclass(frozen=True)
class KetQuaTaiOk:
    byte: bytes
    duong: Literal["url", "yt-dlp"]
    ok: Literal[True] = True


@dataclass(frozen=True)
class KetQuaTaiLoi:
    loi: str
    loi_cau_hinh: bool = False
    ok: Literal[False] = False


KetQuaTai = KetQuaTaiOk | KetQuaTaiLoi


@dataclass(frozen=True)
class PhuThuocTai:
    """The places that touch the outside, replaceable from outside ONLY for tests."""

    tai_url: Callable[[str, DownloadOptions], Awaitable[RemoteFile]] = field(default=download_from_public_url)
    chay: Callable[[list[str], int, TuyChonChay], Awaitable[KetQuaChayYtDlp]] = field(default=chay_yt_dlp)


PHU_THUOC_THAT = PhuThuocTai()


async def tai_tu_url_vao_ram(url: str, tran_byte: int, phu_thuoc: PhuThuocTai = PHU_THUOC_THAT) -> KetQuaTai:
    """Download straight from the source's URL.

    Goes through ``download_from_public_url`` so it inherits the whole guard of the web-reading tool: blocks
    internal IPs, defeats DNS rebinding, re-checks EVERY redirect hop, and stops at once when over the
    ceiling instead of downloading everything first.
    """
    try:
        res = await phu_thuoc.tai_url(url, DownloadOptions(max_bytes=tran_byte))
    except Exception as err:
        return KetQuaTaiLoi(loi=str(err))
    if len(res.data) == 0:
        return KetQuaTaiLoi(loi="Tải về rỗng")
    return KetQuaTaiOk(byte=res.data, duong="url")


def doi_so_tai_yt_dlp(url_goc: str, tran_byte: int) -> list[str]:
    """Arguments for the yt-dlp SELF-DOWNLOAD run, receiving through stdout. Split PURE so it can be tested:
    these flags decide whether anything is written to disk (``-o -``) and which format is chosen
    (``args_chon_format``, shared with the metadata path), and both fail SILENTLY if written wrong.

    ``-o -`` writes straight to stdout so there is no temp file: checked: 4,549,777 bytes, a correct ``ftyp``
    mp4 header.
    """
    return [
        "--no-warnings",
        "--no-playlist",
        # Block BEFORE downloading when the source declares a size. A source that does not declare it makes
        # this flag moot: the real safety net is the buffer-length check in the caller.
        "--max-filesize",
        str(tran_byte),
        *args_chon_format(),
        "-o",
        "-",
        url_goc,
    ]


async def tai_bang_yt_dlp_vao_ram(
    url_goc: str, tran_byte: int, phu_thuoc: PhuThuocTai = PHU_THUOC_THAT
) -> KetQuaTai:
    """Let yt-dlp download by itself.

    Needed when the source's URL cannot be downloaded from our machine: measured, the TikTok URL yt-dlp
    returns is tied to its session and returns **403 right on the machine that just ran yt-dlp**. Downloading
    that URL ourselves fails; letting yt-dlp download it works.
    """
    ket = await phu_thuoc.chay(
        doi_so_tai_yt_dlp(url_goc, tran_byte),
        TRAN_TAI_MS,
        # The buffer ceiling must hold the whole video, plus a margin for what yt-dlp prints extra.
        TuyChonChay(nhi_phan=True, tran_stdout=tran_byte + 1024 * 1024),
    )

    if not ket.ok:
        return KetQuaTaiLoi(loi=ket.loi, loi_cau_hinh=ket.loi_cau_hinh)

    byte = ket.stdout_nhi_phan if ket.stdout_nhi_phan is not None else b""
    if len(byte) == 0:
        # Over ``--max-filesize`` on this path: yt-dlp exits with code 0 but outputs nothing.
        return KetQuaTaiLoi(loi="yt-dlp không tải được nội dung nào (có thể video vượt giới hạn)")
    if len(byte) > tran_byte:
        return KetQuaTaiLoi(loi="Video vượt giới hạn dung lượng")
    return KetQuaTaiOk(byte=byte, duong="yt-dlp")

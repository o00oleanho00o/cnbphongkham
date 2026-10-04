# ported from: src/video/gui-video-qua-zalo.ts
"""Send a video over Zalo. ONE single path, and every step has a measured reason.

    1. PROBE the source url (cheap, guarded)  -> alive or not, what kind, how heavy
    2. GET THE BYTES INTO RAM                 -> probe passed: download straight; probe failed: let yt-dlp
                                                 download itself through stdout
    3. READ THE FRAME SIZE from the buffer    -> do not trust the source metadata
    4. BUILD THE POSTER                       -> download the source cover then upload to Zalo
    5a. HAS poster -> upload the video to Zalo -> ``sendVideo`` (video card)
    5b. NO poster  -> send AS A FILE (no poster needed)

WHY IT MUST BE UPLOADED: measured by a real send to the user's phone, the same video differing only in where
it lives:

    videoUrl = TikTok/Facebook URL  -> a computer can watch it, THE PHONE CANNOT
    videoUrl = Zalo's URL           -> the phone plays it smoothly

Sweeping all 140 zca-js APIs: there is no way to hand Zalo a URL and have Zalo download and host it itself.
So for the phone to play it the bytes must pass through here. In return NO disk write: see
``tai_video_vao_ram``.

WHY READ THE FRAME SIZE FROM THE FILE: declaring a wrong frame CRASHED the Zalo app on phones (a real case).
TikWM returns no width/height at all; yt-dlp's chosen format carries none, and the ``formats`` array declares
double the real stream.

WHY THE POSTER MUST BE UPLOADED TO ZALO: an image URL on an outside host -> the video card is PITCH BLACK; an
empty ``thumbnailUrl`` -> Zalo REFUSES (code 114); ``parseLink`` -> returns a junk placeholder for Facebook.
Detail in ``chuan_bi_anh_bia_video``.

Forced deviations: the zca-js ``API`` object becomes the ``ZaloVideoApi`` Protocol below, listing EXACTLY the
three zca-js methods this module calls (the Zalo personal channel is a Node bridge behind ``ChannelPort``; the
tool layer wires an adapter). The data keys keep the zca-js camelCase names (``videoUrl``, ``thumbnailUrl``,
``attachments``...) because the adapter forwards them unchanged to the bridge. ``Buffer`` is ``bytes``. The
original ``setTimeout(...).unref()`` race becomes ``asyncio.wait_for``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from pema.shared.logger import create_logger
from pema.video.chuan_bi_anh_bia_video import DichAnhBia, ban_ghi_upload, chuan_bi_anh_bia_video
from pema.video.doc_khung_hinh_mp4 import doc_thong_tin_mp4
from pema.video.kiem_url_video_truoc_khi_gui import KetQuaDo, KetQuaDoOk, kiem_url_video_con_song
from pema.video.tai_video_vao_ram import KetQuaTai, KetQuaTaiLoi, tai_bang_yt_dlp_vao_ram, tai_tu_url_vao_ram
from pema.video.thong_tin_video import ThongTinVideo

log = create_logger("gui-video")

TRAN_UPLOAD_MS = 5 * 60_000
"""Time ceiling for the upload.

MANDATORY: ``uploadAttachment`` with a video registers a callback by ``fileId`` and is only resolved when the
completion event arrives through the WEBSOCKET (zca-js ``listen.ts``). With no listener, or a listener that
drops midway, the promise hangs FOREVER, and zca-js sets no timeout. Met for real while testing: the running
bot held the listener slot so the call hung until killed."""


class ZaloVideoApi(Protocol):
    """The zca-js ``API`` methods this module calls, and nothing else.

    * ``upload_attachment(items, thread_id, thread_type)``: ``uploadAttachment``. ``items`` is a list of
      ``{"data": bytes, "filename": str, "metadata": {"totalSize": int, ...}}``. Returns the upload records
      (a list, or a single record) carrying ``fileUrl`` / ``normalUrl`` / ``hdUrl``.
    * ``send_video(options, thread_id, thread_type)``: ``sendVideo`` with
      ``{"videoUrl", "thumbnailUrl", "duration", "width", "height"}``.
    * ``send_message(content, thread_id, thread_type)``: ``sendMessage`` with
      ``{"attachments": [{"data", "filename", "metadata"}]}`` (the send-as-a-file path).

    ``thread_type`` is the zca-js ``ThreadType`` number (0 user, 1 group). ``UploadAttachmentApi`` of
    ``chuan_bi_anh_bia_video`` is the subset, so an adapter implementing this satisfies both.
    """

    async def upload_attachment(
        self, items: list[dict[str, Any]], thread_id: str, thread_type: int
    ) -> Any: ...

    async def send_video(self, options: dict[str, Any], thread_id: str, thread_type: int) -> Any: ...

    async def send_message(self, content: dict[str, Any], thread_id: str, thread_type: int) -> Any: ...


@dataclass(frozen=True)
class DichGuiVideo:
    api: ZaloVideoApi
    thread_key: str
    """``<accountId>:<threadId>``: queue key that keeps message order within a thread."""
    thread_id: str
    thread_type: int


@dataclass(frozen=True)
class KetQuaGui:
    """``dang`` says whether a video card (with poster) or a file (no poster) was sent."""

    duong: Literal["url", "yt-dlp"]
    bytes: int
    dang: Literal["video", "file"]


@dataclass(frozen=True)
class PhuThuocGuiVideo:
    """The places that touch the outside, replaceable from outside ONLY for tests."""

    kiem_url: Callable[[str], Awaitable[KetQuaDo]] = field(default=kiem_url_video_con_song)
    tai_url: Callable[[str, int], Awaitable[KetQuaTai]] = field(default=tai_tu_url_vao_ram)
    tai_yt_dlp: Callable[[str, int], Awaitable[KetQuaTai]] = field(default=tai_bang_yt_dlp_vao_ram)
    chuan_bi_anh_bia: Callable[[DichAnhBia, str], Awaitable[str | None]] = field(
        default=chuan_bi_anh_bia_video
    )


PHU_THUOC_THAT = PhuThuocGuiVideo()


class LoiGuiVideo(Exception):  # noqa: N818 - name kept from the original (LoiGuiVideo)
    """Error of the send path, carrying a TYPED REASON.

    Without the type, at the tool boundary everything looks alike and gets swallowed into one generic
    sentence, losing two pieces of information people need: "the server lacks a tool" (the operator must fix
    it) and "the video is too heavy" with the NUMBER (the user can change the ceiling on the dashboard).
    """

    def __init__(
        self,
        message: str,
        *,
        loi_cau_hinh: bool = False,
        qua_nang: bool = False,
        so_byte: int | None = None,
    ) -> None:
        super().__init__(message)
        self.loi_cau_hinh = loi_cau_hinh is True
        self.qua_nang = qua_nang is True
        self.so_byte = so_byte


def ten_file(video: ThongTinVideo) -> str:
    """File name the recipient sees when sent as a file. FIXED extension, not taken from a stranger's URL."""
    goc = re.sub(r"[^a-zA-Z0-9._-]", "_", video.tac_gia or "video")[:40]
    return f"{goc or 'video'}.mp4"


async def voi_tran_upload[T](goi: Awaitable[T]) -> T:
    """Wrap a time ceiling around a zca-js video upload call.

    MANDATORY: ``uploadAttachment`` for a video registers a callback by ``fileId`` and is only resolved when
    the completion event arrives through the WEBSOCKET. Losing the listener makes the promise hang FOREVER
    (zca-js sets no timeout). Both ``sendVideo`` (upload then send) and ``sendMessage`` with a video
    attachment are hit, so both send paths are wrapped.
    """
    try:
        return await asyncio.wait_for(goi, timeout=TRAN_UPLOAD_MS / 1000)
    except TimeoutError:
        raise LoiGuiVideo(f"Gửi lên Zalo quá {TRAN_UPLOAD_MS}ms") from None


async def up_len_zalo(dich: DichGuiVideo, byte: bytes, ten: str) -> str:
    """Upload the video buffer to Zalo, returning the URL on their infrastructure."""
    goi = dich.api.upload_attachment(
        [{"data": byte, "filename": ten, "metadata": {"totalSize": len(byte)}}],
        dich.thread_id,
        dich.thread_type,
    )

    ket = await voi_tran_upload(goi)
    record = ban_ghi_upload(ket)
    url = ""
    if record is not None:
        url = record.get("fileUrl") or record.get("normalUrl") or record.get("hdUrl") or ""
    if not isinstance(url, str) or url == "":
        raise LoiGuiVideo("Zalo nhận file nhưng không trả về đường dẫn")
    return url


async def gui_dang_file(dich: DichGuiVideo, byte: bytes, ten: str) -> None:
    """Send the video AS A FILE: the fallback when a poster cannot be built.

    ``sendMessage`` with an ``.mp4`` attachment does NOT need a thumbnail (zca-js read: only GIF generates a
    thumb itself). It takes bytes directly so it still does NOT touch the disk. The user settled: better to
    send a file than a video card stuck with a cheap-looking placeholder.
    """
    goi = dich.api.send_message(
        {"attachments": [{"data": byte, "filename": ten, "metadata": {"totalSize": len(byte)}}]},
        dich.thread_id,
        dich.thread_type,
    )
    await voi_tran_upload(goi)


async def gui_video_qua_zalo(
    dich: DichGuiVideo,
    video: ThongTinVideo,
    url_goc: str,
    tran_byte: int,
    phu_thuoc: PhuThuocGuiVideo = PHU_THUOC_THAT,
) -> KetQuaGui:
    """Send the video. Raises ``LoiGuiVideo`` when it cannot be sent: the caller (the tool) catches it and
    returns an error result.

    ``url_goc`` is the link the USER sent (already through the whitelist), unlike ``video.video_url`` which is
    the CDN link returned by the source. yt-dlp self-download needs the former.
    """
    # 1. Probe: cheap, and tells where to take the bytes from
    ket_do = await phu_thuoc.kiem_url(video.video_url)
    if isinstance(ket_do, KetQuaDoOk) and ket_do.so_byte is not None and ket_do.so_byte > tran_byte:
        mb = _math_round(ket_do.so_byte / 1024 / 1024)
        raise LoiGuiVideo(f"Video {mb}MB, vượt giới hạn", qua_nang=True, so_byte=ket_do.so_byte)

    # 2. Bytes into RAM
    if isinstance(ket_do, KetQuaDoOk):
        tai = await phu_thuoc.tai_url(ket_do.url_cuoi, tran_byte)
    else:
        tai = await phu_thuoc.tai_yt_dlp(url_goc, tran_byte)

    if isinstance(tai, KetQuaTaiLoi):
        if not isinstance(ket_do, KetQuaDoOk):
            log.warning("URL nguồn không dùng được, yt-dlp cũng hỏng", ly=ket_do.ly, nguon=video.nguon)
        raise LoiGuiVideo(tai.loi, loi_cau_hinh=tai.loi_cau_hinh)
    if len(tai.byte) > tran_byte:
        raise LoiGuiVideo("Video vượt giới hạn dung lượng", qua_nang=True, so_byte=len(tai.byte))

    # 3. Frame size + duration read from the very buffer about to be sent: ONE walk of the mp4 box tree, do
    # not trust whatever the source declares.
    info = doc_thong_tin_mp4(tai.byte)
    khung = info.khung
    if khung is None:
        # Cannot read it so use the source's numbers. Logged since this is the road to exactly the error
        # class that crashed the user's phone.
        log.warning(
            "không đọc được khung hình từ file - dùng số của nguồn, có thể sai",
            nguon=video.nguon,
            nen_tang=video.nen_tang,
        )
    width = khung.width if khung is not None else video.width
    height = khung.height if khung is not None else video.height
    # Duration: TAKE THE SOURCE'S FIRST (TikTok/Facebook return it ready, reliable), the file only FILLS THE
    # GAP when the source has none (Instagram returns ``duration: null`` -> duration_ms = 0). Unlike the frame
    # size (the file ALWAYS wins since a wrong frame crashes); a wrong duration is only a wrong display label,
    # no crash, so there is no need to flip the source.
    duration_ms = video.duration_ms or info.thoi_luong_ms or 0

    # 4. Poster: download the source cover then upload to Zalo. ``None`` when it cannot be built.
    poster = await phu_thuoc.chuan_bi_anh_bia(
        DichAnhBia(api=dich.api, thread_id=dich.thread_id, thread_type=dich.thread_type),
        video.thumbnail_url,
    )

    # 5 + 6. No poster -> send AS A FILE, better than a video card stuck with a cheap placeholder (Zalo also
    # refuses an empty thumbnail). Sent straight through ``api`` so it stays inside the download queue slot,
    # keeping message order within the thread.
    ten = ten_file(video)
    dang: Literal["video", "file"]
    if poster is None:
        await gui_dang_file(dich, tai.byte, ten)
        dang = "file"
    else:
        url_zalo = await up_len_zalo(dich, tai.byte, ten)
        await dich.api.send_video(
            {
                "videoUrl": url_zalo,
                "thumbnailUrl": poster,
                "duration": duration_ms,
                "width": width,
                "height": height,
            },
            dich.thread_id,
            dich.thread_type,
        )
        dang = "video"

    log.info(
        "đã gửi video",
        nguon=video.nguon,
        duong=tai.duong,
        bytes=len(tai.byte),
        khung=f"{width}x{height}",
        khung_doc_duoc=khung is not None,
        dang=dang,
    )
    return KetQuaGui(duong=tai.duong, bytes=len(tai.byte), dang=dang)


def _math_round(x: float) -> int:
    """JS ``Math.round`` (half rounds UP), not Python's banker's rounding."""
    return int(x + 0.5) if x >= 0 else -int(-x + 0.5)

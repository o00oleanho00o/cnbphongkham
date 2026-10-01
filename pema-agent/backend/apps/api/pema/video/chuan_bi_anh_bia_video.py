# ported from: src/video/chuan-bi-anh-bia-video.ts
"""Build the video POSTER: download the SOURCE cover image into RAM then UPLOAD it to Zalo, returning the
image URL on Zalo's infrastructure. If it cannot be built return ``None``: the caller falls back to SENDING
AS A FILE (no poster needed).

WHY IT MUST BE UPLOADED rather than handing over the source URL: measured on a phone:

    thumbnailUrl = TikTok/Facebook URL   -> the video card shows PITCH BLACK (Zalo is picky about image hosts)
    thumbnailUrl = "" (empty)            -> Zalo REFUSES: ZaloApiError code 114
    thumbnailUrl = image uploaded to Zalo -> the poster shows CORRECTLY

WHY NOT ``parseLink`` any more: measured on a Facebook link, ``parseLink`` returns a ``zadn.vn`` URL but it is
a shared PLACEHOLDER image ("feed_thumb_link" since 2019), not a video frame: exactly the broken poster the
user saw. It LOADS so "check that the image loads" does not catch it. The user settled: better to send a file
than show a cheap-looking placeholder.

WHY NOT EXTRACT A FRAME HERE: it needs H.264 decoding of a stranger's bytes: Node has no WebCodecs, the
pure-JS decoder is Baseline only (TikTok/FB use Main/High) and abandoned, every "WebCodecs for Node" on npm
is ffmpeg in disguise. Exactly the attack surface this design avoids (the reason ffmpeg is not installed).
The same holds in Python.

Does NOT touch the disk: the image goes straight into RAM then to Zalo, a few tens of KB.

Forced deviations / dependencies:

* zca-js ``API`` becomes the narrow ``UploadAttachmentApi`` Protocol (only ``upload_attachment`` is called
  here); ``gui_video_qua_zalo.ZaloVideoApi`` is a superset, so one adapter serves both modules.
* ``readImageSize`` belongs to ``src/zalo/zalo-image-variant.ts`` (package C2); the default of the
  injectable ``PhuThuocAnhBia.doc_kich_thuoc_anh`` is C2's ``zalo_image_variant.read_image_size``, there is no
  second copy of the byte logic.
* The download goes through ``download_from_public_url`` (SSRF guard) exactly as the original.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Protocol, cast

from pema.channels.zalo_personal.zalo_image_variant import read_image_size
from pema.shared.logger import create_logger
from pema.shared.safe_remote_download import DownloadOptions, download_from_public_url

log = create_logger("anh-bia-video")

TRAN_ANH_BYTE = 5 * 1024 * 1024
"""Cover image size ceiling. A real cover is a few tens of KB; 5MB is a wide ceiling only to stop a malicious
source URL pointing at a huge file, not to filter real images."""


class UploadAttachmentApi(Protocol):
    """The ONE zca-js method this module calls: ``api.uploadAttachment(items, threadId, threadType)``.

    ``items`` is a list of ``{"data": bytes, "filename": str, "metadata": {...}}`` (the zca-js key names, the
    Node bridge forwards them unchanged). The result is whatever zca-js returns: a list of upload records or a
    single record, read defensively."""

    async def upload_attachment(
        self, items: list[dict[str, Any]], thread_id: str, thread_type: int
    ) -> Any: ...


def ban_ghi_upload(up: object) -> dict[str, Any] | None:
    """The first upload record of a zca-js ``uploadAttachment`` result: ``Array.isArray(up) ? up[0] : up``,
    read defensively (``None`` when there is no record object)."""
    if isinstance(up, list):
        items = cast("list[object]", up)
        first = items[0] if items else None
    else:
        first = up
    return cast("dict[str, Any]", first) if isinstance(first, dict) else None


@dataclass(frozen=True)
class DichAnhBia:
    api: UploadAttachmentApi
    thread_id: str
    thread_type: int


class KichThuocAnh(Protocol):
    """What the image-size reader returns: ``width`` and ``height`` (C2's dataclass fits structurally)."""

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...


@dataclass(frozen=True)
class _KichThuoc:
    width: int
    height: int


def doc_kich_thuoc_anh_mac_dinh(data: bytes) -> KichThuocAnh | None:
    """Read JPEG/PNG size from a few leading bytes: does not decode the image. It is ``readImageSize`` of
    ``zalo-image-variant.ts`` (package C2, ``zalo_image_variant.read_image_size``); ``None`` when it cannot be
    recognised."""
    size = read_image_size(data)
    return None if size is None else _KichThuoc(width=size[0], height=size[1])


async def _tai_anh_mac_dinh(url: str, max_bytes: int) -> bytes | None:
    try:
        # Through ``download_from_public_url`` to inherit the SSRF guard: the cover image URL is also returned
        # by a third party so it must not be trusted more than the video URL.
        res = await download_from_public_url(url, DownloadOptions(max_bytes=max_bytes))
    except Exception as err:
        log.debug("tải ảnh bìa nguồn hỏng", err=err)
        return None
    return res.data if len(res.data) > 0 else None


@dataclass(frozen=True)
class PhuThuocAnhBia:
    """The places that touch the outside, replaceable from outside ONLY for tests (and ``doc_kich_thuoc_anh``
    for the C2 reader, see the module docstring)."""

    tai_anh: Callable[[str, int], Awaitable[bytes | None]] = field(default=_tai_anh_mac_dinh)
    doc_kich_thuoc_anh: Callable[[bytes], KichThuocAnh | None] = field(default=doc_kich_thuoc_anh_mac_dinh)


PHU_THUOC_THAT = PhuThuocAnhBia()


async def chuan_bi_anh_bia_video(
    dich: DichAnhBia, thumbnail_nguon: str, phu_thuoc: PhuThuocAnhBia = PHU_THUOC_THAT
) -> str | None:
    """Return the poster URL on Zalo's infrastructure, or ``None`` if it cannot be built.

    ``None`` is NOT an error: it is the signal for the caller to fall back to sending as a file. Every
    failing branch goes to ``None``, none raises: losing the poster still leaves a file send, raising loses
    the whole video.
    """
    if thumbnail_nguon == "":
        return None

    buf = await phu_thuoc.tai_anh(thumbnail_nguon, TRAN_ANH_BYTE)
    if not buf:
        return None

    # Read the size by bytes, do NOT decode the image. ``uploadAttachment`` needs width/height for the image
    # branch; if it cannot be read (e.g. WebP) drop it and fall back to sending a file.
    #
    # The original's guard here was watched by the compiler (``co`` is nullable so removing it is a type error
    # at ``co.width``); pyright strict does the same here.
    co = phu_thuoc.doc_kich_thuoc_anh(buf)
    if co is None:
        log.debug("không đọc được kích thước ảnh bìa - lùi sang gửi file", bytes=len(buf))
        return None

    try:
        up = await dich.api.upload_attachment(
            [
                {
                    "data": buf,
                    "filename": "cover.jpg",
                    "metadata": {"totalSize": len(buf), "width": co.width, "height": co.height},
                }
            ],
            dich.thread_id,
            dich.thread_type,
        )

        record = ban_ghi_upload(up)
        if record is None:
            return None
        url = record.get("normalUrl") or record.get("hdUrl") or record.get("thumbUrl") or ""
        return url if isinstance(url, str) and url != "" else None
    except Exception as err:
        log.debug("upload ảnh bìa lên Zalo hỏng - lùi sang gửi file", err=err)
        return None

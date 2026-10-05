# ported from: src/shared/download-image.ts
"""Tải ảnh về bytes, cắt theo stream khi vượt 8MB (vision không cần lớn hơn) và chỉ nhận IP public. Lỗi
gì cũng trả None - ảnh hỏng không được chặn đường trả lời - nhưng vẫn log debug để không mất dấu hoàn toàn.

Forced deviations: ``Buffer`` -> ``bytes``; ``Promise`` -> coroutine; the optional ``transport`` and
``resolver`` keyword arguments are the injection points of ``safe_remote_download`` (tests and callers that
own a transport; production leaves them empty). The failure log carries the exception type only, never the
URL (it can hold a signed query string).
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

import httpx

from pema.shared.logger import create_logger
from pema.shared.safe_remote_download import (
    DownloadOptions,
    HostResolver,
    download_from_public_url,
)

MAX_IMAGE_BYTES = 8 * 1024 * 1024

log = create_logger("download-image")


@dataclass(frozen=True)
class DownloadedImage:
    data: bytes
    media_type: str


@dataclass(frozen=True)
class Base64Image:
    base64: str
    media_type: str


async def download_image(
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: HostResolver | None = None,
) -> DownloadedImage | None:
    """Tải ảnh về bytes, cắt theo stream khi vượt 8MB và chỉ nhận IP public. Lỗi gì cũng trả None."""
    try:
        file = await download_from_public_url(
            url, DownloadOptions(max_bytes=MAX_IMAGE_BYTES), transport=transport, resolver=resolver
        )
    except Exception as err:
        log.debug("Không tải được ảnh", err=err)
        return None
    # Zalo CDN đôi khi không trả content-type ảnh; vision cần media type image/*
    media_type = file.media_type if file.media_type.startswith("image/") else "image/jpeg"
    return DownloadedImage(data=file.data, media_type=media_type)


async def download_image_as_base64(
    url: str,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    resolver: HostResolver | None = None,
) -> Base64Image | None:
    downloaded = await download_image(url, transport=transport, resolver=resolver)
    if downloaded is None:
        return None
    return Base64Image(
        base64=base64.b64encode(downloaded.data).decode("ascii"), media_type=downloaded.media_type
    )

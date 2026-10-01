# ported from: src/shared/download-image.ts
"""The TypeScript module has no test file; these cases cover its documented behaviour (return ``None`` on any
failure, force an ``image/*`` media type, 8MB cap) with ``httpx.MockTransport``: no real network."""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator

import httpx

from pema.shared.download_image import MAX_IMAGE_BYTES, download_image, download_image_as_base64


class _Body(httpx.AsyncByteStream):
    def __init__(self, data: bytes, chunk: int = 1024 * 1024) -> None:
        self._data = data
        self._chunk = chunk

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for start in range(0, len(self._data), self._chunk):
            yield self._data[start : start + self._chunk]


def _transport(status: int, data: bytes, content_type: str | None) -> httpx.MockTransport:
    headers = {"content-type": content_type} if content_type is not None else {}
    return httpx.MockTransport(lambda _request: httpx.Response(status, headers=headers, stream=_Body(data)))


async def test_download_image_returns_bytes_and_image_media_type() -> None:
    """trả bytes và media type ảnh"""
    result = await download_image(
        "https://cdn.example.test/a.png", transport=_transport(200, b"\x89PNG-demo", "image/png")
    )
    assert result is not None
    assert result.data == b"\x89PNG-demo"
    assert result.media_type == "image/png"


async def test_download_image_non_image_content_type_becomes_image_jpeg() -> None:
    """Zalo CDN không trả content-type ảnh thì dùng image/jpeg"""
    for content_type in (None, "application/octet-stream", "text/plain"):
        result = await download_image(
            "https://cdn.example.test/a", transport=_transport(200, b"jpegdata", content_type)
        )
        assert result is not None
        assert result.media_type == "image/jpeg"


async def test_download_image_any_failure_returns_none() -> None:
    """lỗi gì cũng trả None: HTTP lỗi, URL rác, IP nội bộ, vượt 8MB"""
    assert await download_image("https://cdn.example.test/a", transport=_transport(404, b"no", None)) is None
    assert await download_image("khong-phai-url") is None
    assert (
        await download_image("http://127.0.0.1:3900/api/threads", transport=_transport(200, b"x", None))
        is None
    )
    too_big = _transport(200, b"x" * (MAX_IMAGE_BYTES + 1), "image/png")
    assert await download_image("https://cdn.example.test/big.png", transport=too_big) is None


async def test_download_image_as_base64_encodes_the_bytes() -> None:
    """download_image_as_base64 mã hóa bytes, trả None khi tải hỏng"""
    result = await download_image_as_base64(
        "https://cdn.example.test/a.jpg", transport=_transport(200, b"abc", "image/jpeg")
    )
    assert result is not None
    assert base64.b64decode(result.base64) == b"abc"
    assert result.media_type == "image/jpeg"
    assert await download_image_as_base64("khong-phai-url") is None

# ported from: src/images/read-image-sse-stream.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The stall tests need REAL (short) time, exactly like the original: what is under test is the silence
measurement itself. Everything else is scripted byte chunks without any wait.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from collections.abc import AsyncIterator

import httpx
import pytest

from pema.images.image_retry_policy import ImageGenError, LoiVeHutAnh
from pema.images.read_image_sse_stream import read_image_from_sse_stream

# Trọng tâm: phân biệt "vẽ lâu nhưng còn sống" với "kết nối đã chết".
# Provider bắn keepalive mỗi 30 giây (đo thật), nên im lặng là dấu hiệu chết,
# còn tổng thời gian dài thì không nói lên điều gì.

JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0])
JPEG_B64 = base64.b64encode(JPEG).decode()
KEEPALIVE = 'event: progress\ndata: {"stage":"keepalive"}\n\n'
DONE = f"event: done\ndata: {json.dumps({'created': 1, 'data': [{'b64_json': JPEG_B64}]})}\n\n"


class ScheduledStream(httpx.AsyncByteStream):
    """Stream bắn từng mẩu theo lịch (giây kể từ lúc bắt đầu). Không đóng nếu không có ``end_after_s``."""

    def __init__(self, parts: list[tuple[float, str]], end_after_s: float | None = None) -> None:
        self._parts = parts
        self._end_after_s = end_after_s
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        started = time.monotonic()
        for at_s, text in self._parts:
            await asyncio.sleep(max(0.0, at_s - (time.monotonic() - started)))
            yield text.encode()
        if self._end_after_s is None:
            await asyncio.Event().wait()
            return
        await asyncio.sleep(max(0.0, self._end_after_s - (time.monotonic() - started)))

    async def aclose(self) -> None:
        self.closed = True


def _response(stream: ScheduledStream) -> httpx.Response:
    return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=stream)


# ------------------------------------------------------------------ phân biệt chậm với chết


async def test_read_image_from_sse_stream_slow_but_steady_stream_runs_to_the_end() -> None:
    """stream CHẬM nhưng đều đặn vẫn chạy tới cùng, dù tổng lâu hơn trần im lặng nhiều lần"""
    # 5 nhịp cách nhau 80ms với trần im lặng 200ms: tổng 340ms > trần, nhưng
    # chưa lần nào im quá 200ms nên phải xong. Đây chính là ca vẽ ảnh 3-4 phút
    # mà provider vẫn bắn keepalive mỗi 30 giây.
    stream = ScheduledStream(
        [(0.02, KEEPALIVE), (0.10, KEEPALIVE), (0.18, KEEPALIVE), (0.26, KEEPALIVE), (0.34, DONE)],
        0.40,
    )
    b64 = await read_image_from_sse_stream(_response(stream), 200)
    assert base64.b64decode(b64).hex() == JPEG.hex()


async def test_read_image_from_sse_stream_silent_stream_stops_early_with_lost_signal() -> None:
    """stream IM LẶNG quá trần -> dừng sớm, báo mất tín hiệu chứ không đợi hết tổng"""
    stream = ScheduledStream([(0.01, KEEPALIVE), (5.0, DONE)])

    started = time.monotonic()
    with pytest.raises(ImageGenError, match=r"(?i)mất tín hiệu|im lặng"):
        await read_image_from_sse_stream(_response(stream), 100)
    assert time.monotonic() - started < 2, "phải cắt ngay khi im lặng, không chờ tới 5 giây"


async def test_read_image_from_sse_stream_silence_still_closes_the_stream() -> None:
    """im lặng quá trần thì vẫn ĐÓNG stream, không bỏ mặc kết nối"""
    stream = ScheduledStream([(0.0, KEEPALIVE)])

    with pytest.raises(ImageGenError):
        await read_image_from_sse_stream(_response(stream), 80)
    assert stream.closed is True


# PHÂN LỚP lỗi ngay tại đây, vì đây là chỗ duy nhất còn nhìn thấy câu gốc của
# provider - lên tới tool thì nó đã lẫn vào mọi lỗi khác. Lớp này quyết định
# `create_image` có vẽ lại hay không, nên nhận nhầm là bot đợi thêm 1-3 phút
# cho một lỗi vô phương.


async def test_read_image_from_sse_stream_router_says_no_image_is_loi_ve_hut_anh() -> None:
    """router báo không ra ảnh -> LoiVeHutAnh, để tầng trên biết là đáng vẽ lại"""
    err = (
        'event: error\ndata: {"message":"Codex did not return an image. '
        'Account may not be entitled (Plus/Pro required)."}\n\n'
    )
    with pytest.raises(LoiVeHutAnh):
        await read_image_from_sse_stream(_response(ScheduledStream([(0.0, err)], 0.02)), 5000)


async def test_read_image_from_sse_stream_other_provider_error_is_a_plain_error() -> None:
    """lỗi provider KIỂU KHÁC vẫn là Error thường - không được vẽ lại bừa"""
    err = 'event: error\ndata: {"message":"upstream rate limit exceeded"}\n\n'
    with pytest.raises(ImageGenError) as info:
        await read_image_from_sse_stream(_response(ScheduledStream([(0.0, err)], 0.02)), 5000)
    assert not isinstance(info.value, LoiVeHutAnh)


async def test_read_image_from_sse_stream_clean_close_without_done_is_the_same_missing_image_class() -> None:
    """stream đóng sạch mà thiếu done -> cùng lớp hụt ảnh, cũng đáng vẽ lại"""
    with pytest.raises(LoiVeHutAnh):
        await read_image_from_sse_stream(_response(ScheduledStream([(0.0, KEEPALIVE)], 0.02)), 5000)


async def test_read_image_from_sse_stream_lost_signal_is_not_a_missing_image() -> None:
    """mất tín hiệu KHÔNG phải hụt ảnh - vẽ lại chỉ tốn thêm một trần im lặng nữa"""
    with pytest.raises(ImageGenError) as info:
        await read_image_from_sse_stream(_response(ScheduledStream([(0.0, KEEPALIVE)])), 60)
    assert not isinstance(info.value, LoiVeHutAnh)

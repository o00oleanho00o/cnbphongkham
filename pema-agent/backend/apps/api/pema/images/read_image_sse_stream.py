# ported from: src/images/read-image-sse-stream.ts
"""Đọc stream SSE của endpoint vẽ ảnh, trả về base64 của ảnh hoàn chỉnh.

Vì sao phải đi đường stream thay vì lấy thẳng JSON/binary: router nằm sau
Cloudflare, mà Cloudflare cắt kết nối (HTTP 524) khi origin im lặng quá lâu.
Đường không stream chỉ trả byte đầu tiên LÚC VẼ XONG nên vẽ lâu là chết. Đo
thật cùng một prompt chạy song song:
  binary: byte đầu sau 125.4s -> HTTP 524
  SSE:    byte đầu sau   1.8s -> HTTP 200, xong ở 62.7s
Router bắn event ``progress`` liên tục nên Cloudflare luôn thấy có dữ liệu chảy.

Định dạng (đọc stream thật để đối chiếu, không theo tài liệu):
  event: progress      - tiến độ, bỏ qua
  event: partial_image - ảnh DỞ DANG, bỏ qua (lấy nhầm là gửi ảnh chưa vẽ xong)
  event: done          - {created, data:[{b64_json}]}
  event: error         - {message}

Forced deviations: the Fetch ``Response`` + ``ReadableStreamDefaultReader`` become an ``httpx.Response``
opened with ``stream=True`` (read through ``aiter_bytes``); ``Promise.race`` against a ``setTimeout`` becomes
``asyncio.wait`` with a timeout on the task that reads the next chunk (so an error raised by the stream itself
is never mistaken for the stall); ``TextDecoder`` becomes an incremental UTF-8 decoder; ``reader.cancel()``
becomes closing the chunk iterator and the response. The plain ``Error`` is ``ImageGenError``.
"""

from __future__ import annotations

import asyncio
import codecs
import contextlib
import json
from collections.abc import AsyncGenerator, AsyncIterator
from dataclasses import dataclass
from typing import cast

import httpx

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.images.image_retry_policy import ImageGenError, LoiVeHutAnh, la_chu_ve_hut_anh

BLOCK_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class SseBlock:
    event: str
    data: str


def parse_block(raw: str) -> SseBlock | None:
    event = ""
    data = ""
    for line in raw.split("\n"):
        if line.startswith("event:"):
            event = line[6:].strip()
        # Cộng dồn: chuẩn SSE cho phép 1 block có nhiều dòng data
        elif line.startswith("data:"):
            data += line[5:].strip()
    return SseBlock(event=event, data=data) if event else None


def _first_image_b64(parsed: object) -> str | None:
    """``parsed.data?.[0]?.b64_json`` of the original, tolerant of any other shape."""
    if not isinstance(parsed, dict):
        return None
    items = cast("dict[str, object]", parsed).get("data")
    if not isinstance(items, list) or not items:
        return None
    first = cast("list[object]", items)[0]
    if not isinstance(first, dict):
        return None
    value = cast("dict[str, object]", first).get("b64_json")
    return value if isinstance(value, str) else None


def image_from_done(block: SseBlock) -> str | None:
    """Rút b64 ảnh từ block done; trả None nếu block không phải done hợp lệ"""
    if block.event != "done":
        return None
    try:
        return _first_image_b64(json.loads(block.data))
    except ValueError:
        return None


_ERROR_FALLBACK = "Provider báo lỗi trong lúc vẽ"


def error_from(block: SseBlock) -> str | None:
    if block.event != "error":
        return None
    try:
        parsed: object = json.loads(block.data)
    except ValueError:
        return _ERROR_FALLBACK
    if isinstance(parsed, dict):
        message = cast("dict[str, object]", parsed).get("message")
        if isinstance(message, str) and message:
            return message
    return _ERROR_FALLBACK


async def _next_chunk(chunks: AsyncIterator[bytes]) -> bytes | None:
    try:
        return await anext(chunks)
    except StopAsyncIteration:
        return None


async def read_chunk_or_stall(chunks: AsyncIterator[bytes], stall_ms: int) -> bytes | None:
    """Đọc một chunk, nhưng bỏ cuộc nếu IM LẶNG quá lâu.

    Đây là phép đo đúng cho stream, khác hẳn trần tổng thời gian. Đo thật trên
    prompt nặng (tổng 135 giây): provider bắn ``keepalive`` đều đặn mỗi 30 giây,
    khoảng im lặng dài nhất chỉ 30.1 giây. Nên vẽ lâu mà stream còn chảy là KHỎE
    MẠNH, còn im lặng lâu là đã CHẾT - trần tổng không phân biệt được hai thứ đó,
    nó giết cả hai như nhau.

    Returns the chunk, or ``None`` when the stream ended (the original ``done: true``).
    """
    task = asyncio.ensure_future(_next_chunk(chunks))
    try:
        finished, _ = await asyncio.wait({task}, timeout=stall_ms / 1000)
        if not finished:
            raise ImageGenError(
                f"Mất tín hiệu từ nhà cung cấp (im lặng quá {round_half_up(stall_ms / 1000)} giây)"
            )
        return task.result()
    finally:
        # Dọn sau MỖI chunk: không dọn thì chunk đang chờ dở sống tới khi hết hạn
        if not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task


def round_half_up(value: float) -> int:
    """JavaScript ``Math.round`` (half rounds up), not Python's banker's rounding."""
    return int(value + 0.5)


async def read_image_from_sse_stream(response: httpx.Response, stall_ms: int | None = None) -> str:
    """Trả về base64 của ảnh hoàn chỉnh. ``stall_ms`` mặc định lấy ``IMAGE_GEN_STALL_MS`` lúc GỌI.

    ``response`` must be opened with ``stream=True`` (``client.stream(...)``). The original's
    "``response.body`` is null" branch has no equivalent: an empty body simply yields no chunk and ends in
    the "thiếu sự kiện done" error below, the same ``LoiVeHutAnh``.
    """
    stall = get_tuning_int("IMAGE_GEN_STALL_MS") if stall_ms is None else stall_ms

    chunks = response.aiter_bytes()
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    # Buffer bắt buộc: một block SSE có thể bị chẻ làm đôi giữa 2 chunk mạng,
    # xử lý từng chunk rời là mất event done của những ảnh lớn
    buffer = ""
    image_b64: str | None = None

    try:
        while True:
            value = await read_chunk_or_stall(chunks, stall)
            if value is None:
                break
            buffer += decoder.decode(value)

            while (sep := buffer.find(BLOCK_SEPARATOR)) != -1:
                block = parse_block(buffer[:sep])
                buffer = buffer[sep + len(BLOCK_SEPARATOR) :]
                if block is None:
                    continue

                failure = error_from(block)
                # Gắn LỚP lỗi ngay tại đây - chỗ duy nhất còn nhìn thấy câu gốc của
                # provider. Lên tới tool thì câu này đã lẫn vào mọi lỗi khác.
                if failure is not None:
                    raise LoiVeHutAnh(failure) if la_chu_ve_hut_anh(failure) else ImageGenError(failure)

                from_done = image_from_done(block)
                image_b64 = from_done if from_done is not None else image_b64
    finally:
        # Thoát giữa chừng (event error, quá hạn) mà bỏ mặc stream là giữ kết nối
        # sống - bot chạy thường trú nên rò rỉ dần theo từng lượt hỏng
        with contextlib.suppress(Exception):
            await cast("AsyncGenerator[bytes, None]", chunks).aclose()
        with contextlib.suppress(Exception):
            await response.aclose()

    if not image_b64:
        # Stream chạy hết mà không có done: đừng trả chuỗi rỗng rồi ghi ra file 0 byte
        raise LoiVeHutAnh("Provider không trả về ảnh (stream kết thúc mà thiếu sự kiện done)")
    return image_b64

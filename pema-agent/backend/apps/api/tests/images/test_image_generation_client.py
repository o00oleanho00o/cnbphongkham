# ported from: src/images/image-generation-client.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``fetch`` is replaced by ``httpx.MockTransport``: no network, no waiting.
"""

from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass, field
from typing import cast

import httpx
import pytest

from pema.config.runtime_image_settings import ImageGenSettings
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema.images.image_generation_client import (
    GeneratedImage,
    GenerateImageParams,
    RefImage,
    generate_image,
)
from pema.images.image_retry_policy import ImageGenError, LoiVeHutAnh

SETTINGS = ImageGenSettings(base_url="https://router.test", model="cx/gpt-5.5-image", api_key="sk-test")

JPEG = bytes([0xFF, 0xD8, 0xFF, 0xE0])
JPEG_B64 = base64.b64encode(JPEG).decode()


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({"IMAGE_GEN_QUALITY": "high"}))
    yield
    reset_tuning_provider()


def binary_response(data: bytes, mime: str = "image/jpeg") -> httpx.Response:
    """Response giả dạng binary - đúng thứ router trả khi có ?response_format=binary"""
    return httpx.Response(200, content=data, headers={"Content-Type": mime})


def sse_response(*blocks: str) -> httpx.Response:
    """Dựng stream SSE đúng định dạng router trả (đã đọc stream thật để đối chiếu)"""
    return httpx.Response(
        200,
        content=("\n\n".join(blocks) + "\n\n").encode(),
        headers={"Content-Type": "text/event-stream"},
    )


def sse_done(b64: str) -> str:
    return f"event: done\ndata: {json.dumps({'created': 1, 'data': [{'b64_json': b64}]})}"


SSE_PROGRESS = 'event: progress\ndata: {"stage":"response.created","bytesReceived":1393}'


def json_response(b64: str) -> httpx.Response:
    """Response JSON thường - provider không hỗ trợ SSE thì router trả dạng này"""
    return httpx.Response(200, json={"created": 1, "data": [{"b64_json": b64}]})


def ok_sse() -> httpx.Response:
    return sse_response(SSE_PROGRESS, sse_done(JPEG_B64))


@dataclass
class Capture:
    """Bắt lại request để khẳng định client gửi đúng cái gì"""

    calls: list[httpx.Request] = field(default_factory=list[httpx.Request])

    def body(self) -> dict[str, object]:
        return cast("dict[str, object]", json.loads(self.calls[0].content))


def capture(respond: Callable[[], httpx.Response]) -> tuple[Capture, httpx.AsyncClient]:
    cap = Capture()

    def handler(request: httpx.Request) -> httpx.Response:
        cap.calls.append(request)
        return respond()

    return cap, httpx.AsyncClient(transport=httpx.MockTransport(handler))


class ScriptedStream(httpx.AsyncByteStream):
    """Stream script từng chunk; ``then`` quyết định chuyện gì xảy ra sau chunk cuối."""

    def __init__(self, chunks: list[bytes], then: str = "hang") -> None:
        self._chunks = chunks
        self._then = then
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            yield chunk
        if self._then == "hang":
            await asyncio.Event().wait()
        elif self._then == "timeout":
            raise httpx.ReadTimeout("The read operation timed out")

    async def aclose(self) -> None:
        self.closed = True


def sse_stream_response(stream: ScriptedStream) -> httpx.Response:
    return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, stream=stream)


async def _generate(
    client: httpx.AsyncClient, params: GenerateImageParams, settings: ImageGenSettings = SETTINGS
) -> GeneratedImage:
    async with client:
        return await generate_image(params, settings, client)


# ------------------------------------------------------------------ dựng request


async def test_generate_image_build_request_asks_for_sse_via_accept_header() -> None:
    """XIN SSE bằng header Accept - đây là thứ cứu khỏi 524 của Cloudflare"""
    cap, client = capture(ok_sse)
    await _generate(client, GenerateImageParams(prompt="con mèo"))

    assert cap.calls[0].headers["Accept"] == "text/event-stream"


async def test_generate_image_build_request_no_response_format_binary() -> None:
    """KHÔNG kèm response_format=binary - router chỉ stream khi không xin binary"""
    cap, client = capture(ok_sse)
    await _generate(client, GenerateImageParams(prompt="con mèo"))

    assert len(cap.calls) == 1
    assert str(cap.calls[0].url) == "https://router.test/v1/images/generations"


async def test_generate_image_build_request_strips_trailing_slash_of_base_url() -> None:
    """cắt dấu / thừa ở cuối base URL, không thành //v1"""
    cap, client = capture(ok_sse)
    await _generate(
        client,
        GenerateImageParams(prompt="x"),
        ImageGenSettings(base_url="https://router.test/", model=SETTINGS.model, api_key=SETTINGS.api_key),
    )
    assert "//v1" not in str(cap.calls[0].url)


async def test_generate_image_build_request_sends_bearer_key_and_body_with_model_and_prompt() -> None:
    """gửi Bearer key và body có model + prompt"""
    cap, client = capture(ok_sse)
    await _generate(client, GenerateImageParams(prompt="một ly cà phê"))

    assert cap.calls[0].headers["Authorization"] == "Bearer sk-test"
    body = cap.body()
    assert body["model"] == "cx/gpt-5.5-image"
    assert body["prompt"] == "một ly cà phê"


async def test_generate_image_build_request_does_not_send_size() -> None:
    """KHÔNG gửi size: model bỏ qua tham số này (đo thật: xin 1024x1024 nhận 1536x1024)"""
    cap, client = capture(ok_sse)
    await _generate(client, GenerateImageParams(prompt="x"))
    assert "size" not in cap.body()


async def test_generate_image_build_request_sends_quality_from_tuning() -> None:
    """gửi quality theo env - bỏ trống thì provider tự chọn mức thấp hơn"""
    # Đo A/B cùng prompt: có quality=high ra ảnh giàu chi tiết hơn hẳn (khối
    # phát sáng, lớp sóng hạt, nhiều tầng biểu đồ) mà KHÔNG chậm hơn.
    cap, client = capture(ok_sse)
    await _generate(client, GenerateImageParams(prompt="x"))
    assert cap.body()["quality"] == "high"


async def test_generate_image_build_request_defaults_to_jpeg() -> None:
    """mặc định JPEG - nhẹ hơn PNG hàng chục lần"""
    cap, client = capture(ok_sse)
    result = await _generate(client, GenerateImageParams(prompt="x"))
    assert cap.body()["output_format"] == "jpeg"
    assert result.ext == "jpg", "SSE không mang Content-Type riêng cho ảnh - đuôi lấy theo format đã xin"


async def test_generate_image_build_request_transparent_background_forces_png() -> None:
    """nền trong suốt ép sang PNG - JPEG không có kênh alpha"""
    cap, client = capture(ok_sse)
    result = await _generate(client, GenerateImageParams(prompt="logo", transparent_background=True))

    body = cap.body()
    assert body["output_format"] == "png"
    assert body["background"] == "transparent"
    assert result.ext == "png"


# ------------------------------------------------------------------ đọc stream SSE


async def test_generate_image_read_sse_stream_takes_the_done_event_and_skips_progress_and_partial_image() -> (
    None
):
    """lấy ảnh từ event done, bỏ qua progress và partial_image"""
    _, client = capture(
        lambda: sse_response(
            SSE_PROGRESS,
            'event: partial_image\ndata: {"b64_json":"AAAA","index":0}',
            SSE_PROGRESS,
            sse_done(JPEG_B64),
        )
    )
    result = await _generate(client, GenerateImageParams(prompt="x"))
    assert result.data == JPEG, "partial_image là ảnh dở dang - lấy nhầm là gửi ảnh chưa vẽ xong"


async def test_generate_image_read_sse_stream_error_event_raises_with_the_providers_sentence() -> None:
    """event error trong stream -> ném lỗi kèm đúng câu của provider"""
    _, client = capture(
        lambda: sse_response(
            SSE_PROGRESS, 'event: error\ndata: {"message":"Account may not be entitled (Plus/Pro required)."}'
        )
    )
    with pytest.raises(ImageGenError, match=r"Plus/Pro required"):
        await _generate(client, GenerateImageParams(prompt="x"))


async def test_generate_image_read_sse_stream_ends_without_done_is_a_clear_error_not_an_empty_file() -> None:
    """stream kết thúc mà không có done -> lỗi rõ ràng, không trả file rỗng"""
    _, client = capture(lambda: sse_response(SSE_PROGRESS, SSE_PROGRESS))
    with pytest.raises(ImageGenError, match=r"(?i)không trả về ảnh"):
        await _generate(client, GenerateImageParams(prompt="x"))


async def test_generate_image_read_sse_stream_error_midway_still_closes_the_stream() -> None:
    """lỗi giữa chừng vẫn ĐÓNG stream - bot chạy thường trú, bỏ mặc là rò rỉ kết nối"""
    # KHÔNG kết thúc: mô phỏng stream còn dở khi mình bỏ đi giữa chừng
    stream = ScriptedStream(['event: error\ndata: {"message":"provider hỏng"}\n\n'.encode()], then="hang")
    _, client = capture(lambda: sse_stream_response(stream))

    with pytest.raises(ImageGenError, match=r"provider hỏng"):
        await _generate(client, GenerateImageParams(prompt="x"))
    assert stream.closed is True, "phải đóng stream khi thoát sớm"


async def test_generate_image_read_sse_stream_block_split_across_two_network_chunks_is_reassembled() -> None:
    """block SSE bị chẻ làm đôi giữa 2 chunk mạng vẫn ghép lại đúng"""
    full = f"{SSE_PROGRESS}\n\n{sse_done(JPEG_B64)}\n\n".encode()
    cut = len(full) // 2
    stream = ScriptedStream([full[:cut], full[cut:]], then="end")
    _, client = capture(lambda: sse_stream_response(stream))
    result = await _generate(client, GenerateImageParams(prompt="x"))
    assert result.data == JPEG


# ------------------------------------------------------------------ provider không stream


async def test_generate_image_non_streaming_provider_plain_json_b64_json_is_read() -> None:
    """router trả JSON thường vẫn đọc được b64_json"""
    _, client = capture(lambda: json_response(JPEG_B64))
    result = await _generate(client, GenerateImageParams(prompt="x"))
    assert result.data == JPEG


async def test_generate_image_non_streaming_provider_raw_image_bytes_use_the_content_type_extension() -> None:
    """router trả thẳng bytes ảnh vẫn dùng được, đuôi theo Content-Type"""
    _, client = capture(lambda: binary_response(JPEG, "image/png"))
    result = await _generate(client, GenerateImageParams(prompt="x"))
    assert result.data == JPEG
    assert result.ext == "png"


async def test_generate_image_non_streaming_provider_json_without_b64_json_is_loi_ve_hut_anh() -> None:
    """JSON thiếu b64_json cùng lớp hụt ảnh với nhánh SSE - đáng thử lại"""
    _, client = capture(lambda: httpx.Response(200, json={"created": 1, "data": []}))
    with pytest.raises(LoiVeHutAnh):
        await _generate(client, GenerateImageParams(prompt="x"))


# ------------------------------------------------------------------ ảnh gốc để sửa


async def test_generate_image_reference_image_becomes_a_data_uri_in_the_image_field() -> None:
    """ảnh gốc thành data URI ở trường `image` (KHÔNG phải ref_image)"""
    cap, client = capture(ok_sse)
    await _generate(
        client,
        GenerateImageParams(
            prompt="đổi mũ thành beret đỏ", ref_image=RefImage(base64="QUJD", media_type="image/png")
        ),
    )

    body = cap.body()
    assert body["image"] == "data:image/png;base64,QUJD"
    assert "ref_image" not in body, "tên trường sai sẽ bị provider bỏ qua âm thầm"
    assert body["image_detail"] == "high", "đọc kỹ ảnh gốc thì mới sửa đúng chi tiết"


async def test_generate_image_reference_image_absent_means_no_image_field() -> None:
    """không có ảnh gốc thì không gửi trường image"""
    cap, client = capture(ok_sse)
    await _generate(client, GenerateImageParams(prompt="vẽ mới"))
    assert "image" not in cap.body()


# ------------------------------------------------------------------ kiểu response lạ


async def test_generate_image_unknown_response_type_is_a_clear_error_not_a_junk_file() -> None:
    """Content-Type không phải ảnh/SSE/JSON -> lỗi rõ ràng, không ghi file rác"""
    _, client = capture(
        lambda: httpx.Response(
            200, content="<html>trang lỗi của proxy</html>".encode(), headers={"Content-Type": "text/html"}
        )
    )
    with pytest.raises(ImageGenError, match=r"(?i)không trả về ảnh") as info:
        await _generate(client, GenerateImageParams(prompt="x"))
    assert not isinstance(info.value, LoiVeHutAnh), "trang lỗi hạ tầng không phải model đổi ý"


# ------------------------------------------------------------------ đường lỗi


async def test_generate_image_error_path_400_error_is_an_object_with_message() -> None:
    """lỗi 400: error là OBJECT có .message"""
    _, client = capture(
        lambda: httpx.Response(400, json={"error": {"message": "Missing required field: prompt"}})
    )
    with pytest.raises(ImageGenError, match=r"Missing required field"):
        await _generate(client, GenerateImageParams(prompt="x"))


async def test_generate_image_error_path_401_error_is_a_string_a_different_shape_from_400() -> None:
    """lỗi 401: error là CHUỖI - dạng khác hẳn 400, parser chỉ đọc .message sẽ ra undefined"""
    _, client = capture(lambda: httpx.Response(401, json={"error": "API key required for remote API access"}))
    with pytest.raises(ImageGenError) as info:
        await _generate(client, GenerateImageParams(prompt="x"))
    assert "API key required" in str(info.value)
    assert "undefined" not in str(info.value)
    assert "None" not in str(info.value)


async def test_generate_image_error_path_non_json_error_body_still_raises_with_the_http_code() -> None:
    """body lỗi không phải JSON vẫn ném lỗi kèm mã HTTP"""
    _, client = capture(lambda: httpx.Response(502, content=b"<html>502 Bad Gateway</html>"))
    with pytest.raises(ImageGenError, match=r"502"):
        await _generate(client, GenerateImageParams(prompt="x"))


async def test_generate_image_error_path_timeout_at_call_time_is_a_vietnamese_sentence() -> None:
    """quá hạn ngay khi gọi -> câu tiếng Việt nói rõ là timeout, không phải AbortError trần trụi"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("The operation was aborted", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    with pytest.raises(ImageGenError, match=r"(?i)quá lâu|quá hạn"):
        await _generate(client, GenerateImageParams(prompt="x"))


async def test_generate_image_error_path_timeout_midway_through_the_stream_gives_the_same_sentence() -> None:
    """quá hạn GIỮA CHỪNG lúc đọc stream cũng phải ra câu tiếng Việt đó"""
    # Đây mới là ca dễ xảy ra nhất với SSE: lời gọi trả về sau ~1.8 giây rồi mình
    # đọc stream thêm cả phút. Nếu chỉ bọc try/except quanh lời gọi thì timeout lúc
    # đang đọc lọt ra ngoài dạng lỗi trần trụi.
    stream = ScriptedStream([f"{SSE_PROGRESS}\n\n".encode()], then="timeout")
    _, client = capture(lambda: sse_stream_response(stream))
    with pytest.raises(ImageGenError, match=r"(?i)quá lâu|quá hạn"):
        await _generate(client, GenerateImageParams(prompt="x"))


async def test_generate_image_error_path_not_fully_configured_fails_at_once_without_network() -> None:
    """chưa cấu hình đủ 3 trường thì báo lỗi NGAY, không gọi mạng"""
    cap, client = capture(ok_sse)
    with pytest.raises(ImageGenError, match=r"(?i)chưa cấu hình"):
        await _generate(
            client,
            GenerateImageParams(prompt="x"),
            ImageGenSettings(base_url=SETTINGS.base_url, model=SETTINGS.model, api_key=""),
        )
    assert len(cap.calls) == 0

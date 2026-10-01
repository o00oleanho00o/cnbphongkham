# ported from: src/agent/llm-response-sanitizer.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Forced deviation: ``createSanitizingFetch`` (a ``fetch`` wrapper) became ``create_sanitizing_transport`` (an
async HTTP transport wrapper), so ``baseFetch`` is a mock transport and the ``Response`` objects come from
``http_flavour`` (``httpx2`` or ``httpx``, whichever the installed SDKs use).
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest

from pema.agent.llm_response_sanitizer import create_sanitizing_transport, strip_sse_done_trailer
from pema.agent.providers.http_flavour import http as httpx

# The real body from the 25/07 error log: a complete JSON + an SSE trailer
BUGGY_JSON = json.dumps(
    {
        "id": "ed24700c",
        "object": "chat.completion",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "Chào Hải 👋 Có gì mình hỗ trợ bạn không?"},
            }
        ],
    },
    separators=(",", ":"),
    ensure_ascii=False,
)
BUGGY_BODY = f"{BUGGY_JSON}data: [DONE]\n\n"

ANSWER = "Chào Hải 👋 Có gì mình hỗ trợ bạn không?"


def test_strip_sse_done_trailer_cat_duoi_data_done_khoi_json_hoan_chinh_noi_dung_giu_nguyen() -> None:
    """cắt đuôi 'data: [DONE]' khỏi JSON hoàn chỉnh, nội dung giữ nguyên"""
    cleaned = strip_sse_done_trailer(BUGGY_BODY)
    assert cleaned is not None
    parsed = json.loads(cleaned)
    assert parsed["choices"][0]["message"]["content"] == ANSWER


def test_strip_sse_done_trailer_cat_duoc_ca_khi_co_nhieu_duoi_done_lien_tiep() -> None:
    """cắt được cả khi có nhiều đuôi DONE liên tiếp"""
    cleaned = strip_sse_done_trailer(f"{BUGGY_JSON}\ndata: [DONE]\n\ndata: [DONE]\n")
    assert cleaned is not None
    json.loads(cleaned)


def test_strip_sse_done_trailer_json_sach_khong_co_duoi_thi_null_khong_dung_vao() -> None:
    """JSON sạch không có đuôi -> null (không đụng)"""
    assert strip_sse_done_trailer(BUGGY_JSON) is None


def test_strip_sse_done_trailer_stream_sse_that_thi_null_phan_con_lai_khong_phai_json_object() -> None:
    """stream SSE thật -> null (phần còn lại không phải JSON object)"""
    sse = 'data: {"id":"1"}\n\ndata: {"id":"2"}\n\ndata: [DONE]\n\n'
    assert strip_sse_done_trailer(sse) is None


def test_strip_sse_done_trailer_duoi_done_nhung_phan_truoc_la_json_hong_thi_null() -> None:
    """đuôi DONE nhưng phần trước là JSON hỏng -> null"""
    assert strip_sse_done_trailer('{"id": "1"data: [DONE]') is None


def test_strip_sse_done_trailer_new_nan_khong_phai_json_nhu_json_parse() -> None:
    """(mới) NaN/Infinity không phải JSON hợp lệ - như JSON.parse của bản gốc"""
    assert strip_sse_done_trailer('{"a": NaN}data: [DONE]') is None


# ---- createSanitizingFetch -> create_sanitizing_transport ----------------------------------------------


def buggy_response() -> Any:
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content=BUGGY_BODY.encode("utf-8"),
    )


def always(response: Any) -> Callable[[Any], Any]:
    def handler(_request: Any) -> Any:
        return response

    return handler


def post(url: str = "https://router.test/v1/chat/completions", body: str = "{}") -> Any:
    return httpx.Request("POST", url, content=body.encode("utf-8"))


async def test_create_sanitizing_transport_response_loi_duoc_lam_sach_parse_json_duoc_content_type_thanh_json() -> (
    None
):
    """response lỗi được làm sạch: parse JSON được, content-type thành JSON"""
    sanitized = 0

    def on_sanitized() -> None:
        nonlocal sanitized
        sanitized += 1

    transport = create_sanitizing_transport(
        base=httpx.MockTransport(always(buggy_response())), on_sanitized=on_sanitized
    )
    async with httpx.AsyncClient(transport=transport) as client:
        res = await client.post("https://router.test/v1/chat/completions", content=b"{}")

    parsed = res.json()
    assert sanitized == 1
    assert res.headers["content-type"] == "application/json; charset=utf-8"
    assert parsed["choices"][0]["message"]["content"] == ANSWER


async def test_create_sanitizing_transport_response_loi_header_do_dai_va_nen_duoc_bo() -> None:
    """content-length/content-encoding cũ bị xóa để khỏi lệch với body mới"""

    def handler(_request: Any) -> Any:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream", "content-length": "999"},
            content=BUGGY_BODY.encode("utf-8"),
        )

    transport = create_sanitizing_transport(base=httpx.MockTransport(handler))
    res = await transport.handle_async_request(post())
    await res.aread()
    assert res.headers["content-length"] == str(len(BUGGY_JSON.encode("utf-8")))
    assert "content-encoding" not in res.headers


async def test_create_sanitizing_transport_response_json_binh_thuong_di_qua_nguyen_ven_khong_bao_sanitized() -> (
    None
):
    """response JSON bình thường đi qua nguyên vẹn, không báo sanitized"""
    sanitized = 0

    def on_sanitized() -> None:
        nonlocal sanitized
        sanitized += 1

    def handler(_request: Any) -> Any:
        return httpx.Response(
            200, headers={"content-type": "application/json"}, content=BUGGY_JSON.encode("utf-8")
        )

    transport = create_sanitizing_transport(base=httpx.MockTransport(handler), on_sanitized=on_sanitized)
    async with httpx.AsyncClient(transport=transport) as client:
        res = await client.post("https://router.test", content=b"{}")

    assert res.text == BUGGY_JSON
    assert sanitized == 0


async def test_create_sanitizing_transport_request_streaming_that_khong_bi_dung_toi_body_chua_bi_doc() -> (
    None
):
    """request streaming thật không bị đụng tới (body chưa bị đọc)"""

    async def chunks() -> AsyncIterator[bytes]:
        yield BUGGY_BODY.encode("utf-8")

    original = httpx.Response(200, headers={"content-type": "text/event-stream"}, content=chunks())
    transport = create_sanitizing_transport(base=httpx.MockTransport(always(original)))

    res = await transport.handle_async_request(post("https://router.test", '{"model":"m","stream":true}'))

    # Returns the very original object, body not consumed -> the stream reader is still usable
    assert res is original
    assert res.is_stream_consumed is False
    assert (await res.aread()).decode("utf-8") == BUGGY_BODY


async def test_create_sanitizing_transport_response_non_ok_di_qua_nguyen_ven_de_sdk_xu_ly_loi_http() -> None:
    """response non-ok đi qua nguyên vẹn để SDK xử lý lỗi HTTP"""
    original = httpx.Response(502, content=b"upstream error")
    transport = create_sanitizing_transport(base=httpx.MockTransport(always(original)))

    res = await transport.handle_async_request(post("https://router.test"))
    assert res is original
    assert res.status_code == 502


async def test_create_sanitizing_transport_aclose_dong_transport_goc() -> None:
    """(mới) aclose chuyển xuống transport gốc"""
    closed = False

    class Base(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request: Any) -> Any:
            return httpx.Response(200, content=b"{}")

        async def aclose(self) -> None:
            nonlocal closed
            closed = True

    transport = create_sanitizing_transport(base=Base())
    await transport.aclose()
    assert closed is True


@pytest.mark.parametrize("body", ['{"stream": true}', '{"stream":true}', '{"model":"m","stream" : true}'])
async def test_create_sanitizing_transport_new_nhan_ra_stream_true_voi_khoang_trang(body: str) -> None:
    """(mới) nhận ra "stream": true dù có khoảng trắng - y như regex gốc"""
    original = buggy_response()
    transport = create_sanitizing_transport(base=httpx.MockTransport(always(original)))
    res = await transport.handle_async_request(post("https://router.test", body))
    assert res is original

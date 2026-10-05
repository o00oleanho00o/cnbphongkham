# ported from: src/shared/jina-reader-fallback.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``fetchFn`` of the original is an ``httpx.AsyncClient`` over ``httpx.MockTransport``: no real network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

import httpx

from pema.shared.jina_reader_fallback import (
    JinaFetchOptions,
    fetch_via_jina_reader,
    parse_jina_response,
)
from pema.shared.safe_remote_download import AbortSignal

# Định dạng thật của r.jina.ai
JINA_BODY = "\n".join(
    [
        "Title: Kết quả xổ số Đà Lạt 19/07/2026 - Minh Ngọc™",
        "URL Source: https://www.minhngoc.net.vn/",
        "Published Time: Sun, 19 Jul 2026 10:00:00 GMT",
        "",
        "Markdown Content:",
        "Giải ĐB | 087842",
        "Giải nhất | 47409",
    ]
)

# Jina trả HTTP 200 kèm cảnh báo này khi trang đích chặn CHÍNH NÓ
JINA_BLOCKED_BODY = "\n".join(
    [
        "Title: Attention Required! | Cloudflare",
        "URL Source: https://sjc.com.vn/giavang",
        "Warning: Target URL returned error 403: Forbidden",
    ]
)


def respond(body: str, status: int = 200) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status, text=body))
    )


def client_of(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def async_client_of(
    handler: Callable[[httpx.Request], Coroutine[None, None, httpx.Response]],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------ parseJinaResponse


def test_parse_jina_response_splits_title_and_content_after_markdown_content_marker() -> None:
    """tách title và phần nội dung sau 'Markdown Content:'"""
    parsed = parse_jina_response(JINA_BODY)
    assert parsed.title == "Kết quả xổ số Đà Lạt 19/07/2026 - Minh Ngọc™"
    assert parsed.text == "Giải ĐB | 087842\nGiải nhất | 47409"
    assert "URL Source" not in parsed.text, "phần header không được lẫn vào nội dung"


def test_parse_jina_response_without_marker_takes_whole_body_losing_nothing() -> None:
    """không có marker thì lấy nguyên body, không mất dữ liệu"""
    parsed = parse_jina_response("chỉ có mỗi chữ này")
    assert parsed.text == "chỉ có mỗi chữ này"
    assert parsed.title == ""


# ------------------------------------------------------------------ fetchViaJinaReader


async def test_fetch_via_jina_reader_gets_content_when_jina_answers_normally() -> None:
    """lấy được nội dung khi Jina trả bình thường"""
    result = await fetch_via_jina_reader(
        "https://minhngoc.net.vn/", JinaFetchOptions(max_chars=5000, client=respond(JINA_BODY))
    )
    assert result is not None
    assert "087842" in result.text
    assert "Minh Ngọc" in result.title


async def test_fetch_via_jina_reader_target_blocking_jina_too_counts_as_failure() -> None:
    """trang đích chặn cả Jina (200 + Warning) coi như thất bại, không trả rác cho model"""
    result = await fetch_via_jina_reader(
        "https://sjc.com.vn/giavang", JinaFetchOptions(max_chars=5000, client=respond(JINA_BLOCKED_BODY))
    )
    assert result is None


async def test_fetch_via_jina_reader_merges_turn_signal_so_abort_cancels_jina_too() -> None:
    """gộp signal của lượt vào fetch - lượt abort thì Jina cũng bị hủy"""
    never = asyncio.Event()
    started = asyncio.Event()
    state = {"cancelled": False}

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await never.wait()
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise
        return httpx.Response(200, text=JINA_BODY)

    signal = AbortSignal()
    pending = asyncio.ensure_future(
        fetch_via_jina_reader(
            "https://a.vn", JinaFetchOptions(max_chars=100, client=async_client_of(handler), signal=signal)
        )
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    assert pending.done() is False
    signal.abort()
    result = await asyncio.wait_for(pending, timeout=2)

    assert result is None
    assert state["cancelled"] is True, "lượt abort thì request đang chạy phải bị hủy theo"


async def test_fetch_via_jina_reader_own_timeout_cancels_hanging_request() -> None:
    """timeout riêng của Jina cũng hủy request treo và trả None"""
    never = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await never.wait()
        return httpx.Response(200, text=JINA_BODY)

    result = await fetch_via_jina_reader(
        "https://a.vn", JinaFetchOptions(max_chars=100, timeout_ms=10, client=async_client_of(handler))
    )
    assert result is None


async def test_fetch_via_jina_reader_cuts_to_max_chars_to_avoid_bloating_context() -> None:
    """cắt theo maxChars để không phình context"""
    long = f"Markdown Content:\n{'x' * 500}"
    result = await fetch_via_jina_reader(
        "https://a.vn", JinaFetchOptions(max_chars=100, client=respond(long))
    )
    assert result is not None
    assert len(result.text) == 100


async def test_fetch_via_jina_reader_http_error_or_exception_returns_none() -> None:
    """HTTP lỗi hoặc ném exception đều trả null - đây đã là nhánh lưới đỡ"""
    assert (
        await fetch_via_jina_reader(
            "https://a.vn", JinaFetchOptions(max_chars=100, client=respond("nope", 429))
        )
        is None
    )

    def throwing(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("mạng chết", request=request)

    assert (
        await fetch_via_jina_reader(
            "https://a.vn", JinaFetchOptions(max_chars=100, client=client_of(throwing))
        )
        is None
    )


async def test_fetch_via_jina_reader_empty_content_returns_none_instead_of_blank_string() -> None:
    """nội dung rỗng cũng trả null thay vì chuỗi trắng"""
    result = await fetch_via_jina_reader(
        "https://a.vn", JinaFetchOptions(max_chars=100, client=respond("Markdown Content:\n   "))
    )
    assert result is None


async def test_fetch_via_jina_reader_key_adds_bearer_no_key_still_works() -> None:
    """có key thì gắn Bearer, không key vẫn gọi được"""
    seen: list[str | None] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return httpx.Response(200, text=JINA_BODY)

    client = client_of(spy)
    await fetch_via_jina_reader("https://a.vn", JinaFetchOptions(max_chars=100, client=client))
    await fetch_via_jina_reader(
        "https://a.vn", JinaFetchOptions(max_chars=100, api_key="jina-key", client=client)
    )

    assert seen[0] is None, "không key thì không gửi Authorization"
    assert seen[1] == "Bearer jina-key"


# ---- added ----


async def test_fetch_via_jina_reader_puts_target_url_after_the_endpoint_and_asks_for_plain_text() -> None:
    """URL đích nằm sau endpoint r.jina.ai và yêu cầu text/plain"""
    seen: list[httpx.Request] = []

    def spy(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text=JINA_BODY)

    await fetch_via_jina_reader(
        "https://minhngoc.net.vn/", JinaFetchOptions(max_chars=100, client=client_of(spy))
    )

    assert str(seen[0].url) == "https://r.jina.ai/https://minhngoc.net.vn/"
    assert seen[0].headers["accept"] == "text/plain"

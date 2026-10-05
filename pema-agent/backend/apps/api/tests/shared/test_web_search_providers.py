# ported from: src/shared/web-search-providers.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

``fetchFn`` of the original is an ``httpx.AsyncClient`` over ``httpx.MockTransport``: no real network.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import httpx

from pema.shared import web_search_providers as providers
from pema.shared.web_search_providers import (
    SearchOptions,
    SearchResult,
    parse_ddg_html,
    search_web,
    unwrap_ddg_redirect,
)

# Trích từ HTML thật của html.duckduckgo.com (rút gọn) - đúng selector result__a
DDG_HTML = """
<div class="result results_links results_links_deep web-result">
  <h2 class="result__title">
    <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fvnexpress.net%2Ftin-tuc&amp;rut=abc123">Tin tức <b>mới nhất</b></a>
  </h2>
  <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fvnexpress.net%2Ftin-tuc">Báo <b>VnExpress</b> - tin nhanh &amp; nóng</a>
</div>
<div class="result">
  <a rel="nofollow" class="result__a" href="https://tuoitre.vn/">Tuổi Trẻ Online</a>
  <a class="result__snippet" href="https://tuoitre.vn/">Tin tức 24h</a>
</div>"""


def json_response(body: Any) -> httpx.Response:
    return httpx.Response(200, json=body)


def client_of(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ------------------------------------------------------------------ parseDdgHtml + unwrapDdgRedirect


def test_parse_ddg_html_extracts_title_url_snippet_and_unwraps_uddg_redirect() -> None:
    """bóc title/url/snippet, giải redirect uddg về URL thật"""
    results = parse_ddg_html(DDG_HTML, 5)
    assert len(results) == 2
    assert results[0] == SearchResult(
        title="Tin tức mới nhất",
        url="https://vnexpress.net/tin-tuc",
        snippet="Báo VnExpress - tin nhanh & nóng",
    )
    assert results[1].url == "https://tuoitre.vn/"


def test_parse_ddg_html_respects_max_results() -> None:
    """tôn trọng maxResults"""
    assert len(parse_ddg_html(DDG_HTML, 1)) == 1


def test_parse_ddg_html_html_without_results_returns_empty_list_without_throwing() -> None:
    """HTML không có kết quả trả mảng rỗng, không throw"""
    assert parse_ddg_html("<html><body>No results.</body></html>", 5) == []


def test_parse_ddg_html_unwrap_ddg_redirect_keeps_plain_url() -> None:
    """unwrapDdgRedirect giữ nguyên URL thường"""
    assert unwrap_ddg_redirect("https://tuoitre.vn/") == "https://tuoitre.vn/"


# ---- added: edge cases of the redirect unwrapping ----


def test_unwrap_ddg_redirect_malformed_percent_sequence_keeps_raw_url() -> None:
    """chuỗi %-encode hỏng thì giữ nguyên URL (decodeURIComponent ném lỗi ở bản gốc)"""
    raw = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fa.vn%zz"
    assert unwrap_ddg_redirect(raw) == raw
    empty = "//duckduckgo.com/l/?uddg="
    assert unwrap_ddg_redirect(empty) == empty


# ------------------------------------------------------------------ searchWeb - chuỗi provider


async def test_search_web_without_brave_key_goes_straight_to_duckduckgo_by_post_form() -> None:
    """không có key Brave: đi thẳng DuckDuckGo bằng POST form (GET bị challenge)"""
    calls: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append({"url": str(request.url), "method": request.method, "body": request.content.decode()})
        return httpx.Response(200, text=DDG_HTML)

    results = await search_web("tin tức", SearchOptions(max_results=5, client=client_of(handler)))
    assert len(results) == 2
    assert len(calls) == 1
    assert "duckduckgo.com" in calls[0]["url"]
    assert calls[0]["method"] == "POST", "GET trần bị DDG trả trang challenge"
    assert "q=tin" in calls[0]["body"]


async def test_search_web_with_brave_key_brave_first_maps_results_correctly() -> None:
    """có key Brave: Brave trước, map đúng kết quả"""
    urls: list[str] = []
    tokens: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        tokens.append(request.headers.get("x-subscription-token", ""))
        return json_response(
            {
                "web": {
                    "results": [
                        {"title": "Kết quả <b>Brave</b>", "url": "https://a.vn", "description": "mô tả"}
                    ]
                }
            }
        )

    results = await search_web(
        "q", SearchOptions(max_results=5, brave_api_key="key", client=client_of(handler))
    )
    assert results == [SearchResult(title="Kết quả Brave", url="https://a.vn", snippet="mô tả")]
    assert "api.search.brave.com" in urls[0]
    assert tokens == ["key"]


async def test_search_web_brave_failure_quota_429_falls_back_to_duckduckgo_without_throwing() -> None:
    """Brave lỗi (hết quota 429) thì rơi về DuckDuckGo, không throw"""

    def handler(request: httpx.Request) -> httpx.Response:
        if "brave" in str(request.url):
            return httpx.Response(429, text="quota")
        return httpx.Response(200, text=DDG_HTML)

    results = await search_web(
        "q", SearchOptions(max_results=5, brave_api_key="key", client=client_of(handler))
    )
    assert len(results) == 2, "phải có kết quả từ DDG dù Brave chết"


async def test_search_web_all_providers_dead_returns_empty_list_not_thrown_to_agent() -> None:
    """mọi provider chết: trả mảng rỗng để tool tự diễn giải, không ném ra agent"""
    client = client_of(lambda _request: httpx.Response(500, text="die"))
    results = await search_web("q", SearchOptions(max_results=5, brave_api_key="key", client=client))
    assert results == []


# ---- added ----


async def test_search_web_brave_with_no_results_falls_through_to_duckduckgo() -> None:
    """Brave trả rỗng thì thử DuckDuckGo"""

    def handler(request: httpx.Request) -> httpx.Response:
        if "brave" in str(request.url):
            return json_response({"web": {"results": []}})
        return httpx.Response(200, text=DDG_HTML)

    results = await search_web(
        "q", SearchOptions(max_results=5, brave_api_key="key", client=client_of(handler))
    )
    assert len(results) == 2


async def test_search_web_brave_junk_json_does_not_throw_and_falls_back() -> None:
    """Brave trả JSON lạ hình dạng thì không ném lỗi, rơi về DuckDuckGo"""

    def handler(request: httpx.Request) -> httpx.Response:
        if "brave" in str(request.url):
            return json_response(["không", "phải", "object"])
        return httpx.Response(200, text=DDG_HTML)

    results = await search_web(
        "q", SearchOptions(max_results=5, brave_api_key="key", client=client_of(handler))
    )
    assert len(results) == 2


async def test_search_web_total_deadline_cuts_a_hanging_provider(monkeypatch: Any) -> None:
    """provider treo thì bị cắt bởi timeout tổng, kết quả rỗng thay vì treo agent"""
    monkeypatch.setattr(providers, "TIMEOUT_MS", 20)
    never = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await never.wait()
        return httpx.Response(200, text=DDG_HTML)

    results = await search_web(
        "q", SearchOptions(max_results=5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    )
    assert results == []

# ported from: src/shared/web-search-providers.ts
"""Web search cho agent theo pattern chuỗi provider của GoClaw/Hermes: Brave trước khi có key (kết quả
tốt hơn, free tier 2000 query/tháng), DuckDuckGo LUÔN đứng cuối - không cần key, nên web search không bao
giờ "chưa cấu hình". Provider lỗi thì rơi xuống provider sau, không ném ra agent.

``client`` tiêm được để test không chạm mạng thật.

Clinic note: every query leaves the infrastructure for a third party (Brave, DuckDuckGo). In the
``patient_channel`` policy profile the web tools are switched off by the policy layer; the feature is kept.

Forced deviations from the TypeScript original:

* ``fetchFn?: typeof fetch`` -> ``client: httpx.AsyncClient | None`` (tests pass a client over
  ``httpx.MockTransport``). Without one, a client is created per call and redirects are followed, like
  ``fetch``.
* ``AbortSignal.timeout(TIMEOUT_MS)`` -> ``asyncio.timeout`` around the whole call (headers and body), so the
  ceiling stays a TOTAL one and not httpx's per-phase timeout.
* The search QUERY is never logged (the original logged it at debug level): in the clinic a query can contain
  a patient's words. Logs carry provider names, statuses and error types only.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import unquote

import httpx

from pema.shared.html_to_text import strip_html_tags
from pema.shared.logger import create_logger

log = create_logger("web-search")

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
DDG_ENDPOINT = "https://html.duckduckgo.com/html/"
# DDG chặn UA rỗng/lạ; UA trình duyệt phổ thông là đủ
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)
TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass(frozen=True)
class SearchOptions:
    max_results: int
    brave_api_key: str | None = None
    client: httpx.AsyncClient | None = None


class SearchProviderError(Exception):
    """A provider answered with an error status (the ``throw new Error(...)`` of the original)."""


_MALFORMED_PERCENT = re.compile(r"%(?![0-9A-Fa-f]{2})")


def unwrap_ddg_redirect(raw_url: str) -> str:
    """DDG bọc link kết quả qua trang redirect: /l/?uddg=<url-encoded>&rut=... Bóc URL thật ra để agent không
    phải đi vòng."""
    if "uddg=" not in raw_url:
        return raw_url
    # decodeURIComponent throws on a malformed percent sequence; Python's unquote would leave it in place
    if _MALFORMED_PERCENT.search(raw_url):
        return raw_url
    try:
        decoded = unquote(raw_url, errors="strict")
    except UnicodeDecodeError:
        return raw_url
    parts = decoded.split("uddg=")
    after = parts[1] if len(parts) > 1 else ""
    if not after:
        return raw_url
    amp = after.find("&")
    return after if amp == -1 else after[:amp]


_LINK_RE = re.compile(r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>')
_SNIPPET_RE = re.compile(r'<a[^>]*class="result__snippet[^"]*"[^>]*>([\s\S]*?)</a>')


def parse_ddg_html(html: str, max_results: int) -> list[SearchResult]:
    """Parse HTML kết quả DDG (selector result__a / result__snippet như GoClaw dùng)."""
    snippets = [strip_html_tags(m.group(1)) for m in _SNIPPET_RE.finditer(html)]
    results: list[SearchResult] = []
    for match in _LINK_RE.finditer(html):
        if len(results) >= max_results:
            break
        index = len(results)
        results.append(
            SearchResult(
                title=strip_html_tags(match.group(2)),
                url=unwrap_ddg_redirect(match.group(1)),
                snippet=snippets[index] if index < len(snippets) else "",
            )
        )
    return results


async def _request(client: httpx.AsyncClient | None, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """``fetchWithTimeout``: one total deadline of ``TIMEOUT_MS`` for the whole exchange."""
    async with asyncio.timeout(TIMEOUT_MS / 1000):
        if client is not None:
            return await client.request(method, url, follow_redirects=True, **kwargs)
        async with httpx.AsyncClient(follow_redirects=True) as own:
            return await own.request(method, url, **kwargs)


def _text(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _brave_items(body: object) -> list[dict[str, Any]]:
    """``body.web?.results ?? []``, tolerant of any JSON shape (a provider change must not throw)."""
    if not isinstance(body, dict):
        return []
    web = cast("dict[str, Any]", body).get("web")
    if not isinstance(web, dict):
        return []
    raw = cast("dict[str, Any]", web).get("results")
    if not isinstance(raw, list):
        return []
    return [cast("dict[str, Any]", item) for item in cast("list[Any]", raw) if isinstance(item, dict)]


async def _search_brave(query: str, opts: SearchOptions) -> list[SearchResult]:
    res = await _request(
        opts.client,
        "GET",
        BRAVE_ENDPOINT,
        params={"q": query, "count": str(opts.max_results)},
        headers={"Accept": "application/json", "X-Subscription-Token": opts.brave_api_key or ""},
    )
    if not res.is_success:
        raise SearchProviderError(f"Brave API trả HTTP {res.status_code}")

    items = _brave_items(res.json())
    found: list[SearchResult] = []
    for item in items:
        if not item.get("url"):
            continue
        found.append(
            SearchResult(
                title=strip_html_tags(_text(item.get("title"))),
                url=_text(item.get("url")),
                snippet=strip_html_tags(_text(item.get("description"))),
            )
        )
    return found[: opts.max_results]


async def _search_duckduckgo(query: str, opts: SearchOptions) -> list[SearchResult]:
    # PHẢI là POST form: GET trần bị DDG trả 202 + trang challenge (kiểm chứng
    # 07/2026). POST là cách form HTML chính thức của trang này submit - vẫn là
    # endpoint public cho client không chạy JS.
    res = await _request(
        opts.client,
        "POST",
        DDG_ENDPOINT,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
        },
        data={"q": query, "b": ""},
    )
    if not res.is_success:
        raise SearchProviderError(f"DuckDuckGo trả HTTP {res.status_code}")
    return parse_ddg_html(res.text, opts.max_results)


async def search_web(query: str, opts: SearchOptions) -> list[SearchResult]:
    """Chuỗi tìm kiếm: Brave (khi có key) -> DuckDuckGo. Trả list rỗng khi mọi provider đều lỗi - caller
    (tool) tự diễn giải cho model, không throw."""
    if opts.brave_api_key:
        try:
            results = await _search_brave(query, opts)
            if results:
                return results
            log.debug("Brave không có kết quả - thử DuckDuckGo")
        except Exception as err:
            log.warning("Brave search lỗi - rơi về DuckDuckGo", err=err)

    try:
        return await _search_duckduckgo(query, opts)
    except Exception as err:
        log.warning("DuckDuckGo search lỗi", err=err)
        return []

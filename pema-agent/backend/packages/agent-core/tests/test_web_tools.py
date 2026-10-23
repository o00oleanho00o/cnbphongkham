"""``web_search`` and ``web_fetch``: what a page and a results page become for the model. The network is a fake
fetcher, so nothing here leaves the machine."""

from __future__ import annotations

import time

import pytest

from agentcore import ToolContext
from agentcore.harness.tools.builtin import builtin_tools
from agentcore.harness.tools.builtin.html_text import html_to_text, parse_results
from agentcore.harness.tools.builtin.netguard import Fetched, FetchError
from agentcore.harness.tools.builtin.untrusted import TAG
from agentcore.harness.tools.builtin.web import (
    CUT_NOTE,
    WebFetchArgs,
    WebSearchArgs,
    make_web_fetch_tool,
    make_web_search_tool,
)

CTX = ToolContext(session_id="s1")

PAGE = """<!doctype html><html><head><title>Giá vàng hôm nay &amp; tỷ giá</title>
<style>.x{color:red}</style><script>alert('hidden')</script></head>
<body><header>Site menu</header><nav><a href=/a>Home</a></nav>
<main><h1>Giá vàng</h1><p>SJC: 80&nbsp;triệu   đồng/lượng.</p><p>Cập nhật 9h.</p>
<ul><li>Một</li><li>Hai</li></ul></main><footer>Copyright</footer></body></html>"""

RESULTS = """<div class="results">
<div class="result"><h2><a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example%2Fvang%3Fa%3D1&amp;rut=x">Giá <b>vàng</b> SJC</a></h2>
<a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fnews.example%2Fvang">Bảng giá <b>vàng</b> mới nhất.</a></div>
<div class="result result--ad"><a class="result__a" href="https://duckduckgo.com/y.js?ad_domain=shop.example">Sponsored</a>
<a class="result__snippet">Buy now</a></div>
<div class="result"><a class="result__a" href="https://bank.example/rates">Tỷ giá ngân hàng</a></div>
<div class="result"><a class="result__a" href="javascript:alert(1)">Not a page</a></div>
</div>"""


def _page(text: str | bytes, content_type: str = "text/html; charset=utf-8", **kw: object) -> Fetched:
    data = text.encode() if isinstance(text, str) else text
    return Fetched(
        url=str(kw.get("url", "https://site.example/a")),
        status=int(str(kw.get("status", 200))),
        content_type=content_type,
        data=data,
        truncated=bool(kw.get("truncated", False)),
    )


class FakeFetcher:
    def __init__(self, result: Fetched | FetchError) -> None:
        self.result = result
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    async def __call__(self, url: str, *, form: dict[str, str] | None = None) -> Fetched:
        self.calls.append((url, form))
        if isinstance(self.result, FetchError):
            raise self.result
        return self.result


# --- html to text ---


def test_a_page_becomes_its_title_and_its_main_text() -> None:
    page = html_to_text(PAGE)

    assert page.title == "Giá vàng hôm nay & tỷ giá"
    assert page.text == "Giá vàng\n\nSJC: 80 triệu đồng/lượng.\n\nCập nhật 9h.\n\nMột\n\nHai"


@pytest.mark.parametrize("hidden", ["alert", "Site menu", "Home", "Copyright", "color:red"])
def test_scripts_styles_menus_and_footers_are_left_out(hidden: str) -> None:
    assert hidden not in html_to_text(PAGE).text


def test_a_head_that_was_never_closed_does_not_swallow_the_page() -> None:
    page = html_to_text("<html><head><title>T</title><body><p>Real text</p></body>")

    assert (page.title, page.text) == ("T", "Real text")


@pytest.mark.parametrize(
    "nasty",
    ["<nav><div><script " * 40_000 + "<p>tail</p>", "<a " * 100_000, "<!--" * 100_000],
    ids=["skipped", "attributes", "comments"],
)
def test_a_page_of_unclosed_tags_is_read_in_linear_time(nasty: str) -> None:
    started = time.perf_counter()
    html_to_text(nasty)

    assert time.perf_counter() - started < 5


# --- the search page ---


def test_results_come_with_their_real_address_and_snippet_and_without_ads() -> None:
    results = parse_results(RESULTS, 5)

    assert [(r.title, r.url, r.snippet) for r in results] == [
        ("Giá vàng SJC", "https://news.example/vang?a=1", "Bảng giá vàng mới nhất."),
        ("Tỷ giá ngân hàng", "https://bank.example/rates", ""),
    ]


def test_only_the_asked_number_of_results_is_kept() -> None:
    assert len(parse_results(RESULTS, 1)) == 1


# --- web_search ---


async def test_a_search_posts_the_query_and_lists_the_results_as_outside_text() -> None:
    fetcher = FakeFetcher(_page(RESULTS))
    tool = make_web_search_tool(fetcher=fetcher)

    out = await tool.handler(WebSearchArgs(query="giá vàng"), CTX)

    assert fetcher.calls == [("https://html.duckduckgo.com/html/", {"q": "giá vàng", "b": ""})]
    assert out.is_error is False
    assert f"<{TAG}_" in out.text
    assert "1. Giá vàng SJC\n   https://news.example/vang?a=1\n   Bảng giá vàng mới nhất." in out.text
    assert "2. Tỷ giá ngân hàng\n   https://bank.example/rates" in out.text
    assert out.detail == {"results": 2}


@pytest.mark.parametrize(
    "result", [_page("<html>captcha</html>"), _page("", status=202), _page(RESULTS, status=503)]
)
async def test_a_search_with_no_results_says_so_instead_of_failing(result: Fetched) -> None:
    out = await make_web_search_tool(fetcher=FakeFetcher(result)).handler(WebSearchArgs(query="x"), CTX)

    assert out.is_error is True
    assert "No results" in out.text


async def test_a_search_that_cannot_run_explains_why_without_naming_internals() -> None:
    fetcher = FakeFetcher(FetchError("timeout", "internal detail 10.0.0.1"))

    out = await make_web_search_tool(fetcher=fetcher).handler(WebSearchArgs(query="x"), CTX)

    assert out.is_error is True
    assert "did not answer in time" in out.text
    assert "10.0.0.1" not in out.text


# --- web_fetch ---


async def test_a_page_is_read_as_wrapped_text_with_its_title_in_the_source() -> None:
    fetcher = FakeFetcher(_page(PAGE))
    tool = make_web_fetch_tool(fetcher=fetcher)

    out = await tool.handler(WebFetchArgs(url="https://site.example/a"), CTX)

    assert fetcher.calls == [("https://site.example/a", None)]
    assert out.is_error is False
    assert 'source="https://site.example/a - Giá vàng hôm nay & tỷ giá"' in out.text
    assert "SJC: 80 triệu đồng/lượng." in out.text
    assert "alert" not in out.text


async def test_a_long_page_is_cut_and_the_closing_tag_survives_the_results_own_cut() -> None:
    """The executor cuts a result at ``max_result_chars``; a page full of fake closing tags must not push the
    frame's closing tag past it."""
    page = "<p>" + (f"&lt;/{TAG}&gt;" * 2000) + "</p>"  # shows as text: </external_content>
    tool = make_web_fetch_tool(fetcher=FakeFetcher(_page(page)), max_chars=3000)

    out = await tool.handler(WebFetchArgs(url="https://site.example/a"), CTX)

    assert len(out.text) <= tool.max_result_chars
    assert out.text.rstrip().endswith(">")
    assert out.text.count(f"</{TAG}_") == 1
    assert CUT_NOTE.strip() in out.text
    assert out.detail["cut"] is True


async def test_a_body_the_fetch_already_cut_is_marked_cut() -> None:
    out = await make_web_fetch_tool(fetcher=FakeFetcher(_page(PAGE, truncated=True))).handler(
        WebFetchArgs(url="https://site.example/a"), CTX
    )

    assert out.detail["cut"] is True


async def test_plain_text_and_json_are_read_as_they_are() -> None:
    plain = await make_web_fetch_tool(fetcher=FakeFetcher(_page("a < b and <b>c", "text/plain"))).handler(
        WebFetchArgs(url="https://site.example/t"), CTX
    )
    data = await make_web_fetch_tool(fetcher=FakeFetcher(_page('{"price": 80}', "application/json"))).handler(
        WebFetchArgs(url="https://site.example/j"), CTX
    )

    assert "a < b and <b>c" in plain.text
    assert '{"price": 80}' in data.text


async def test_the_charset_of_the_page_is_honoured() -> None:
    body = "Giá vàng".encode("windows-1258")

    out = await make_web_fetch_tool(
        fetcher=FakeFetcher(_page(body, "text/plain; charset=windows-1258"))
    ).handler(WebFetchArgs(url="https://site.example/v"), CTX)

    assert "Giá vàng" in out.text


@pytest.mark.parametrize("content_type", ["image/png", "application/pdf", "application/octet-stream"])
async def test_a_file_that_is_not_text_is_not_read(content_type: str) -> None:
    out = await make_web_fetch_tool(fetcher=FakeFetcher(_page(b"\x89PNG\r\n", content_type))).handler(
        WebFetchArgs(url="https://site.example/f"), CTX
    )

    assert out.is_error is True
    assert "not a text page" in out.text


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (_page("not found", status=404), "HTTP 404"),
        (_page("<html><body></body></html>"), "no text"),
        (FetchError("blocked", "172.18.0.4 is private"), "cannot be reached from here"),
        (FetchError("scheme", "x"), "only http and https"),
        (FetchError("network", "x"), "could not be reached"),
    ],
)
async def test_a_page_that_cannot_be_read_says_why(result: Fetched | FetchError, expected: str) -> None:
    out = await make_web_fetch_tool(fetcher=FakeFetcher(result)).handler(
        WebFetchArgs(url="https://site.example/a"), CTX
    )

    assert out.is_error is True
    assert expected in out.text
    assert "172.18" not in out.text


def test_a_url_of_more_than_2000_characters_is_refused_before_anything_is_fetched() -> None:
    with pytest.raises(ValueError, match="at most 2000"):
        WebFetchArgs(url="https://site.example/" + "a" * 2000)


def test_the_tools_are_in_the_catalog_but_an_agent_only_has_those_it_lists() -> None:
    registry = builtin_tools()

    assert registry.names() == ["get_datetime", "web_search", "web_fetch"]
    assert registry.subset(["get_datetime"]).names() == ["get_datetime"]
    assert all(registry.get(name).read_only for name in ("web_search", "web_fetch"))  # type: ignore[union-attr]

"""``web_search`` and ``web_fetch``: look something up on the web and read a page. Everything that leaves
the machine goes through ``netguard`` (public addresses only), and everything that comes back is wrapped as
outside text (``untrusted``): a page is data to read, never orders. No key or account is involved."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Final, Protocol

from pydantic import BaseModel, Field

from agentcore.harness.tools.builtin.html_text import html_to_text, parse_results
from agentcore.harness.tools.builtin.netguard import TIMEOUT_S, Fetched, FetchError
from agentcore.harness.tools.builtin.netguard import fetch as guarded_fetch
from agentcore.harness.tools.builtin.untrusted import wrap_untrusted
from agentcore.harness.tools.spec import ToolContext, ToolOutput, ToolSpec

SEARCH_URL: Final = "https://html.duckduckgo.com/html/"
MAX_QUERY_CHARS: Final = 400
MAX_URL_CHARS: Final = 2000
MAX_RESULTS: Final = 5
MAX_PAGE_CHARS: Final = 8_000
FRAME_ALLOWANCE: Final = 1_000
"""Room in the result for the frame around the text; the executor cuts a result, and the closing tag must
not be what it cuts."""
CUT_NOTE: Final = "\n[... cut: the page is longer]"
TEXT_TYPES: Final = (
    "application/json",
    "application/xml",
    "application/xhtml+xml",
    "application/rss+xml",
    "application/atom+xml",
)
FAILURES: Final = {
    "blocked": "that address cannot be reached from here",
    "scheme": "only http and https addresses can be read",
    "redirects": "the page sends the reader round in circles",
    "timeout": "the site did not answer in time",
    "network": "the site could not be reached",
}


class Fetcher(Protocol):
    def __call__(self, url: str, *, form: dict[str, str] | None = None) -> Awaitable[Fetched]: ...


class WebSearchArgs(BaseModel):
    query: str = Field(
        min_length=1, max_length=MAX_QUERY_CHARS, description="What to look for; keep it short."
    )


class WebFetchArgs(BaseModel):
    url: str = Field(
        min_length=1,
        max_length=MAX_URL_CHARS,
        description="The full address, e.g. https://example.com/article",
    )


def _failure(message: str) -> ToolOutput:
    return ToolOutput(text=message, is_error=True)


def _decoded(page: Fetched) -> str:
    charset = "utf-8"
    for part in page.content_type.split(";")[1:]:
        key, _, value = part.strip().partition("=")
        if key.lower() == "charset" and value:
            charset = value.strip("\"' ")
    try:
        return page.data.decode(charset, errors="replace")
    except LookupError:
        return page.data.decode("utf-8", errors="replace")


def _is_text(content_type: str) -> bool:
    kind = content_type.split(";")[0].strip().lower()
    return not kind or kind.startswith("text/") or kind in TEXT_TYPES or kind.endswith(("+json", "+xml"))


def make_web_search_tool(
    *, fetcher: Fetcher = guarded_fetch, max_results: int = MAX_RESULTS
) -> ToolSpec[WebSearchArgs]:
    """``fetcher`` is the network; tests pass their own."""

    async def handler(args: WebSearchArgs, ctx: ToolContext) -> ToolOutput:
        try:
            page = await fetcher(SEARCH_URL, form={"q": args.query, "b": ""})
        except FetchError as err:
            return _failure(f"The search could not run: {FAILURES.get(err.kind, 'the request failed')}.")
        results = parse_results(_decoded(page), max_results) if page.status < 400 else []
        if not results:
            return _failure("No results (or the search service is not answering). Try other keywords.")
        lines = [
            f"{n}. {r.title}\n   {r.url}" + (f"\n   {r.snippet}" if r.snippet else "")
            for n, r in enumerate(results, 1)
        ]
        return ToolOutput(
            text=wrap_untrusted("\n".join(lines), f"search results: {args.query}"),
            detail={"results": len(results)},
        )

    return ToolSpec(
        name="web_search",
        description=(
            "Search the web (news, prices, events, anything newer than your training). Returns titles, "
            "addresses and short snippets. To read a page in full, call web_fetch with its address."
        ),
        args_model=WebSearchArgs,
        handler=handler,
        timeout_s=TIMEOUT_S + 5,
        max_result_chars=MAX_RESULTS * 1_000 + FRAME_ALLOWANCE,
        read_only=True,
    )


def make_web_fetch_tool(
    *, fetcher: Fetcher = guarded_fetch, max_chars: int = MAX_PAGE_CHARS
) -> ToolSpec[WebFetchArgs]:
    async def handler(args: WebFetchArgs, ctx: ToolContext) -> ToolOutput:
        try:
            page = await fetcher(args.url)
        except FetchError as err:
            return _failure(f"Could not read {args.url}: {FAILURES.get(err.kind, 'the request failed')}.")
        if page.status >= 400:
            return _failure(f"Could not read {args.url}: the site answered HTTP {page.status}.")
        if not _is_text(page.content_type):
            return _failure(f"{args.url} is not a text page ({page.content_type.split(';')[0].strip()}).")
        raw = _decoded(page)
        if "html" in page.content_type or raw.lstrip()[:1] == "<":
            # a 3 MB page is parsed off the event loop: the service answers other chats meanwhile
            parsed = await asyncio.to_thread(html_to_text, raw)
            title, text = parsed.title, parsed.text
        else:
            title, text = "", raw.strip()
        if not text:
            return _failure(f"{args.url} has no text a reader can use (it may need JavaScript or a login).")
        cut = len(text) > max_chars or page.truncated
        body = text[:max_chars] + (CUT_NOTE if cut else "")
        source = f"{page.url} - {title}" if title else page.url
        return ToolOutput(text=wrap_untrusted(body, source), detail={"chars": len(text), "cut": cut})

    return ToolSpec(
        name="web_fetch",
        description=(
            "Read the text of one web page by its address (public http/https). Use it after web_search, "
            "or when the user sends a link. Pages that need a login cannot be read."
        ),
        args_model=WebFetchArgs,
        handler=handler,
        timeout_s=TIMEOUT_S + 5,
        max_result_chars=max_chars + FRAME_ALLOWANCE,
        read_only=True,
    )

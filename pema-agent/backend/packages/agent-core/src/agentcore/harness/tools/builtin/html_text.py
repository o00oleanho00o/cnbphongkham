"""Readable text out of an HTML page, and the results out of a DuckDuckGo results page. Standard library
only. ``html.parser`` is quadratic on tags that never close, so comments are dropped and a ``<`` with no
``>`` before the next ``<`` is turned into text first; a 3 MB page of unclosed tags then costs about as much
as any other.

shortcut: no filter for link-dense lists (menus) beyond dropping nav, header, footer and aside; add one if
pages show only their menu to the model.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

SKIP: frozenset[str] = frozenset(
    {
        "script",
        "style",
        "noscript",
        "svg",
        "head",
        "nav",
        "footer",
        "aside",
        "form",
        "select",
        "iframe",
        "template",
        "header",
    }
)
BREAK: frozenset[str] = frozenset(
    {
        "p",
        "div",
        "br",
        "li",
        "ul",
        "ol",
        "tr",
        "table",
        "section",
        "article",
        "main",
        "blockquote",
        "pre",
        "hr",
        "dt",
        "dd",
        "figure",
        "figcaption",
        "details",
        "summary",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }
)
SPACES = re.compile(r"[ \t\r\f\v ]+")
BLANK_LINES = re.compile(r"\n{3,}")
UNCLOSED = re.compile(r"<(?![^<>]{1,20000}>)")
SEARCH_HOST = "duckduckgo.com"


@dataclass(frozen=True, slots=True)
class Page:
    title: str
    text: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    title: str
    url: str
    snippet: str


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title = ""
        self._skipping = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        elif tag == "body":
            self._skipping = 0  # a head that was never closed ends here
        if tag in SKIP:
            self._skipping += 1
        elif tag in BREAK and not self._skipping:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        if tag in SKIP:
            self._skipping = max(0, self._skipping - 1)
        elif tag in BREAK and not self._skipping:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        elif not self._skipping:
            self.parts.append(data)


def _untangle(html: str) -> str:
    """Comments out (an unclosed one hides the rest, as in a browser), then a ``<`` with no ``>`` before the
    next ``<`` as text. Comments go first, or the markup inside one would be read as the page."""
    parts: list[str] = []
    at = 0
    while (start := html.find("<!--", at)) != -1:
        parts.append(html[at:start])
        end = html.find("-->", start + 4)
        at = len(html) if end == -1 else end + 3
    parts.append(html[at:])
    return UNCLOSED.sub("&lt;", "".join(parts))


def html_to_text(html: str) -> Page:
    reader = _Reader()
    reader.feed(_untangle(html))
    reader.close()
    lines = (SPACES.sub(" ", line).strip() for line in "".join(reader.parts).split("\n"))
    text = BLANK_LINES.sub("\n\n", "\n".join(lines)).strip()
    return Page(title=SPACES.sub(" ", reader.title).strip(), text=text)


class _Results(HTMLParser):
    """``a.result__a`` is a result's title and address, ``a.result__snippet`` its description."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[SearchResult] = []
        self._capture: str | None = None
        self._href = ""
        self._text: list[str] = []
        self._snippets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        values = dict(attrs)
        classes = (values.get("class") or "").split()
        if "result__a" in classes:
            self._capture, self._href, self._text = "title", values.get("href") or "", []
        elif "result__snippet" in classes:
            self._capture, self._text = "snippet", []

    def handle_data(self, data: str) -> None:
        if self._capture is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "a" or self._capture is None:
            return
        text = SPACES.sub(" ", "".join(self._text)).strip()
        if self._capture == "title":
            self.results.append(SearchResult(title=text, url=_target(self._href), snippet=""))
        elif self.results and not self.results[-1].snippet:
            last = self.results[-1]
            self.results[-1] = SearchResult(last.title, last.url, text)
        self._capture = None


def _target(href: str) -> str:
    """DuckDuckGo wraps each address in a redirect page (``/l/?uddg=<address>``); the address itself."""
    wrapped = parse_qs(urlsplit(href).query).get("uddg")
    return wrapped[0] if wrapped else href


def parse_results(html: str, limit: int) -> list[SearchResult]:
    """The first ``limit`` results with an http(s) address of their own (ads and the search engine's own
    pages are left out)."""
    parser = _Results()
    parser.feed(_untangle(html))
    parser.close()
    kept = [
        result
        for result in parser.results
        if result.title
        and urlsplit(result.url).scheme in ("http", "https")
        and (urlsplit(result.url).hostname or "") not in (SEARCH_HOST, f"www.{SEARCH_HOST}")
    ]
    return kept[:limit]

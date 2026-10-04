# ported from: src/agent/llm-response-sanitizer.ts
"""Defence against a faulty response from the router proxy (9Router): in some cases the router answers a
NON-streaming request with a complete JSON body that carries an extra SSE trailer ``data: [DONE]`` (and the
header content-type: text/event-stream). The SDK's JSON parse then fails at the first character after the
closing ``}`` - the whole agent turn dies although the answer was generated and the tokens were spent.

Forced deviation: the original wraps ``fetch`` for the AI SDK provider (``createSanitizingFetch``). The
``openai``/``anthropic`` Python SDKs sit on an HTTP client, so the wrapper becomes an async TRANSPORT wrapper
(``create_sanitizing_transport``) handed to the SDK's HTTP client. The transport class must come from the
SAME HTTP library as the SDK (``httpx2`` on recent releases), hence ``http_flavour``.

This module imports no env/logger so that a test can import it statically.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from pema.agent.providers.http_flavour import http

SSE_DONE_TRAILER = re.compile(r"(?:\s*data:\s*\[DONE\]\s*)+\Z")
_STREAM_TRUE = re.compile(r'"stream"\s*:\s*true')


def _reject_constant(name: str) -> Any:
    """``JSON.parse`` refuses NaN/Infinity, Python's ``json`` accepts them: refuse here too."""
    raise ValueError(name)


def strip_sse_done_trailer(body: str) -> str | None:
    """Cut the ``data: [DONE]`` trailer when what remains is a complete JSON object.

    Returns the cleaned body, or None when the body does not match exactly this faulty case (no trailer,
    or the rest is not JSON - e.g. a real SSE stream).
    """
    if SSE_DONE_TRAILER.search(body) is None:
        return None

    cleaned = SSE_DONE_TRAILER.sub("", body, count=1).strip()
    # A real SSE stream looks like "data: {...}\n\ndata: [DONE]" - after cutting the trailer the rest starts
    # with "data:", not "{" -> leave it alone
    if not cleaned.startswith("{"):
        return None

    try:
        json.loads(cleaned, parse_constant=_reject_constant)
    except ValueError:
        return None
    return cleaned


class _SanitizingTransport(http.AsyncBaseTransport):
    def __init__(self, base: Any, on_sanitized: Callable[[], None] | None) -> None:
        self._base = base
        self._on_sanitized = on_sanitized

    async def handle_async_request(self, request: Any) -> Any:
        res = await self._base.handle_async_request(request)
        if not res.is_success:
            return res
        if _STREAM_TRUE.search(_request_text(request)) is not None:
            return res

        await res.aread()
        text: str = res.text
        cleaned = strip_sse_done_trailer(text)

        # The body has been read so the response must be rebuilt whether or not it was fixed. Drop
        # content-length/content-encoding: the client already decoded the body, keeping the old headers
        # would disagree with the new body.
        headers = http.Headers(res.headers)
        for name in ("content-length", "content-encoding"):
            if name in headers:
                del headers[name]
        if cleaned is not None:
            headers["content-type"] = "application/json; charset=utf-8"
            if self._on_sanitized is not None:
                self._on_sanitized()

        return http.Response(
            status_code=res.status_code,
            headers=headers,
            content=cleaned.encode("utf-8") if cleaned is not None else res.content,
            request=request,
            extensions=res.extensions,
        )

    async def aclose(self) -> None:
        await self._base.aclose()


def _request_text(request: Any) -> str:
    """The request body as text, or "" when it is a stream that has not been read (then it is not a plain
    JSON body to look into)."""
    try:
        content: bytes = request.content
    except http.RequestNotRead:
        return ""
    return content.decode("utf-8", errors="replace")


def create_sanitizing_transport(*, base: Any, on_sanitized: Callable[[], None] | None = None) -> Any:
    """Wrap an async HTTP transport for the SDK client: any non-streaming response that carries the SSE
    trailer is cut clean and returned as ordinary JSON. A real streaming response (the request has
    ``"stream": true``) is not touched - reading the body here would break the stream.

    ``base`` is the transport to wrap (the SDK's default one, or a mock transport in tests);
    ``on_sanitized`` is called when a faulty response was detected and fixed - used to log a warning.
    """
    return _SanitizingTransport(base, on_sanitized)

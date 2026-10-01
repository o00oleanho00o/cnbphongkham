# ported from: none (glue for the ``openai`` / ``anthropic`` SDKs; there is no counterpart in zalo-agent)
"""Which HTTP library the installed LLM SDKs are built on.

Recent ``openai`` and ``anthropic`` releases moved from ``httpx`` to the ``httpx2`` fork; older releases (the
``>=1.54`` floor of ``pyproject``) still use ``httpx``. A custom transport handed to an SDK client (a test
``MockTransport``, the router response sanitizer) must come from the SAME library as the client, so code that
builds one asks this module instead of importing a fixed name. The module is typed ``Any`` on purpose: the two
libraries have the same API but unrelated classes, which no static type can express.
"""

from __future__ import annotations

from typing import Any


def _load() -> Any:
    try:
        import httpx2  # pyright: ignore[reportMissingImports]

        return httpx2
    except ImportError:  # pragma: no cover - only on an older SDK
        import httpx

        return httpx


http: Any = _load()
"""``httpx2`` when the SDKs use it, else ``httpx``: ``http.AsyncClient``, ``http.MockTransport``, ..."""

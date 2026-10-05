# ported from: src/agent/cache-session-id.ts
"""A stable per-thread session key, sent to the router through the ``x-session-id`` header to turn prompt
caching on.

No forced deviation (``node:crypto`` sha256 becomes ``hashlib``).

Why it is needed (read from the 9Router source, open-sse/utils/sessionManager.js): the router derives the
cache key in this order - the ``x-session-id`` header first, then ``body.prompt_cache_key``, then a FALLBACK
that hashes the text of the assistant in the request. A client that sends nothing falls into that fallback,
and the assistant text GROWS after every answer -> a different hash every turn -> upstream sees a new
session -> the cache never hits (measured: CACHED TOKENS = 0 on 181k input tokens).

The header is the COMMON path for every provider, not only OpenAI:
- codex.js / grok-cli.js: poured into the upstream ``prompt_cache_key``
- claude.js (Anthropic): keeps the fingerprint consistent while cloaking; the router injects
  ``cache_control`` itself, the client need not
- kiro / antigravity: session identity
- ordinary providers (DeepSeek, Groq...): ignored, harmless

PURE module, imports no env - the caller passes the configuration in.
"""

from __future__ import annotations

import hashlib

CACHE_SESSION_HEADER = "x-session-id"
"""The header name the router reads FIRST (``SESSION_HEADER_KEYS`` in sessionManager.js)."""


def cache_session_id(account_id: str, thread_id: str, epoch: int = 0) -> str:
    """A stable key for 1 thread of 1 account. Hashed instead of joined plainly: the Zalo thread id is a
    real user identifier and should not leak into the router's log/telemetry. The same thread always gives
    the same key, a different thread surely gives a different one.

    ``epoch`` is the number of times the thread context was wiped (column ``threads.context_epoch``). It is
    inside the hash so that every wipe opens a NEW SESSION with the router: without it a wipe still sends
    the old key and the router keeps the cached prefix of the conversation that was just deleted. The same
    way goclaw calls ``ResetCLISession`` after /reset and Hermes rotates ``session_id``. Default 0 so every
    old call site keeps its key.
    """
    digest = hashlib.sha256(f"{account_id}:{thread_id}:{epoch}".encode()).hexdigest()
    return f"zalo-agent-{digest[:32]}"


def cache_session_headers(enabled: bool, account_id: str, thread_id: str, epoch: int = 0) -> dict[str, str]:
    """Headers that go with the LLM request. Returns an empty dict when off so the caller can spread it
    straight into the provider configuration without an ``if``."""
    if not enabled or not account_id or not thread_id:
        return {}
    return {CACHE_SESSION_HEADER: cache_session_id(account_id, thread_id, epoch)}

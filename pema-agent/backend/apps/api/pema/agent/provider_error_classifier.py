# ported from: src/agent/provider-error-classifier.ts
"""Classify a provider error so every kind is cured the right way.

Forced deviation (Vercel AI SDK -> own loop + official SDKs): ``APICallError.isInstance`` and
``RetryError.lastError`` of the SDK become DUCK TYPING, so no SDK type is imported here:

* the exception the adapters raise (``ProviderCallError``: ``status_code``, ``response_headers``,
  ``response_body``), and any other exception or mapping exposing ``status_code`` / ``statusCode`` /
  ``status`` and, for the ``Retry-After`` header, ``response_headers`` / ``responseHeaders`` /
  ``response.headers``;
* the ``__cause__`` chain: the loop (and any retry helper) wraps the last provider error in another
  exception; the original read ``RetryError.lastError`` first, here the first error of the chain that
  carries a status code is read, and the ``last_error`` attribute of a retry wrapper when there is one.
  For the NETWORK signs the original read ``cause.message`` (``TypeError: fetch failed`` with an
  ``ECONNREFUSED`` cause); here the whole chain of messages is read;
* ``TimeoutError`` / ``ConnectionError`` (and the well-known network exception names of httpx / openai /
  anthropic) are network signs in the chain, in place of the Node socket error codes of the phrase list;
* ``LoiCauHinhLlm`` stays recognised by its shape (``llm_config_error``).

The step that must not be forgotten (kept from the original): with every error the SDK treats as retryable
(429, 5xx) what comes out of the call is NOT the provider error but a wrapper ("Failed after 3 attempts. Last
error: ..."), which carries no status code, so a classifier reading the top error directly would be blind to
exactly the two most frequent kinds. Measured on ``ai@7.0.37`` with ``maxRetries: 2``: HTTP 429 and 500 give
3 calls then the wrapper; 401 and 400 give 1 call and the bare error.

Before this module everything shared one path: a blind ``maxRetries: 2`` plus exactly two special branches
(empty completion, provider rejecting images). Quota exhausted, context overflow, wrong key and a network blip
were treated alike - and retrying the wrong kind HARMS: a wrong key retried twice is just three times slower
and still broken, an exhausted quota hit again right away may be throttled harder.

Same family as ``vision_rejection_fallback`` (the classifier for exactly ONE kind of error): extend that
family, do not build a parallel system.

PURE module: no log, no env, no DB.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import cast

from pema.agent.llm_config_error import LoiCauHinhLlm
from pema_contracts.turn_errors import ProviderErrorKind

# Context overflow signs in the error MESSAGE.
#
# String matching is needed because no provider has a code of its own for this case - all of them answer a
# generic 400, shared with the other parameter errors. The list is gathered from the real wording of OpenAI,
# Anthropic and the compatible gateways.
DAU_HIEU_TRAN_CONTEXT = (
    "context length",
    "context_length",
    "context window",
    "maximum context",
    "too many tokens",
    "too long",
    "prompt is too long",
    "reduce the length",
    "exceeds the maximum",
)

# NETWORK-layer errors - did not reach the provider, or cut in the middle
DAU_HIEU_MANG = (
    "econnreset",
    "econnrefused",
    "etimedout",
    "enotfound",
    "eai_again",
    "epipe",
    "socket hang up",
    "fetch failed",
    "network error",
    "aborted",
    "timeout",
)

# Python-side network signs: exception class names (httpx / httpx2, openai, anthropic) that are transport
# failures. Read by NAME so no SDK type is imported.
_TEN_LOP_MANG = frozenset(
    {
        "APIConnectionError",
        "APITimeoutError",
        "ConnectError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
        "ReadError",
        "WriteError",
        "RemoteProtocolError",
        "NetworkError",
        "TimeoutException",
        "TransportError",
    }
)

_DO_SAU_CHUOI = 8
"""Depth limit when walking the ``__cause__`` chain (a cycle must not hang a failing turn)."""

_TRAN_CHO_LAI_GIAY = 60


def _doc(obj: object, ten: str) -> object:
    """Read a field of an error-like object: a mapping key or an attribute (the original read both shapes)."""
    if isinstance(obj, Mapping):
        return cast("Mapping[str, object]", obj).get(ten)
    return getattr(obj, ten, None)


def _chuoi_nguyen(obj: object, *ten: str) -> int | None:
    for t in ten:
        v = _doc(obj, t)
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    return None


def _mat_xich(err: object) -> list[object]:
    """``err`` followed by its ``__cause__`` chain (outermost first), cycle-safe and depth-limited."""
    out: list[object] = []
    cur: object | None = err
    seen: set[int] = set()
    while cur is not None and id(cur) not in seen and len(out) <= _DO_SAU_CHUOI:
        out.append(cur)
        seen.add(id(cur))
        cur = cur.__cause__ if isinstance(cur, BaseException) else None
    return out


def _ma_cua_mot(err: object) -> int | None:
    """Status code of ONE error object: ``status_code`` / ``statusCode`` / ``status``, or the one of an
    attached ``response`` (the shape of the official SDK exceptions)."""
    ma = _chuoi_nguyen(err, "status_code", "statusCode", "status")
    if ma is not None:
        return ma
    response = _doc(err, "response")
    if response is not None:
        return _chuoi_nguyen(response, "status_code", "status")
    return None


def _boc_loi(err: object) -> object:
    """Unwrap a retry wrapper (``RetryError.lastError`` of the original).

    The ``last_error`` attribute of a wrapper wins; otherwise the first error of the ``__cause__`` chain that
    carries a status code; otherwise the error itself (``LoiCauHinhLlm``, a plain network error ...).
    """
    last_error = _doc(err, "last_error") if isinstance(err, BaseException) else None
    if last_error is not None:
        return last_error
    if _ma_cua_mot(err) is not None or not isinstance(err, BaseException):
        return err
    for cur in _mat_xich(err)[1:]:
        if _ma_cua_mot(cur) is not None:
            return cur
    return err


def _la_loi_mang(err: object) -> bool:
    for cur in _mat_xich(err):
        if isinstance(cur, TimeoutError | ConnectionError):
            return True
        if type(cur).__name__ in _TEN_LOP_MANG:
            return True
    return False


def _thong_bao(obj: object) -> str:
    if isinstance(obj, BaseException):
        return str(obj)
    message = _doc(obj, "message")
    return message if isinstance(message, str) else ""


def chuoi_loi(err: object) -> str:
    """Gather every place that may hold the error description into one lowercase string to scan."""
    if isinstance(err, str):
        return err.lower()
    if err is None or isinstance(err, bool | int | float | list | tuple):
        return ""
    phan: list[str] = [_thong_bao(err)]
    body = _doc(err, "response_body")
    if body is None:
        body = _doc(err, "responseBody")
    phan.append(body if isinstance(body, str) else "")
    # A real network error is usually wrapped: ``TypeError: fetch failed`` whose cause is the
    # ``connect ECONNREFUSED`` one. Not reading the cause chain misses exactly the most frequent case.
    if isinstance(err, BaseException):
        for cause in _mat_xich(err)[1:]:
            phan.append(_thong_bao(cause))
    return " ".join(phan).lower()


def ma_http_cua(raw: object) -> int | None:
    """HTTP status if there is one: ``status_code`` of a provider error, else a few familiar field names.
    Looks through a wrapper (see ``_boc_loi``)."""
    return _ma_cua_mot(_boc_loi(raw))


def phan_loai_loi_provider(err: object) -> ProviderErrorKind:
    goc = _boc_loi(err)

    # CHECKED BEFORE anything else. This is OUR OWN error, the provider was never called so there is no HTTP
    # code to read - letting it fall through gives ``unknown``, and ``unknown`` is treated like ``transient``
    # so the sender receives "try again in a few minutes". That is a lie: an empty configuration does not
    # cure itself however long one waits.
    #
    # This state is NOT rare any more since ``.env`` has only one mandatory variable: the bot starts with
    # nothing configured, so it is the default state of a first install and every incoming message goes here.
    if LoiCauHinhLlm.is_instance(goc):
        return ProviderErrorKind.CONFIG

    ma = ma_http_cua(goc)
    chuoi = chuoi_loi(goc)

    # HTTP code first, string after: the code is structured data sent by the provider, while the string is
    # written differently by every vendor and may change at any time.
    if ma == 429:
        return ProviderErrorKind.RATE_LIMIT
    if ma in (401, 403):
        return ProviderErrorKind.AUTH

    # Context overflow is ALWAYS a 400 shared with other parameter errors, so it can only be recognised by
    # the message. Scanned only inside the 4xx group so a 500 with the words "too long" in an HTML page body
    # is not caught by mistake.
    if ma is not None and 400 <= ma < 500:
        if any(d in chuoi for d in DAU_HIEU_TRAN_CONTEXT):
            return ProviderErrorKind.CONTEXT_OVERFLOW
        return ProviderErrorKind.UNKNOWN

    if ma is not None and ma >= 500:
        return ProviderErrorKind.TRANSIENT

    # No code: either a network error (did not reach the provider) or something else. Still scan for context
    # overflow because some gateways throw an error with no code.
    if any(d in chuoi for d in DAU_HIEU_TRAN_CONTEXT):
        return ProviderErrorKind.CONTEXT_OVERFLOW
    if _la_loi_mang(goc) or any(d in chuoi for d in DAU_HIEU_MANG):
        return ProviderErrorKind.TRANSIENT
    return ProviderErrorKind.UNKNOWN


def nen_thu_lai(loai: ProviderErrorKind) -> bool:
    """Which kind is worth retrying - ``unknown`` is allowed because it fails safe."""
    return loai not in (ProviderErrorKind.AUTH, ProviderErrorKind.CONFIG)


def _header_retry_after(err: object) -> str | None:
    """The ``Retry-After`` header of a provider error, whatever the spelling of the headers field."""
    headers: object = _doc(err, "response_headers")
    if headers is None:
        headers = _doc(err, "responseHeaders")
    if headers is None:
        response = _doc(err, "response")
        headers = _doc(response, "headers") if response is not None else None
    if not isinstance(headers, Mapping):
        return None
    for key, value in cast("Mapping[object, object]", headers).items():
        if isinstance(key, str) and key.lower() == "retry-after" and isinstance(value, str) and value:
            return value
    return None


def giay_cho_lai(raw: object) -> float | None:
    """Seconds the provider says to wait (``Retry-After``), if any.

    The header may be a number of seconds or an HTTP date. Capped at 60 seconds: waiting longer means the turn
    has already hit ``LLM_TURN_TIMEOUT_MS`` and locked the thread, better to report the error early than leave
    the sender waiting in vain.
    """
    err = _boc_loi(raw)
    if not isinstance(err, BaseException):
        return None
    header = _header_retry_after(err)
    if not header:
        return None

    try:
        giay = float(header)
    except ValueError:
        giay = math.nan
    if math.isfinite(giay) and giay >= 0:
        return min(giay, float(_TRAN_CHO_LAI_GIAY))

    try:
        moc = parsedate_to_datetime(header)
    except (TypeError, ValueError, IndexError):
        return None
    if moc.tzinfo is None:
        moc = moc.replace(tzinfo=UTC)
    con_lai = math.ceil((moc - datetime.now(UTC)).total_seconds())
    return float(min(max(0, con_lai), _TRAN_CHO_LAI_GIAY))


__all__: list[str] = [
    "DAU_HIEU_MANG",
    "DAU_HIEU_TRAN_CONTEXT",
    "chuoi_loi",
    "giay_cho_lai",
    "ma_http_cua",
    "nen_thu_lai",
    "phan_loai_loi_provider",
]

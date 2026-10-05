# ported from: none (stands in for ``APICallError`` of the Vercel AI SDK)
"""The provider exception the adapters raise, and the retry rule of the SDK's ``maxRetries``.

``APICallError`` carried ``statusCode``, ``responseHeaders``, ``responseBody``, ``isRetryable`` and
``message``; ``provider_error_classifier`` reads exactly those. The three official SDKs (``openai``,
``anthropic``, ``google-genai``) each have their own exception type, so every adapter converts its SDK
exception into this one at the boundary (the original exception stays in ``__cause__``) and the engine never
imports an SDK type. The classifier still reads by duck typing (``status_code`` / ``statusCode``,
``response_headers`` or ``response.headers``) so a raw SDK exception that slips through is classified too.

``is_retryable_error`` is the SDK's rule: retry 408, 409, 429 and 5xx, and network-level failures; never a
401/403/400. The retry LOOP itself lives in ``agent_loop`` (the adapters are built with ``max_retries=0``) so
that fake models exercise it in the translated tests exactly like the SDK's ``maxRetries: 2`` was measured.
"""

from __future__ import annotations

from collections.abc import Mapping


class ProviderCallError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_headers: Mapping[str, str] | None = None,
        response_body: str | None = None,
        is_retryable: bool | None = None,
        url: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_headers: dict[str, str] = {k.lower(): v for k, v in (response_headers or {}).items()}
        self.response_body = response_body
        self.url = url
        self.is_retryable = (
            is_retryable
            if is_retryable is not None
            else (status_code is not None and (status_code in {408, 409, 429} or status_code >= 500))
        )


def is_retryable_error(err: BaseException) -> bool:
    """``maxRetries`` rule: a provider error says so itself; a network failure or timeout is retryable; a
    configuration error or anything else is not."""
    if isinstance(err, ProviderCallError):
        return err.is_retryable
    if isinstance(err, TimeoutError | ConnectionError):
        return True
    status = getattr(err, "status_code", None)
    if isinstance(status, int):
        return status in {408, 409, 429} or status >= 500
    return False

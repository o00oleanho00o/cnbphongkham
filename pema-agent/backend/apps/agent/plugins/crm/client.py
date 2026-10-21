"""Calls to the CRM's agent gateway through ``crm-signer`` (docs/PLAN-crm-plugin.md 3.3, 3.9).

The plugin sends no credential: ``crm-signer`` signs each call. One call opens its own HTTP client (a plugin's
``on_disable`` cannot close an async client), never follows a redirect, and turns every failure into a
``CrmError`` whose message is a sentence the agent can pass on: the CRM's own message when it sent one
(written for this, no names or phones), otherwise one per kind of failure.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

import httpx

UNREACHABLE: Final = "CRM đang không trả lời. Hẹn khách nhân viên sẽ liên hệ lại để giữ lịch."
CLOSED: Final = "Cổng CRM chưa mở cho agent. Hẹn khách nhân viên sẽ liên hệ lại."
BY_STATUS: Final = {
    404: "Không tìm thấy lịch này của khách.",
    409: "Lịch vừa thay đổi hoặc giờ đó vừa có người đặt. Xem lại rồi hỏi khách.",
    422: "Thông tin chưa hợp lệ. Hỏi lại khách cho đúng.",
    429: "Khách đã thay đổi quá nhiều lần. Hẹn khách nhân viên sẽ liên hệ lại.",
}


class CrmError(Exception):
    """A failure the agent can tell the person about; ``str()`` is that sentence."""


class CrmClient:
    def __init__(
        self, base_url: str, *, timeout_s: float, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._base = base_url.rstrip("/")
        self._timeout = timeout_s
        self._transport = transport

    async def call(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str | int] | None = None,
        body: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Any:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, follow_redirects=False, transport=self._transport
            ) as http:
                answer = await http.request(
                    method, f"{self._base}{path}", params=params, json=body, headers=headers
                )
        except httpx.HTTPError as err:
            raise CrmError(UNREACHABLE) from err
        if answer.is_success:
            return answer.json()
        raise CrmError(_sentence(answer))


def _sentence(answer: httpx.Response) -> str:
    if answer.status_code in {401, 403} or answer.status_code >= 500:
        return CLOSED if answer.status_code < 500 else UNREACHABLE
    try:
        message = answer.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = None
    if isinstance(message, str) and message.strip():
        return message.strip()[:300]
    return BY_STATUS.get(answer.status_code, UNREACHABLE)

"""TypeSafe's evaluation API (``POST https://api.typesafe.ai/v1/systemone``): one request per state, all the
questions of the call in it. One call of ``ask_many`` opens its own HTTP client (the plugin keeps none
alive: a plugin's ``on_disable`` cannot close an async client) and runs its requests together, a few at a
time. Every failure becomes a ``JudgeUnavailableError`` whose message is a sentence a person can read; it
never carries the key and never anything of what TypeSafe sent back beyond its status."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

import httpx

from agent_app.plugins import JudgeUnavailableError

ENDPOINT: Final = "https://api.typesafe.ai/v1/systemone"
RETRY_AFTER_S: Final = 0.3
RETRIED: Final = frozenset({429, 499, 529})
"""Rate limit, a request cut off half way (499) and overload: asked once more after a short wait, when
there is time."""


@dataclass(slots=True)
class Meter:
    """What a call used, counted as the answers come in (a call that fails half way still paid for these)."""

    calls: int = 0
    tokens: int = 0


class JevClient:
    def __init__(self, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._transport = transport

    async def ask_many(
        self,
        *,
        key: str,
        model: str,
        states: Sequence[Any],
        questions: Mapping[str, Mapping[str, Any]],
        timeout_s: float,
        concurrency: int,
        meter: Meter,
    ) -> list[dict[str, Any]]:
        """The answers of each state, in order. Raises ``JudgeUnavailableError`` when one request fails or the
        whole takes more than ``timeout_s``."""
        limit = asyncio.Semaphore(max(1, concurrency))
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}

        async def one(http: httpx.AsyncClient, state: Any) -> dict[str, Any]:
            body = {"model": model, "state": state, "questions": questions}
            async with limit:
                return await self._request(http, headers, body, questions, meter)

        try:
            async with httpx.AsyncClient(
                transport=self._transport, follow_redirects=False, timeout=timeout_s
            ) as http:
                async with asyncio.timeout(timeout_s):
                    return list(await asyncio.gather(*(one(http, state) for state in states)))
        except TimeoutError as err:
            raise JudgeUnavailableError("TypeSafe không trả lời kịp.") from err

    async def _request(
        self,
        http: httpx.AsyncClient,
        headers: dict[str, str],
        body: dict[str, Any],
        questions: Mapping[str, Mapping[str, Any]],
        meter: Meter,
    ) -> dict[str, Any]:
        response = await _post(http, headers, body)
        if response.status_code in RETRIED:
            await asyncio.sleep(RETRY_AFTER_S)
            response = await _post(http, headers, body)
        if response.status_code >= 400:
            raise _http_error(response.status_code)
        return _answers(response, questions, meter)


async def _post(http: httpx.AsyncClient, headers: dict[str, str], body: dict[str, Any]) -> httpx.Response:
    try:
        return await http.post(ENDPOINT, json=body, headers=headers)
    except httpx.TimeoutException as err:
        raise JudgeUnavailableError("TypeSafe không trả lời kịp.") from err
    except httpx.TransportError as err:
        raise JudgeUnavailableError("Không kết nối được tới api.typesafe.ai.") from err


def _http_error(code: int) -> JudgeUnavailableError:
    if code in (401, 402, 403):
        return JudgeUnavailableError("Khóa TypeSafe sai, hết hạn hoặc hết tiền.")
    if code == 429:
        return JudgeUnavailableError("TypeSafe đang giới hạn lượt gọi.")
    if code == 499:
        return JudgeUnavailableError("TypeSafe ngắt kết nối giữa chừng (HTTP 499).")
    if code >= 500:
        return JudgeUnavailableError(f"TypeSafe lỗi hoặc quá tải (HTTP {code}).")
    return JudgeUnavailableError(f"TypeSafe từ chối yêu cầu (HTTP {code}); kiểm tra tên model.")


def _answers(
    response: httpx.Response, questions: Mapping[str, Mapping[str, Any]], meter: Meter
) -> dict[str, Any]:
    unreadable = JudgeUnavailableError("TypeSafe trả về dữ liệu không đọc được.")
    try:
        payload: Any = response.json()
        answers: dict[str, Any] = payload["answers"]
        tokens = int(payload.get("usage", {}).get("input_tokens", 0))
        valid = all(_readable(answers.get(name)) for name in questions)
    except (ValueError, KeyError, TypeError, AttributeError) as err:
        raise unreadable from err
    meter.calls += 1
    meter.tokens += tokens
    if not valid:
        raise unreadable
    return {name: answers[name] for name in questions}


def _readable(answer: Any) -> bool:
    """An answer with the number its type promises: ``noul`` a probability, the others a ``confidence``."""
    if not isinstance(answer, dict):
        return False
    found = cast("dict[str, Any]", answer)
    noul = found.get("noul")
    if found.get("type") == "noul":
        return isinstance(noul, int | float) and not isinstance(noul, bool) and _probability(noul)
    return "type" in found


def _probability(value: float) -> bool:
    return math.isfinite(value) and 0.0 <= value <= 1.0

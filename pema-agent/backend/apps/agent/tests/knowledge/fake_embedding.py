"""A fake OpenAI-compatible ``/embeddings`` service for the knowledge tests, with vectors anyone can work out
by hand: one axis per concept (how often its words appear) plus a small constant, normalised. A text about
"sạm da" is close to a text about "nám" by vector without sharing a single word with it."""

from __future__ import annotations

import asyncio
import json
import math
import re
from collections.abc import Awaitable, Callable
from typing import Final

import httpx

from plugins.knowledge.text import fold

CONCEPTS: Final = (
    ("nam", "sam", "dom nau", "hori"),  # pigment
    ("gia", "tien", "bao nhieu", "phi"),  # price
    ("huy", "lo hen", "doi lich"),  # cancel / reschedule
    ("bao luu", "tam dung"),  # pause a package
    ("the", "chuyen khoan", "hoa don"),  # payment
)
DIMENSIONS: Final = len(CONCEPTS) + 1
KEY: Final = "sk-test-synthetic"
BASE_URL: Final = "https://embed.test/v1"


def concept_vector(text: str) -> list[float]:
    """One axis per concept, plus a small constant so that no vector is zero."""
    folded = f" {' '.join(re.findall(r'[a-z0-9]+', fold(text)))} "
    raw = [float(sum(folded.count(f" {word} ") for word in words)) for words in CONCEPTS] + [0.1]
    norm = math.sqrt(math.fsum(x * x for x in raw))
    return [x / norm for x in raw]


def embeddings_transport(calls: list[list[str]]) -> httpx.MockTransport:
    """Answers with concept vectors and records the inputs of every call."""

    def answer(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(list(body["input"]))
        data = [{"index": i, "embedding": concept_vector(t)} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"object": "list", "data": data, "model": body["model"]})

    return httpx.MockTransport(answer)


def status_transport(code: int, calls: list[list[str]] | None = None) -> httpx.MockTransport:
    """A service that always answers with this HTTP status."""

    def answer(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(list(json.loads(request.content)["input"]))
        return httpx.Response(code, text="error")

    return httpx.MockTransport(answer)


def slow_transport(seconds: float) -> httpx.MockTransport:
    """A service that answers only after ``seconds``."""

    async def answer(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(seconds)
        body = json.loads(request.content)
        data = [{"index": i, "embedding": concept_vector(t)} for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"data": data})

    handler: Callable[[httpx.Request], Awaitable[httpx.Response]] = answer
    return httpx.MockTransport(handler)

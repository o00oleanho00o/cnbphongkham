"""The embedding service the store searches by meaning with: an OpenAI-compatible ``POST …/embeddings``.

One call opens its own HTTP client (the plugin keeps none alive: a plugin's ``on_disable`` cannot close an
async client, and a call takes seconds anyway). Vectors come back cut to the dimensions asked for and
normalised, so cosine similarity is a dot product. Every failure becomes an ``EmbeddingError`` whose message
is a sentence a person can read; it never carries the key and never more than a short piece of what the
service said.
"""

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal
from urllib.parse import urlsplit

import httpx

EMBED_BATCH: Final = 16
"""Texts per call."""
EMBED_MAX_CHARS: Final = 8000
"""A text is cut to this before it is sent (Qwen3 takes about 32k tokens)."""
TEST_TEXT: Final = "Kiểm tra kết nối: bảng giá điều trị nám"
BODY_LOOKED_AT: Final = 1000
"""How much of an error body is read for the word "dimension" (the body itself is never shown)."""

ErrorKind = Literal[
    "config", "auth", "not_found", "rate_limit", "server", "timeout", "network", "bad_response", "dimensions"
]
TRANSIENT: Final[frozenset[str]] = frozenset({"rate_limit", "server", "timeout", "network", "bad_response"})


class EmbeddingError(Exception):
    """A failed embedding call; ``message`` is Vietnamese, for the page."""

    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind: ErrorKind = kind
        self.message = message

    @property
    def transient(self) -> bool:
        """Worth trying again later (a limit, an outage); false for a wrong key, address or setting."""
        return self.kind in TRANSIENT


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    base_url: str
    model: str
    dimensions: int
    query_prefix: str
    document_prefix: str
    api_key: str = field(default="", repr=False)
    key_broken: bool = False
    """A key is stored but no longer decrypts (the service's secret key changed)."""

    @property
    def ready(self) -> bool:
        return bool(self.base_url.strip() and self.model.strip() and self.api_key) and not self.key_broken

    @property
    def space(self) -> str:
        """Names what a vector was made with; vectors of different spaces are never compared. The query
        prefix, the address and the key do not matter to a stored vector, so they are not in it."""
        raw = f"{self.model}|{self.dimensions}|{self.document_prefix}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def endpoint(self) -> str:
        base = self.base_url.strip().rstrip("/")
        return base if base.endswith("/embeddings") else f"{base}/embeddings"


@dataclass(frozen=True, slots=True)
class Probe:
    dimensions: int
    """Length the service returned, before any cut."""
    norm: float
    """L2 norm the service returned."""
    ms: float


class EmbeddingClient:
    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        timer: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._transport = transport
        self._timer = timer

    async def embed(
        self, config: EmbeddingConfig, texts: Sequence[str], *, timeout_s: float
    ) -> list[list[float]]:
        """One normalised vector of ``config.dimensions`` per text, in order."""
        vectors = await self._call(config, texts, timeout_s)
        return [_normalised(_cut(raw, config.dimensions)) for raw in vectors]

    async def probe(self, config: EmbeddingConfig, *, timeout_s: float = 15.0) -> Probe:
        """One tiny call, to tell a person whether the settings work: what the service sent, as it sent it."""
        started = self._timer()
        raw = (await self._call(config, [TEST_TEXT], timeout_s))[0]
        if len(raw) < config.dimensions:
            raise _short(config.dimensions, len(raw))
        return Probe(len(raw), math.sqrt(math.fsum(x * x for x in raw)), (self._timer() - started) * 1000)

    async def _call(
        self, config: EmbeddingConfig, texts: Sequence[str], timeout_s: float
    ) -> list[list[float]]:
        if not config.ready:
            raise _not_ready(config)
        if not 1 <= len(texts) <= EMBED_BATCH:
            raise ValueError(f"1 to {EMBED_BATCH} texts per call, got {len(texts)}")
        body = {
            "model": config.model,
            "input": [text[:EMBED_MAX_CHARS] for text in texts],
            "dimensions": config.dimensions,
            "encoding_format": "float",
        }
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(
                transport=self._transport, follow_redirects=False, timeout=timeout_s
            ) as http:
                response = await http.post(config.endpoint, json=body, headers=headers)
        except httpx.TimeoutException as err:
            raise EmbeddingError("timeout", f"Quá {timeout_s:g} giây không trả lời.") from err
        except httpx.TransportError as err:
            host = urlsplit(config.endpoint).hostname or "dịch vụ embedding"
            raise EmbeddingError("network", f"Không kết nối được tới {host}.") from err
        if response.status_code >= 400:
            raise _http_error(response, config.dimensions)
        return _vectors(response, len(texts))


def _not_ready(config: EmbeddingConfig) -> EmbeddingError:
    if config.key_broken:
        return EmbeddingError(
            "config", "Khóa API đã lưu không giải mã được (khóa bí mật của agent đã đổi). Nhập lại khóa."
        )
    return EmbeddingError("config", "Chưa cài địa chỉ, model hoặc khóa API cho embedding.")


def _short(wanted: int, got: int) -> EmbeddingError:
    return EmbeddingError("dimensions", f"Dịch vụ trả về {got} chiều, ít hơn số chiều đã cài ({wanted}).")


def _http_error(response: httpx.Response, dimensions: int) -> EmbeddingError:
    code = response.status_code
    if code in (401, 403):
        return EmbeddingError("auth", "Khóa API sai hoặc hết hạn.")
    if code == 404:
        return EmbeddingError("not_found", "Sai địa chỉ hoặc tên model.")
    if code == 429:
        return EmbeddingError("rate_limit", "Dịch vụ embedding đang giới hạn lượt gọi, thử lại sau.")
    if code >= 500:
        return EmbeddingError("server", f"Dịch vụ embedding lỗi (HTTP {code}).")
    if "dimension" in response.text[:BODY_LOOKED_AT].lower():
        return EmbeddingError("dimensions", f"Model không nhận số chiều {dimensions}.")
    return EmbeddingError("bad_response", f"Dịch vụ từ chối yêu cầu (HTTP {code}).")


def _vectors(response: httpx.Response, count: int) -> list[list[float]]:
    unreadable = EmbeddingError("bad_response", "Dịch vụ trả về dữ liệu không đọc được.")
    try:
        payload: Any = response.json()
        rows: Any = payload["data"]
        ordered = sorted(rows, key=lambda row: row["index"])
        found = [[float(x) for x in row["embedding"]] for row in ordered]
    except (ValueError, KeyError, TypeError) as err:
        raise unreadable from err
    if len(found) != count or any(not all(math.isfinite(x) for x in vector) for vector in found):
        raise unreadable
    return found


def _cut(vector: list[float], dimensions: int) -> list[float]:
    if len(vector) < dimensions:
        raise _short(dimensions, len(vector))
    return vector[:dimensions]


def _normalised(vector: list[float]) -> list[float]:
    norm = math.sqrt(math.fsum(x * x for x in vector))
    if norm == 0:
        raise EmbeddingError("bad_response", "Dịch vụ trả về dữ liệu không đọc được.")
    return [x / norm for x in vector]

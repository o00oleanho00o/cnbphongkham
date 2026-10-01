"""Embeddings for the vector side of the hybrid search: bge-m3 (1024 dimensions) through an OpenAI-compatible
``/embeddings`` endpoint - Ollama (``/v1/embeddings``) or ``llama-server``.

NEW module, not a port: zalo-agent searched by keyword only. This is the one extension over the original.

Privacy rule (PLAN-AI01 principle 4): the text of a knowledge document is clinic procedure/FAQ text, never
patient data, but it still must not leave the clinic's infrastructure through a mis-typed URL.
``kiem_tra_dia_chi_noi_bo`` therefore REFUSES a base URL whose host is not loopback / private / link-local /
CGNAT (Tailscale ``100.64.0.0/10``) / a single-label or ``.local`` / ``.internal`` / ``.ts.net`` /
``.lan`` name, unless ``PEMA_EMBEDDING_ALLOW_REMOTE=true`` is set on purpose.

Failure policy (the search must keep working with the keyword side alone):
* ``embed`` raises ``EmbeddingError`` when the endpoint is down or answers badly; callers that can live
  without a vector (``kb_search``, ``kb_ingest_worker``) catch it, log the error TYPE (never the text) and
  carry on without vectors;
* the answer is checked: one vector per input text, each of exactly ``KB_EMBEDDING_DIMENSIONS`` floats -
  a different model would silently corrupt the index otherwise (changing the model needs a migration).

``HashingEmbeddingClient`` is a deterministic FAKE for tests and offline development: it hashes words into a
1024-dimension bag-of-words vector. It is NOT a language model and says nothing about meaning; tests that
need "similar meaning without shared words" build their own mapping (see ``tests/knowledge``).

Run with a real model: ``docs`` of the package F, or the README of ``kb-samples/``.
"""

from __future__ import annotations

import hashlib
import ipaddress
import math
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic_settings import BaseSettings, SettingsConfigDict

from pema.knowledge.kb_fts_query import tach_tu_khoa
from pema.shared.logger import create_logger
from pema_contracts.knowledge import KB_EMBEDDING_DIMENSIONS

log = create_logger("knowledge.embedding")

_LOCAL_SUFFIXES = (".local", ".internal", ".lan", ".ts.net", ".home.arpa", ".localdomain")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


class EmbeddingError(Exception):
    """The embedding endpoint is unreachable or returned something unusable."""


class EmbeddingSettings(BaseSettings):
    """``PEMA_EMBEDDING_*`` environment variables (a ``.env`` is never committed, see
    ``infra/.env.example``)."""

    model_config = SettingsConfigDict(env_prefix="PEMA_EMBEDDING_", env_file=".env", extra="ignore")

    enabled: bool = False
    """Off = the knowledge base runs on keyword search only (no vectors are computed or stored).

    TẠM TẮT LLM LOCAL (2026-10-02): default off because bge-m3 runs on the local Ollama, which is paused while
    the agent uses a third-party LLM API. Keyword search is what zalo-agent itself does. Re-enable with
    ``PEMA_EMBEDDING_ENABLED=true`` (or set this default back to True)."""
    base_url: str = "http://localhost:11434/v1"
    """OpenAI-compatible root. Ollama default. The client posts to ``<base_url>/embeddings``."""
    model: str = "bge-m3"
    timeout_s: float = 60.0
    batch_size: int = 16
    allow_remote: bool = False
    """Allow a public host. Leave false: clinic text must stay on the clinic's own machines."""


def la_dia_chi_noi_bo(host: str) -> bool:
    """Is ``host`` a machine inside the clinic's own network (see the module docstring)."""
    host = host.strip().strip("[]").lower()
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return "." not in host or host.endswith(_LOCAL_SUFFIXES) or host == "localhost"
    return ip.is_loopback or ip.is_private or ip.is_link_local or (ip.version == 4 and ip in _CGNAT)


def kiem_tra_dia_chi_noi_bo(base_url: str, *, allow_remote: bool) -> None:
    host = urlparse(base_url).hostname or ""
    if not allow_remote and not la_dia_chi_noi_bo(host):
        raise EmbeddingError(
            "Địa chỉ embedding nằm ngoài mạng nội bộ của phòng khám. Chỉ dùng máy trong mạng nội bộ "
            "(hoặc đặt PEMA_EMBEDDING_ALLOW_REMOTE=true nếu chủ phòng khám chấp thuận)."
        )


class OllamaEmbeddingClient:
    """``EmbeddingClient`` over ``POST <base_url>/embeddings`` ``{"model": ..., "input": [...]}``."""

    def __init__(
        self,
        settings: EmbeddingSettings | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings or EmbeddingSettings()
        kiem_tra_dia_chi_noi_bo(self._settings.base_url, allow_remote=self._settings.allow_remote)
        self._http = httpx.AsyncClient(
            base_url=self._settings.base_url.rstrip("/") + "/",
            timeout=self._settings.timeout_s,
            transport=transport,
        )

    @property
    def dimensions(self) -> int:
        return KB_EMBEDDING_DIMENSIONS

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        size = max(1, self._settings.batch_size)
        for start in range(0, len(texts), size):
            out.extend(await self._embed_batch(texts[start : start + size]))
        return out

    async def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        try:
            response = await self._http.post(
                "embeddings", json={"model": self._settings.model, "input": batch}
            )
            response.raise_for_status()
            body: Any = response.json()
            data = body["data"]
            vectors = [list(map(float, item["embedding"])) for item in sorted(data, key=lambda i: i["index"])]
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as err:
            raise EmbeddingError(f"Không lấy được embedding ({type(err).__name__})") from err
        if len(vectors) != len(batch):
            raise EmbeddingError("Số vector embedding trả về không khớp số văn bản gửi lên")
        for vector in vectors:
            if len(vector) != KB_EMBEDDING_DIMENSIONS:
                raise EmbeddingError(
                    f"Vector embedding có {len(vector)} chiều, kho tri thức cần {KB_EMBEDDING_DIMENSIONS}"
                )
        return vectors

    async def aclose(self) -> None:
        await self._http.aclose()


class HashingEmbeddingClient:
    """Deterministic FAKE: a hashed bag of words, L2-normalised. For tests and offline development only."""

    @property
    def dimensions(self) -> int:
        return KB_EMBEDDING_DIMENSIONS

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(t) for t in texts]

    def _one(self, text: str) -> list[float]:
        vector = [0.0] * KB_EMBEDDING_DIMENSIONS
        for word in tach_tu_khoa(text.lower()):
            digest = hashlib.blake2b(word.encode("utf-8"), digest_size=4).digest()
            vector[int.from_bytes(digest, "big") % KB_EMBEDDING_DIMENSIONS] += 1.0
        norm = math.sqrt(sum(x * x for x in vector))
        return [x / norm for x in vector] if norm else vector

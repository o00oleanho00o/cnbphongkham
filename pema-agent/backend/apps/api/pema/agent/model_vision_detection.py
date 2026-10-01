# ported from: src/agent/model-vision-detection.ts
"""Can the model in effect read images?

Forced deviations: ``fetch`` + ``AbortController`` become the ``http`` flavour of the installed SDKs
(``httpx2`` or ``httpx``, see ``providers.http_flavour``) with a 5 s timeout, and the HTTP client is
injectable (``make_models_fetcher``) so tests use ``http.MockTransport``; ``Date.now()`` is a monotonic clock
(``_now``, patched by the TTL test); ``ModelOverride`` is the ``ModelOverrideLike`` protocol.

mode on/off: forced by hand. mode auto: ask the router through ``GET {base_url}/models`` - 9Router returns
``capabilities.vision`` for each model (exactly the data of the eye icon on the router UI) and marks a combo
with ``owned_by: "combo"`` (verified on a running instance). A standard OpenAI endpoint has neither field ->
"unknown" -> counted as HAVING vision to keep the old behaviour.

Four states instead of a boolean because a combo needs its own treatment: a combo mixes members with and
without vision, 9Router's auto-switch pushes a vision member to the front when the CURRENT turn has an
image, but a HISTORY image deliberately does not pin the combo (combo.js: "History media must not pin the
combo") - landing on a blind member strips the image silently. The hybrid mode (attach pixels AND the
description) cures exactly this hole.

NEGATIVE cache (``mark_model_no_vision``): the reactive fallback of the agent loop detects that a model
rejects images with an HTTP 4xx and remembers it here - later turns go straight to describe/blind instead of
running into the wall again.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final, Literal, cast

from pema.agent.llm_provider import ModelOverrideLike, model_hieu_luc
from pema.agent.providers.http_flavour import http
from pema.config.env_llm import la_goi_thang_hang
from pema.config.runtime_llm_settings import get_effective_llm_settings
from pema.config.runtime_vision_settings import get_vision_settings
from pema.shared.logger import create_logger

log = create_logger("vision-detection")

CACHE_TTL_S: Final = 10 * 60
"""The /models lookup is cached 10 minutes - a model/router change need not wait too long."""

_MODELS_TIMEOUT_S: Final = 5.0

type ModelVisionKind = Literal["vision", "no-vision", "combo", "unknown"]


@dataclass(frozen=True)
class ModelsCapabilities:
    vision_by_model: dict[str, bool]
    """vision by model id; a model without capabilities has no key"""
    combo_ids: set[str]
    """ids of the combos (owned_by = "combo") - no capabilities but known to be a combo"""


@dataclass(frozen=True)
class _CacheEntry:
    capabilities: ModelsCapabilities
    expires_at: float


_cache_by_base_url: dict[str, _CacheEntry] = {}
"""Cache per base URL - several agents on different models still share ONE /models call."""

_no_vision_until: dict[str, float] = {}
"""Negative cache: the model rejected an image with a real 4xx error (the reactive fallback writes here).
Key ``{base_url}|{model}``. Beats the /models result because it is real evidence from the provider itself,
while /models can be optimistic (unknown counts as having vision)."""

type ModelsFetcher = Callable[[str, str], Awaitable[object]]
"""``(url, api_key) -> parsed JSON``. Raises on any failure."""


def _now() -> float:
    return time.monotonic()


async def default_fetcher(url: str, api_key: str, *, http_client: Any | None = None) -> object:
    """The real lookup: ``GET url`` with a bearer key, 5 s timeout, JSON body."""
    client: Any = http_client if http_client is not None else http.AsyncClient(timeout=_MODELS_TIMEOUT_S)
    try:
        res = await client.get(url, headers={"Authorization": f"Bearer {api_key}"}, timeout=_MODELS_TIMEOUT_S)
        if res.status_code >= 400:
            raise RuntimeError(f"HTTP {res.status_code}")
        return res.json()
    finally:
        if http_client is None:
            await client.aclose()


def make_models_fetcher(http_client: Any | None = None) -> ModelsFetcher:
    """A fetcher over an injected HTTP client (tests: ``http.AsyncClient(transport=http.MockTransport(...))``)."""

    async def fetch(url: str, api_key: str) -> object:
        return await default_fetcher(url, api_key, http_client=http_client)

    return fetch


def parse_models_capabilities(payload: object) -> ModelsCapabilities:
    """Pull the vision map + the list of combos out of the /models response."""
    vision_by_model: dict[str, bool] = {}
    combo_ids: set[str] = set()
    data = cast("dict[str, Any]", payload).get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        return ModelsCapabilities(vision_by_model, combo_ids)
    for raw in cast("list[Any]", data):
        if not isinstance(raw, dict):
            continue
        entry = cast("dict[str, Any]", raw)
        model_id = entry.get("id")
        if not isinstance(model_id, str):
            continue
        capabilities = entry.get("capabilities")
        vision = (
            cast("dict[str, Any]", capabilities).get("vision") if isinstance(capabilities, dict) else None
        )
        if isinstance(vision, bool):
            vision_by_model[model_id] = vision
        if entry.get("owned_by") == "combo":
            combo_ids.add(model_id)
    return ModelsCapabilities(vision_by_model, combo_ids)


async def _lookup_from_router(base_url: str, api_key: str, fetcher: ModelsFetcher) -> ModelsCapabilities:
    cached = _cache_by_base_url.get(base_url)
    if cached is not None and cached.expires_at > _now():
        return cached.capabilities

    parsed = ModelsCapabilities({}, set())
    try:
        url = f"{base_url.removesuffix('/')}/models"
        parsed = parse_models_capabilities(await fetcher(url, api_key))
    except Exception as exc:
        # A router that cannot return /models counts as "unknown" - cached too, so /models is not hammered on
        # every message while the router is in trouble
        log.debug("cannot look up /models - treating the model as having vision", base_url=base_url, err=exc)
    _cache_by_base_url[base_url] = _CacheEntry(parsed, _now() + CACHE_TTL_S)
    return parsed


def mark_model_no_vision(override: ModelOverrideLike | None = None) -> None:
    """Reactive fallback calls this when the provider REJECTS an image with a 4xx: remember that the model in
    effect cannot read images so later turns go straight to describe/blind. A direct vendor path (Anthropic,
    Google) is NEVER marked - Claude and Gemini both read images, a 4xx there is something else (an image too
    large, a broken request), and marking only does harm. It really happened with Gemini: a 400 for a missing
    thought_signature was blamed on the image, and a model that reads images was treated as blind."""
    base = get_effective_llm_settings()
    # Through ``model_hieu_luc`` and not the raw override: an agent declaring a mismatching provider has its
    # override ignored when the client is built, so the real turn runs on the shared provider. Reading the raw
    # one here would exit early thinking Anthropic is running, the negative cache would never be written, and
    # the reactive fallback would run into the pixel path EVERY turn - two model calls per turn.
    chosen = model_hieu_luc(override)
    if la_goi_thang_hang(chosen.provider):
        return
    _no_vision_until[f"{base.base_url or ''}|{chosen.model}"] = _now() + CACHE_TTL_S
    log.warning(
        "remembering a model that cannot read images (provider rejected it with a 4xx)", model=chosen.model
    )


def clear_vision_detection_cache() -> None:
    """Clear the cache (negative one too) - call when the provider/vision settings change on the dashboard."""
    _cache_by_base_url.clear()
    _no_vision_until.clear()


async def classify_model_vision(
    override: ModelOverrideLike | None = None, fetcher: ModelsFetcher | None = None
) -> ModelVisionKind:
    """Classify the image-reading ability of the model in effect (agent override -> runtime settings -> env,
    the same order as ``resolve_language_model``)."""
    mode = get_vision_settings().mode
    if mode == "on":
        return "vision"
    if mode == "off":
        return "no-vision"

    base = get_effective_llm_settings()
    # Same reason as ``mark_model_no_vision``: it must be the model that REALLY runs, not the one the agent
    # declared. Reading the raw one makes an agent declaring `anthropic` count as image-capable and the bot
    # attaches pixels, while the real turn goes to a router model that may be blind.
    chosen = model_hieu_luc(override)

    if la_goi_thang_hang(chosen.provider):
        return "vision"

    # Real evidence (the provider already rejected an image) beats every guess
    negative_until = _no_vision_until.get(f"{base.base_url or ''}|{chosen.model}")
    if negative_until is not None and negative_until > _now():
        return "no-vision"

    if not base.base_url or not base.api_key:
        return "unknown"

    capabilities = await _lookup_from_router(base.base_url, base.api_key, fetcher or default_fetcher)
    vision = capabilities.vision_by_model.get(chosen.model)
    if vision is True:
        return "vision"
    if vision is False:
        log.info(
            "router says the model cannot read images - dropping images from the request", model=chosen.model
        )
        return "no-vision"
    if chosen.model in capabilities.combo_ids:
        return "combo"
    return "unknown"


async def model_reads_images(
    override: ModelOverrideLike | None = None, fetcher: ModelsFetcher | None = None
) -> bool:
    """True unless it is certain the model can NOT read images - keeps the old optimistic behaviour."""
    return (await classify_model_vision(override, fetcher)) != "no-vision"

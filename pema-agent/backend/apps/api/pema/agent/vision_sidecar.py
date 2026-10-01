# ported from: src/agent/vision-sidecar.ts
"""A "hired pair of eyes" for a main model that cannot read images: call a second, vision model (usually a
free Gemini through an OpenAI-compatible endpoint) to describe the image as text ONCE and cache it - the
main model and every later turn only read text.

Learned from the text-mode of Hermes (``agent/image_routing.py``): describe at the moment of use, cache per
image, a prompt that forces copying every word and number verbatim because the main use case of the bot is
reading receipts, forms and documents - a generic description is useless for anything that touches money.

Forced deviations:

* SQLite -> Postgres, sync -> async: the description cache is the async ``ImageDescriptionStore`` protocol
  (``pema_contracts.conversation``) with ``clinic_id`` first, passed as keyword-only ``clinic_id`` / ``store``
  (``describe_image``, ``ensure_descriptions_for``); ``ask_about_image`` and ``test_sidecar`` never cache and
  need neither.
* Vercel ``createOpenAICompatible`` + ``streamText`` become ``OpenAICompatibleModel`` (the ``openai`` SDK,
  ``max_retries=0``, always streaming - the invariant "no non-stream LLM call is left" is kept). The SDK's
  ``maxRetries: 1`` is kept by ONE retry here on a retryable error (``is_retryable_error``). The HTTP client
  is injectable through ``http_client_factory`` so tests use ``http.MockTransport``.
* The question of ``ask_about_image`` is not written to the log (it is patient text).
* ``test_sidecar`` keeps the original name; pytest only collects it from a test module that imports it by
  name, so tests call it through the module.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

from pema.agent.history_to_model_messages import StoredImageLoader
from pema.agent.model_types import ModelRequest
from pema.agent.providers.errors import is_retryable_error
from pema.agent.providers.openai_compatible import OpenAICompatibleModel
from pema.config.runtime_vision_settings import (
    VisionSidecarSettings,
    get_vision_settings,
    is_sidecar_configured,
)
from pema.shared.logger import create_logger
from pema_contracts.conversation import ImageDescriptionStore

log = create_logger("vision-sidecar")

DESCRIBE_PROMPT: Final = (
    "Mô tả chi tiết ảnh này bằng tiếng Việt cho một AI khác không xem được ảnh. "
    "BẮT BUỘC: chép NGUYÊN VĂN mọi chữ và con số nhìn thấy trong ảnh (số vé, mã, "
    "ngày tháng, tên, giá tiền, biển số...), tách phần chữ và phần số đúng như in. "
    "Sau đó tả bố cục, vật thể, người, màu sắc. Không suy diễn thông tin không có trong ảnh."
)
"""Fixed prompt - changing it leaves the old cached descriptions usable, so no version is needed."""

DESCRIBE_MAX_TOKENS: Final = 2048
"""Token ceiling of one image description. 1024 (the old number) is enough for an ordinary image but NOT for
a text-heavy one - a menu, a price list, a list, a screenshot - because the prompt asks for every word and
number verbatim. Accented Vietnamese is ~2.7 chars per token so 2048 is ~5,500 characters of description,
enough for a dense image."""

NOT_CONFIGURED_MESSAGE: Final = "Chưa cấu hình đủ base URL + model + API key cho sidecar"

_RETRY_DELAY_S = 0.5
"""Pause before the one retry (the SDK's own back-off of ``maxRetries: 1``)."""


@dataclass(frozen=True)
class SidecarImage:
    base64: str
    media_type: str
    cache_key: str | None = None
    """Media path used as the cache key; none (image not persisted) = the description is not cached."""


@dataclass(frozen=True)
class SidecarResult:
    """Result of one sidecar call. ``truncated`` is mandatory: a description cut in the middle that gets cached
    makes the cut copy live FOR EVER, every later turn reads it and nobody knows why the bot answers with a
    gap."""

    text: str
    truncated: bool


type SidecarCaller = Callable[[VisionSidecarSettings, SidecarImage, str], Awaitable[SidecarResult]]


def make_sidecar_caller(*, http_client_factory: Callable[[], Any] | None = None) -> SidecarCaller:
    """The real call path - a factory so tests inject a fake HTTP client (``http.MockTransport``) or a whole
    fake caller (every function below takes ``call``)."""

    async def call(settings: VisionSidecarSettings, image: SidecarImage, prompt: str) -> SidecarResult:
        model = OpenAICompatibleModel(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            http_client=http_client_factory() if http_client_factory is not None else None,
        )
        # Streaming like every other LLM call of the project. The sidecar points straight at Gemini today so
        # it meets no Cloudflare 524, BUT the base URL is editable from the dashboard - point it at a router
        # and it does. Keeping one invariant "no non-stream LLM call is left" is cheaper than remembering
        # which place is exempt and why.
        request = ModelRequest(
            system="",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "file", "data": image.base64, "mediaType": image.media_type},
                        {"type": "text", "text": prompt},
                    ],
                }
            ],
            max_output_tokens=DESCRIBE_MAX_TOKENS,
        )
        for attempt in range(2):  # maxRetries: 1
            try:
                completion = await model.complete(request)
                break
            except Exception as exc:
                if attempt == 0 and is_retryable_error(exc):
                    await asyncio.sleep(_RETRY_DELAY_S)
                    continue
                raise
        # finish_reason "length" = the model was mid-sentence when it hit the token ceiling
        return SidecarResult(text=completion.text.strip(), truncated=completion.finish_reason == "length")

    return call


default_caller: SidecarCaller = make_sidecar_caller()


async def describe_image(
    image: SidecarImage,
    call: SidecarCaller | None = None,
    *,
    clinic_id: UUID,
    store: ImageDescriptionStore,
) -> str | None:
    """Describe ONE image, cache first. An error (sidecar dead, quota gone, broken image) returns ``None`` -
    the caller decides what to tell the main model; it does NOT raise, so one broken image does not kill the
    whole answer."""
    if image.cache_key:
        cached = await store.get_image_description(clinic_id, image.cache_key)
        if cached:
            return cached

    settings = get_vision_settings()
    if not is_sidecar_configured(settings):
        return None

    caller = call or default_caller
    try:
        result = await caller(settings.sidecar, image, DESCRIBE_PROMPT)
        description = result.text
        if not description:
            return None
        # A truncated description is still USABLE for this turn (better than nothing) but must ABSOLUTELY
        # NOT be cached: the cut copy would live for ever and every later turn would read it
        if image.cache_key and not result.truncated:
            await store.save_image_description(clinic_id, image.cache_key, description, settings.sidecar.model)
        if result.truncated:
            log.warning(
                "image description cut at the token ceiling - used for this turn, NOT cached; "
                "consider raising DESCRIBE_MAX_TOKENS",
                cache_key=image.cache_key,
                chars=len(description),
            )
        else:
            log.info(
                "sidecar described an image",
                cache_key=image.cache_key,
                model=settings.sidecar.model,
                chars=len(description),
            )
        return description
    except Exception as exc:
        log.warning("sidecar image description failed - skipping this image", cache_key=image.cache_key, err=exc)
        return None


async def ensure_descriptions_for(
    rel_paths: Sequence[str],
    load_image: StoredImageLoader,
    call: SidecarCaller | None = None,
    *,
    clinic_id: UUID,
    store: ImageDescriptionStore,
) -> None:
    """Describe (and cache) the images saved in the media store BEFORE - used for history images about to be
    loaded back into the context. An image that cannot be loaded (the file was cleaned up) is skipped
    quietly."""
    for rel_path in rel_paths:
        if await store.get_image_description(clinic_id, rel_path):
            continue
        stored = load_image(rel_path)
        if stored is None:
            continue
        await describe_image(
            SidecarImage(stored.base64, stored.media_type, rel_path), call, clinic_id=clinic_id, store=store
        )


async def ask_about_image(image: SidecarImage, question: str, call: SidecarCaller | None = None) -> str:
    """Ask the sidecar ONE SPECIFIC QUESTION about an image (the ``read_image`` tool) - unlike
    ``describe_image``: the prompt is the agent's own question and it is NOT cached (every question differs,
    the general description has its own cache). Raises so the tool can explain it to the model."""
    settings = get_vision_settings()
    if not is_sidecar_configured(settings):
        raise RuntimeError(NOT_CONFIGURED_MESSAGE)
    prompt = (
        "Trả lời câu hỏi sau về ảnh bằng tiếng Việt, chính xác theo những gì nhìn thấy, "
        f"không suy diễn thông tin không có trong ảnh: {question}"
    )
    result = await (call or default_caller)(settings.sidecar, image, prompt)
    log.info(
        "sidecar answered a question about an image",
        model=settings.sidecar.model,
        question_chars=len(question),
        chars=len(result.text),
        truncated=result.truncated,
    )
    # The answer is not cached so a cut one only hurts this turn - say it plainly so the model knows the rest
    # is missing and does not conclude firmly from half the data
    if result.truncated:
        return f"{result.text}\n\n(Phần mô tả bị cắt vì quá dài - có thể còn chi tiết chưa liệt kê.)"
    return result.text


TEST_PIXEL_PNG_BASE64: Final = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
"""A white 1x1 PNG - enough for the "Test sidecar" button to prove the vision path really runs."""


async def test_sidecar(call: SidecarCaller | None = None) -> str:
    """Call the sidecar with a tiny test image - return the error verbatim for the UI to show."""
    settings = get_vision_settings()
    if not is_sidecar_configured(settings):
        raise RuntimeError(NOT_CONFIGURED_MESSAGE)
    result = await (call or default_caller)(
        settings.sidecar, SidecarImage(TEST_PIXEL_PNG_BASE64, "image/png"), DESCRIBE_PROMPT
    )
    return result.text

# ported from: src/agent/agent-turn-content.ts
"""Build the input of ONE agent turn in 4 image modes (the ``auto|native|text`` model of Hermes, plus
``blind`` when there is no sidecar and ``hybrid`` for the combos of a router):

* native:   the main model reads images: attach pixels, as always.
* describe: the main model can NOT read images but a sidecar exists: replace pixels by a text description (the
            sidecar describes once, cached in the DB).
* hybrid:   the model is a COMBO mixing members with and without vision: attach BOTH pixels AND description:
  the
            vision member sees the pixels, a turn that falls on a blind member (fallback, or a history image
            that does not trigger the router's auto-switch) has its pixels stripped but the text description
            survives.
* blind:    cannot read images, no sidecar: drop the images and insert a note so the bot tells the truth
  instead
            of staying silent or inventing.

Forced deviations (SQLite -> Postgres, sync -> async, Node file system -> injected seams): the image store,
the downloader and the description cache are injected through ``TurnContentDeps`` (``loadStoredImage``,
``downloadImageAsBase64`` and the ``image-description-store`` of the original); ``ParsedMessage`` is
``InboundMessage``; ``StoredMessage.created_at`` is an aware datetime. The history renderer is synchronous and
the description cache is async, so the descriptions of the history images that fit the budget are prefetched
(at most ``HISTORY_IMAGE_CONTEXT_LIMIT`` lookups) before rendering.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pema.agent.batch_to_user_lines import dong_tin_cua_luot
from pema.agent.history_to_model_messages import (
    HistoryImageRendering,
    StoredImage,
    StoredImageLoader,
    collect_images_within_budget,
    history_to_model_messages,
    sender_trust_from,
)
from pema.agent.llm_provider import ModelOverrideLike
from pema.agent.model_types import ModelMessage
from pema.agent.model_vision_detection import classify_model_vision
from pema.agent.token_estimate import ngan_sach_an_toan
from pema.agent.trim_context_to_budget import DaCat, cat_ngu_canh_theo_ngan_sach
from pema.agent.vision_sidecar import SidecarImage, describe_image, ensure_descriptions_for
from pema.config.runtime_tuning_settings import bot_time_zone, get_tuning, get_tuning_int
from pema.config.runtime_vision_settings import is_sidecar_configured
from pema_contracts.agents import Allowlist
from pema_contracts.channel import InboundMessage
from pema_contracts.conversation import ImageDescriptionStore, StoredMessage

type ImageContextMode = Literal["native", "describe", "hybrid", "blind"]
"""How the images of a turn reach the main model (see the module docstring)."""


class ImageDownloader(Protocol):
    """``downloadImageAsBase64``: fetch an image by URL (package D4's ``download_image``), ``None`` on
    failure."""

    async def __call__(self, url: str, /) -> StoredImage | None: ...


type DescribeBeforeHook = Callable[[Sequence[str]], Awaitable[None]]
"""Seam of the description step run BEFORE building (``moTaTruoc``): receives the history images about to
enter
the context."""


@dataclass(frozen=True)
class TurnContentDeps:
    """Every collaborator of the builder, injected (nothing global except tuning and the vision settings)."""

    clinic_id: Any
    """The clinic (``UUID``) the description cache belongs to."""
    load_image: StoredImageLoader
    """``loadStoredImage``: an image already persisted in the media store, by relative path."""
    download_image: ImageDownloader
    """Fallback when the image was not persisted: download straight from the channel URL."""
    image_descriptions: ImageDescriptionStore
    """Cache of the sidecar descriptions (``image-description-store``)."""


async def resolve_image_context_mode(override: ModelOverrideLike | None = None) -> ImageContextMode:
    kind = await classify_model_vision(override)
    sidecar = is_sidecar_configured()
    if kind == "no-vision":
        return "describe" if sidecar else "blind"
    if kind == "combo":
        # Without a sidecar hybrid does nothing more than native: the router's auto-switch still pushes the
        # vision member to the front when the turn has images
        return "hybrid" if sidecar else "native"
    # vision + unknown: optimistic like the old behaviour
    return "native"


def _blind_image_note(count: int) -> str:
    return (
        f"[Người dùng gửi kèm {count} ảnh nhưng bạn KHÔNG xem được ảnh trực tiếp - "
        "nói thật điều đó và nhờ họ mô tả bằng chữ nếu cần nội dung ảnh để trả lời.]"
    )


DESCRIBE_FAILED_NOTE = (
    "[Có ảnh đính kèm nhưng hệ thống đọc ảnh đang trục trặc, chưa mô tả được - "
    "nói thật với người dùng nếu cần nội dung ảnh để trả lời.]"
)


@dataclass(frozen=True)
class BuiltTurn:
    messages: list[ModelMessage]
    image_mode: ImageContextMode
    da_cat: DaCat | None
    """``None`` = nothing was cut. Otherwise the agent loop logs a warning."""


def _history_rendering(
    image_mode: ImageContextMode, descriptions: dict[str, str]
) -> HistoryImageRendering | None:
    if image_mode == "describe":
        return HistoryImageRendering(describe=descriptions.get, keep_pixels=False)
    if image_mode == "hybrid":
        return HistoryImageRendering(describe=descriptions.get, keep_pixels=True)
    return None


async def build_turn_messages(
    *,
    history: Sequence[StoredMessage],
    batch: Sequence[InboundMessage],
    id_bo_qua: Sequence[int] = (),
    tran_lich_su: int = 0,
    override: ModelOverrideLike | None = None,
    force_mode: ImageContextMode | None = None,
    allowlist: Allowlist | None = None,
    tran_token: int,
    deps: TurnContentDeps,
    mo_ta_truoc: DescribeBeforeHook | None = None,
) -> BuiltTurn:
    """History + the current batch -> the complete messages for the model, images handled per mode. Also
    returns the image mode so the agent loop can log a diagnosis.

    ``force_mode`` forces the mode instead of auto-detecting: the reactive fallback path (a native turn whose
    images the provider refused with a 4xx is rebuilt in describe/blind and retried, without waiting for the
    detection cache to expire).

    ``id_bo_qua``: ids of the history rows that do NOT belong to this turn: messages waiting in the batcher.
    ``tran_lich_su``: ceiling of the number of history messages AFTER filtering; the caller must read the DB
    with a surplus equal to the number of rows about to be filtered and pass the real ceiling here; 0 = no
    cut. ``tran_token``: token ceiling of the input = the MODEL's window, not the discounted budget (this
    function discounts it through ``ngan_sach_an_toan``). MANDATORY (keyword without default): an optional
    parameter with default 0 means "forgot to pass it" silently switches the budget off, the very bug that hit
    the rebuild path after the provider refused images. To not limit, pass 0 explicitly. ``mo_ta_truoc``: the
    description step before the images of the history enter the context; a seam because the real path calls
    the sidecar over the network, and the invariant to pin is NOT "describes right" but "describes the SAME
    LIST of images the render step will use". That invariant once broke SILENTLY: the description step ran on
    the unfiltered history while the render ran on the filtered one, so the description budget fell on the
    images of this very turn, the old images were never described, and ``describe`` mode also drops the
    pixels: the line reached the model as bare text with no trace of the image.
    """
    image_mode = force_mode or await resolve_image_context_mode(override)
    # blind: history image budget = 0, the content falls back to the text "[gửi kèm N ảnh]"
    image_limit = 0 if image_mode == "blind" else get_tuning_int("HISTORY_IMAGE_CONTEXT_LIMIT")

    # Filter ONCE and share the list between the description step and the message build. On two different
    # lists the budget falls on this image while the render needs that one: an old image is never described,
    # and ``describe`` mode drops its pixels too, so the line goes to the model as bare text with no trace of
    # the image, and it breaks SILENTLY.
    lich_su = _loc_lich_su_cho_luot(history, batch, id_bo_qua, tran_lich_su)

    descriptions: dict[str, str] = {}
    if image_mode in ("describe", "hybrid"):
        # Describe BEFORE the history images that are about to enter the context, passive-listen images that
        # never went through an agent turn included (a group sends a lottery ticket and only then mentions the
        # bot). The build below only reads the cache.
        paths = collect_images_within_budget(lich_su, image_limit)
        if mo_ta_truoc is not None:
            await mo_ta_truoc(paths)
        else:
            await ensure_descriptions_for(
                paths, deps.load_image, clinic_id=deps.clinic_id, store=deps.image_descriptions
            )
        for path in paths:
            description = await deps.image_descriptions.get_image_description(deps.clinic_id, path)
            if description:
                descriptions[path] = description

    messages = history_to_model_messages(
        lich_su,
        image_limit,
        deps.load_image,
        bot_time_zone(),
        _history_rendering(image_mode, descriptions),
        sender_trust_from(allowlist) if allowlist is not None else None,
    )
    # The WHOLE batch of this turn is merged into EXACTLY ONE user message, so the zone protected from cutting
    # is the last 1 message. This number must match the line right below: change how the batch is merged and
    # it must change too.
    current = await build_current_turn_content(batch, image_mode, deps=deps)
    messages.append({"role": "user", "content": current})

    # The budget comes from the ceiling through ``ngan_sach_an_toan``: ONE function shared with the in-turn
    # stop condition (``vuot_tran_token``) and the wrap-up call. This place used to multiply by 0.7 itself
    # while the stop condition compared against 100% of the ceiling, so the two halves of one feature read the
    # number in two different meanings.
    cat = cat_ngu_canh_theo_ngan_sach(
        tin_nhan=messages,
        tran_token=ngan_sach_an_toan(tran_token),
        so_tin_bao_ve_cuoi=1,
        co_anh=_image_quality(),
    )
    return BuiltTurn(messages=cat.tin_nhan, image_mode=image_mode, da_cat=cat.da_cat)


def _image_quality() -> Literal["thumb", "normal", "hd"]:
    value = str(get_tuning("ZALO_IMAGE_QUALITY"))
    if value == "thumb":
        return "thumb"
    if value == "hd":
        return "hd"
    return "normal"


def _loc_lich_su_cho_luot(
    history: Sequence[StoredMessage],
    batch: Sequence[InboundMessage],
    id_bo_qua: Sequence[int],
    tran_lich_su: int,
) -> list[StoredMessage]:
    """The REAL history of the turn: drop the rows that do not belong to it, then cut back to the ceiling.

    Drops two groups:

      1. The messages of this very batch. User messages are now written AT RECEIPT, so when the turn reads the
         history its question is already there; without the filter the model reads the same question twice.
      2. The messages WAITING in the batcher (``id_bo_qua``): they are either pulled in mid-turn under the
         "new message" label or belong to the next turn; neither is the history of this turn.

    Filtered by ROW id, not by content: two people sending the same text, or one asking the same old question
    again, is normal and must not be swallowed.

    CUTTING BACK after the filter is the easiest part to forget. ``get_recent_messages`` returns the N NEWEST
    messages and the rows just filtered are among them: the caller reads with a surplus and this function cuts
    to the ceiling, otherwise the history window shrinks by the batch size and nobody sees it.

    Nothing to filter (a direct test call, or a scheduled turn with a synthetic message): only the cut
    remains, which is the old behaviour.
    """
    bo_qua = set(id_bo_qua)
    for m in batch:
        if m.history_row_id is not None:
            bo_qua.add(m.history_row_id)
    con_lai = list(history) if not bo_qua else [h for h in history if h.id is None or h.id not in bo_qua]
    return con_lai[-tran_lich_su:] if tran_lich_su > 0 else con_lai


async def build_current_turn_content(
    batch: Sequence[InboundMessage], image_mode: ImageContextMode, *, deps: TurnContentDeps
) -> list[dict[str, Any]]:
    """Merge every image + text of the batch into the content of ONE user turn."""
    parts: list[dict[str, Any]] = []
    total_images = 0

    for msg in batch:
        for image in msg.images:
            total_images += 1
            # blind: do not download, do not attach: only one summary note below
            if image_mode == "blind":
                continue

            # An image persisted before (by the turn processor) is read from the store, not downloaded again;
            # when persisting failed, fall back to downloading straight from the channel URL as before
            stored = deps.load_image(image.local_path) if image.local_path else None
            downloaded = stored or await deps.download_image(image.url)
            if downloaded is None:
                continue

            # describe/hybrid: the sidecar describes (cached by local_path)
            if image_mode in ("describe", "hybrid"):
                description = await describe_image(
                    SidecarImage(downloaded.base64, downloaded.media_type, image.local_path),
                    clinic_id=deps.clinic_id,
                    store=deps.image_descriptions,
                )
                if description:
                    parts.append({"type": "text", "text": f"[Mô tả ảnh người dùng vừa gửi: {description}]"})
                elif image_mode == "describe":
                    # describe that could not describe = the main model is completely blind to this image
                    parts.append({"type": "text", "text": DESCRIBE_FAILED_NOTE})
                # hybrid needs no failure note: the pixels are attached right below

            if image_mode in ("native", "hybrid"):
                # Part "file" instead of "image": the image type is deprecated in the SDK shape (a warning per
                # image) and will be removed
                parts.append({"type": "file", "data": downloaded.base64, "mediaType": downloaded.media_type})

    if image_mode == "blind" and total_images > 0:
        parts.append({"type": "text", "text": _blind_image_note(total_images)})

    parts.append({"type": "text", "text": dong_tin_cua_luot(batch)})
    return parts

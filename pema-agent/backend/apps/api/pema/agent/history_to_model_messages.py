# ported from: src/agent/history-to-model-messages.ts
"""The stored history -> the model message list, with the most recent images re-attached within a budget.

Forced deviations: the Vercel AI SDK ``ModelMessage``/``UserContent`` become the plain dicts of
``pema.agent.model_types`` (the image part keeps the SDK shape ``{"type": "file", "data": b64, "mediaType":
...}``); ``StoredMessage`` is the contract of ``pema_contracts.conversation`` (``created_at`` an aware
datetime); the ``Allowlist`` is the contract of ``pema_contracts.agents``; ``SenderTrust`` is a frozen
dataclass holding the ``is_unverified`` function. The module stays pure and sync.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from pema.agent.model_types import ModelMessage
from pema.agent.user_message_line import dong_tin_nguoi_dung
from pema_contracts.agents import Allowlist, AllowlistMode
from pema_contracts.conversation import StoredMessage


@dataclass(frozen=True)
class StoredImage:
    base64: str
    media_type: str


type StoredImageLoader = Callable[[str], StoredImage | None]
"""Read a stored image from disk - injectable so tests need no filesystem."""

type ImageDescriptionLookup = Callable[[str], str | None]
"""Look up the text description of an image (sidecar cache). Passed in = the main model cannot read images:
replace pixels with the description text, an image with no description falls back to the existing text
"[gửi kèm N ảnh]". Not passed = normal mode, attach the pixels."""


@dataclass(frozen=True)
class HistoryImageRendering:
    """How to render history images when a sidecar exists:

    * ``keep_pixels=False`` (describe): only the description text - the main model cannot read images.
    * ``keep_pixels=True`` (hybrid, for a combo): BOTH pixels AND description - the vision member of the
      combo sees the pixels, a blind member has its pixels stripped by the router but the text description
      survives so it still knows what the image contains.
    """

    describe: ImageDescriptionLookup
    keep_pixels: bool


def plan_image_budget(history: Sequence[StoredMessage], image_limit: int) -> dict[int, int]:
    """Split the image budget from the newest message upward: the closer the message, the more it deserves
    its images. Returns a map message index -> number of images taken (insertion order = newest first).
    A separate function so the agent loop knows BEFORE building the messages which images are about to
    enter the context (they need describing first)."""
    image_budget_by_index: dict[int, int] = {}
    budget = image_limit
    index = len(history) - 1
    while index >= 0 and budget > 0:
        message = history[index]
        count = len(message.images) if message.role == "user" else 0
        if count > 0:
            take = min(count, budget)
            image_budget_by_index[index] = take
            budget -= take
        index -= 1
    return image_budget_by_index


def collect_images_within_budget(history: Sequence[StoredMessage], image_limit: int) -> list[str]:
    """Paths of the history images that will enter the context under the budget - to describe them first."""
    plan = plan_image_budget(history, image_limit)
    paths: list[str] = []
    for index, take in plan.items():
        paths.extend(history[index].images[:take])
    return paths


UNVERIFIED_TAG = "[chưa xác minh]"
"""Label put before the message of someone who is NOT in the allowlist. The persona explains what the label
means; here we only attach it in the right place."""


@dataclass(frozen=True)
class SenderTrust:
    is_unverified: Callable[[str | None], bool]


def sender_trust_from(allowlist: Allowlist) -> SenderTrust:
    """Build the checker from the allowlist configuration of the account.

    Mode "all" returns never-mark: the bot owner deliberately lets everyone write, labelling everybody makes
    the label lose all meaning and only costs tokens. Only mode "list" has the notion of
    someone-outside-the-list.
    """
    if allowlist.mode != AllowlistMode.LIST:
        return SenderTrust(is_unverified=lambda _sender_id: False)
    trong = set(allowlist.user_ids)
    # An old message stored before the sender_id column existed has no id - do not guess it is a stranger,
    # because labelling the bot owner wrongly is worse than missing one.
    return SenderTrust(is_unverified=lambda sender_id: sender_id is not None and sender_id not in trong)


def history_to_model_messages(
    history: Sequence[StoredMessage],
    image_limit: int,
    load_image: StoredImageLoader,
    time_zone: str,
    rendering: HistoryImageRendering | None = None,
    sender_trust: SenderTrust | None = None,
) -> list[ModelMessage]:
    """History -> ModelMessage, with up to ``image_limit`` of the most recent images attached again so the
    model can look at old images ("what is the group on the picture called?" a few minutes after sending
    one). An image outside the budget (or whose file was cleaned up) falls back to the existing text
    "[gửi kèm N ảnh]"."""
    image_budget_by_index = plan_image_budget(history, image_limit)

    out: list[ModelMessage] = []
    for index, message in enumerate(history):
        if message.role != "user":
            out.append({"role": "assistant", "content": message.content})
            continue

        # Attach the send time so the model knows the gap between conversation segments (someone who comes
        # back after 3 days is not continued as if they had just written).
        #
        # Someone outside the allowlist is still written into the history (the recordOnly and
        # groupPassiveListen branches) and replayed to the model on a later turn. Without a mark, what they
        # wrote sits in the history exactly like the bot owner's words - one cleverly composed message in a
        # group is enough to try steering the model on a later turn.
        text = dong_tin_nguoi_dung(
            created_at=message.created_at,
            time_zone=time_zone,
            sender_name=message.sender_name,
            nhan_chua_xac_minh=(
                UNVERIFIED_TAG
                if sender_trust is not None and sender_trust.is_unverified(message.sender_id)
                else None
            ),
            noi_dung=message.content,
        )

        take = image_budget_by_index.get(index, 0)
        if take == 0:
            out.append({"role": "user", "content": text})
            continue

        parts: list[dict[str, Any]] = []
        for rel_path in message.images[:take]:
            # describe/hybrid: attach the text description from the sidecar cache (when it exists)
            if rendering is not None:
                description = rendering.describe(rel_path)
                if description:
                    parts.append({"type": "text", "text": f"[Mô tả ảnh đính kèm: {description}]"})
                # describe (keep_pixels=False): the main model is blind, pixels are token-costly garbage
                if not rendering.keep_pixels:
                    continue
            image = load_image(rel_path)
            # A "file" part instead of "image" - the old kind is deprecated in AI SDK v7
            if image is not None:
                parts.append({"type": "file", "data": image.base64, "mediaType": image.media_type})
        parts.append({"type": "text", "text": text})
        # Every image file was cleaned up / has no description yet -> plain text keeps the payload small
        out.append({"role": "user", "content": text if len(parts) == 1 else parts})
    return out

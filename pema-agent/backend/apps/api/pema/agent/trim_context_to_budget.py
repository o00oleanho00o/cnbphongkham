# ported from: src/agent/trim-context-to-budget.ts
"""Trim context when the token estimate goes over budget.

No forced deviation (messages are plain dicts in the SDK's shape, see ``model_types.ModelMessage``).

A PURE function: no env, no DB, no log. That way every branch is testable without a model or a filesystem.

The order of the cut is DELIBERATE:

1. Drop IMAGES from the oldest messages first. Images are the heaviest thing in the context (each is worth
   a hundred lines of text), and losing an old image hurts less than losing a whole conversation turn.
2. Only then drop the oldest MESSAGES.

Two things are ABSOLUTELY never cut:

* The messages of the current turn (``so_tin_bao_ve_cuoi``): cutting into them loses the very question the
  user just asked, and the bot would answer the previous one.
* Never cut IN THE MIDDLE of a message. Web content is already wrapped in a ``<noi_dung_ngoai>`` block; a
  half cut would drop the closing tag and turn the remainder into something the model reads as system
  words, exactly the hole that wrapper exists to close.

What is cut does not vanish from the bot's memory: ``thread_summarizer`` still folds old messages into the
rolling summary through its own path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from pema.agent.model_types import ModelMessage
from pema.agent.token_estimate import TOKEN_MOI_ANH_THEO_CO, CoAnh, uoc_luong_token_tin_nhan


@dataclass(frozen=True)
class DaCat:
    so_anh_bo: int
    so_tin_bo: int
    token_truoc: int
    token_sau: int


@dataclass(frozen=True)
class KetQuaCat:
    tin_nhan: list[ModelMessage]
    da_cat: DaCat | None
    """``None`` = nothing had to be cut."""


def _la_phan_anh(part: object) -> bool:
    return isinstance(part, dict) and cast("dict[str, Any]", part).get("type") in ("file", "image")


def _la_phan_chu(part: object) -> bool:
    return isinstance(part, dict) and cast("dict[str, Any]", part).get("type") == "text"


def _bo_anh_khoi_tin(tin: ModelMessage) -> tuple[ModelMessage, int]:
    """Drop every image part of a message, keep the text. Returns ``(message, so_anh_bo)``."""
    raw = tin.get("content")
    if not isinstance(raw, list):
        return tin, 0
    content = cast("list[Any]", raw)

    con_lai = [p for p in content if not _la_phan_anh(p)]
    so_anh_bo = len(content) - len(con_lai)
    if so_anh_bo == 0:
        return tin, 0

    # Only one text part left: collapse to a string for a compact payload
    if len(con_lai) == 1 and _la_phan_chu(con_lai[0]):
        return {**tin, "content": con_lai[0].get("text")}, so_anh_bo
    # Everything dropped and nothing left: leave a trace instead of an empty message (providers reject empty
    # content, and the model should know an image used to be here)
    if len(con_lai) == 0:
        return {**tin, "content": "[ảnh cũ đã lược bớt cho gọn ngữ cảnh]"}, so_anh_bo
    return {**tin, "content": con_lai}, so_anh_bo


def cat_ngu_canh_theo_ngan_sach(
    *,
    tin_nhan: list[ModelMessage],
    tran_token: int,
    so_tin_bao_ve_cuoi: int,
    co_anh: CoAnh | None = None,
) -> KetQuaCat:
    """Trim ``tin_nhan`` to ``tran_token``.

    * ``tran_token``: token ceiling for the input part. Less than or equal to 0 = cut nothing.
    * ``so_tin_bao_ve_cuoi``: number of messages at the END of the array that belong to the current turn,
      never cut. The caller (``agent_turn_content``) knows this number because it merges history and batch.
      Clamped to at least 1: the invariant "never return an empty array" at the end of the function only
      holds while the protected zone is not empty. Passing 0 or a negative number would make every message
      cuttable and the function would return an empty array, the provider refuses, the whole turn dies.
    * ``co_anh``: the configured image size, which decides how many tokens each image weighs.
    """
    token_moi_anh = TOKEN_MOI_ANH_THEO_CO[co_anh or "normal"]
    token_truoc = uoc_luong_token_tin_nhan(tin_nhan, token_moi_anh)
    if tran_token <= 0 or token_truoc <= tran_token:
        return KetQuaCat(tin_nhan=tin_nhan, da_cat=None)

    # Index of the first message of the protected zone
    mo_bao_ve = max(0, len(tin_nhan) - max(1, so_tin_bao_ve_cuoi))
    ds = list(tin_nhan)
    so_anh_bo = 0
    so_tin_bo = 0

    # Step 1: drop images, from the OLDEST message onwards, stop as soon as there is room
    for i in range(mo_bao_ve):
        if uoc_luong_token_tin_nhan(ds, token_moi_anh) <= tran_token:
            break
        tin, bo = _bo_anh_khoi_tin(ds[i])
        if bo > 0:
            ds[i] = tin
            so_anh_bo += bo

    # Step 2: still over, drop the oldest messages outright, still leaving the protected zone
    dau = 0
    while dau < mo_bao_ve and uoc_luong_token_tin_nhan(ds, token_moi_anh) > tran_token:
        dau += 1
        so_tin_bo += 1
        ds = ds[1:]
        # ``ds`` got shorter so the protection mark inside ``ds`` shifts with it - the loop compares ``dau``
        # with the ORIGINAL ``mo_bao_ve`` so it still counts the number of dropped messages correctly

    # Drop an ORPHAN ``tool`` message at the head of the array.
    #
    # The loop above cuts by INDEX and knows nothing about the constraint that ``assistant(tool-call)`` must
    # be immediately followed by ``tool(tool-result)``. All it takes is stopping right after dropping an
    # assistant message and the remaining array opens with a tool-result that has no matching call: OpenAI
    # answers 400 "messages with role 'tool' must be a response to a preceeding message with 'tool_calls'",
    # Anthropic answers 400 "unexpected tool_result block". Measured: 42/48 probed combinations fell into
    # exactly this shape (the assistant is heavy from long text + tool-call, the tool-result is light).
    #
    # This path is only reachable through the wrap-up turn (``run_wrap_up``): the array of
    # ``build_turn_messages`` has no ``tool`` message at all.
    while len(ds) > 0 and ds[0].get("role") == "tool":
        ds = ds[1:]
        so_tin_bo += 1

    # Cut as far as possible and still over: return the protected zone and NOT an empty array. The turn
    # should still run with the very question the user just asked, better to overflow than to send empty.
    #
    # Over the ceiling but NOTHING could be cut (the protected zone covers the whole array): return ``None``
    # like when no cut was needed. Reporting ``da_cat`` with all zeros would print a "trimmed" log line
    # while nothing was removed.
    if so_anh_bo == 0 and so_tin_bo == 0:
        return KetQuaCat(tin_nhan=ds, da_cat=None)
    return KetQuaCat(
        tin_nhan=ds,
        da_cat=DaCat(
            so_anh_bo=so_anh_bo,
            so_tin_bo=so_tin_bo,
            token_truoc=token_truoc,
            token_sau=uoc_luong_token_tin_nhan(ds, token_moi_anh),
        ),
    )

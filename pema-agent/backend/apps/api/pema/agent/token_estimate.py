# ported from: src/agent/token-estimate.ts
"""Estimate the number of input tokens BEFORE calling the model.

Forced deviations: ``asSchema(zod).jsonSchema`` of the Vercel AI SDK disappears, a tool's schema is
already a JSON Schema dict (``AgentTool.parameters``). ``len()`` counts code points where the original
counted UTF-16 units; the two agree on every Vietnamese character (all in the BMP).

Why an estimate and not a real count: an exact count needs the tokenizer of the model that is running,
and the model can be changed from the dashboard (a router may even route to another model silently).
Pulling in a tokenizer only to be wrong in another way is not worth it (no dependency for something
that can be measured).

Why the ``agent_turns`` table is not enough to calibrate (tried on 2026-08-02, 78 turns):
``agent_turns.input_tokens`` is ``totalUsage``, the SUM over every step and not the size of one call; and
the table does not store the character count, so the other half of the ratio is missing.

THE CALIBRATION PATH (the "turn completed" log on EVERY turn, ``agent_loop``):

* ``uoc_luong.that`` = ``steps[0].usage.input_tokens``. On ai@7.0.37 this is ALREADY the TOTAL input tokens
  (cache reads included; ``inputTokenDetails.{noCacheTokens, cacheReadTokens}`` is only the breakdown),
  so do NOT add cache-read on top.
* ``ky_tu_input`` = ``dem_ky_tu_input_day_du(system, tools, messages)``: the character side covers EXACTLY
  the scope of ``that`` (system + tools schema + messages), because ``system`` and ``tools`` are sent
  SEPARATELY from ``messages``.

On a turn WITHOUT images (``imageMode`` other than native/hybrid) and ``soTinChen = 0`` the ratio of
``ky_tu_input`` to ``uoc_luong.that`` is the MEASURED figure for tuning ``KY_TU_MOI_TOKEN``. Images add
tokens to ``that`` without matching characters, so turns with images must be excluded.

Reference figures of 2026-08-02: the real system prompt is 5,858 chars; the heaviest turn ever logged
was 184,835 tokens accumulated over 8 steps.

Pure module: no log, no env, no DB.
"""

from __future__ import annotations

import contextlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Literal, cast

from pema.agent.model_types import ModelMessage
from pema.shared.ky_tu_moi_token import KY_TU_MOI_TOKEN
from pema_contracts.tools import AgentTool

# The chars -> token constant lives in ``shared/ky_tu_moi_token`` (with the measurement and the reason).
# It is its own file because the cross rule in ``config/`` and the Settings page also need it, and
# neither may pull this file in. Re-exported so call sites keep their import path.
__all__ = [
    "HE_SO_AN_TOAN",
    "KY_TU_MOI_TOKEN",
    "PHU_PHI_MOI_TIN",
    "TOKEN_MOI_ANH_THEO_CO",
    "CoAnh",
    "SoSanhUocLuong",
    "dem_ky_tu_input_day_du",
    "dem_ky_tu_tin_nhan",
    "dem_ky_tu_tools",
    "ngan_sach_an_toan",
    "so_sanh_uoc_luong",
    "uoc_luong_token_tin",
    "uoc_luong_token_tin_nhan",
]

type CoAnh = Literal["thumb", "normal", "hd"]

TOKEN_MOI_ANH_THEO_CO: Mapping[CoAnh, int] = MappingProxyType({"thumb": 180, "normal": 700, "hd": 2_800})
"""Cost of each image in tokens, by the CONFIGURED IMAGE SIZE.

Images are NOT counted by the length of the base64 string: that string reflects the compression of the
file and not the number of vision tokens; using it as the yardstick inflates the estimate until the
whole history is cut.

The numbers come from the existing ``estimateImageTokens`` (``zalo-image-variant.ts``, Anthropic's
(w*h)/750 formula) applied to the three sizes ``ZALO_IMAGE_QUALITY`` allows. It used to be ONE flat 800:
right for ``normal`` but 3.5 times short for ``hd`` (977x2128 = 2772 tokens). Short is the dangerous
direction: the images of the current turn sit in the protected zone so the trimmer cannot help, and an
album sent continuously merges into one arbitrarily long batch.
"""

PHU_PHI_MOI_TIN = 4
"""Per-message overhead: role, separators, the provider's framing."""

HE_SO_AN_TOAN = 0.7
"""Safety factor: only use this fraction of the ceiling.

The declared ceiling is THE MODEL'S WINDOW (the documentation and the input box both say so). The part
left over is for what the estimate cannot see: what the model writes (``LLM_MAX_OUTPUT_TOKENS`` up to
16,384), tool results accumulating across steps, and the error of the chars-per-token constant itself.
"""

_JSON_LOI = (TypeError, ValueError, RecursionError, OverflowError)


def _json_stringify(value: object) -> str:
    """``JSON.stringify``: compact separators, non-ASCII kept. May raise (unserialisable, circular)."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _dang_object(part: object) -> bool:
    """JS ``typeof part === "object"`` for the parts that can occur (dict or list)."""
    return isinstance(part, Mapping | list | tuple)


def _kieu_va_text(part: object) -> tuple[object, object]:
    """``(part.type, part.text)`` of a dict part, ``(None, None)`` for a list."""
    if not isinstance(part, Mapping):
        return None, None
    p: Mapping[str, Any] = part  # pyright: ignore[reportUnknownVariableType]
    return p.get("type"), p.get("text")


def _token_cua_phan(part: object, token_moi_anh: int) -> int:
    """Estimate the tokens of one content part."""
    if isinstance(part, str):
        return math.ceil(len(part) / KY_TU_MOI_TOKEN)
    if not _dang_object(part):
        return 0
    kieu, text = _kieu_va_text(part)
    if kieu == "text" and isinstance(text, str):
        return math.ceil(len(text) / KY_TU_MOI_TOKEN)
    if kieu in ("file", "image"):
        return token_moi_anh
    # The rest (``tool-call``, ``tool-result``, ``reasoning`` ...) is measured by JSON length. Returning 0
    # as the first version did is DANGEROUSLY wrong: a 60,000-char ``web_fetch`` tool result would be
    # reported as 4 tokens, so exactly the HEAVIEST messages would be treated as the lightest and never cut.
    try:
        return math.ceil(len(_json_stringify(part)) / KY_TU_MOI_TOKEN)
    except _JSON_LOI:
        return 0


def uoc_luong_token_tin(tin: ModelMessage, token_moi_anh: int = TOKEN_MOI_ANH_THEO_CO["normal"]) -> int:
    """Estimate the tokens of one ``ModelMessage`` (multi-part messages with images included)."""
    noi_dung = tin.get("content")
    if isinstance(noi_dung, str):
        return math.ceil(len(noi_dung) / KY_TU_MOI_TOKEN) + PHU_PHI_MOI_TIN
    if not isinstance(noi_dung, list):
        return PHU_PHI_MOI_TIN
    tong = PHU_PHI_MOI_TIN
    for phan in cast("list[object]", noi_dung):
        tong += _token_cua_phan(phan, token_moi_anh)
    return tong


def uoc_luong_token_tin_nhan(
    tins: Sequence[ModelMessage], token_moi_anh: int = TOKEN_MOI_ANH_THEO_CO["normal"]
) -> int:
    """Estimate the tokens of a whole array of messages."""
    tong = 0
    for t in tins:
        tong += uoc_luong_token_tin(t, token_moi_anh)
    return tong


def _ky_tu_cua_phan(part: object) -> int:
    """Number of text characters of a content part (an image gives 0: an image is not characters)."""
    if isinstance(part, str):
        return len(part)
    if not _dang_object(part):
        return 0
    kieu, text = _kieu_va_text(part)
    if kieu == "text" and isinstance(text, str):
        return len(text)
    if kieu in ("file", "image"):
        return 0
    try:
        return len(_json_stringify(part))
    except _JSON_LOI:
        return 0


def dem_ky_tu_tin_nhan(tins: Sequence[ModelMessage]) -> int:
    """Count the text CHARACTERS of a whole message array (images give 0). See ``dem_ky_tu_input_day_du``."""
    tong = 0
    for t in tins:
        c = t.get("content")
        if isinstance(c, str):
            tong += len(c)
            continue
        if not isinstance(c, list):
            continue
        for phan in cast("list[object]", c):
            tong += _ky_tu_cua_phan(phan)
    return tong


def dem_ky_tu_tools(tools: Mapping[str, AgentTool] | None) -> int:
    """Count the characters of the tools schema the way the provider RECEIVES it: each tool = name +
    description + the JSON schema of its parameters. This is the large FIXED part of the input that
    ``messages`` does not have."""
    if not tools:
        return 0
    tong = 0
    for ten, t in tools.items():
        tong += len(ten) + len(t.description or "")
        # an odd schema (not JSON-serialisable): drop the schema part, name + description still count
        with contextlib.suppress(*_JSON_LOI):
            tong += len(_json_stringify(t.parameters))
    return tong


def dem_ky_tu_input_day_du(
    system_prompt: str, tools: Mapping[str, AgentTool] | None, messages: Sequence[ModelMessage]
) -> int:
    """The "characters" side covering EXACTLY the scope that ``steps[0].usage.input_tokens`` counts: system
    prompt + tools schema + messages. Divided by the real token count (``that``) on a turn WITHOUT images
    and ``soTinChen = 0`` it gives the CLEAN chars-per-token ratio for tuning ``KY_TU_MOI_TOKEN``.

    Why all three: ``system`` and ``tools`` are sent SEPARATELY from ``messages`` (``agent_loop``), so
    counting only ``messages`` leaves the numerator short of the system prompt (a few thousand chars) and
    the tools, and the ratio comes out systematically low.
    """
    return len(system_prompt) + dem_ky_tu_tools(tools) + dem_ky_tu_tin_nhan(messages)


def ngan_sach_an_toan(tran_token: float) -> int:
    """The budget that is really used, derived from the declared ceiling.

    ONE function for EVERY place: this is where it once went wrong. The cut before the turn took 70% of
    the ceiling, while the stop condition inside the turn compared against 100%. Consequence: if the user
    set the ceiling exactly to the model window (as the documentation says), the provider answered 400
    BEFORE the usage came back, so the stop condition never ran and half the feature was useless.
    """
    if not math.isfinite(tran_token) or tran_token <= 0:
        return 0
    return math.floor(tran_token * HE_SO_AN_TOAN)


@dataclass(frozen=True)
class SoSanhUocLuong:
    uoc_luong: int
    that: int
    lech_phan_tram: int


def so_sanh_uoc_luong(uoc_luong: int, that: int | None) -> SoSanhUocLuong | None:
    """The estimate next to the real number, to read in the log and tune the two constants above.

    No real number (the first step has not returned usage yet) gives ``None``: do not invent a ratio from
    a zero.
    """
    if not that or that <= 0:
        return None
    # ``Math.round`` of JS rounds half UP (python's ``round`` rounds half to even)
    lech = math.floor(((uoc_luong - that) / that) * 100 + 0.5)
    return SoSanhUocLuong(uoc_luong=uoc_luong, that=that, lech_phan_tram=lech)

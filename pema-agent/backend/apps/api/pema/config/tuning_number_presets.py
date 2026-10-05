# ported from: src/config/tuning-number-presets.ts
"""Quick-pick marks for the NUMBER fields where the operator can hardly invent the figure, shared by the
Settings page and the Agents page.

WHY A FILE OF ITS OWN: the two pages get their data by two very different ways (the Settings page receives the
definitions through the JSON of ``GET /admin/model/tuning``, the Agents page builds its form from a local
constant). One list per side would drift apart after a few model generations, and nothing says so. This file
imports nothing (but the standard library) so any consumer can load it.

WHY ``label`` IS SEPARATE FROM ``hint``: the select menu keeps ``label`` whole and truncates ``hint``
(``label`` cannot shrink, ``hint`` carries all the missing width). Putting both the number and the note into
one string cuts the tail in a narrow field and reads "128.000 - phổ thông, an toàn cho mọ...": hit for real.

THESE ARE SUGGESTED MARKS, NOT A CLOSED LIST. The hand-entry field stays (the "Tùy chỉnh" entry) and takes
every value within the ``min``..``max`` of the env schema. Model names will go stale: then fix the LABEL, do
not drop the mark: a person using an old mark whose mark vanishes finds their field fallen to custom mode for
no visible reason.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class NumberPreset:
    """``MocSoGoiY``."""

    value: int
    label: str
    """ONLY the number. The part that must survive a narrow field."""
    hint: str
    """A short note, allowed to be cut when narrow."""


TRAN_KY_TU_HINT: Final = 22
"""Ceiling of the ``hint`` length, GUARDED BY A TEST.

The select popup is ``min-w-max`` so it is as wide as the longest entry. Measured on the Agents page: a 38-39
character hint made the popup 323 px, and the right column of the form sits against the window edge so the
popup touched the edge and the ``overflow:auto`` of ``<main>`` cut 1 px off: identical at 1280 px and 1500 px,
not random.

A ceiling of 22 characters measures a popup of about 220 px. The figure comes from the TIGHTEST of the two
places that use it, the row on the Settings page: the closed field is only 176 px and sits against the right
edge of the panel, so the popup may only stick out about 57 px more. A ceiling of 28 (popup 244 px) still
sticks out 11 px beyond the window: measured.

Adding a mark with a longer hint reopens exactly that bug, hence the test."""

MOC_CUA_SO_NGU_CANH: Final[tuple[NumberPreset, ...]] = (
    NumberPreset(32_000, "32.000", "model nhỏ, máy riêng"),
    NumberPreset(128_000, "128.000", "phổ thông, an toàn"),
    NumberPreset(200_000, "200.000", "Claude Haiku 4.5"),
    NumberPreset(256_000, "256.000", "Mistral 3, Qwen3, GLM"),
    NumberPreset(1_000_000, "1.000.000", "Claude 5, Gemini 3.1"),
    NumberPreset(1_050_000, "1.050.000", "GPT-5.6"),
    NumberPreset(2_000_000, "2.000.000", "tối đa cho phép"),
)
"""Context window: the token ceiling for the INPUT part of one model call.

Figures looked up on 2026-08-22: Claude Opus 5 / Sonnet 5: 1M; Haiku 4.5: 200K (the official Anthropic
documentation; a few third-party roundups say 256K for Haiku 4.5, taken from the original documentation);
GPT-5.6 Sol / Terra / Luna: 1.05M; Gemini 3.1 Pro / 3 Flash / 3.1 Flash-Lite: 1M. 256K is the MEDIAN of every
model tracked up to 19/08/2026, so it is here as a common mark and not as one model's: Mistral Large 3 and
Medium 3.5,
Kimi K2.6, Qwen3, GLM, ERNIE, Doubao, Hunyuan."""

MOC_TRAN_TOKEN_VIET_RA: Final[tuple[NumberPreset, ...]] = (
    NumberPreset(4_096, "4.096", "trả lời ngắn, rẻ"),
    NumberPreset(8_192, "8.192", "đủ cho chat thường"),
    NumberPreset(16_384, "16.384", "mặc định, đủ tạo file"),
    NumberPreset(32_000, "32.000", "viết dài, báo cáo"),
    NumberPreset(64_000, "64.000", "trần Haiku 4.5, Gemini"),
    NumberPreset(128_000, "128.000", "trần Claude 5, GPT-5.6"),
)
"""The token ceiling of what the bot WRITES in one step.

Unlike the context window these marks are NOT freely selectable: the two cross rules of
``runtime_tuning_settings`` clamp it from both sides, and with the default set (window 128,000,
``DOCUMENT_MAX_CHARS`` 20,000) the valid range is only 11,429 - 38,399.

  below -> ``DOCUMENT_MAX_CHARS`` in tokens ``> ceiling * 0.7`` blocks: the bot writes the whole file content
  INTO
           the tool call, a ceiling too low cuts it mid-way and loses the whole turn.
  above -> ``window * 0.3 <= ceiling`` blocks: the bot keeps 30% of the window for what it writes, a ceiling
  over
           that reserve leaves no room for context.

The marks 4,096 / 64,000 / 128,000 are DELIBERATELY still here although the default set refuses them: they are
valid when the user edits the paired parameter along, and the error message of the cross rule says exactly
which one to change. Dropping them hides half of the valid range of non-default configurations.

Figures looked up on 2026-08-22: Claude Opus 5 / Sonnet 5 / Fable 5 and GPT-5.6 are all 128,000; Claude Haiku
4.5 64,000; Gemini 3.1 Pro 65,536."""


def la_moc_co_san(danh_sach: Sequence[NumberPreset], so: float) -> bool:
    """Is the value one of the marks of the list."""
    return any(m.value == so for m in danh_sach)


def _to_number(text: str) -> float:
    """``Number(s)`` of JS: a junk string is NaN (never equal to a mark)."""
    try:
        return float(text)
    except ValueError:
        return float("nan")


def dang_nhap_tay_cua_so(danh_sach: Sequence[NumberPreset], gia_tri: str, da_bam_tuy_chinh: bool) -> bool:
    """Must the field show the HAND-ENTRY input, or does the menu of marks suffice?

    Shared by the Settings page and the Agents page: both once wrote this same expression themselves, and a
    drift here drops the field into the wrong mode with nothing saying so.

    ``da_bam_tuy_chinh`` must WIN over everything else: deriving purely from the value makes the field jump
    back to the menu right after "Tùy chỉnh" is pressed (the current value still equals a mark), i.e. hand
    entry is never reachable.

    An EMPTY string is not hand entry: on the Agents page it means "follow the shared Settings" and the menu
    has an entry for that meaning. A JUNK string is: a broken value must show in the input so it can be fixed,
    hiding it behind a menu shows an empty menu with no clue why.
    """
    if da_bam_tuy_chinh:
        return True
    s = gia_tri.strip()
    if s == "":
        return False
    return not la_moc_co_san(danh_sach, _to_number(s))

# ported from: src/agent/tools/tag-ky-tu-an.ts (a copy; the module is package D4's ``tools/tag_ky_tu_an.py``)
"""Strip INVISIBLE characters (ASCII smuggling) from text.

Why a copy here: ``memory_prompt_block`` and ``thread_summary_prompt_block`` (package D1) need it, while the
original lives under ``agent/tools`` (package D4), which is not on this branch. It is a 5-line pure function;
package G should make one of the two re-export the other.

Main range: Unicode Tags (U+E0000-U+E007F), the Riley Goodside channel (01/2024): every code maps 1-1 to a
printable ASCII character and RENDERS EMPTY in every browser/terminal/editor, so the operator reading a
document on the dashboard sees nothing, but the model's tokenizer still reads the letters: an instruction
hidden in this range reaches the model intact.

Four extra characters, measured in the security review (same family "the operator sees nothing"): the four
Hangul fillers U+3164, U+115F, U+1160, U+FFA0 (absent from modern Korean text, which uses precomposed
syllables), and U+2800 BRAILLE PATTERN BLANK (the Braille SPACE: filtering it glues Braille words together,
which is the real price).

NOT filtered: U+1D41D MATHEMATICAL BOLD SMALL D (it changes the MEANING inside a formula, and filtering one
code among 1024 of its block is the illusion of a filter: an attacker takes another code of the block).
ONLY these ranges, not ``\\p{Cf}`` globally and no NFKC: a broader filter breaks ZWJ emoji sequences, ZWNJ
(Persian/Indic text) and other valid Unicode variants; the only price of the Tags range is the subdivision
flags (England, Scotland, Wales), irrelevant to a Vietnamese bot.

Pure module: no import of the application.
"""

from __future__ import annotations

import re

KY_TU_AN_RE = re.compile(r"[󠀀-󠁿ㅤᅟᅠﾠ⠀]")


def loc_ky_tu_an(text: str) -> str:
    """Strip the invisible characters from ``text``; returns ``text`` itself when there is nothing to
    strip."""
    return KY_TU_AN_RE.sub("", text) if KY_TU_AN_RE.search(text) else text

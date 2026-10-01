# ported from: src/agent/tools/tag-ky-tu-an.ts
"""Filter INVISIBLE characters (ASCII smuggling) out of text.

STOPGAP COPY. The original lives in ``src/agent/tools``, which package D4 owns (``pema/agent/tools/
tag_ky_tu_an.py``); the chunker is the only consumer in the knowledge base, and D3 cannot import a file
that its worktree does not contain. When D4 and D3 are merged (package G), replace this module by an import
of ``pema.agent.tools.tag_ky_tu_an.loc_ky_tu_an`` and delete it. Same function, same character set.

Main range: Unicode Tags (U+E0000-U+E007F) - the Riley Goodside channel (01/2024): each code point maps 1-1
to a printable ASCII character and RENDERS EMPTY everywhere (browser, terminal, editor) - an operator
looking at the document on the dashboard sees nothing - but a model tokenizer still reads the letters, so
an instruction hidden in this range reaches the model intact.

Five extra single characters measured in the original security review (outside the Tags block, same
family "the operator sees nothing on the dashboard"): U+3164 HANGUL FILLER, U+115F HANGUL CHOSEONG FILLER,
U+1160 HANGUL JUNGSEONG FILLER, U+FFA0 HALFWIDTH HANGUL FILLER (all four fillers of the old Hangul syllable
composition, absent from modern Korean text) and U+2800 BRAILLE PATTERN BLANK (the SPACE of Braille: still
filtered because it renders empty and is a known smuggling channel; the real cost is that Braille words
stick together).

NOT filtered: U+1D41D MATHEMATICAL BOLD SMALL D (it was in the first version and was REMOVED): it changes
the MEANING inside a formula (``𝐝x/𝐝t`` the derivative would become the plain division ``x/t``), and
filtering one code point among the 1024 of its block is the illusion of a filter, not a filter.

ONLY these ranges/points, NOT every ``\\p{Cf}`` and no NFKC: a wider filter was measured to break ZWJ
emoji sequences, ZWNJ (Persian/Indic text) and other valid Unicode variants. The only trade-off of the Tags
range is regional subdivision flags (England, Scotland, Wales) - irrelevant to a Vietnamese bot.

Pure module: no environment, no database.
"""

from __future__ import annotations

import re
from typing import Final

_KY_TU_AN_RE: Final = re.compile("[\U000e0000-\U000e007fㅤᅟᅠﾠ⠀]")


def loc_ky_tu_an(text: str) -> str:
    """Filter invisible characters out of ``text``. Nothing found: returns ``text`` itself."""
    return _KY_TU_AN_RE.sub("", text)

# ported from: src/shared/bo-dau-tieng-viet.ts
"""Strip Vietnamese diacritics: used for the folded column of ``agent.kb_chunk`` (the FTS side) and for the
customer's question before searching. An FTS index does not know that "hoa hồng" and "hoa hong" are the
same phrase.

The letter ``đ``/``Đ`` must be replaced EXPLICITLY, by a string replacement done AFTER ``NFD``: U+0111 is a
letter of its own in the alphabet (with a stroke), not a base letter plus a combining mark, so NFD cannot
split it apart (measured in the original).

Pure function, imports nothing from the application. Forced deviation: none (``String.normalize("NFD")``
is ``unicodedata.normalize("NFD", ...)``).
"""

from __future__ import annotations

import re
import unicodedata

# Unicode combining marks (tone + hat/horn): block U+0300-U+036F. Built from code points so that no bare
# combining character sits in the source, where editors render it glued to the previous character.
_COMBINING_START = 0x0300
_COMBINING_END = 0x036F
_COMBINING_MARKS = re.compile(f"[{chr(_COMBINING_START)}-{chr(_COMBINING_END)}]")


def bo_dau_tieng_viet(s: str) -> str:
    return _COMBINING_MARKS.sub("", unicodedata.normalize("NFD", s)).replace("đ", "d").replace("Đ", "D")

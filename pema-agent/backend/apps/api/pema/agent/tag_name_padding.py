# ported from: none (support for src/agent/memory-prompt-block.ts and thread-summary-prompt-block.ts)
"""The padding-tolerant tag-name regex shared by ``memory_prompt_block`` and ``thread_summary_prompt_block``.

The original builds ``new RegExp([...THE.replace(/_/g, "")].join("[\\p{Cf}\\p{Mn}_]*"), "giu")``. Python's
``re`` has no ``\\p{..}`` property escapes (and the ``regex`` library is not a dependency), so the class of
format characters (``Cf``), nonspacing marks (``Mn``) and the underscore is spelled out once from
``unicodedata`` at import. Only planes 0, 1 and 14 hold ``Cf``/``Mn`` characters, so only those are scanned
(about 200k lookups, a few tens of milliseconds, once per process).

The Unicode tables of Python and of the Node build the original ran on can differ by a release; the class
only decides which invisible characters an attacker may interleave in a tag name, so a character that one
side knows and the other does not is an edge case, not a hole in the design.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from itertools import chain

_SCANNED_PLANES = (range(0x20000), range(0xE0000, 0xF0000))


def _ranges() -> Iterable[tuple[int, int]]:
    start: int | None = None
    previous = -2
    for codepoint in chain.from_iterable(_SCANNED_PLANES):
        if unicodedata.category(chr(codepoint)) in ("Cf", "Mn"):
            if start is None:
                start = codepoint
            elif codepoint != previous + 1:
                yield start, previous
                start = codepoint
            previous = codepoint
    if start is not None:
        yield start, previous


def _padding_class() -> str:
    body = "".join(f"\\U{low:08x}-\\U{high:08x}" for low, high in _ranges())
    return f"[{body}_]*"


PADDING = _padding_class()
"""Regex source: zero or more invisible characters, diacritics or underscores."""


def tag_name_regex(tag: str) -> re.Pattern[str]:
    """Match every letter of ``tag`` (underscores dropped) with ``PADDING`` allowed between letters, case
    insensitive."""
    return re.compile(PADDING.join(re.escape(ch) for ch in tag.replace("_", "")), re.IGNORECASE)

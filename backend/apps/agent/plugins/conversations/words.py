"""The words a scenario search matches on: Vietnamese folded to plain letters, and the pairs of neighbours.

The same idea as the knowledge store's keyword search ("Điều trị NÁM" -> dieu, tri, nam, dieutri, trinam),
kept here so the two plugins stay apart."""

from __future__ import annotations

import itertools
import re
import unicodedata
from typing import Final

MAX_QUERY_TERMS: Final = 24
SOCIAL: Final = frozenset(
    {
        *("chao", "alo", "hi", "hello", "da", "vang", "uh", "ok", "oke", "okay", "cam", "on", "nhe", "nha"),
        *("nhen", "oi", "xin", "a", "ah", "ha", "di", "la", "the", "nao", "co", "khong", "anh", "chi", "em"),
        *("ban", "cho", "minh", "toi"),
    }
)
"""Words that carry no question: a message made of these alone is not worth keeping."""


def fold(text: str) -> str:
    """Lower case, without Vietnamese marks."""
    lowered = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text))


def terms(text: str) -> list[str]:
    """The folded words and each pair of neighbours joined, in order and without repeats."""
    found = words(text)
    return list(dict.fromkeys([*found, *(a + b for a, b in itertools.pairwise(found))]))


def query_terms(question: str) -> list[str]:
    """The terms of a question without the words every question has, at most ``MAX_QUERY_TERMS``."""
    kept = [w for w in words(question) if w not in SOCIAL]
    return list(dict.fromkeys([*kept, *(a + b for a, b in itertools.pairwise(kept))]))[:MAX_QUERY_TERMS]


def meaningful(text: str) -> list[str]:
    """The words of a text that say something (not greetings or thanks)."""
    return [w for w in words(text) if w not in SOCIAL]

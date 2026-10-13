"""Words for the plain search over skills: lower case, no diacritics, so "tư vấn" finds "tu van"."""

from __future__ import annotations

import re
import unicodedata
from typing import Final

from .models import Item

WORD: Final = re.compile(r"[a-z0-9]+")


def fold(value: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFD", value) if unicodedata.category(c) != "Mn")
    return stripped.replace("đ", "d").replace("Đ", "D").lower()


def words(value: str) -> list[str]:
    return WORD.findall(fold(value))


def relevance(query: str, item: Item) -> int:
    """How many of the query's words the item holds, the name and the description counting more."""
    wanted = set(words(query))
    name, description, body = set(words(item.name)), set(words(item.description)), set(words(item.body))
    return sum(3 * (w in name) + 2 * (w in description) + (w in body) for w in wanted)

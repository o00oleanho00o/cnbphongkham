"""Small to big: the search finds a short chunk (one fact under its own heading); what the agent and the
judge read is the section around it, so the neighbouring facts (opening and closing time, price and
promotion) come with it and the judge sees a passage that stands on its own.

A chunk's ``path`` holds the headings above it, joined with `` > ``. The section of a chunk is the chunks
of the same document whose path is, or lies under, its path without the last heading (for a document that
goes from its title straight to the small headings, that is the whole document). A chunk with fewer than
``MIN_DEPTH`` headings has no section; a section longer than ``MAX_SECTION_CHARS`` is cut to the chunks
nearest the one found, so a chunk that is long already is not widened at all.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Final

from .models import Chunk, Hit

SEPARATOR: Final = " > "
MIN_DEPTH: Final = 2
MAX_SECTION_CHARS: Final = 1200


def parent_of(path: str) -> str:
    """The headings above the last one; empty when there is no section around a chunk of this depth."""
    parts = path.split(SEPARATOR)
    return SEPARATOR.join(parts[:-1]) if len(parts) >= MIN_DEPTH else ""


def in_section(path: str, parent: str) -> bool:
    return path == parent or path.startswith(parent + SEPARATOR)


def widen(hit: Hit, members: Sequence[Chunk], limit: int = MAX_SECTION_CHARS) -> tuple[Hit, frozenset[str]]:
    """The hit with the text of its section in place of its own chunk (its heading becomes the section's,
    and each other chunk keeps its own heading as a line), and the ids of the chunks it now holds. Unchanged
    when no other chunk of the section is there."""
    parent = parent_of(hit.chunk.path)
    ordered = sorted(members, key=lambda c: c.ordinal)
    ids = [c.id for c in ordered]
    alone = (hit, frozenset({hit.chunk.id}))
    if not parent or hit.chunk.id not in ids or len(ordered) < 2:
        return alone
    chosen = _nearest(ordered, ids.index(hit.chunk.id), limit)
    if len(chosen) < 2:
        return alone
    body = "\n\n".join(_part(c, parent) for c in chosen)
    return replace(hit, chunk=replace(hit.chunk, path=parent, body=body)), frozenset(c.id for c in chosen)


def _nearest(ordered: Sequence[Chunk], at: int, limit: int) -> list[Chunk]:
    """All of them when they fit, else the one at ``at`` and the nearest ones either side while they fit,
    taking a side and then the other, so the window does not lean to one end."""
    if sum(len(c.body) for c in ordered) <= limit:
        return list(ordered)
    low = high = at
    used = len(ordered[at].body)
    first = "before"
    while True:
        sides = {
            "before": ordered[low - 1] if low > 0 else None,
            "after": ordered[high + 1] if high + 1 < len(ordered) else None,
        }
        order = [first, "after" if first == "before" else "before"]
        fits = [side for side in order if (c := sides[side]) and used + len(c.body) <= limit]
        if not fits:
            return list(ordered[low : high + 1])
        side = fits[0]
        taken = sides[side]
        used += len(taken.body) if taken else 0
        low, high = (low - 1, high) if side == "before" else (low, high + 1)
        first = "after" if side == "before" else "before"


def _part(chunk: Chunk, parent: str) -> str:
    heading = chunk.path[len(parent) + len(SEPARATOR) :] if chunk.path != parent else ""
    return f"{heading}\n{chunk.body}" if heading else chunk.body

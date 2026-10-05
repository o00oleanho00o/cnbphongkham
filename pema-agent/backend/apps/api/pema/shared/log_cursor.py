# ported from: src/shared/log-cursor.ts
"""Pagination cursor for the Logs page.

A log line has NO id: only a timestamp ``time`` (ms). And the logger writes SEVERAL lines in the SAME
millisecond when the bot is busy: one agent turn fires a whole cluster of adjacent lines. So a cursor that
carries only ``time`` breaks in one of two ways, depending on the comparison:

  - take ``time < mark``  -> LOSES every line in the same millisecond as the last line of the page
  - take ``time <= mark`` -> REPEATS those very lines on the next page

Both are bad, and bad exactly when the log is most worth reading (when the bot is busy). So the cursor also
carries ``da_lay``: how many lines with EXACTLY that mark were already taken. The next page skips exactly that
many and continues: nothing lost, nothing repeated.

String form ``<time>.<da_lay>`` so it travels in a query string without encoding.

Pure module, imports nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_SAFE_INTEGER = 2**53 - 1
"""``Number.MAX_SAFE_INTEGER``: past it a time comparison is no longer trustworthy."""

_CURSOR_RE = re.compile(r"(\d+)\.(\d+)")


@dataclass(frozen=True)
class ConTroLog:
    time: int
    """Timestamp (ms) of the last line of the previous page."""
    da_lay: int
    """How many lines with exactly that ``time`` were returned on the previous pages."""


def doi_con_tro_thanh_chuoi(c: ConTroLog) -> str:
    return f"{c.time}.{c.da_lay}"


def doc_con_tro(raw: str | None) -> ConTroLog | None:
    """Read a cursor from the query string. ``None`` when the string is broken.

    A broken cursor must NOT fall back to the first page: that is how a client appends endless copies without
    anyone noticing (Hermes states the rule in ``list_sessions``: "Unknown cursor -> empty page, do not fall
    back to full list"). A caller that gets ``None`` returns an EMPTY page, not the first one.

    ONLY a string of digits on both sides of the dot is accepted, exactly the form we generate. Not
    ``float()`` followed by an integer check: ``Number("")`` is 0 in JS and not NaN, so a truncated cursor
    ("1700000000000.") slipped through as ``da_lay: 0`` and the next page returned the whole same-millisecond
    cluster AGAIN. A test caught exactly this case.
    """
    if not raw:
        return None
    match = _CURSOR_RE.fullmatch(raw)
    if match is None:
        return None
    time = int(match.group(1))
    da_lay = int(match.group(2))
    if time > _SAFE_INTEGER or time <= 0:
        return None
    if da_lay > _SAFE_INTEGER:
        return None
    return ConTroLog(time=time, da_lay=da_lay)

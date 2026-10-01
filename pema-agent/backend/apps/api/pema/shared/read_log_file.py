# ported from: src/shared/read-log-file.ts
"""Read back the log written to files, to show on the dashboard.

Each line is one JSON object (ndjson); ``level`` is the pino NUMBER (``LOG_LEVELS``), see ``log_file_lines``
for how the stdlib-logging lines of ``pema.shared.logger`` are read into that shape.

PURE module: takes the directory as a parameter and touches no environment, so a test runs it directly and any
caller can use it. It is synchronous (disk + parse): an async route calls it through ``asyncio.to_thread``.

Reads a whole file then filters in memory, no streaming: the file rotates every day so each file is the log of
one day. In exchange there is a ``MAX_BYTES_PER_FILE`` ceiling (``log_file_lines``) so an unusual day does not
bring the page down.

Forced deviation: pino-roll named the files ``bot.<day>.<n>.log``; ``TimedRotatingFileHandler`` names the
current file ``bot.log`` and the rotated ones ``bot.log.<day>``. Files are therefore ordered newest first with
``bot.log`` (the current one) on top, then the rest by name descending (the date suffix sorts by time).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from pema.shared.log_cursor import ConTroLog, doi_con_tro_thanh_chuoi
from pema.shared.log_file_lines import LOG_LEVELS, LogEntry, doc_duoi_file, tach_dong

__all__ = ["LOG_LEVELS", "LogEntry", "ReadLogsOptions", "ReadLogsResult", "read_recent_logs"]

_CURRENT_LOG = "bot.log"
_ROTATED = re.compile(r"^bot\.log\.\d")


@dataclass(frozen=True)
class ReadLogsOptions:
    limit: int
    min_level: int | None = None
    """Only from this level up (a pino number)."""
    scope: str | None = None
    search: str | None = None
    """Look for text in the whole log line, case-insensitive."""
    before: ConTroLog | None = None
    """Only lines OLDER than this position: the "Xem thêm" button. See ``log_cursor`` for why the cursor needs
    ``da_lay`` and not only the timestamp."""


@dataclass(frozen=True)
class ReadLogsResult:
    entries: list[LogEntry]
    scopes: list[str]
    """Scopes seen in the files that were READ: to build the filter box without hard-coding. Not every scope
    that ever existed: an old file that did not need opening is not opened."""
    files_read: int
    """How many files had to be opened: tells how many days the result spans."""
    next_cursor: str | None
    """Cursor for the next "Xem thêm"; ``None`` = no more log to read.

    Knowing it is the end by taking ONE EXTRA line (``limit + 1``) and trimming: far cheaper than counting the
    total matching lines, which would parse every file."""


def _list_log_files(directory: Path) -> list[str] | None:
    try:
        names = [
            f.name
            for f in directory.iterdir()
            if f.is_file() and (f.name.endswith(".log") or _ROTATED.match(f.name))
        ]
    except OSError:
        return None
    # Newest first: the current file, then by name descending, and stop early
    return sorted(names, key=lambda n: (n == _CURRENT_LOG, n), reverse=True)


def read_recent_logs(directory: Path, options: ReadLogsOptions) -> ReadLogsResult:
    files = _list_log_files(directory)
    if files is None:
        return ReadLogsResult(entries=[], scopes=[], files_read=0, next_cursor=None)

    needle = options.search.lower() if options.search else None

    def matches(e: LogEntry) -> bool:
        if options.min_level is not None and e.level < options.min_level:
            return False
        if options.scope and e.scope != options.scope:
            return False
        if needle:
            import json

            in_line = f"{e.msg} {e.scope} {json.dumps(e.fields, ensure_ascii=False, default=str)}".lower()
            if needle not in in_line:
                return False
        return True

    # Walk from the newest file to the old ones and STOP as soon as there are enough lines. The old version
    # read
    # and parsed the whole 7-day log (~6.5 MB measured) on every visit to return 200 lines.
    #
    # Take ONE extra line to know whether more log lies behind without counting the total.
    can_lay = options.limit + 1
    before = options.before
    entries: list[LogEntry] = []
    scopes: set[str] = set()
    files_read = 0
    # How many lines matching the filter have EXACTLY the ``time`` of the last line walked, counted from the
    # start
    # of the stream (the lines skipped by the cursor included). This is the ``da_lay`` of the next page's
    # cursor.
    cung_moc = 0
    moc_dang_dem = -1

    for name in files:
        if len(entries) >= can_lay:
            break
        files_read += 1

        # Inside a file the last line is the newest so walk backwards
        lines = doc_duoi_file(directory / name).split("\n")
        for raw in reversed(lines):
            if not raw.strip():
                continue
            e = tach_dong(raw)
            if e is None:
                continue
            # Scopes are gathered from EVERY line of an opened file, filtered-out lines included: otherwise
            # filtering by one scope leaves the box with only that scope
            if e.scope:
                scopes.add(e.scope)
            if not matches(e):
                continue

            # The count must run BEFORE the cursor drops a line, since ``da_lay`` is counted from the stream
            # start
            if e.time != moc_dang_dem:
                moc_dang_dem = e.time
                cung_moc = 0
            cung_moc += 1

            if before is not None:
                # A line newer than the cursor: already returned on a previous page
                if e.time > before.time:
                    continue
                # Same mark: skip exactly the number already returned, the rest belongs to this page
                if e.time == before.time and cung_moc <= before.da_lay:
                    continue

            entries.append(e)
            if len(entries) >= can_lay:
                break

    more = len(entries) > options.limit
    page = entries[: options.limit]
    last = page[-1] if page else None
    # ``cung_moc`` now matches the EXTRA line (if any), not the last line of the page, so count again within
    # the
    # page instead of using that variable directly.
    next_cursor = (
        doi_con_tro_thanh_chuoi(
            ConTroLog(time=last.time, da_lay=_so_dong_cung_moc_tinh_tu_dau(page, last.time, before))
        )
        if more and last is not None
        else None
    )
    return ReadLogsResult(entries=page, scopes=sorted(scopes), files_read=files_read, next_cursor=next_cursor)


def _so_dong_cung_moc_tinh_tu_dau(page: list[LogEntry], moc: int, before: ConTroLog | None) -> int:
    """Total number of lines with mark ``time`` returned SINCE THE START of the stream, previous pages
    included.

    The previous page already returned ``before.da_lay`` lines at that mark, so if this page still has lines
    at
    the same mark they must be added up: not adding makes the next page skip too few and return exactly the
    lines just seen."""
    n = sum(1 for e in page if e.time == moc)
    return before.da_lay + n if before is not None and before.time == moc else n

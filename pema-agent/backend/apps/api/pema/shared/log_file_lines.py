# ported from: src/shared/log-file-lines.ts
"""Read a log file and split one ndjson line into a ``LogEntry``.

Split from ``read_log_file`` so that file keeps the file choice, the filtering and the paging: this is the
part that touches the disk and parses, with no business rule.

Forced deviation (pino -> stdlib ``logging``, see ``pema.shared.logger``): a line is ``{"time": <ISO 8601>,
"level": "<name>", "scope": ..., "msg": ..., <fields>}``; pino wrote ``time`` as epoch milliseconds and
``level`` as a number. The parser converts both, so ``LogEntry`` keeps the pino shape (``time`` in ms,
``level`` as the pino number) that the cursor and the filters work on. ``pid`` and ``hostname`` do not exist
in the Python lines (nothing to strip).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Final, cast

LOG_LEVELS: Final[dict[str, int]] = {
    "trace": 10,
    "debug": 20,
    "info": 30,
    "warn": 40,
    "error": 50,
    "fatal": 60,
}
"""pino's numbers. ``warning`` (the stdlib name) and ``critical`` are read as ``warn`` and ``fatal``."""

_LEVEL_ALIASES: Final[dict[str, int]] = {**LOG_LEVELS, "warning": 40, "critical": 60}

MAX_BYTES_PER_FILE: Final = 4 * 1024 * 1024
"""Only read the TAIL of a big file: the newest lines are at the end."""


@dataclass(frozen=True)
class LogEntry:
    time: int
    """Epoch milliseconds."""
    level: int
    """The pino number: the UI turns it into a label."""
    scope: str
    msg: str
    fields: dict[str, Any] = field(default_factory=dict[str, Any])
    """Every remaining field (thread id, account id, err ...): where the context lives."""


def doc_duoi_file(file_path: Path) -> str:
    """Read the tail of a file, dropping the first line when it was cut in the middle."""
    size = file_path.stat().st_size
    if size <= MAX_BYTES_PER_FILE:
        return file_path.read_text(encoding="utf-8", errors="replace")
    with file_path.open("rb") as handle:
        handle.seek(size - MAX_BYTES_PER_FILE)
        text = handle.read(MAX_BYTES_PER_FILE).decode("utf-8", errors="replace")
    # The first line is almost surely cut off -> drop it
    return text[text.find("\n") + 1 :]


def _epoch_ms(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int | float):
        return int(value)
    if isinstance(value, str):
        try:
            return round(datetime.fromisoformat(value).timestamp() * 1000)
        except ValueError:
            return 0
    return 0


def tach_dong(raw: str) -> LogEntry | None:
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        # A broken line (half written when the process died) must not kill the whole page
        return None
    if not isinstance(parsed, dict):
        return None
    obj = cast("dict[str, Any]", parsed)
    level_raw = obj.get("level")
    if isinstance(level_raw, bool):
        return None
    if isinstance(level_raw, int | float):
        level = int(level_raw)
    elif isinstance(level_raw, str) and level_raw.lower() in _LEVEL_ALIASES:
        level = _LEVEL_ALIASES[level_raw.lower()]
    else:
        return None
    scope = obj.get("scope")
    msg = obj.get("msg")
    fields = {k: v for k, v in obj.items() if k not in {"level", "time", "scope", "msg"}}
    return LogEntry(
        level=level,
        time=_epoch_ms(obj.get("time")),
        scope=scope if isinstance(scope, str) else "",
        msg=msg if isinstance(msg, str) else "",
        fields=fields,
    )

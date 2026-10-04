# ported from: src/agent/user-message-line.ts
"""ONE user message line as the model reads it: ``[08/08 00:12] Hải: nội dung``.

Forced deviation: the instant is an aware ``datetime`` (the original passed an ISO-UTC string); the
"invalid date" branch of ``formatTimestamp`` has no counterpart because a ``datetime`` cannot be invalid.
A NAIVE datetime is read as UTC so the result never depends on the zone of the process.

Why it is one shared function: there are TWO paths that build a user message - the history
(``history_to_model_messages``) and the message of the running turn (``agent_turn_content``, shared with
messages that arrive in the middle of a turn). The two paths drifting apart caused a real bug:

  The history carried a time label, the current turn's message did NOT. So the newest timestamp the model
  saw was always the one of the message BEFORE. On 07/08/2026, a message at 23:37 died on a provider error
  and went into the history; at 00:12 the next day the user wrote again, the model read the 23:37 label at
  the end of the history and believed the question was sent then - it had to call ``get_datetime`` to
  untangle what "today" means.

Hermes met exactly this and solved it the right way: one single render function, and ONE switch governing
both the current message and the replayed history (``gateway/run.py`` passes the same ``inject_timestamps``
to both paths). goclaw guards against the confusion with a structural label ``[Your current message]`` - a
different way, the same insight: that boundary has to be stated somehow.

PURE module: the time zone is passed in by the caller (same rule as ``current_datetime``), so it does not
pull in ``runtime_tuning_settings`` - whose original opens the DB at import time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pema.shared.current_datetime import get_date_time_parts


def format_timestamp(instant: datetime, time_zone: str) -> str:
    """``[25/07 14:30]`` in ``BOT_TIMEZONE``, NOT the time of the process.

    The old version used ``d.getHours()``/``d.getDate()`` - the LOCAL time of the machine running the bot.
    On a Windows dev machine (Vietnam zone) it coincides with ``BOT_TIMEZONE`` so it was right by
    coincidence; in a Docker container (``node:24-alpine`` runs UTC, no ``TZ=`` anywhere in the Dockerfile
    or compose) the history labels were 7 hours off against the "Hôm nay là..." line of the system prompt -
    that line already went through ``BOT_TIMEZONE``. The model received a self-contradicting prompt and had
    no way to know which side was right.

    This used to be the ONLY place in ``src/`` that built a time for the model to read without going
    through ``BOT_TIMEZONE``, i.e. the only place that bypassed the "Múi giờ của bot" field of the
    dashboard.
    """
    moment = instant if instant.tzinfo is not None else instant.replace(tzinfo=UTC)
    p = get_date_time_parts(time_zone, moment)
    # ``p.date`` is "25/07/2026" - drop the year to keep it short, keep the old shape. Cut with split and not
    # a [:5] slice so that changing the format at the source does not silently yield a truncated string.
    ngay, thang = p.date.split("/")[:2]
    return f"[{ngay}/{thang} {p.time}]"


def dong_tin_nguoi_dung(
    *,
    created_at: datetime | None,
    time_zone: str,
    sender_name: str | None = None,
    nhan_chua_xac_minh: str | None = None,
    noi_dung: str,
) -> str:
    """Join exactly one line. The order is fixed: ``[giờ] [nhãn] Tên: nội dung`` - the shape the persona
    describes to the model ("định dạng [ngày/tháng giờ:phút] Tên: nội dung"); change it here and the same
    sentence in ``persona_prompt`` must change too.

    ``created_at`` missing = drop the time label altogether (old messages stored before the column existed).
    ``sender_name`` empty = no name (a message of unknown sender). ``nhan_chua_xac_minh``: a sender outside
    the allowlist gets a label so the model reads without obeying.
    """
    ts = format_timestamp(created_at, time_zone) if created_at else ""
    nhan = f"{nhan_chua_xac_minh} " if nhan_chua_xac_minh else ""
    ten = f"{sender_name}: " if sender_name else ""
    return f"{ts} {nhan}{ten}{noi_dung}".strip()

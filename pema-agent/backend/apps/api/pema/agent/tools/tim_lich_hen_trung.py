# ported from: src/agent/tools/tim-lich-hen-trung.ts
"""Find an existing schedule that duplicates the one the model is about to create.

WHY THIS FILE EXISTS - a real case of 2026-08-20, read from the trace:

A user asked for a reminder; the bot set it in turn 2 and said "Đã đặt lịch xong rồi". In turn 3 the user
only wrote "okay cảm ơn bạn" - and the bot CREATED THE SAME REMINDER AGAIN. The model stated its own intent
in the trace: "Mình KIỂM TRA và chốt lịch nhắc ngay để bảo đảm tin sẽ được gửi đúng giờ nhé."

It really wanted to check. But the conversation history does NOT carry tool calls
(``history_to_model_messages`` only returns ``{role: assistant, content}``, plain text), so in the next
turn the
model has no evidence the tool ran; it only sees the sentence it said itself. The only thing within reach to
"check" was ``create``. Result: two identical jobs, the user received two messages at 11:00 and two
proactive-send slots were spent.

THE DEDUPE KEY = ``(kind, schedule, NAME)``, WITHOUT ``payload``. Measured on those two jobs, not guessed:

  name     "Nhắc đóng học phí Phật học"  ==  "Nhắc đóng học phí Phật học"
  kind     message                       ==  message
  schedule once 2026-08-30 11:00         ==  once 2026-08-30 11:00
  payload  "🔔 ... nhớ đóng ... nhé!"     !=  "... hôm nay nhớ đóng ... nhé."

``payload`` is free prose, so the model rewrites it differently every time - a key containing it misses
exactly
the case to catch. ``name`` is a SHORT label summarising the intent, so it comes out identical to the
character.

WHY NOT drop ``name`` from the key as well (i.e. block every job on the same time): a person can perfectly
book
TWO different things at the same hour ("11:00 nhắc đóng học phí" and "11:00 nhắc họp phụ huynh"). Dropping
``name`` would wrongly block that. The price is that this is a GUESS BY NAME: a name off by one word slips
through. ``cung_lich`` below is the safety net for that slip - it does not block, it only gives the model the
information so it tells the user.

Forced deviation (SQLite store -> Postgres scheduler port): ``schedule_columns`` of ``scheduled-job-
record.ts``
is owned by package S; the three-line mapping is re-implemented locally in ``_schedule_columns`` (the same
mapping S uses to write the row: once -> ``run_at``, every -> ``every_minutes``, cron -> ``cron_expr``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pema_contracts.scheduler import (
    CronSchedule,
    EverySchedule,
    JobKind,
    OnceSchedule,
    ParsedSchedule,
    ScheduledJob,
    ScheduleKind,
)


@dataclass(frozen=True)
class KetQuaTimTrung:
    trung_khit: ScheduledJob | None = None
    """EXACT duplicate (same name + same kind + same schedule). The caller returns this job to the model
    instead of creating another one - this is a SUCCESS (the desired state already exists), not an error."""
    cung_lich: list[ScheduledJob] = field(default_factory=list[ScheduledJob])
    """Same run schedule but a DIFFERENT name. Still created normally; the caller only appends one sentence to
    the result so the model can tell the user."""


def chuan_hoa_ten(ten: str) -> str:
    """Normalise a name before comparing: trim, collapse runs of whitespace, lower-case.

    Does NOT strip Vietnamese diacritics. Two DIFFERENT reminders that differ only by a diacritic is a case
    that does not exist, so stripping them only opens more collisions without catching anything more - the
    same reasoning settled in ``kb-search`` for diacritics ("đóng" vs "đồng").
    """
    return re.sub(r"\s+", " ", ten.strip()).lower()


def _schedule_columns(schedule: ParsedSchedule) -> tuple[str | None, int | None, str | None]:
    """``schedule_columns`` of ``scheduled-job-record.ts`` (owned by package S): exactly one of the three
    columns has a value, the others are NULL. Returns ``(run_at, every_minutes, cron_expr)``."""
    run_at = schedule.run_at_utc if isinstance(schedule, OnceSchedule) else None
    every_minutes = schedule.minutes if isinstance(schedule, EverySchedule) else None
    cron_expr = schedule.expr if isinstance(schedule, CronSchedule) else None
    return run_at, every_minutes, cron_expr


def _cung_lich_chay(job: ScheduledJob, schedule: ParsedSchedule) -> bool:
    """Do the two schedules run at EXACTLY the same beat/moment - compared on the shape stored in the DB."""
    if job.schedule_kind != ScheduleKind(schedule.kind):
        return False
    # The columns rather than peeling each branch by hand: this is the SAME mapping the scheduler uses to
    # write
    # the row, so the two sides cannot drift in how they read a schedule.
    run_at, every_minutes, cron_expr = _schedule_columns(schedule)
    return job.run_at == run_at and job.every_minutes == every_minutes and job.cron_expr == cron_expr


def tim_lich_hen_trung(
    *,
    jobs: list[ScheduledJob],
    name: str,
    kind: JobKind,
    schedule: ParsedSchedule,
) -> KetQuaTimTrung:
    # Consider ONLY jobs that are REALLY about to run. A disabled job, or an enabled one that lost its
    # next run
    # (``next_run_at = NULL``), will never fire - the user asking to set that schedule again is a VALID
    # request, blocking it would be wrong.
    sap_chay = [j for j in jobs if j.enabled and j.next_run_at is not None]
    cung_lich = [j for j in sap_chay if j.kind == kind and _cung_lich_chay(j, schedule)]

    ten_can_tim = chuan_hoa_ten(name)
    trung_khit = next((j for j in cung_lich if chuan_hoa_ten(j.name) == ten_can_tim), None)

    return KetQuaTimTrung(
        trung_khit=trung_khit,
        # Take the exact duplicate itself out of the "same schedule, other name" list - it is already reported
        # through its own road, telling it again would only confuse the model.
        cung_lich=[j for j in cung_lich if trung_khit is None or j.id != trung_khit.id],
    )

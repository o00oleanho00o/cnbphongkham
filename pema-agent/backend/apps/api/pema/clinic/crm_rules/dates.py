# ported from: prototype/shared/crm-data.js (addDays, days)
"""Calendar-day arithmetic of the CRM rules.

The JavaScript helpers work on ``YYYY-MM-DD`` strings anchored at noon UTC so that DST and the machine's zone
never move a day. Python ``date`` objects have the same property, so the helpers are one-liners; what is kept
is the SIGN convention of ``days``: ``days(from, to)`` is ``to - from``, positive when ``from`` is in the
past.

One forced deviation: a birthday on 29 February (JavaScript turns ``2026-02-29`` into 1 March and then builds
an invalid ``2026-02-29T09:00:00+07:00`` due date) is observed on 28 February in a non-leap year.
"""

from __future__ import annotations

from calendar import isleap
from datetime import date, timedelta


def add_days(day: date, n: int) -> date:
    """``addDays(day, n)``."""
    return day + timedelta(days=n)


def days_between(from_day: date, to_day: date) -> int:
    """``days(from, to)``: whole days from ``from_day`` to ``to_day`` (negative if ``to_day`` is earlier)."""
    return (to_day - from_day).days


def birthday_in_year(birth_date: date, year: int) -> date:
    """The day the birthday is observed in ``year`` (29 February becomes 28 February in a non-leap year)."""
    if birth_date.month == 2 and birth_date.day == 29 and not isleap(year):
        return date(year, 2, 28)
    return date(year, birth_date.month, birth_date.day)


def next_birthday(birth_date: date, today: date) -> date:
    """The coming birthday on or after ``today``, rolling over to next year (crm-test: year boundary)."""
    this_year = birthday_in_year(birth_date, today.year)
    if this_year < today:
        return birthday_in_year(birth_date, today.year + 1)
    return this_year

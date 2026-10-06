"""``clinic.account_roster`` (package O, step O1): who covers which channel identity when.

Later steps of package O add the assignment history, the notification outbox and the push tokens to this
module. Columns only, like the rest of ``pema.clinic.models``; the database owns the foreign keys and the
CHECKs (exactly one of ``weekdays`` and ``on_date``, ``start_time <> end_time``).
"""

from __future__ import annotations

from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import ARRAY, Date, DateTime, Integer, Text, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class AccountRoster(Base):
    __tablename__ = "account_roster"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    account_id: Mapped[str] = mapped_column(Text)
    user_id: Mapped[UUID]
    weekdays: Mapped[list[str] | None] = mapped_column(ARRAY(Text), default=None)
    """``mon`` .. ``sun`` (the keys of ``clinic.staff_profiles.shift``); ``None`` when the entry is for one
    date."""
    on_date: Mapped[date | None] = mapped_column(Date, default=None)
    start_time: Mapped[time] = mapped_column(Time)
    end_time: Mapped[time] = mapped_column(Time)
    """Earlier than ``start_time``: the slot ends the next morning (a night shift)."""
    note: Mapped[str | None] = mapped_column(Text, default=None)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012

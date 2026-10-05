"""Declarative base of the ORM mapping of ``clinic.*``.

New module (not a port). The mapping is deliberately thin: columns only, no ``relationship`` and no
``ForeignKey`` declarations. The database owns the composite ``(clinic_id, id)`` foreign keys and the row
level security (migration 0001), so the ORM never has to reproduce them; joins are written explicitly in
the actions. ``updated_at`` is not mapped: a trigger maintains it and nothing reads it.

``version`` columns use SQLAlchemy's ``version_id_col``: every UPDATE is ``... WHERE version = <old>`` and a
lost race raises ``StaleDataError``, which the actions map to ``version_conflict`` (optimistic locking of
ARCH-PB01).
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

CLINIC_SCHEMA = "clinic"


class Base(DeclarativeBase):
    metadata = MetaData(schema=CLINIC_SCHEMA)

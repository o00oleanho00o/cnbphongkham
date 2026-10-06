"""appointment room (package U, step U10): the room-column grid of ``/schedule``.

Source: ``prototype/shared/operations-data.js`` (``appointments[].room``, ``validate``: a room that is busy or
blocked refuses the booking). U4 added ``clinic.room`` and ``clinic.room_block`` but an appointment still had no
room, so the room rules (room against appointment, room against block) had nothing to check. This revision adds
the one nullable column:

* ``clinic.appointment.room_id``: the room of the visit, or NULL (every appointment made before this revision, and
  every booking that does not name a room, keeps NULL and shows in the grid's "Chưa xếp phòng" column). The
  composite key ``(clinic_id, room_id)`` is the one ``clinic.room_block`` uses; with a NULL room ``MATCH SIMPLE``
  does not check it.
* ``appointment_room_day_idx`` for the grid and the room-conflict lookup.

Nothing else changes: the table already carries the ``be_app`` grants of the other columns. Single tenant
(``st_0009_single_tenant``): no row level security.

Revision ID: u10_0010_appointment_room
Revises: u11_0010_accountant_role
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u10_0010_appointment_room"
down_revision = "u11_0010_accountant_role"
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("ALTER TABLE clinic.appointment ADD COLUMN room_id uuid")
    _sql(
        "ALTER TABLE clinic.appointment ADD CONSTRAINT appointment_room_fk "
        "FOREIGN KEY (clinic_id, room_id) REFERENCES clinic.room (clinic_id, id)"
    )
    _sql(
        "CREATE INDEX appointment_room_day_idx ON clinic.appointment (clinic_id, room_id, starts_at) "
        "WHERE room_id IS NOT NULL"
    )


def downgrade() -> None:
    _sql("DROP INDEX IF EXISTS clinic.appointment_room_day_idx")
    _sql("ALTER TABLE clinic.appointment DROP CONSTRAINT IF EXISTS appointment_room_fk")
    _sql("ALTER TABLE clinic.appointment DROP COLUMN IF EXISTS room_id")

"""the seventh role, ``accountant`` (package U, step U11).

Source: ``recipes/U/12-U11-accountant-role-finance.md``. The role is stored as ``text`` (never a native Postgres
enum type), so no ``ALTER TYPE`` is needed; what limits the values is a CHECK constraint on three columns. This
revision widens them to accept ``accountant``, and nothing else:

* ``clinic.user_account.role`` (the sign-in account),
* ``clinic.audit_log.actor_role`` (the audit trail names the actor's role; the log stays append-only, only the
  constraint changes),
* ``clinic.staff_profiles.role`` (the care skill/shift profile; an accountant has none today, the constraint
  just must not reject the role if a profile is ever written).

No data is rewritten: no existing user changes role. Downgrade is refused while a row holds ``accountant``
(Postgres refuses to add the narrower constraint over such a row), which is the intended guard.

Revision ID: u11_0010_accountant_role
Revises: u6_0010_finance
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u11_0010_accountant_role"
down_revision = "u6_0010_finance"
branch_labels = None
depends_on = None

OLD_ROLES = ("owner", "manager", "doctor", "cs_staff", "reception", "patient")
NEW_ROLES = ("owner", "manager", "doctor", "cs_staff", "reception", "accountant", "patient")
OLD_STAFF = ("owner", "manager", "doctor", "cs_staff", "reception")
NEW_STAFF = (*OLD_STAFF, "accountant")

# (table, column, constraint name): the names Postgres gave the inline CHECKs of 0001 and m_0001
CHECKS = (
    ("clinic.user_account", "role", "user_account_role_check"),
    ("clinic.audit_log", "actor_role", "audit_log_actor_role_check"),
)
STAFF_CHECK = ("clinic.staff_profiles", "role", "staff_profiles_role_check")


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def _quoted(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _swap(table: str, column: str, name: str, values: tuple[str, ...]) -> None:
    _sql(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {name}")
    _sql(f"ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({column} IN ({_quoted(values)}))")


def upgrade() -> None:
    for table, column, name in CHECKS:
        _swap(table, column, name, NEW_ROLES)
    table, column, name = STAFF_CHECK
    _swap(table, column, name, NEW_STAFF)


def downgrade() -> None:
    for table, column, name in CHECKS:
        _swap(table, column, name, OLD_ROLES)
    table, column, name = STAFF_CHECK
    _swap(table, column, name, OLD_STAFF)

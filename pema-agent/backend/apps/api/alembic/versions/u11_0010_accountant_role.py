"""the seventh role, ``accountant`` (package U, step U11).

Source: ``recipes/U/12-U11-accountant-role-finance.md``. The role is stored as ``text`` (never a native Postgres
enum type), so no ``ALTER TYPE`` is needed; what limits the values is a CHECK constraint on three columns. This
revision widens them to accept ``accountant``, and nothing else:

* ``clinic.user_account.role`` (the sign-in account),
* ``clinic.audit_log.actor_role`` (the audit trail names the actor's role; the log stays append-only, only the
  constraint changes),
* ``clinic.staff_profiles.role`` (the care skill/shift profile; an accountant has none today, the constraint
  just must not reject the role if a profile is ever written).

No data is rewritten: no existing user changes role.

Downgrade is a deliberate no-op: the three CHECKs stay widened. Narrowing them again would make Postgres refuse
(IntegrityError) as soon as one ``accountant`` account, audit row or staff profile exists, which broke every
downgrade that passes through this revision (the care and database migration round-trip tests). The ways to
"fix" that without leaving the constraint wide are all worse: deleting the rows destroys data, turning the
accountant into another role silently changes what the account may do (every other staff role holds more
privileges than the accountant), and rewriting ``audit_log.actor_role`` rewrites history. A wider CHECK costs
nothing: the old code never writes the value, and a downgrade that goes below the tables themselves
(``0001_clinic_schema``, ``m_0001_care_tables``) drops them with their constraints anyway. Code older than this
revision reading an ``accountant`` row would not know the role; downgrading the application below U11 means
first moving or locking those accounts by hand.

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

NEW_ROLES = ("owner", "manager", "doctor", "cs_staff", "reception", "accountant", "patient")
NEW_STAFF = ("owner", "manager", "doctor", "cs_staff", "reception", "accountant")

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
    """Keep the widened CHECKs (see the module docstring): narrowing them fails while an accountant exists."""

"""agent_rt: delivery of replies to chat channels run by plugins.

A message heard by a plugin channel is stored with ``delivery = 'pending'``; once its turn has finished, the
reply is sent through the channel, part by part (``delivered_parts`` lets a retry resume after the last part
sent). A failed send waits until ``delivery_after`` and is tried again; ``sending`` older than a few minutes
belongs to a crashed process and is taken over. Messages from the HTTP gateway keep ``delivery`` NULL.

Revision ID: 0006_delivery
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0006_delivery"
down_revision = "0005_plugins"
branch_labels = None
depends_on = None

SCHEMA = "agent_rt"
TABLE = "agent_ingress"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("delivery", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column(
        TABLE, sa.Column("delivery_attempts", sa.Integer(), nullable=False, server_default="0"), schema=SCHEMA
    )
    op.add_column(
        TABLE, sa.Column("delivered_parts", sa.Integer(), nullable=False, server_default="0"), schema=SCHEMA
    )
    op.add_column(TABLE, sa.Column("delivery_error", sa.Text(), nullable=True), schema=SCHEMA)
    op.add_column(TABLE, sa.Column("delivery_at", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA)
    op.add_column(
        TABLE, sa.Column("delivery_after", sa.DateTime(timezone=True), nullable=True), schema=SCHEMA
    )
    op.create_check_constraint(
        "agent_ingress_delivery",
        TABLE,
        "delivery IS NULL OR delivery IN ('pending', 'sending', 'sent', 'failed', 'skipped')",
        schema=SCHEMA,
    )
    op.create_check_constraint(
        "agent_ingress_delivery_error_size",
        TABLE,
        "delivery_error IS NULL OR char_length(delivery_error) <= 1000",
        schema=SCHEMA,
    )
    op.create_index(
        "agent_ingress_delivery_open",
        TABLE,
        ["agent", "session_id", "id"],
        schema=SCHEMA,
        postgresql_where=sa.text("delivery IN ('pending', 'sending')"),
    )


def downgrade() -> None:
    op.drop_index("agent_ingress_delivery_open", table_name=TABLE, schema=SCHEMA)
    op.drop_constraint("agent_ingress_delivery_error_size", TABLE, schema=SCHEMA)
    op.drop_constraint("agent_ingress_delivery", TABLE, schema=SCHEMA)
    for column in ("delivery_after", "delivery_at", "delivery_error", "delivered_parts", "delivery_attempts"):
        op.drop_column(TABLE, column, schema=SCHEMA)
    op.drop_column(TABLE, "delivery", schema=SCHEMA)

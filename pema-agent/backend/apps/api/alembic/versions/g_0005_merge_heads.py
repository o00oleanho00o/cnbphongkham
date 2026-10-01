"""Merge the four heads that the parallel packages added after 0003 (package G).

b1_0004 (auth session and inbox), b2_0001 (CRM protocol marker), p0001 (identity link) and
s_0004 (scheduler runtime) all chain from ``0003_clinic_agent_access``. No schema change of its own.
"""

from __future__ import annotations

revision = "g_0005_merge_heads"
down_revision = (
    "b1_0004_auth_session_and_inbox",
    "b2_0001_crm_protocol_marker",
    "p0001_identity_link",
    "s_0004_scheduler_runtime",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do: the merge only joins the branches."""


def downgrade() -> None:
    """Nothing to do."""

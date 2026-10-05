"""Merge the two heads that packages H1 and H2 added after g_0006 (integration H).

b1_0007 (absolute session expiry) and h2_0007 (data retention) both chain from ``g_0006_definer_search_path``.
No schema change of its own.
"""

from __future__ import annotations

revision = "h_0008_merge_heads"
down_revision = (
    "b1_0007_session_absolute_expiry",
    "h2_0007_retention",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Nothing to do: the merge only joins the branches."""


def downgrade() -> None:
    """Nothing to do."""

"""Tenant id used while the agent serves a single tenant.

Every store call and tool context already carries a tenant id, so serving several tenants later does not
change the interfaces.
"""

from __future__ import annotations

from typing import Final

DEFAULT_TENANT: Final = "default"

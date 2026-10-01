"""Role to permission matrix of docs/ARCH-PB01.md, deny by default. Owner: B1."""

from pema.clinic.rbac.authorize import (
    has_permission,
    is_clinical,
    is_doctor_scoped,
    is_role,
    require,
    require_any,
)
from pema.clinic.rbac.matrix import (
    AGENT_PERMISSIONS,
    CLINICAL_ROLES,
    ROLE_PERMISSIONS,
    SCHEDULER_PERMISSIONS,
    permissions_for,
)

__all__ = [
    "AGENT_PERMISSIONS",
    "CLINICAL_ROLES",
    "ROLE_PERMISSIONS",
    "SCHEDULER_PERMISSIONS",
    "has_permission",
    "is_clinical",
    "is_doctor_scoped",
    "is_role",
    "permissions_for",
    "require",
    "require_any",
]

"""The installation clinic id: one installation is ONE clinic (single tenant, package ST-A).

New module (not a port). The ``clinic_id`` column stays in every table as the fixed "installation id", but no
caller chooses it any more: the id of the only row of ``clinic.clinic`` is loaded once per process and every
DTO that used to ask the caller for ``clinic_id`` fills it in by itself (``Field(default_factory=
installation_clinic_id)``). Passing it explicitly still works (tests, code not yet migrated).

This module is a leaf (contracts import nothing from ``pema``): it only holds the process-wide value.
``pema.core.db.get_installation_clinic_id`` loads it (from ``PEMA_CLINIC_ID`` or from the database) and calls
``set_installation_clinic_id``; ``pema.core.testing.ensure_test_clinic`` does the same for a test database.

Reading it before it was loaded raises ``InstallationClinicNotLoadedError``: a missing id must stop the
process, never become a random one.
"""

from __future__ import annotations

from uuid import UUID


class InstallationClinicNotLoadedError(RuntimeError):
    """``installation_clinic_id()`` was called before the id was loaded for this process."""


_installation_clinic_id: UUID | None = None


def set_installation_clinic_id(clinic_id: UUID) -> None:
    """Store the id of the only clinic of this installation (once at start-up, or by a test fixture)."""
    global _installation_clinic_id
    _installation_clinic_id = clinic_id


def reset_installation_clinic_id() -> None:
    """Forget the id (tests that swap databases)."""
    global _installation_clinic_id
    _installation_clinic_id = None


def installation_clinic_id_or_none() -> UUID | None:
    """The loaded id, or ``None`` when nothing was loaded yet (never raises)."""
    return _installation_clinic_id


def installation_clinic_id() -> UUID:
    """The id of the only clinic of this installation; raises when it was not loaded yet."""
    if _installation_clinic_id is None:
        raise InstallationClinicNotLoadedError(
            "the installation clinic id is not loaded: call get_installation_clinic_id(db) at start-up"
        )
    return _installation_clinic_id

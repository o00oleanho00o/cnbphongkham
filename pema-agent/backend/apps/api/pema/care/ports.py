"""Ports of package M: thin ``Protocol`` s for interfaces that belong to other packages.

New module (not a port). A package M step codes against these and never reimplements the other package.

* ``PatientCreatedHook``: B1's ``create_patient`` action (``pema.clinic.actions.patients``) has no extension
  point yet, so the pairing of a new patient with its care agent is a hook that the action's caller (or the
  action itself, once it takes a hook) invokes inside the SAME session right after the patient row is flushed.
  ``pema.care.pairing.CareAgentPairing`` is the implementation.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


@runtime_checkable
class PatientCreatedHook(Protocol):
    """Called once per new patient, in the unit of work that created it (idempotent: a repeat is harmless)."""

    async def on_patient_created(self, session: AsyncSession, patient_id: UUID) -> None: ...

"""``RoutingDirectory`` of package M with the roster of package O1 in front (package O, step O1).

Package M picks who is asked about a handoff from a ``RoutingDirectory``: the staff profiles with their load
(``list_staff``) and the owners of the patient (``ownership``), and its chain ``build_candidates`` always
puts the owners first, then everybody else on shift, then the 24/7 on-call contact LAST. That code is
read-only here (package O does not edit ``pema.care``); this adapter changes only what the port answers.

What it does: ``ownership(patient_id)`` finds the identity the patient writes to (the ``account_id`` of
their latest conversation), asks ``roster.who_is_on(identity, now)`` and puts the operators on duty for that
identity in the owner slots: the first on-duty doctor in the ``doctor`` slot, the first on-duty
owner/manager/cs_staff in the ``cs_owner`` slot. The care chain therefore ranks them first, ahead of the
people who merely are on shift, with the on-call contact still last and unchanged. A patient with no
identity yet, an identity with nobody on duty, or a failed lookup leaves the answer of the inner directory
exactly as it was (the roster is a preference, never a reason to fail a handoff).

Known limits (open items for package M, see the O1 report): ``Ownership`` has two slots, so at most one
on-duty operator per slot is ranked first; the rest follow in M's normal order. A rostered operator takes
the slot of the patient's own CS owner or treating doctor (the real owner is then reached through the normal
"on shift" pass); and M labels the reason ``cs_owner`` / ``treating_doctor`` because ``RankReason`` has no
``roster`` value.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pema.care.ports import RoutingDirectory
from pema.care.routing_types import Ownership, StaffInfo
from pema.clinic.actions import roster
from pema.core.db import ClinicDatabase
from pema_contracts.ops import OnDutyOperator
from pema_contracts.roles import Role

logger = logging.getLogger(__name__)

type Clock = Callable[[], datetime]


class RosterSource(Protocol):
    """What the adapter needs from the roster (``SqlRosterSource`` is the real one; tests use a fake)."""

    async def identity_of_patient(self, patient_id: UUID) -> str | None: ...

    async def who_is_on(self, account_id: str, at: datetime) -> Sequence[OnDutyOperator]: ...


class SqlRosterSource:
    """``RosterSource`` over ``pema.clinic.actions.roster`` (role ``be_app``)."""

    def __init__(self, db: ClinicDatabase, clinic_id: UUID) -> None:
        self._db = db
        self._clinic_id = clinic_id

    async def identity_of_patient(self, patient_id: UUID) -> str | None:
        return await roster.identity_of_patient(self._db, self._clinic_id, patient_id)

    async def who_is_on(self, account_id: str, at: datetime) -> Sequence[OnDutyOperator]:
        return await roster.who_is_on(self._db, self._clinic_id, account_id, at)


class RosterRoutingDirectory:
    """``RoutingDirectory`` over an inner directory, preferring the operators rostered for the patient's
    identity."""

    def __init__(self, inner: RoutingDirectory, *, source: RosterSource, clock: Clock) -> None:
        self._inner = inner
        self._source = source
        self._clock = clock

    async def list_staff(self, clinic_id: UUID) -> Sequence[StaffInfo]:
        return await self._inner.list_staff(clinic_id)

    async def ownership(self, patient_id: UUID) -> Ownership:
        base = await self._inner.ownership(patient_id)
        try:
            account_id = await self._source.identity_of_patient(patient_id)
            if account_id is None:
                return base
            on_duty = await self._source.who_is_on(account_id, self._clock())
        except Exception as exc:  # a roster that cannot be read must not stop a handoff
            logger.error("roster lookup failed", extra={"error": type(exc).__name__})
            return base
        doctor = next((op.id for op in on_duty if op.role is Role.DOCTOR), None)
        cs_owner = next((op.id for op in on_duty if op.role is not Role.DOCTOR), None)
        return Ownership(
            cs_owner=cs_owner if cs_owner is not None else base.cs_owner,
            doctor=doctor if doctor is not None else base.doctor,
        )

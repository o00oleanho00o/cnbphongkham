"""The bridge between package M's control state machine and the assignment of package O (step O2).

Package M works per PATIENT (``CareControl.accept(ctx, patient_id)``, ``release_to_auto(ctx, patient_id,
...)``);
a thread of the shared inbox is per customer and identity (``clinic.conversation``). This module maps one onto
the other and nothing more (the code of ``pema.care`` is read only here, and registering it in the live care
loop is the job of package M7):

* ``CareAssignmentBridge`` implements ``pema.clinic.actions.assignment.CareHandback`` over M's ``CareControl``
  and ``ControlStore``: the clinic's "release to the agent" asks ``is_staff_state`` and calls
  ``release_to_auto``; M's refusals (not in STAFF, a level above the agent's own, a past ``until``) come
  back as
  ``CareHandbackRefusedError``;
* ``accept_and_claim``: M's ``accept`` (``HANDOFF_ROUTING -> STAFF``) followed by ``claim`` on the
  patient's open
  conversation. A patient may have several open conversations (several identities, several threads): the one
  with the LATEST inbound message is claimed, the others are left alone (``open_conversation_of_patient``).
  When
  the patient has none, or a colleague already holds that thread, M's accept stands and the thread is not
  touched (logged by code, never by name);
* ``release_and_free``: M's ``release_to_auto`` followed by a release of the thread the staff member holds
  (back to the queue). Nothing is freed when somebody else holds it.

Logs carry codes only: no patient, no name, no text.
"""

from __future__ import annotations

import logging
from datetime import datetime
from uuid import UUID

from pema.care.control import CareControl
from pema.care.handoff_types import InvalidTransitionError
from pema.care.models import ControlState
from pema.care.ports import ControlSnapshot, ControlStore, HandoffRequestSnapshot
from pema.clinic.actions import assignment
from pema.clinic.actions.assignment import CareHandbackRefusedError
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError

logger = logging.getLogger(__name__)


class CareAssignmentBridge:
    def __init__(self, db: ClinicDatabase, control: CareControl, store: ControlStore) -> None:
        self._db = db
        self._control = control
        self._store = store

    # ------------------------------------------------------------- CareHandback (clinic -> care)
    async def is_staff_state(self, ctx: ActionContext, patient_id: UUID) -> bool:
        snapshot = await self._store.get_control(patient_id)
        return snapshot.state is ControlState.STAFF

    async def release_to_auto(self, ctx: ActionContext, patient_id: UUID, note: str) -> None:
        try:
            await self._control.release_to_auto(ctx, patient_id, note)
        except (InvalidTransitionError, PermissionError, ValueError) as exc:
            raise CareHandbackRefusedError(type(exc).__name__) from exc

    # ------------------------------------------------------------- care -> clinic
    async def accept_and_claim(self, ctx: ActionContext, patient_id: UUID) -> HandoffRequestSnapshot:
        """M's accept, then the claim of the patient's latest open conversation."""
        request = await self._control.accept(ctx, patient_id)
        try:
            claimed = await assignment.claim_for_patient(self._db, ctx, patient_id)
        except DomainError as exc:
            logger.warning("accepted handoff, conversation not claimed", extra={"code": exc.code.value})
        else:
            if claimed is None:
                logger.info("accepted handoff, no open conversation to claim")
        return request

    async def release_and_free(
        self,
        ctx: ActionContext,
        patient_id: UUID,
        note: str,
        override_level: int | None = None,
        until: datetime | None = None,
    ) -> ControlSnapshot:
        """M's release to the agent, then the release of the thread the staff member holds."""
        snapshot = await self._control.release_to_auto(ctx, patient_id, note, override_level, until)
        try:
            await assignment.release_for_patient(self._db, ctx, patient_id)
        except DomainError as exc:
            logger.warning("released to the agent, conversation not freed", extra={"code": exc.code.value})
        return snapshot

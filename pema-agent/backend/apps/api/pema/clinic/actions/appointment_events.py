# new module (not a port): the prototype re-ran the CRM rules on every render (``PemaCRM.run()`` after each
# ``reception`` / ``setStatus`` / ``cancel``); the backend runs them as a job (``crm_rules.runner``)
"""What a change of an appointment tells the rest of the clinic, after it committed.

``crm-automation.js`` ``reception`` / ``cancel`` called ``run()`` straight away so that a missed or cancelled
visit starts the ``no_show`` recall, an arrival today stops the ``due`` reminder and a newly booked patient
stops being ``overdue``. Here the rules read the appointment table (``crm_rules.sql_store``), so the data
change IS the event; this module only says "run the rules soon". Not ported: the prototype also stamped
``reactivatedAt`` on the check-in after a CSKH booking; nothing here writes ``patient.reactivated_at`` yet (it
needs a "booked after care while dormant" marker the schema does not have: open item of package B2).
The composition root installs one listener (it wakes the CRM loop);
with none installed ``notify`` does nothing, so tests and tools are unaffected. ``notify`` is synchronous,
never raises and carries ids and statuses only (no name, no phone).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from pema.shared.logger import create_logger

_log = create_logger("appointment.events")


@dataclass(frozen=True, slots=True)
class AppointmentChange:
    appointment_id: UUID
    patient_id: UUID
    kind: str
    """``create``, ``update`` or the verb of a transition (``confirm``, ``check_in``, ``start``, ``complete``,
    ``cancel``, ``miss``)."""
    status: str
    """The status after the change."""


type Listener = Callable[[AppointmentChange], None]

_listener: Listener | None = None


def install_listener(listener: Listener | None) -> None:
    """Install (or, with ``None``, remove) the process-wide listener."""
    global _listener
    _listener = listener


def notify(change: AppointmentChange) -> None:
    listener = _listener
    if listener is None:
        return
    try:
        listener(change)
    except Exception as err:  # a broken listener must never fail the clinic operation
        _log.error("appointment listener failed", err=err)

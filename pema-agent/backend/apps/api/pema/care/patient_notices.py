"""The ONE template message a patient gets when a handoff opens outside clinic hours (PLAN-AI01-M section 7).
New module (not a port).

``CareControl`` sends exactly one message per routing round; by default it is the holding message of M2b.
This composer replaces its text when the clinic is closed and the request is deep enough
(``RoutingConfig.oncall_direct_from_depth``, D3 by default):

* D5 (red flag): the doctor-approved template ``emergency_out_of_hours`` with the on-call number read from the
  database right now and GENERIC emergency guidance. No model writes any part of it (D5 never reaches
  the LLM).
* D3-D4: the template ``holding_out_of_hours`` with a response-time estimate (the next opening of the clinic).

Inside clinic hours, or for a shallower request, ``compose`` returns ``None`` and the default holding message
stays. The use of the on-call number is audited (``oncall_used:patient_notice``). Without a configured on-call
contact the D5 text cannot name a number: ``None`` is returned (the urgent holding message goes out) and the
missing contact is logged as an error.
"""

from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pema.care.handoff_types import Depth, HandoffDecision
from pema.care.oncall import PURPOSE_PATIENT_NOTICE, OnCallDirectory
from pema.care.ports import CareAgentSnapshot, RoutingConfigSource, SendWindowProvider

logger = logging.getLogger(__name__)


def format_eta(moment: datetime, now: datetime, time_zone: str) -> str:
    """``08:00`` (today) or ``08:00 ngày 04/10`` in clinic local time."""
    try:
        zone = ZoneInfo(time_zone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = ZoneInfo("UTC")
    local = moment.astimezone(zone)
    clock = local.strftime("%H:%M")
    if local.date() == now.astimezone(zone).date():
        return clock
    return f"{clock} ngày {local.strftime('%d/%m')}"


class PatientNotices:
    """``PatientNoticeComposer``."""

    def __init__(
        self,
        *,
        config_source: RoutingConfigSource,
        window: SendWindowProvider,
        oncall: OnCallDirectory,
    ) -> None:
        self._config = config_source
        self._window = window
        self._oncall = oncall

    async def compose(self, agent: CareAgentSnapshot, decision: HandoffDecision, now: datetime) -> str | None:
        window = await self._window.get(agent.clinic_id)
        if window.is_open(now):
            return None
        config = await self._config.get(agent.clinic_id)
        if decision.depth.rank < config.oncall_direct_from_depth.rank:
            return None
        if decision.depth is Depth.D5:
            contact = await self._oncall.current_on_call(agent.clinic_id, now)
            if contact is None:
                return None
            await self._oncall.record_use(agent.id, PURPOSE_PATIENT_NOTICE, decision.depth.value, now)
            return config.emergency_out_of_hours.replace("{oncall_number}", contact.zalo_number)
        eta = format_eta(window.next_open(now), now, window.time_zone)
        return config.holding_out_of_hours.replace("{eta}", eta)

"""The eight calls the agent may make, and the permission each one needs (docs/PLAN-crm-plugin.md 3.2, 3.9).

A request that is not exactly one of these (method, path shape) never reaches the CRM. The path sent on is
rebuilt from the matched parts, so nothing the agent wrote outside the shapes below travels further.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Final

_PARTS: Final = {
    "channel": r"[A-Za-z0-9_.:-]{1,64}",
    "external_id": r"[A-Za-z0-9_.:@=-]{1,128}",
    "appointment_id": r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}",
}
_PERSON: Final = "/contacts/{channel}/{external_id}"


@dataclass(frozen=True)
class Route:
    method: str
    template: str
    scope: str
    pattern: re.Pattern[str] = field(init=False, compare=False, repr=False)

    def __post_init__(self) -> None:
        body = re.escape(self.template).replace(r"\{", "{").replace(r"\}", "}")
        for name, shape in _PARTS.items():
            body = body.replace("{" + name + "}", f"(?P<{name}>{shape})")
        object.__setattr__(self, "pattern", re.compile(body))


ROUTES: Final = (
    Route("GET", "/free-slots", "agent.slots.read"),
    Route("PUT", _PERSON, "agent.contact.write"),
    Route("POST", _PERSON + "/appointments", "agent.booking.write"),
    Route("GET", _PERSON + "/appointments", "agent.appointment.read"),
    Route("POST", _PERSON + "/appointments/{appointment_id}/confirm", "agent.appointment.change"),
    Route("POST", _PERSON + "/appointments/{appointment_id}/reschedule", "agent.appointment.change"),
    Route("POST", _PERSON + "/appointments/{appointment_id}/cancel", "agent.appointment.change"),
    Route("GET", "/reminders", "agent.reminders.read"),
)


def match(method: str, path: str) -> tuple[Route, str] | None:
    """The route of ``method`` and ``path`` (the part after ``/agent-gateway``) and the path to send on."""
    for route in ROUTES:
        if route.method != method:
            continue
        found = route.pattern.fullmatch(path)
        if found is None:
            continue
        parts = found.groupdict()
        if any(value in {".", ".."} for value in parts.values()):
            return None
        return route, route.template.format(**parts)
    return None

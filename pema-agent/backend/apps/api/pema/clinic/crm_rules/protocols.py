# new module (package U, step U4): the laser-co2 constants of crm-automation.js as configuration
"""Protocol configuration the rule engine reads (``clinic.protocol``).

``crm-automation.js`` hard-coded one protocol: sessions of ``'laser-co2'`` start the chain D+1, D+3, D+7 (only
for a session 0 to 45 days old) and, once per session, a D+30 recommendation. Those numbers are now data:

* ``milestones``: day offset of each of ``d1``, ``d3``, ``d7``. A milestone present here WINS over
  ``RuleConfig.delay_days`` of the same rule; a rule with no milestone keeps its own delay.
* ``followup_days``: the recommended next visit after a session of the protocol (30 for laser-co2);
  ``None`` means the protocol recommends nothing.
* ``window_days``: how old the latest session may be for ``d1``/``d3``/``d7`` to apply (45).
* ``active``: an inactive protocol creates no chain tasks and no recommendation.

``DEFAULT_PROTOCOLS`` holds exactly the constants the engine had, so an empty configuration (an unmigrated
store, a unit test, a clinic whose ``clinic.protocol`` has no row for the code) behaves as before. This is
what the "laser-co2 is unchanged" tests pin down.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pema.clinic.crm_rules.rules import LASER_PROTOCOL_ID
from pema_contracts.crm import RuleKey

DEFAULT_WINDOW_DAYS = 45
DEFAULT_FOLLOWUP_DAYS = 30
DEFAULT_PROTOCOL_NAME = "Laser CO2"


@dataclass(frozen=True, slots=True)
class ProtocolConfig:
    code: str
    name: str
    milestones: Mapping[RuleKey, int]
    followup_days: int | None
    window_days: int = DEFAULT_WINDOW_DAYS
    active: bool = True

    def delay_for(self, key: RuleKey, rule_delay_days: int) -> int:
        """Day offset of rule ``key`` for a session of this protocol."""
        return self.milestones.get(key, rule_delay_days)


DEFAULT_PROTOCOLS: Mapping[str, ProtocolConfig] = {
    LASER_PROTOCOL_ID: ProtocolConfig(
        code=LASER_PROTOCOL_ID,
        name=DEFAULT_PROTOCOL_NAME,
        milestones={RuleKey.D1: 1, RuleKey.D3: 3, RuleKey.D7: 7},
        followup_days=DEFAULT_FOLLOWUP_DAYS,
    )
}


def protocol_for(protocols: Mapping[str, ProtocolConfig] | None, code: str | None) -> ProtocolConfig | None:
    """The configuration of ``code``: the stored one, else the built-in default (laser-co2), else ``None``."""
    if code is None:
        return None
    if protocols is not None and code in protocols:
        return protocols[code]
    return DEFAULT_PROTOCOLS.get(code)

# ported from: prototype/shared/crm-automation.js (profile)
"""CRM profile (lifecycle stage, overdue days, risk) computed from visits, plans and appointments.

The JS ``profile(p)`` read the patient's whole state; here it is a pure function of the few facts it used,
so Patient 360 and the agent's care context compute it the same way. The ten rules that CREATE tasks are
package B2's; this is only the read model (``CrmProfile``).

Forced deviation: the JS used ``D.DAY`` (the fixed demo day 2026-09-20); here ``today`` is passed in.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

from pema_contracts.crm import CrmProfile

type LifecycleStage = Literal["new", "returning", "treating", "dormant", "reactivated"]

DORMANT_AFTER_DAYS = 90
"""JS: ``age >= 90`` is ``dormant``."""

HIGH_RISK_OVERDUE_DAYS = 7
HIGH_RISK_ABANDON_DAYS = 45


@dataclass(frozen=True)
class ProfileFacts:
    today: date
    last_visit: date | None
    """Date of the newest completed session (JS ``p.lastVisit``)."""
    has_sessions: bool
    total_sessions: int
    completed_sessions: int
    next_appointment: date | None
    """Date of the next active, not completed appointment from today on (JS ``upcoming(p)[0]``)."""
    recommendation_at: date | None
    expected_visit_source: str | None
    reactivated: bool
    marketing_opt_out: bool


def days_between(start: date, end: date) -> int:
    """JS ``D.days(from, to)``: whole days from ``start`` to ``end`` (negative if ``end`` is earlier)."""
    return (end - start).days


def lifecycle_stage(facts: ProfileFacts) -> LifecycleStage:
    """JS: ``reactivated`` > ``new`` (no session yet) > ``dormant`` (>= 90 days) > ``treating``
    (sessions left) > ``returning``."""
    age = days_between(facts.last_visit, facts.today) if facts.last_visit else 0
    remaining = max(0, facts.total_sessions - facts.completed_sessions)
    if facts.reactivated:
        return "reactivated"
    if not facts.has_sessions:
        return "new"
    if age >= DORMANT_AFTER_DAYS:
        return "dormant"
    if remaining:
        return "treating"
    return "returning"


def compute_profile(facts: ProfileFacts) -> CrmProfile:
    expected = facts.next_appointment or facts.recommendation_at
    age = days_between(facts.last_visit, facts.today) if facts.last_visit else 0
    remaining = max(0, facts.total_sessions - facts.completed_sessions)
    overdue = max(0, days_between(expected, facts.today)) if expected else 0
    has_next = facts.next_appointment is not None
    high = not has_next and (
        overdue > HIGH_RISK_OVERDUE_DAYS or (remaining > 0 and age > HIGH_RISK_ABANDON_DAYS)
    )
    return CrmProfile(
        lifecycle_stage=lifecycle_stage(facts),
        last_visit_at=facts.last_visit,
        expected_next_visit_at=expected,
        expected_visit_source="appointment" if has_next else facts.expected_visit_source,
        overdue_days=overdue,
        remaining_sessions=remaining,
        risk_level="high" if high else "normal",
        marketing_opt_out=facts.marketing_opt_out,
    )

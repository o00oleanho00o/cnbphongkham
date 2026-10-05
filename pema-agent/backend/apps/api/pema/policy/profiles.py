"""The two policy profiles as data, and how a caller picks one (PLAN-AI01 section 5).

New module. The DATA of ``staff_assistant`` and ``patient_channel`` already lives in
``pema_contracts.policy`` (package A, ``DEFAULT_PROFILES``); this module adds what a caller needs around
it:

* ``resolve_profile``: account profile + agent profile -> the profile that applies (the restrictive one
  wins, ``effective_profile_key``);
* ``build_policy_context``: the ``PolicyContext`` every hook receives, built once per turn / job from the
  account and the agent, so D1, S, C1 and C2 do not each re-derive the profile;
* ``profiles_out``: the payload of ``GET /admin/policy/profiles``.

Both profiles are returned from ``DEFAULT_PROFILES`` unchanged: this package never edits the table of
the plan, it only implements the behaviour the flags ask for (``pema.policy.hooks``).
"""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from pema_contracts.admin_agent import PolicyProfilesOut
from pema_contracts.agents import AccountConfig, AgentProfile
from pema_contracts.channel import ChannelKind
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    PolicyContext,
    PolicyProfile,
    PolicyProfileKey,
    effective_profile_key,
)


def get_profile(
    key: PolicyProfileKey, profiles: Mapping[PolicyProfileKey, PolicyProfile] = DEFAULT_PROFILES
) -> PolicyProfile:
    return profiles[key]


def resolve_profile(
    account_profile: PolicyProfileKey,
    agent_profile: PolicyProfileKey,
    profiles: Mapping[PolicyProfileKey, PolicyProfile] = DEFAULT_PROFILES,
) -> PolicyProfile:
    """The profile of a turn: ``patient_channel`` if the account OR its agent is ``patient_channel``."""
    return profiles[effective_profile_key(account_profile, agent_profile)]


def build_policy_context(
    *,
    clinic_id: UUID,
    account: AccountConfig,
    agent: AgentProfile,
    thread_id: str,
    isolated: bool = False,
    patient_id: UUID | None = None,
    identity_verified: bool = False,
    request_id: str | None = None,
    channel: ChannelKind | None = None,
    profiles: Mapping[PolicyProfileKey, PolicyProfile] = DEFAULT_PROFILES,
) -> PolicyContext:
    """``PolicyContext`` for one turn or job. ``patient_id`` / ``identity_verified`` come from
    ``PolicyHooks.verify_identity`` (never from the message text)."""
    return PolicyContext(
        clinic_id=clinic_id,
        account_id=account.id,
        agent_id=agent.id,
        channel=channel or account.channel,
        thread_id=thread_id,
        profile=resolve_profile(account.policy_profile, agent.policy_profile, profiles),
        isolated=isolated,
        patient_id=patient_id,
        identity_verified=identity_verified,
        request_id=request_id,
    )


def profiles_out(
    profiles: Mapping[PolicyProfileKey, PolicyProfile] = DEFAULT_PROFILES,
) -> PolicyProfilesOut:
    """Both profiles in a stable order (staff_assistant first), for the admin UI."""
    return PolicyProfilesOut(profiles=[profiles[key] for key in PolicyProfileKey])

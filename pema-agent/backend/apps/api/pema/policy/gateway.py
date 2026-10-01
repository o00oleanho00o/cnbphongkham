"""What the policy hooks read from, and write to, the clinic (the ``agent_worker`` door).

New module. ``pema.policy`` may reach the clinic only through ``pema.clinic.actions`` (import-linter) and,
for the few facts the agent-facing actions of package B1 do not expose, through the views and SECURITY
DEFINER functions of schema ``clinic_agent`` (revision ``p0001_identity_link`` adds the identity ones).
This module is that second door: a Protocol (``PolicyGateway``) the hooks depend on, and the SQL
implementation (``SqlPolicyGateway``) that runs as role ``agent_worker`` with ``ClinicDatabase``.

Nothing here touches ``clinic.*`` tables: the role has no privilege on them, and a test proves it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy import text

from pema.core.db import ClinicDatabase
from pema_contracts.channel import ChannelKind


class LinkOutcome(StrEnum):
    CANDIDATE_CREATED = "candidate_created"
    """Phone matched exactly one patient; the link is ``pending`` until staff confirm it."""
    VERIFIED = "verified"
    """A reception-issued one-time code was redeemed; the link is verified."""
    ALREADY_VERIFIED = "already_verified"
    NO_MATCH = "no_match"
    AMBIGUOUS = "ambiguous"
    """The phone matches several patients (a shared family number): a human must decide."""
    INVALID_CODE = "invalid_code"
    EXPIRED_CODE = "expired_code"
    REJECTED_BY_STAFF = "rejected_by_staff"
    RATE_LIMITED = "rate_limited"
    CONFLICT = "conflict"
    """The identity is already verified for another patient."""


@dataclass(frozen=True)
class LinkResult:
    outcome: LinkOutcome
    patient_id: UUID | None = None
    patient_code: str | None = None
    identity_id: UUID | None = None


@dataclass(frozen=True)
class PatientPolicyFlags:
    """The minimum the policy needs about a patient (view ``clinic_agent.patient_ref`` + consent)."""

    patient_id: UUID
    code: str
    full_name: str
    """Used ONLY to build the PII mask of a VERIFIED patient; never put in a log or a prompt."""
    marketing_opt_out: bool
    consent_messaging: bool
    consent_marketing: bool


@dataclass(frozen=True)
class ApprovedTemplate:
    template_key: str
    marketing: bool


class PolicyGateway(Protocol):
    async def patient_flags(self, clinic_id: UUID, patient_id: UUID) -> PatientPolicyFlags | None: ...

    async def approved_template(self, clinic_id: UUID, template_key: str) -> ApprovedTemplate | None:
        """A doctor-approved, active template (``message_template_approved``), or ``None``."""
        ...

    async def link_by_phone_hash(
        self, clinic_id: UUID, channel: ChannelKind, external_user_id: str, phone_hash: str
    ) -> LinkResult:
        """Candidate link by an exact phone-hash match. Never verifies by itself."""
        ...

    async def redeem_link_code(
        self, clinic_id: UUID, channel: ChannelKind, external_user_id: str, code_hash: str
    ) -> LinkResult:
        """Redeem a one-time code issued by reception for one patient: verifies the link."""
        ...


class SqlPolicyGateway:
    """``PolicyGateway`` over Postgres as role ``agent_worker`` (views and functions of ``clinic_agent``)."""

    def __init__(self, db: ClinicDatabase) -> None:
        self._db = db

    async def patient_flags(self, clinic_id: UUID, patient_id: UUID) -> PatientPolicyFlags | None:
        async with self._db.session(clinic_id) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT code, full_name, marketing_opt_out "
                        "FROM clinic_agent.patient_ref WHERE id = :pid"
                    ),
                    {"pid": patient_id},
                )
            ).first()
            if row is None:
                return None
            consents = (
                await session.execute(
                    text("SELECT kind, granted FROM clinic_agent.consent_current WHERE patient_id = :pid"),
                    {"pid": patient_id},
                )
            ).all()
        granted = {str(kind): bool(flag) for kind, flag in consents}
        return PatientPolicyFlags(
            patient_id=patient_id,
            code=str(row.code),
            full_name=str(row.full_name),
            marketing_opt_out=bool(row.marketing_opt_out),
            consent_messaging=granted.get("messaging", False),
            consent_marketing=granted.get("marketing", False),
        )

    async def approved_template(self, clinic_id: UUID, template_key: str) -> ApprovedTemplate | None:
        async with self._db.session(clinic_id) as session:
            row = (
                await session.execute(
                    text(
                        "SELECT template_key, marketing FROM clinic_agent.message_template_approved "
                        "WHERE template_key = :k"
                    ),
                    {"k": template_key},
                )
            ).first()
        if row is None:
            return None
        return ApprovedTemplate(template_key=str(row.template_key), marketing=bool(row.marketing))

    async def _link(self, clinic_id: UUID, statement: str, params: dict[str, object]) -> LinkResult:
        async with self._db.session(clinic_id) as session:
            row = (await session.execute(text(statement), params)).first()
        if row is None:
            return LinkResult(LinkOutcome.NO_MATCH)
        return LinkResult(
            outcome=LinkOutcome(str(row.outcome)),
            patient_id=row.patient_id,
            patient_code=None if row.patient_code is None else str(row.patient_code),
            identity_id=row.identity_id,
        )

    async def link_by_phone_hash(
        self, clinic_id: UUID, channel: ChannelKind, external_user_id: str, phone_hash: str
    ) -> LinkResult:
        return await self._link(
            clinic_id,
            "SELECT outcome, patient_id, patient_code, identity_id "
            "FROM clinic_agent.link_identity_by_phone_hash(:ch, :uid, :h)",
            {"ch": channel.value, "uid": external_user_id, "h": phone_hash},
        )

    async def redeem_link_code(
        self, clinic_id: UUID, channel: ChannelKind, external_user_id: str, code_hash: str
    ) -> LinkResult:
        return await self._link(
            clinic_id,
            "SELECT outcome, patient_id, patient_code, identity_id "
            "FROM clinic_agent.redeem_identity_code(:ch, :uid, :h)",
            {"ch": channel.value, "uid": external_user_id, "h": code_hash},
        )

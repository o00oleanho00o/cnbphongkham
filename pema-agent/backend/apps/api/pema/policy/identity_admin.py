"""Staff side of the policy: account profile, identity links, reception codes (API process, role ``be_app``).

New module behind ``routers/admin_policy.py``. Every method:

* checks ``Permission.ADMIN_POLICY`` (deny by default; ``can`` is injectable so package B1's role matrix
  replaces the conservative default below),
* works inside ``ClinicDatabase.session()`` (single tenant: no RLS),
* writes one ``clinic.audit_log`` row with ids and codes only (never a name, phone or code).

PACKAGE B1 NOTE. The plan wants UI and agent to go through the same action layer. B1 has not published
identity actions yet, so the SQL lives here; ``pema.clinic.actions`` may absorb it later without changing
the route or the DTOs. Only ``pema.api`` and ``pema.bootstrap`` may import this module's DB parts
(the agent side imports ``pema.policy.hooks`` and ``pema.policy.gateway`` only).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.core.db import ClinicDatabase
from pema.policy.identity import LINK_CODE_TTL_MINUTES, format_link_code, generate_link_code, link_code_hash
from pema.policy.profiles import profiles_out
from pema.shared.logger import create_logger
from pema_contracts.actions import ActionContext
from pema_contracts.admin_agent import AccountOut, AccountPolicyUpdate, IdentityConfirm, PolicyProfilesOut
from pema_contracts.agents import AccountConfig, AccountStore
from pema_contracts.clinic_actions import IdentityLink, IdentityLinkStatus
from pema_contracts.common import to_vn
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission, Role

log = create_logger("policy-admin")

_ADMIN_POLICY_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.MANAGER})
_ISSUE_CODE_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.MANAGER, Role.RECEPTION, Role.CS_STAFF})
MAX_PENDING_LISTED = 200


class PermissionChecker(Protocol):
    def __call__(self, ctx: ActionContext, permission: Permission) -> bool: ...


def default_can(ctx: ActionContext, permission: Permission) -> bool:
    """Conservative stand-in for the role matrix of package B1. Staff users only; the agent never."""
    if ctx.actor_type is not ActorType.USER or ctx.actor_role is None:
        return False
    if permission is Permission.ADMIN_POLICY:
        return ctx.actor_role in _ADMIN_POLICY_ROLES
    if permission is Permission.PATIENT_WRITE:
        return ctx.actor_role in _ISSUE_CODE_ROLES
    return False


AccountViewFactory = Callable[[AccountConfig], Awaitable[AccountOut]]


async def default_account_view(account: AccountConfig) -> AccountOut:
    """``running`` and ``has_credentials`` belong to the channel packages; without them: not running."""
    return AccountOut(**account.model_dump(), running=False, has_credentials=account.has_bot_token)


@dataclass(frozen=True)
class IssuedLinkCode:
    code: str
    """Plain code, shown ONCE to the staff member (``K7QM-4XNR``). Only its hash is stored."""
    expires_at: datetime
    patient_id: UUID


class PolicyAdminService:
    def __init__(
        self,
        *,
        db: ClinicDatabase,
        accounts: AccountStore,
        account_view: AccountViewFactory = default_account_view,
        can: PermissionChecker = default_can,
    ) -> None:
        self._db = db
        self._accounts = accounts
        self._account_view = account_view
        self._can = can

    # ------------------------------------------------------------------------------ helpers
    def _require(self, ctx: ActionContext, permission: Permission) -> UUID:
        if not self._can(ctx, permission) or ctx.actor_user_id is None:
            raise DomainError(ErrorCode.FORBIDDEN, "Bạn không có quyền thực hiện thao tác này.")
        return ctx.actor_user_id

    @staticmethod
    async def _audit(
        session: AsyncSession,
        ctx: ActionContext,
        action: str,
        entity_type: str,
        entity_id: str | None,
        details: dict[str, object],
    ) -> None:
        await session.execute(
            text(
                "INSERT INTO clinic.audit_log (clinic_id, actor_type, actor_user_id, actor_role, action, "
                "entity_type, entity_id, request_id, details) "
                "VALUES (:clinic, 'user', :user, :role, :action, :etype, :eid, :rid, CAST(:details AS jsonb))"
            ),
            {
                "clinic": ctx.clinic_id,
                "user": ctx.actor_user_id,
                "role": None if ctx.actor_role is None else ctx.actor_role.value,
                "action": action,
                "etype": entity_type,
                "eid": entity_id,
                "rid": ctx.request_id,
                "details": json.dumps(details),
            },
        )

    # ------------------------------------------------------------------------ account profile
    @staticmethod
    def list_profiles() -> PolicyProfilesOut:
        """Both profiles as data. Read-only and public to every staff session, so no permission check."""
        return profiles_out()

    async def set_account_profile(
        self, ctx: ActionContext, account_id: str, update: AccountPolicyUpdate
    ) -> AccountOut:
        self._require(ctx, Permission.ADMIN_POLICY)
        before = await self._accounts.get_account(ctx.clinic_id, account_id)
        if before is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy tài khoản.")
        updated = await self._accounts.update_account(
            ctx.clinic_id, account_id, {"policy_profile": update.policy_profile}
        )
        if updated is None:
            raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy tài khoản.")
        async with self._db.session() as session:
            await self._audit(
                session,
                ctx,
                "policy.account_profile.set",
                "account",
                account_id,
                {"from": before.policy_profile.value, "to": updated.policy_profile.value},
            )
        log.info(
            "account profile changed",
            account_id=account_id,
            from_profile=before.policy_profile.value,
            to_profile=updated.policy_profile.value,
        )
        return await self._account_view(updated)

    # --------------------------------------------------------------------------- identity links
    async def list_pending(self, ctx: ActionContext) -> list[IdentityLink]:
        self._require(ctx, Permission.ADMIN_POLICY)
        async with self._db.session() as session:
            rows = (
                await session.execute(
                    text(
                        "SELECT i.channel, i.external_user_id, i.patient_id, p.code AS patient_code "
                        "FROM clinic.channel_identity i "
                        "LEFT JOIN clinic.patient p ON p.clinic_id = i.clinic_id AND p.id = i.patient_id "
                        "WHERE i.verification_status = 'pending' "
                        "ORDER BY i.last_inbound_at DESC NULLS LAST LIMIT :limit"
                    ),
                    {"limit": MAX_PENDING_LISTED},
                )
            ).all()
        return [
            IdentityLink(
                channel=row.channel,
                external_user_id=str(row.external_user_id),
                status=IdentityLinkStatus.PENDING,
                patient_id=row.patient_id,
                patient_code=None if row.patient_code is None else str(row.patient_code),
            )
            for row in rows
        ]

    async def confirm(self, ctx: ActionContext, body: IdentityConfirm) -> IdentityLink:
        user_id = self._require(ctx, Permission.ADMIN_POLICY)
        async with self._db.session() as session:
            row = (
                await session.execute(
                    text(
                        "SELECT id, verification_status FROM clinic.channel_identity "
                        "WHERE channel = :channel AND external_user_id = :uid FOR UPDATE"
                    ),
                    {"channel": body.channel.value, "uid": body.external_user_id},
                )
            ).first()
            if row is None:
                raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy liên kết Zalo này.")
            if str(row.verification_status) == "verified" and not body.reject:
                raise DomainError(ErrorCode.INVALID_STATE, "Liên kết này đã được xác minh.")
            identity_id = str(row.id)

            if body.reject:
                await session.execute(
                    text(
                        "UPDATE clinic.channel_identity "
                        "SET verification_status = 'rejected', patient_id = NULL, "
                        "verified_at = NULL, verified_by = :user WHERE id = :id"
                    ),
                    {"user": user_id, "id": row.id},
                )
                await self._audit(
                    session,
                    ctx,
                    "identity.reject",
                    "channel_identity",
                    identity_id,
                    {"channel": body.channel.value},
                )
                return IdentityLink(
                    channel=body.channel,
                    external_user_id=body.external_user_id,
                    status=IdentityLinkStatus.REJECTED,
                )

            patient = (
                await session.execute(
                    text("SELECT code FROM clinic.patient WHERE id = :pid"), {"pid": body.patient_id}
                )
            ).first()
            if patient is None:
                raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy hồ sơ bệnh nhân.")
            verified_at = (
                await session.execute(
                    text(
                        "UPDATE clinic.channel_identity "
                        "SET patient_id = :pid, verification_status = 'verified', "
                        "verified_at = now(), verified_by = :user WHERE id = :id RETURNING verified_at"
                    ),
                    {"pid": body.patient_id, "user": user_id, "id": row.id},
                )
            ).scalar_one()
            await self._audit(
                session,
                ctx,
                "identity.confirm",
                "channel_identity",
                identity_id,
                {"channel": body.channel.value, "patient_id": str(body.patient_id)},
            )
        return IdentityLink(
            channel=body.channel,
            external_user_id=body.external_user_id,
            status=IdentityLinkStatus.VERIFIED,
            patient_id=body.patient_id,
            patient_code=str(patient.code),
            verified_at=to_vn(verified_at),
        )

    # ------------------------------------------------------------------------ reception codes
    async def issue_link_code(
        self, ctx: ActionContext, patient_id: UUID, *, ttl_minutes: int = LINK_CODE_TTL_MINUTES
    ) -> IssuedLinkCode:
        """Reception hands the code to the patient in person; they type it into the chat."""
        user_id = self._require(ctx, Permission.PATIENT_WRITE)
        code = generate_link_code()
        digest = link_code_hash(code)
        if digest is None:  # unreachable: the generator only emits valid codes
            raise DomainError(ErrorCode.INTERNAL, "Không tạo được mã xác minh.")
        expires_at = datetime.now(UTC) + timedelta(minutes=ttl_minutes)
        async with self._db.session() as session:
            exists = (
                await session.execute(
                    text("SELECT 1 FROM clinic.patient WHERE id = :pid"), {"pid": patient_id}
                )
            ).first()
            if exists is None:
                raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy hồ sơ bệnh nhân.")
            await session.execute(
                text(
                    "INSERT INTO clinic.identity_link_code "
                    "(clinic_id, patient_id, code_hash, issued_by, expires_at) "
                    "VALUES (:clinic, :pid, :hash, :user, :exp)"
                ),
                {
                    "clinic": ctx.clinic_id,
                    "pid": patient_id,
                    "hash": digest,
                    "user": user_id,
                    "exp": expires_at,
                },
            )
            await self._audit(
                session,
                ctx,
                "identity.code_issued",
                "patient",
                str(patient_id),
                {"ttl_minutes": ttl_minutes},
            )
        return IssuedLinkCode(
            code=format_link_code(code), expires_at=to_vn(expires_at), patient_id=patient_id
        )

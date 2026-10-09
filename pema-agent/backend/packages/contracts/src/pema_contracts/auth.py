"""Auth DTOs. Session transport is an HttpOnly cookie carrying the JWT (set by the BE); the body only
describes the session. Agent/service callers use ``Authorization: Bearer <service token>``."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, SecretStr, field_validator

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.roles import Permission, Role


class LoginRequest(ApiModel):
    """Sign-in of a staff member. One installation is one clinic (single tenant): no clinic field."""

    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(max_length=1024)


class ChangePasswordRequest(ApiModel):
    """A signed-in user changes their OWN password (``POST /auth/password``). The floor of the new password
    (8 characters) and the 'must differ' rule are checked by the action, so the refusal carries the Vietnamese
    message of the original and is not a bare schema error."""

    current_password: SecretStr = Field(max_length=1024)
    new_password: SecretStr = Field(max_length=1024)


class ResetPasswordRequest(ApiModel):
    """The owner sets a new password for ANOTHER staff account (``POST /admin/users/{user_id}/password``).
    The floor of the new password (8 characters) is checked by the action, like ``ChangePasswordRequest``,
    so the refusal carries the Vietnamese message. No current password: the owner does not know it."""

    new_password: SecretStr = Field(max_length=1024)


class UserSummary(ApiModel):
    id: UUID
    display_name: str
    role: Role
    clinic_id: UUID
    clinic_name: str


class SessionInfo(ApiModel):
    user: UserSummary
    expires_at: VnDatetime


class MeResponse(ApiModel):
    user: UserSummary
    permissions: list[Permission]


class PermissionsResponse(ApiModel):
    role: Role
    permissions: list[Permission]


class AgentTokenResponse(ApiModel):
    """A short token (EdDSA JWT, ``aud`` ``pema-agent``) with which the clinic web's server calls the agent
    service for the signed-in staff member. Checked by the agent against ``GET /.well-known/jwks.json``."""

    token: str
    expires_at: VnDatetime


class PublicJwk(ApiModel):
    kty: str
    crv: str
    x: str
    kid: str
    use: str
    alg: str


class JwksResponse(ApiModel):
    """The public keys that check the agent tokens (RFC 7517 key set)."""

    keys: list[PublicJwk]


class StaffUserOut(ApiModel):
    """One staff account of the clinic as the owner and the manager see it (``GET /admin/users``). Never
    carries a password or a hash. ``email`` is the sign-in name (lower case, unique per clinic)."""

    id: UUID
    display_name: str
    email: str
    role: Role
    active: bool = Field(description="False = locked: cannot sign in and every session was ended.")
    last_login_at: VnDatetime | None = None
    created_at: VnDatetime
    version: int = Field(ge=1, description="Optimistic lock: send it back in PATCH.")


class StaffUserCreate(ApiModel):
    """The owner creates a staff account (``POST /admin/users``). ``patient`` is not a staff role. The initial
    password follows the 8-character floor of a password change (checked by the action, so the refusal carries
    the Vietnamese message)."""

    display_name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: Role
    password: SecretStr = Field(max_length=1024)

    @field_validator("email")
    @classmethod
    def _lower_case_email(cls, value: str) -> str:
        return value.lower()


class StaffUserUpdate(ApiModel):
    """The owner edits a staff account (``PATCH /admin/users/{user_id}``). Only the fields sent change.
    Locking (``active: false``) or changing the role ends every session of that user; the owner cannot lock
    or re-role their own account, and the clinic always keeps one active owner."""

    version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    active: bool | None = None


class AssignableStaffOut(ApiModel):
    """A colleague a task or a conversation can be handed to (``GET /staff/assignable``, every signed-in staff
    member may read it). The minimum a picker needs: no e-mail, phone, last sign-in or lock state (locked
    accounts are never listed). ``role`` is only one of the roles that can handle conversations and tasks."""

    id: UUID
    name: str
    role: Role

"""Auth DTOs. Session transport is an HttpOnly cookie carrying the JWT (set by the BE); the body only
describes the session. Agent/service callers use ``Authorization: Bearer <service token>``."""

from __future__ import annotations

from uuid import UUID

from pydantic import Field, SecretStr

from pema_contracts.common import ApiModel, VnDatetime
from pema_contracts.roles import Permission, Role


class LoginRequest(ApiModel):
    clinic_slug: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]*$")
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

"""Policy profiles and the zalo_uid <-> patient identity link (package P implements).

Paths, methods and DTOs are the skeleton's (a contract); only the bodies changed. Two things come from
the composition layer (package G wires them, tests override them):

* ``request.app.state.policy_admin``: a ``pema.policy.identity_admin.PolicyAdminService``;
* ``request.state.action_context``: the ``ActionContext`` the auth layer of package B1 builds from the
  session cookie (clinic, user, role).

Without them the routes answer 501 / 401 like the rest of the skeleton, so wiring is explicit and a
forgotten dependency is loud, never a silent allow.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from pema.api.deps import admin_router
from pema.policy.identity_admin import PolicyAdminService
from pema_contracts.actions import ActionContext
from pema_contracts.admin_agent import AccountOut, AccountPolicyUpdate, IdentityConfirm, PolicyProfilesOut
from pema_contracts.clinic_actions import IdentityLink
from pema_contracts.errors import DomainError, ErrorCode

router = admin_router("policy", "admin-policy")


def get_policy_admin(request: Request) -> PolicyAdminService:
    service: object = getattr(request.app.state, "policy_admin", None)
    if not isinstance(service, PolicyAdminService):
        raise DomainError(ErrorCode.NOT_IMPLEMENTED, "Chức năng chưa được triển khai.")
    return service


def get_action_context(request: Request) -> ActionContext:
    ctx: object = getattr(request.state, "action_context", None)
    if not isinstance(ctx, ActionContext):
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Bạn cần đăng nhập.")
    return ctx


PolicyAdmin = Annotated[PolicyAdminService, Depends(get_policy_admin)]
CurrentAction = Annotated[ActionContext, Depends(get_action_context)]


@router.get(
    "/profiles", response_model=PolicyProfilesOut, summary="staff_assistant and patient_channel as data"
)
async def list_policy_profiles(service: PolicyAdmin) -> PolicyProfilesOut:
    return service.list_profiles()


@router.put(
    "/accounts/{account_id}",
    response_model=AccountOut,
    summary="Assign a policy profile to an account (audited)",
)
async def set_account_policy(
    account_id: str, body: AccountPolicyUpdate, service: PolicyAdmin, ctx: CurrentAction
) -> AccountOut:
    return await service.set_account_profile(ctx, account_id, body)


@router.get(
    "/identity/pending",
    response_model=list[IdentityLink],
    summary="Candidate zalo_uid links waiting for staff confirmation",
)
async def list_pending_identity_links(service: PolicyAdmin, ctx: CurrentAction) -> list[IdentityLink]:
    return await service.list_pending(ctx)


@router.post(
    "/identity/confirm",
    response_model=IdentityLink,
    summary="Confirm or reject a zalo_uid <-> patient link (audited)",
)
async def confirm_identity_link(
    body: IdentityConfirm, service: PolicyAdmin, ctx: CurrentAction
) -> IdentityLink:
    return await service.confirm(ctx, body)

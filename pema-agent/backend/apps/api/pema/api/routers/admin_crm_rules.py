"""CRM automation rules admin (package B2).

Thin routes over ``pema.clinic.crm_rules.admin``. Two dependencies are the seams to the rest of the
application and are overridden at composition time (package G, ``app.dependency_overrides``):

* ``get_action_context``: who is calling, from the session cookie (package B1, ``pema.api.dashboard_auth``).
  The default answers 501, so an unwired route can never be reached anonymously;
* ``get_rules_admin``: the service (``SqlCrmRuleAdminService(db)``). The default answers 501.

The role check itself (owner or manager) runs inside the service, never here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from pema.api.deps import admin_router, not_implemented
from pema.clinic.crm_rules.admin import CrmRuleAdminService
from pema_contracts.actions import ActionContext
from pema_contracts.crm import CrmRuleOut, CrmRuleUpdate, RuleKey

router = admin_router("rules", "admin-crm")


def get_action_context() -> ActionContext:
    """Placeholder until the session dependency of package B1 is wired (see module docstring)."""
    not_implemented()


def get_rules_admin() -> CrmRuleAdminService:
    """Placeholder until package G wires ``SqlCrmRuleAdminService`` (see module docstring)."""
    not_implemented()


ActionContextDep = Annotated[ActionContext, Depends(get_action_context)]
RulesAdminDep = Annotated[CrmRuleAdminService, Depends(get_rules_admin)]


@router.get("", response_model=list[CrmRuleOut], summary="The 10 CRM automation rules")
async def list_rules(ctx: ActionContextDep, service: RulesAdminDep) -> list[CrmRuleOut]:
    return await service.list_rules(ctx)


@router.patch("/{rule_key}", response_model=CrmRuleOut, summary="Tune a rule (version lock)")
async def update_rule(
    rule_key: RuleKey, body: CrmRuleUpdate, ctx: ActionContextDep, service: RulesAdminDep
) -> CrmRuleOut:
    return await service.update_rule(ctx, rule_key, body)

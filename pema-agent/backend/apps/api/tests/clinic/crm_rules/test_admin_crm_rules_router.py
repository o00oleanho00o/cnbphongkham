# new tests (route plumbing of /admin/rules)
"""``GET /admin/rules`` and ``PATCH /admin/rules/{rule_key}``: the unwired defaults fail closed, an allowed role
gets the rules, a forbidden role gets 403, a stale version gets 409. The SQL behaviour of the service is in
``test_crm_rules_database.py`` (needs Postgres)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from pema.api.routers import admin_crm_rules
from pema.bootstrap import create_app
from pema.clinic.crm_rules.admin import require_rules_admin
from pema.clinic.crm_rules.rules import DEFAULT_RULES
from pema_contracts.actions import ActionContext
from pema_contracts.crm import CrmRuleOut, CrmRuleUpdate, RuleKey
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Role

CLINIC = uuid4()


class FakeAdminService:
    def __init__(self) -> None:
        self.rules = {
            r.key: CrmRuleOut(
                id=uuid4(),
                rule_key=r.key,
                name=r.name,
                trigger=r.trigger,
                delay_days=r.delay_days,
                suggested_action=r.suggested_action,
                priority=r.priority,
                active=r.active,
                send_mode=r.send_mode,
                version=1,
            )
            for r in DEFAULT_RULES
        }

    async def list_rules(self, ctx: ActionContext) -> list[CrmRuleOut]:
        require_rules_admin(ctx)
        return list(self.rules.values())

    async def update_rule(self, ctx: ActionContext, rule_key: RuleKey, body: CrmRuleUpdate) -> CrmRuleOut:
        require_rules_admin(ctx)
        current = self.rules[rule_key]
        if body.version != current.version:
            raise DomainError(ErrorCode.VERSION_CONFLICT, "Quy tắc đã được người khác sửa.")
        updated = current.model_copy(
            update={
                "active": body.active if body.active is not None else current.active,
                "version": current.version + 1,
            }
        )
        self.rules[rule_key] = updated
        return updated


def _ctx(role: Role | None, actor_type: ActorType = ActorType.USER) -> ActionContext:
    return ActionContext(clinic_id=CLINIC, actor_type=actor_type, actor_user_id=uuid4(), actor_role=role)


@pytest.fixture
def app() -> FastAPI:
    return create_app()


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


@pytest_asyncio.fixture
async def anonymous(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with _client(app) as client:
        yield client


async def test_an_unwired_route_fails_closed_with_501(anonymous: httpx.AsyncClient) -> None:
    """Route chưa được nối xác thực thì từ chối (501), không bao giờ trả dữ liệu cho người ẩn danh."""
    for method, path in (("GET", "/api/v1/admin/rules"), ("PATCH", "/api/v1/admin/rules/d1")):
        response = await anonymous.request(method, path, json={"version": 1})
        assert response.status_code == 501
        assert response.json()["error"]["code"] == "not_implemented"


async def test_a_wired_context_without_a_service_answers_501(app: FastAPI) -> None:
    """Đã có ngữ cảnh người dùng nhưng chưa nối dịch vụ thì trả 501."""
    app.dependency_overrides[admin_crm_rules.get_action_context] = lambda: _ctx(Role.OWNER)
    async with _client(app) as client:
        assert (await client.get("/api/v1/admin/rules")).status_code == 501


@pytest.mark.parametrize("role", [Role.OWNER, Role.MANAGER])
async def test_owner_and_manager_list_the_ten_rules(app: FastAPI, role: Role) -> None:
    """Chủ và quản lý xem được mười quy tắc."""
    service = FakeAdminService()
    app.dependency_overrides[admin_crm_rules.get_action_context] = lambda: _ctx(role)
    app.dependency_overrides[admin_crm_rules.get_rules_admin] = lambda: service
    async with _client(app) as client:
        response = await client.get("/api/v1/admin/rules")
    assert response.status_code == 200
    assert [r["rule_key"] for r in response.json()] == [r.key.value for r in DEFAULT_RULES]


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT, None])
async def test_other_roles_are_forbidden(app: FastAPI, role: Role | None) -> None:
    """Các vai trò khác không được xem hay chỉnh quy tắc."""
    service = FakeAdminService()
    app.dependency_overrides[admin_crm_rules.get_action_context] = lambda: _ctx(role)
    app.dependency_overrides[admin_crm_rules.get_rules_admin] = lambda: service
    async with _client(app) as client:
        listed = await client.get("/api/v1/admin/rules")
        patched = await client.patch("/api/v1/admin/rules/d1", json={"version": 1, "active": False})
    assert listed.status_code == patched.status_code == 403


async def test_an_agent_or_scheduler_actor_is_forbidden_even_with_an_owner_role(app: FastAPI) -> None:
    """Tác nhân agent/bộ lập lịch không được chỉnh quy tắc, dù mang vai trò chủ."""
    service = FakeAdminService()
    app.dependency_overrides[admin_crm_rules.get_action_context] = lambda: _ctx(Role.OWNER, ActorType.AGENT)
    app.dependency_overrides[admin_crm_rules.get_rules_admin] = lambda: service
    async with _client(app) as client:
        assert (await client.get("/api/v1/admin/rules")).status_code == 403


async def test_a_tune_bumps_the_version_and_a_stale_version_conflicts(app: FastAPI) -> None:
    """Chỉnh quy tắc tăng version; version cũ bị từ chối với 409."""
    service = FakeAdminService()
    app.dependency_overrides[admin_crm_rules.get_action_context] = lambda: _ctx(Role.MANAGER)
    app.dependency_overrides[admin_crm_rules.get_rules_admin] = lambda: service
    async with _client(app) as client:
        ok = await client.patch("/api/v1/admin/rules/d1", json={"version": 1, "active": False})
        stale = await client.patch("/api/v1/admin/rules/d1", json={"version": 1, "active": True})
    assert ok.status_code == 200
    assert ok.json()["version"] == 2
    assert ok.json()["active"] is False
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "version_conflict"

"""``/api/v1/admin/policy/*``: wiring, auth and the envelope (new tests; the SQL is in test_identity_sql.py).

Without the two wired dependencies the routes behave like the rest of the skeleton (501 / 401), so a
forgotten wiring is loud. With them, the route only delegates to ``PolicyAdminService``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import cast
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from pema.api.routers.admin_policy import get_action_context, get_policy_admin
from pema.bootstrap import create_app
from pema.core.db import ClinicDatabase
from pema.policy.identity_admin import PolicyAdminService
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.admin_agent import AccountOut, AccountPolicyUpdate, IdentityConfirm
from pema_contracts.channel import ChannelKind
from pema_contracts.clinic_actions import IdentityLink, IdentityLinkStatus
from pema_contracts.policy import PolicyProfileKey
from pema_contracts.roles import ActorType, Role
from pema_contracts.testing import FAKE_CLINIC_ID, InMemoryAccountStore, fake_account_config

BASE = "/api/v1/admin/policy"


def _staff(role: Role) -> ActionContext:
    return ActionContext(
        clinic_id=FAKE_CLINIC_ID,
        actor_type=ActorType.USER,
        actor_user_id=uuid4(),
        actor_role=role,
        source=ActionSource.UI,
    )


class _Service:
    """Stands in for ``PolicyAdminService`` on the success paths (no database here)."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    @staticmethod
    def list_profiles() -> object:
        return PolicyAdminService.list_profiles()

    async def list_pending(self, ctx: ActionContext) -> list[IdentityLink]:
        self.calls.append("pending")
        return [
            IdentityLink(
                channel=ChannelKind.ZALO_BOT,
                external_user_id="zu-1",
                status=IdentityLinkStatus.PENDING,
                patient_id=uuid4(),
                patient_code="P025",
            )
        ]

    async def confirm(self, ctx: ActionContext, body: IdentityConfirm) -> IdentityLink:
        self.calls.append("reject" if body.reject else "confirm")
        status = IdentityLinkStatus.REJECTED if body.reject else IdentityLinkStatus.VERIFIED
        return IdentityLink(channel=body.channel, external_user_id=body.external_user_id, status=status)

    async def set_account_profile(
        self, ctx: ActionContext, account_id: str, update: AccountPolicyUpdate
    ) -> AccountOut:
        self.calls.append("account")
        cfg = fake_account_config(
            id=account_id, clinic_id=ctx.clinic_id, policy_profile=update.policy_profile
        )
        return AccountOut(**cfg.model_dump(), running=False, has_credentials=False)


@pytest_asyncio.fixture
async def bare() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def wired() -> AsyncIterator[tuple[httpx.AsyncClient, _Service, FastAPI]]:
    app = create_app()
    service = _Service()
    app.dependency_overrides[get_policy_admin] = lambda: service
    app.dependency_overrides[get_action_context] = lambda: _staff(Role.OWNER)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c, service, app


async def test_routes_answer_501_until_the_service_is_wired(bare: httpx.AsyncClient) -> None:
    """chưa nối dịch vụ (G chưa làm): mọi route trả 501 như bộ khung, không âm thầm cho qua"""
    assert (await bare.get(f"{BASE}/profiles")).status_code == 501
    assert (await bare.get(f"{BASE}/identity/pending")).status_code == 501
    body = {"channel": "zalo_bot", "external_user_id": "u", "patient_id": str(uuid4())}
    assert (await bare.post(f"{BASE}/identity/confirm", json=body)).status_code == 501


async def test_profiles_lists_both_profiles(wired: tuple[httpx.AsyncClient, _Service, FastAPI]) -> None:
    """GET /profiles trả hai hồ sơ dưới dạng dữ liệu"""
    client, _, _ = wired
    resp = await client.get(f"{BASE}/profiles")
    assert resp.status_code == 200
    keys = [p["key"] for p in resp.json()["profiles"]]
    assert keys == ["staff_assistant", "patient_channel"]
    patient = resp.json()["profiles"][1]
    assert patient["outbound_mode"] == "review"
    assert patient["pii_mask"] == "required"
    assert "web_fetch" in patient["disabled_tool_keys"]


async def test_pending_confirm_reject_and_account_delegate_to_the_service(
    wired: tuple[httpx.AsyncClient, _Service, FastAPI],
) -> None:
    """pending / confirm / reject / đổi hồ sơ tài khoản chuyển cho dịch vụ và trả đúng DTO"""
    client, service, _ = wired
    pending = await client.get(f"{BASE}/identity/pending")
    assert pending.status_code == 200
    assert pending.json()[0]["patient_code"] == "P025"
    body = {"channel": "zalo_bot", "external_user_id": "zu-1", "patient_id": str(uuid4())}
    confirmed = await client.post(f"{BASE}/identity/confirm", json=body)
    assert confirmed.json()["status"] == "verified"
    rejected = await client.post(f"{BASE}/identity/confirm", json={**body, "reject": True})
    assert rejected.json()["status"] == "rejected"
    account = await client.put(f"{BASE}/accounts/acc-1", json={"policy_profile": "patient_channel"})
    assert account.status_code == 200
    assert account.json()["policy_profile"] == "patient_channel"
    assert service.calls == ["pending", "confirm", "reject", "account"]


async def test_an_unknown_profile_value_is_a_validation_error(
    wired: tuple[httpx.AsyncClient, _Service, FastAPI],
) -> None:
    """giá trị hồ sơ lạ bị 422, không đi tới dịch vụ"""
    client, service, _ = wired
    resp = await client.put(f"{BASE}/accounts/acc-1", json={"policy_profile": "anything_goes"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_failed"
    assert service.calls == []


async def test_missing_session_is_401(wired: tuple[httpx.AsyncClient, _Service, FastAPI]) -> None:
    """thiếu ngữ cảnh đăng nhập: 401 (dịch vụ đã nối nhưng không có người dùng)"""
    client, service, app = wired
    del app.dependency_overrides[get_action_context]
    resp = await client.get(f"{BASE}/identity/pending")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthenticated"
    assert service.calls == []


@pytest.mark.parametrize("role", [Role.RECEPTION, Role.DOCTOR, Role.CS_STAFF, Role.PATIENT])
async def test_real_service_forbids_roles_without_admin_policy(role: Role) -> None:
    """dịch vụ thật trả 403 cho vai trò không có admin.policy (kiểm quyền trước khi chạm DB)"""
    app = create_app()
    service = PolicyAdminService(db=cast(ClinicDatabase, object()), accounts=InMemoryAccountStore())
    app.dependency_overrides[get_policy_admin] = lambda: service
    app.dependency_overrides[get_action_context] = lambda: _staff(role)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        pending = await client.get(f"{BASE}/identity/pending")
        update = await client.put(f"{BASE}/accounts/acc-1", json={"policy_profile": "staff_assistant"})
    assert pending.status_code == 403
    assert pending.json()["error"]["code"] == "forbidden"
    assert update.status_code == 403


def test_default_profile_enum_is_what_the_route_accepts() -> None:
    """hai giá trị hồ sơ hợp lệ khớp enum hợp đồng"""
    assert {p.value for p in PolicyProfileKey} == {"staff_assistant", "patient_channel"}

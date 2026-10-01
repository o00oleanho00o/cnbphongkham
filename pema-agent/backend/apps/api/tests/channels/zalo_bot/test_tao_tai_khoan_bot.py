# ported from: src/zalo-bot/tao-tai-khoan-bot.test.ts
"""Storing the token of a bot account through the admin API (``PUT /admin/accounts/{id}/bot-token``).

The two most important invariants are about SECRETS and about FAILING CLOSED:

* The token must not leak into any response.
* A wrong token must NOT be stored: stored, the account looks configured but never runs and the only symptom
  is a silent bot.

Account CREATION through the dashboard (``POST /api/accounts``, loai, allowlist defaults, PATCH not changing
the kind) is package C2's / D2's route in Pema (``admin_accounts``), so those cases of the original file are
not translated here; the open item is in the C1 report.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import UUID

import httpx
import pytest
from fastapi import FastAPI, Request

from pema.api.deps import API_PREFIX
from pema.api.errors import install_error_handlers
from pema.api.routers import admin_bot_accounts
from pema.channels.zalo_bot.bot_account_admin import BotAccountAdminService
from pema.channels.zalo_bot.bot_account_manager import BotAccountManager
from pema.channels.zalo_bot.settings import ZaloBotSettings
from pema.channels.zalo_bot.testing import FakeBotClient, RouterStack, make_router_stack
from pema.channels.zalo_bot.zalo_bot_api_client import BotApiClient, LoiZaloBotApi
from pema_contracts.actions import ActionContext
from pema_contracts.channel import ChannelKind
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission, Role
from pema_contracts.testing import fake_account_config

TOKEN_THAT_DANG = "123456789:abcDEF_ghi-JKL"
URL_B1 = f"{API_PREFIX}/admin/accounts/b1/bot-token"


async def staff_resolver(request: Request, permission: Permission) -> ActionContext:
    """A stand-in for package B1's session check: a cookie is required; the clinic is the synthetic one."""
    if request.cookies.get("pema_session") != "ok":
        raise DomainError(ErrorCode.UNAUTHENTICATED, "Chưa đăng nhập.")
    assert permission is Permission.ADMIN_ACCOUNTS
    return ActionContext(
        clinic_id=UUID("00000000-0000-4000-8000-000000000001"),
        actor_type=ActorType.USER,
        actor_role=Role.OWNER,
    )


class Harness:
    def __init__(
        self, stack: RouterStack, app: FastAPI, manager: BotAccountManager, probe: list[str]
    ) -> None:
        self.stack = stack
        self.app = app
        self.manager = manager
        self.probe_tokens = probe
        self.runner_clients: list[FakeBotClient] = []


@pytest.fixture
async def harness() -> AsyncIterator[Harness]:
    bot = fake_account_config(id="b1", label="Bot", channel=ChannelKind.ZALO_BOT)
    personal = fake_account_config(id="b2", label="Thường", channel=ChannelKind.ZALO_PERSONAL)
    stack = make_router_stack(account=bot)
    await stack.accounts.create_account(
        stack.clinic_id, account_id=personal.id, label=personal.label, channel=personal.channel, agent_id=None
    )
    probe: list[str] = []
    runner_clients: list[FakeBotClient] = []

    def factory(token: str) -> BotApiClient:
        probe.append(token)
        client = FakeBotClient()
        runner_clients.append(client)
        return client

    manager = BotAccountManager(
        accounts=stack.accounts,
        router=stack.router,
        registry=stack.registry,
        settings=ZaloBotSettings(mode="polling"),
        client_factory=factory,
    )
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(admin_bot_accounts.router, prefix=API_PREFIX)
    app.state.staff_context_resolver = staff_resolver
    app.state.bot_account_admin = BotAccountAdminService(
        accounts=stack.accounts, manager=manager, client_factory=factory
    )
    h = Harness(stack, app, manager, probe)
    h.runner_clients = runner_clients
    yield h
    await manager.stop_all()
    await stack.batcher.clear_pending_batches()


def http(h: Harness, *, cookie: bool = True) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=h.app, raise_app_exceptions=False),
        base_url="http://test",
        cookies={"pema_session": "ok"} if cookie else None,
    )


def stored(h: Harness, account_id: str = "b1") -> str | None:
    return h.stack.accounts.bot_tokens.get((h.stack.clinic_id, account_id))


async def test_token_sai_dinh_dang_bi_chan_truoc_khi_ra_mang(harness: Harness) -> None:
    """token SAI ĐỊNH DẠNG bị chặn trước khi ra mạng"""
    # Pasting a whole notification sentence, or half a token, is the most common mistake.
    async with http(harness) as client:
        res = await client.put(URL_B1, json={"token": "day khong phai token"})
    assert res.status_code == 422
    assert stored(harness) is None
    # Not only the status: point at the branch being measured (schema validation), not the network branch.
    assert res.json()["error"]["code"] == "validation_failed"
    assert any("token" in f["loc"] for f in res.json()["error"]["details"]["fields"])
    assert harness.probe_tokens == [], "định dạng sai mà vẫn ra mạng"


async def test_zalo_tu_choi_token_thi_khong_luu_fail_closed(harness: Harness) -> None:
    """Zalo TỪ CHỐI token thì KHÔNG lưu - fail closed"""

    # The factory is injected, so this goes through no real network (the original measured a request to the
    # Internet on every test run before it was injected).
    def reject(token: str) -> BotApiClient:
        return FakeBotClient(me_error=LoiZaloBotApi("getMe thất bại: Unauthorized", "getMe", 200, 401))

    harness.app.state.bot_account_admin = BotAccountAdminService(
        accounts=harness.stack.accounts, manager=harness.manager, client_factory=reject
    )
    async with http(harness) as client:
        res = await client.put(URL_B1, json={"token": TOKEN_THAT_DANG})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "validation_failed"
    assert stored(harness) is None, "token hỏng vẫn được lưu"
    assert TOKEN_THAT_DANG not in res.text


async def test_mang_rot_luc_kiem_cung_khong_luu_nhanh_khac_han_zalo_tu_choi(harness: Harness) -> None:
    """MẠNG RỚT lúc kiểm cũng KHÔNG lưu - nhánh khác hẳn Zalo từ chối"""

    def offline(token: str) -> BotApiClient:
        return FakeBotClient(me_error=LoiZaloBotApi("Không gọi được getMe: ConnectError", "getMe"))

    harness.app.state.bot_account_admin = BotAccountAdminService(
        accounts=harness.stack.accounts, manager=harness.manager, client_factory=offline
    )
    async with http(harness) as client:
        res = await client.put(URL_B1, json={"token": TOKEN_THAT_DANG})
    assert res.status_code == 422
    assert stored(harness) is None


async def test_token_dung_thi_luu_khoi_dong_duoc_va_khong_lo_token_ra_response(harness: Harness) -> None:
    """token ĐÚNG thì lưu, KHỞI ĐỘNG được, và KHÔNG lộ token ra response"""
    # The success branch must be run at least once, otherwise removing the store call from the route keeps the
    # suite green. Also the restart: one of the decisions of the Accounts page.
    async with http(harness) as client:
        res = await client.put(URL_B1, json={"token": TOKEN_THAT_DANG})
    assert res.status_code == 200
    body = res.json()
    assert body["has_bot_token"] is True
    assert body["running"] is True, "lưu token xong mà account không lên sóng"
    assert TOKEN_THAT_DANG not in res.text, "token lọt vào response"
    assert "token" not in {k for k in body if k not in {"has_bot_token"}}, (
        "AccountOut không mang trường token"
    )
    assert stored(harness) == TOKEN_THAT_DANG
    assert harness.manager.is_running(harness.stack.clinic_id, "b1") is True
    assert harness.stack.registry.get_running(harness.stack.clinic_id, "b1") is not None
    # Two clients: one probes the token before it is stored, one is the running account.
    assert harness.probe_tokens == [TOKEN_THAT_DANG, TOKEN_THAT_DANG]


async def test_tai_khoan_ca_nhan_khong_nhan_token(harness: Harness) -> None:
    """tài khoản CÁ NHÂN không nhận token"""
    async with http(harness) as client:
        res = await client.put(f"{API_PREFIX}/admin/accounts/b2/bot-token", json={"token": TOKEN_THAT_DANG})
    assert res.status_code == 422
    # Same reason as above: without the account-kind check the call falls to the network branch and also ends
    # in 4xx.
    assert "tài khoản loại bot" in res.json()["error"]["message"]
    assert stored(harness, "b2") is None
    assert harness.probe_tokens == []


async def test_account_khong_ton_tai_thi_404(harness: Harness) -> None:
    """account không tồn tại thì 404"""
    async with http(harness) as client:
        res = await client.put(
            f"{API_PREFIX}/admin/accounts/khong-co/bot-token", json={"token": TOKEN_THAT_DANG}
        )
    assert res.status_code == 404


async def test_doi_dang_nhap(harness: Harness) -> None:
    """đòi đăng nhập"""
    async with http(harness, cookie=False) as client:
        res = await client.put(URL_B1, json={"token": TOKEN_THAT_DANG})
    assert res.status_code == 401
    assert stored(harness) is None


async def test_thieu_cau_noi_xac_thuc_thi_tu_choi_het_fail_closed(harness: Harness) -> None:
    """(mới) app chưa nối staff_context_resolver thì không ai được qua"""
    del harness.app.state.staff_context_resolver
    async with http(harness) as client:
        res = await client.put(URL_B1, json={"token": TOKEN_THAT_DANG})
    assert res.status_code == 401


async def test_manager_start_all_bo_qua_tai_khoan_khong_token_va_khong_chet_vi_mot_tai_khoan_hong(
    harness: Harness,
) -> None:
    """(mới) start_all: tài khoản chưa có token bị bỏ qua, token hỏng không chặn tài khoản khác"""
    started = await harness.manager.start_all()
    assert started == 0, "không có token thì không khởi động"

    await harness.stack.accounts.set_bot_token(harness.stack.clinic_id, "b1", TOKEN_THAT_DANG)
    assert await harness.manager.start_all() == 1
    assert harness.manager.is_running(harness.stack.clinic_id, "b1")
    await harness.manager.stop(harness.stack.clinic_id, "b1")
    assert harness.stack.registry.get_running(harness.stack.clinic_id, "b1") is None

"""Closed loop on a single-tenant installation (package ST-G1).

One installation is ONE clinic: a member of staff signs in with e-mail and password only, and several Zalo
accounts of that clinic work side by side without touching each other. Both run on the real API (lifespan,
``be_app`` role), the real worker (``agent_worker`` role), a real Postgres and a real Redis; the LLM and Zalo are
fakes.
"""

from __future__ import annotations

import pytest

from pema.composition.testing import ACCOUNT_PASSWORD, LoopFactory, scripted
from pema_contracts.policy import PolicyProfileKey

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def test_staff_signs_in_with_email_and_password_only_then_me_and_refresh_work(
    make_loop: LoopFactory,
) -> None:
    """đăng nhập thật chỉ bằng email + mật khẩu (không có mã phòng khám): login 200, /me 200, refresh 200"""
    async with make_loop.open(scripted("không dùng"), PolicyProfileKey.STAFF_ASSISTANT) as loop:
        login = await loop.http.post(
            "/api/v1/auth/login", json={"email": "owner@example.test", "password": ACCOUNT_PASSWORD}
        )
        assert login.status_code == 200, login.text
        assert "pema_session" in login.cookies
        assert login.json()["user"]["clinic_name"], "the one clinic of the installation comes back by name"
        assert "clinic_slug" not in login.text

        me = await loop.http.get("/api/v1/me")
        assert me.status_code == 200, me.text
        assert me.json()["user"]["role"] == "owner"
        assert me.json()["user"]["clinic_id"] == str(loop.clinic_id)

        refreshed = await loop.http.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200, refreshed.text


async def test_two_zalo_accounts_of_the_same_clinic_answer_their_own_customers_independently(
    make_loop: LoopFactory,
) -> None:
    """hai tài khoản Zalo cùng phòng khám chạy độc lập: mỗi khách nhận trả lời qua đúng tài khoản của mình"""
    async with make_loop.open(
        scripted("Dạ em chào anh/chị ạ."), PolicyProfileKey.STAFF_ASSISTANT, extra_accounts=1
    ) as loop:
        (second,) = loop.extra_account_ids
        first = loop.account_id
        assert first != second

        r1 = await loop.send_zalo_text("xin chào tài khoản một", uid="uid-khach-mot", account_id=first)
        r2 = await loop.send_zalo_text("xin chào tài khoản hai", uid="uid-khach-hai", account_id=second)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text

        sent_first = await loop.wait_sent_by(first, 1)
        sent_second = await loop.wait_sent_by(second, 1)

        assert [chat for chat, _text, _mode in sent_first] == ["uid-khach-mot"]
        assert [chat for chat, _text, _mode in sent_second] == ["uid-khach-hai"]
        assert len(loop.bots[first].sent) == 1, "account two's customer is never answered through account one"
        assert len(loop.bots[second].sent) == 1, "account one's customer is never answered through account two"

        wrong_secret = await loop.http.post(
            f"/api/v1/webhooks/zalo-bot/{second}",
            json={"ok": True, "result": {}},
            headers={"X-Bot-Api-Secret-Token": "secret-of-another-account"},
        )
        assert wrong_secret.status_code in (401, 403), "each account has its own webhook secret"

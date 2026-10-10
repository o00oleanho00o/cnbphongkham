"""The activity routes of the gateway without a database: the admin scope is required, lists are empty, a missing
session or turn is a 404; and the pure rules of paging and searching."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from agent_app.activity import MAX_PAGE, clamp_page, like_pattern
from agent_app.gateway import GatewaySettings, create_app
from agent_app.profile import load_profile
from agent_app.runtime import build_runtime

TOKEN = "c" * 40
ADMIN_TOKEN = "d" * 40
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
CHAT = {"Authorization": f"Bearer {TOKEN}"}
DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"
MISSING_TURN = "00000000-0000-4000-8000-000000000009"


def _service() -> httpx.AsyncClient:
    runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=None)
    app = create_app(
        runtime.dispatcher(),
        GatewaySettings(token=TOKEN, admin_token=ADMIN_TOKEN),
        admin=runtime.model_admin,
    )
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


async def test_the_activity_routes_need_the_admin_scope() -> None:
    async with _service() as client:
        chat_token = [
            (await client.get(path, headers=CHAT)).status_code
            for path in ("/v1/admin/sessions", "/v1/admin/traces", "/v1/admin/usage")
        ]
        nobody = (await client.get("/v1/admin/sessions")).status_code

    assert (chat_token, nobody) == ([403, 403, 403], 401)


async def test_without_a_database_the_lists_are_empty_and_a_detail_is_not_found() -> None:
    async with _service() as client:
        sessions = (await client.get("/v1/admin/sessions", headers=ADMIN)).json()
        traces = (await client.get("/v1/admin/traces?errors_only=true", headers=ADMIN)).json()
        usage = (await client.get("/v1/admin/usage?days=7", headers=ADMIN)).json()
        no_session = await client.get("/v1/admin/sessions/dev:http:u:0", headers=ADMIN)
        no_delete = await client.delete("/v1/admin/sessions/dev:http:u:0", headers=ADMIN)
        no_turn = await client.get(f"/v1/admin/traces/{MISSING_TURN}", headers=ADMIN)
        bad_turn = await client.get("/v1/admin/traces/not-a-uuid", headers=ADMIN)

    assert sessions == {"items": [], "has_more": False}
    assert traces == {"items": [], "has_more": False}
    assert usage == {"today": None, "days": []}
    assert [r.status_code for r in (no_session, no_delete, no_turn, bad_turn)] == [404, 404, 404, 404]


def test_a_search_is_escaped_for_like_and_an_empty_one_is_no_filter() -> None:
    assert like_pattern("  ") is None
    assert like_pattern("a_b") == "%a\\_b%"
    assert like_pattern("50%") == "%50\\%%"
    assert like_pattern("c:\\x") == "%c:\\\\x%"


@pytest.mark.parametrize(("page", "expected"), [(-3, 0), (0, 0), (7, 7), (MAX_PAGE + 5, MAX_PAGE)])
def test_a_page_number_stays_in_range(page: int, expected: int) -> None:
    assert clamp_page(page) == expected

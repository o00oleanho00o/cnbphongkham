from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio

from pema.api.export_openapi import DEFAULT_PATH, render_openapi
from pema.bootstrap import create_app

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
EXPECTED_PATHS = [
    # clinic CRM (B1, B2)
    "/api/v1/auth/login",
    "/api/v1/me",
    "/api/v1/patients/{patient_id}/360",
    "/api/v1/appointments",
    "/api/v1/crm/tasks",
    "/api/v1/crm/activities",
    "/api/v1/conversations/{conversation_id}/messages",
    "/api/v1/review-items/{item_id}/approve",
    "/api/v1/admin/rules",
    "/api/v1/admin/logs/audit",
    "/api/v1/admin/templates",
    "/api/v1/admin/templates/{template_id}/approve",
    # channels (C1, C2)
    "/api/v1/webhooks/zalo-bot/{clinic_slug}/{account_id}",
    "/api/v1/webhooks/zalo-bridge/{clinic_slug}/{account_id}",
    "/api/v1/admin/channels/{channel}/kill-switch",
    "/api/v1/admin/accounts",
    "/api/v1/admin/accounts/{account_id}/login",
    "/api/v1/admin/accounts/{account_id}/login/status",
    "/api/v1/admin/accounts/{account_id}/bot-token",
    "/api/v1/admin/friends/{account_id}/requests",
    # engine admin (D1..D5, S, P)
    "/api/v1/admin/agents",
    "/api/v1/admin/model/provider",
    "/api/v1/admin/model/tuning",
    "/api/v1/admin/tools",
    "/api/v1/admin/tools/image-gen",
    "/api/v1/admin/kb/sources",
    "/api/v1/admin/kb/search",
    "/api/v1/admin/schedules",
    "/api/v1/admin/schedules/{job_id}/run",
    "/api/v1/admin/mcp/servers",
    "/api/v1/admin/mcp/servers/{server_id}/reapprove",
    "/api/v1/admin/usage/overview",
    "/api/v1/admin/traces",
    "/api/v1/admin/logs/app",
    "/api/v1/admin/threads",
    "/api/v1/admin/memories",
    "/api/v1/admin/policy/profiles",
    "/api/v1/admin/policy/identity/confirm",
]


@pytest_asyncio.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture(scope="module")
def schema() -> dict[str, Any]:
    return create_app().openapi()


def test_committed_openapi_json_is_up_to_date() -> None:
    assert DEFAULT_PATH.read_text(encoding="utf-8") == render_openapi(), (
        "apps/api/openapi.json is stale: run `make openapi` and commit the result"
    )


def test_expected_endpoints_are_declared(schema: dict[str, Any]) -> None:
    missing = [p for p in EXPECTED_PATHS if p not in schema["paths"]]
    assert missing == []


def test_operation_ids_are_unique_and_tagged(schema: dict[str, Any]) -> None:
    ids: list[str] = []
    for path_item in schema["paths"].values():
        for method, op in path_item.items():
            if method in HTTP_METHODS:
                ids.append(op["operationId"])
                assert op["tags"], op["operationId"]
    assert len(ids) == len(set(ids))


def test_every_tag_used_by_a_route_is_described(schema: dict[str, Any]) -> None:
    described = {t["name"] for t in schema["tags"]}
    used = {tag for item in schema["paths"].values() for op in item.values() for tag in op["tags"]}
    assert used <= described


def test_every_admin_and_clinic_route_requires_the_session_cookie(schema: dict[str, Any]) -> None:
    open_paths = {"/healthz", "/api/v1/auth/login"}
    unsecured: list[str] = []
    for path, item in schema["paths"].items():
        if path in open_paths or "/webhooks/" in path:
            continue
        for method, op in item.items():
            if method in HTTP_METHODS and not any("SessionCookie" in req for req in op.get("security", [])):
                unsecured.append(f"{method.upper()} {path}")
    assert unsecured == []


def test_secrets_are_write_only_in_the_admin_dtos(schema: dict[str, Any]) -> None:
    schemas = schema["components"]["schemas"]
    for name in ("AccountOut", "LlmSettingsOut", "McpServerView", "VisionSettingsOut", "ImageGenSettingsOut"):
        props = set(schemas[name]["properties"])
        assert not props & {"bot_token", "token", "api_key", "headers", "password", "credential"}, name


def test_kill_switch_and_daily_cap_are_in_the_channel_settings_schema(schema: dict[str, Any]) -> None:
    props = schema["components"]["schemas"]["ChannelSettingsOut"]["properties"]
    assert {"kill_switch_on", "daily_cap", "proactive_sent_today", "bridge_state"} <= set(props)


async def test_health_is_the_only_live_endpoint(client: httpx.AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

# GET endpoints that left the 501 skeleton because their package implemented them (each has its own route tests).
IMPLEMENTED_GET = {
    "/api/v1/admin/model/provider",
    "/api/v1/admin/model/vision",
    "/api/v1/admin/model/tuning",
    "/api/v1/admin/usage/overview",
    "/api/v1/admin/traces",
    "/api/v1/admin/traces/turn/{turn_id}",
    "/api/v1/admin/logs/app",
}


def _fill_path(path: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name == "channel":
            return "zalo_bot"
        if name == "rule_key":
            return "d1"
        if name in {"turn_id", "fact_id"}:
            return "1"
        if name.endswith("_id") and name not in {
            "patient_id",
            "conversation_id",
            "item_id",
            "appointment_id",
            "task_id",
            "template_id",
        }:
            return "synthetic-id"
        if name == "clinic_slug":
            return "demo"
        return str(uuid4())

    return re.sub(r"\{(\w+)\}", repl, path)


async def test_every_get_endpoint_answers_501_with_error_envelope(
    client: httpx.AsyncClient, schema: dict[str, Any]
) -> None:
    checked = 0
    for path, item in schema["paths"].items():
        op = item.get("get")
        if op is None or path == "/healthz" or path in IMPLEMENTED_GET:
            continue
        params = {
            p["name"]: str(uuid4())
            for p in op.get("parameters", [])
            if p["in"] == "query" and p.get("required")
        }
        resp = await client.get(_fill_path(path), params=params)
        assert resp.status_code == 501, path
        assert resp.json()["error"]["code"] == "not_implemented", path
        checked += 1
    assert checked >= 40


async def test_validation_errors_use_the_error_envelope_without_echoing_input(
    client: httpx.AsyncClient,
) -> None:
    resp = await client.post("/api/v1/auth/login", json={"clinic_slug": "demo", "email": "a@example.test"})
    assert resp.status_code == 422
    body = resp.json()["error"]
    assert body["code"] == "validation_failed"
    assert "a@example.test" not in resp.text


async def test_post_with_valid_body_reaches_the_501_stub(client: httpx.AsyncClient) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"clinic_slug": "demo", "email": "staff@example.test", "password": "synthetic"},
    )
    assert resp.status_code == 501


async def test_bot_token_with_bad_shape_is_rejected_before_the_stub(client: httpx.AsyncClient) -> None:
    resp = await client.put("/api/v1/admin/accounts/bot-1/bot-token", json={"token": "not a token"})
    assert resp.status_code == 422
    assert "not a token" not in resp.text

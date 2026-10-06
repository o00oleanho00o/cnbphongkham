"""Credential boundary: nothing an operator can reach carries a credential (package O, step O1).

New tests (no zalo-agent original). Credentials of a channel account (``bot_token_enc``, ``credential_enc`` = the
zca-js cookie, ``webhook_secret_enc``) never leave the server. Four checks:

1. the DTOs of ``pema_contracts.ops`` have no field that could hold a credential (strict, no exemption);
2. every RESPONSE schema of the OpenAPI document is free of credential-looking field names, except three named
   fields of the manager-only ``/admin/accounts`` flows of package C2 (a boolean and the QR image the manager
   scans on the bridge host); the routes that return them are under ``/admin/accounts`` and
   ``/admin/policy/accounts`` and need permissions only the owner and the manager hold; the ``example`` values of
   the document hold none either;
3. with marker values planted in the three ``*_enc`` columns, no response of the identity and roster routes, no
   audit row and no field of an action result contains a marker (needs ``PEMA_TEST_DATABASE_URL``);
4. a log capture around an identity update holds no marker, no ``*_enc`` and no cookie.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, cast

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pema.bootstrap import create_app
from pema.clinic.actions import identities, roster
from pema.clinic.actions.seed_demo import SeedResult
from pema.clinic.rbac import ROLE_PERMISSIONS
from pema.core.db import ClinicDatabase
from pema_contracts import ops
from pema_contracts.ops import IdentityUpdate, RosterEntryCreate, Weekday
from pema_contracts.roles import Permission, Role

SECRETS = {
    "bot_token_enc": "ENC-BOT-TOKEN-MARKER-7f3a",
    "credential_enc": "ENC-COOKIE-MARKER-91bc",
    "webhook_secret_enc": "ENC-WEBHOOK-MARKER-d204",
}
FORBIDDEN_NAME = re.compile(
    r"(_enc$|cookie|imei|user_?agent|webhook_secret|(^|_)qr|^token$|^secret$|credentials?$|password_hash)",
    re.IGNORECASE,
)
MANAGER_ONLY_ADMIN_ACCOUNTS = {
    ("AccountOut", "has_credentials"),  # a boolean: "this account has a login"
    ("QrLoginStatus", "qr_png_base64"),  # the QR the manager scans on the bridge host (C2, admin.accounts)
}


def _property_names(schema: Any) -> list[str]:
    properties = cast(dict[str, Any], cast(dict[str, Any], schema or {}).get("properties", {}))
    return list(properties)


# ------------------------------------------------------------------------------------------ 1. the DTOs
def test_the_identity_and_roster_dtos_have_no_field_that_could_hold_a_credential() -> None:
    models = [
        value for value in vars(ops).values() if isinstance(value, type) and issubclass(value, ops.ApiModel)
    ]
    assert len(models) >= 8
    for model in models:
        schema = model.model_json_schema()
        for name in [
            *_property_names(schema),
            *(n for d in schema.get("$defs", {}).values() for n in _property_names(d)),
        ]:
            assert not FORBIDDEN_NAME.search(name), f"{model.__name__}.{name}"


# ----------------------------------------------------------------------------------- 2. the whole API
def _response_schema_names(spec: dict[str, Any]) -> set[str]:
    """Names of the component schemas reachable from a response body (request-only bodies are left out: a
    password or a bot token is something an operator TYPES, never something the server sends back)."""
    seen: set[str] = set()
    schemas = cast(dict[str, Any], spec["components"]["schemas"])

    def visit(node: Any) -> None:
        if isinstance(node, dict):
            fields = cast(dict[str, Any], node)
            ref = fields.get("$ref")
            if isinstance(ref, str):
                name = ref.rsplit("/", 1)[-1]
                if name not in seen:
                    seen.add(name)
                    visit(schemas.get(name, {}))
            for value in fields.values():
                visit(value)
        elif isinstance(node, list):
            for item in cast(list[Any], node):
                visit(item)

    for path_item in cast(dict[str, Any], spec["paths"]).values():
        for operation in cast(dict[str, Any], path_item).values():
            if isinstance(operation, dict):
                visit(cast(dict[str, Any], operation).get("responses", {}))
    return seen


def test_no_response_schema_of_the_api_has_a_credential_looking_field() -> None:
    spec = create_app().openapi()
    found: set[tuple[str, str]] = set()
    for name in _response_schema_names(spec):
        for prop in _property_names(spec["components"]["schemas"].get(name)):
            if FORBIDDEN_NAME.search(prop):
                found.add((name, prop))
    assert found == MANAGER_ONLY_ADMIN_ACCOUNTS


def test_the_qr_and_account_flags_are_only_reachable_under_admin_accounts() -> None:
    spec = create_app().openapi()
    holders = {"AccountOut", "QrLoginStatus"}
    for path, item in spec["paths"].items():
        for operation in item.values():
            if not isinstance(operation, dict):
                continue
            used = {
                ref.rsplit("/", 1)[-1] for ref in re.findall(r'"\$ref": "([^"]+)"', json.dumps(operation))
            }
            if used & holders:
                assert path.startswith(("/api/v1/admin/accounts", "/api/v1/admin/policy/accounts")), path


def test_the_examples_of_the_openapi_document_hold_no_credential() -> None:
    spec = create_app().openapi()
    examples: list[Any] = []

    def collect(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in cast(dict[str, Any], node).items():
                if key in ("example", "examples"):
                    examples.append(value)
                collect(value)
        elif isinstance(node, list):
            for item in cast(list[Any], node):
                collect(item)

    collect(spec)
    blob = json.dumps(examples)
    assert not re.search(r"_enc|cookie|imei|BEGIN [A-Z ]*KEY|bot_token|webhook_secret", blob, re.IGNORECASE)


# ------------------------------------------------------------------------------- 3. planted markers
@pytest.fixture
def credentialed(add_account: Any, admin: Engine) -> str:
    add_account("long", **SECRETS)
    add_account("bell", purpose="internal", **SECRETS)
    return "long"


@pytest.mark.db
async def test_no_identity_or_roster_response_carries_a_planted_credential(
    client_factory: Any, world: SeedResult, credentialed: str, admin: Engine
) -> None:
    manager = await client_factory("manager")
    doctor = await client_factory("doctor.mai")
    created = await manager.post(
        "/api/v1/roster",
        json={
            "account_id": "long",
            "user_id": str(world.users["cs.thu"]),
            "weekdays": ["mon"],
            "start": "08:00",
            "end": "12:00",
        },
    )
    assert created.status_code == 201
    bodies = [
        (await doctor.get("/api/v1/identities")).text,
        (await manager.get("/api/v1/identities")).text,
        (await manager.patch("/api/v1/identities/long", json={"daily_cap": 11, "label": "Long"})).text,
        (await manager.patch("/api/v1/identities/bell", json={"daily_cap": 2})).text,
        (await doctor.get("/api/v1/roster")).text,
        (await doctor.get("/api/v1/identities/long/on-duty")).text,
        created.text,
    ]
    for body in bodies:
        assert body
        for marker in SECRETS.values():
            assert marker not in body
        assert not re.search(r"_enc|cookie|credential", body, re.IGNORECASE)
    with admin.connect() as conn:
        trail = "".join(
            row.details or ""
            for row in conn.execute(text("SELECT details::text AS details FROM clinic.audit_log"))
        )
    for marker in SECRETS.values():
        assert marker not in trail


@pytest.mark.db
async def test_no_action_result_carries_a_planted_credential(
    db: ClinicDatabase, world: SeedResult, credentialed: str, staff_ctx: Any
) -> None:
    owner = staff_ctx("owner")
    results: list[str] = [row.model_dump_json() for row in await identities.list_identities(db, owner)]
    results.append((await identities.get_identity(db, owner, "long")).model_dump_json())
    results.append(
        (
            await identities.update_identity_settings(db, owner, "long", IdentityUpdate(daily_cap=4))
        ).model_dump_json()
    )
    entry = await roster.create_entry(
        db,
        owner,
        RosterEntryCreate(
            account_id="long",
            user_id=world.users["cs.thu"],
            weekdays=[Weekday.MON],
            start="08:00",
            end="12:00",
        ),
    )
    results.append(entry.model_dump_json())
    for body in results:
        for marker in SECRETS.values():
            assert marker not in body
        assert "_enc" not in body


@pytest.mark.parametrize("role", [Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT])
def test_an_operator_does_not_hold_the_permissions_of_the_account_admin_routes(role: Role) -> None:
    """The routes that return the account flags and the QR (``/admin/accounts``, ``/admin/policy/accounts``)
    need ``admin.accounts`` / ``admin.policy``: only the owner and the manager hold them."""
    held = ROLE_PERMISSIONS[role]
    assert Permission.ADMIN_ACCOUNTS not in held
    assert Permission.ADMIN_POLICY not in held
    assert {r for r, p in ROLE_PERMISSIONS.items() if Permission.ADMIN_ACCOUNTS in p} == {
        Role.OWNER,
        Role.MANAGER,
    }


# ------------------------------------------------------------------------------------ 4. log capture
@pytest.mark.db
async def test_an_identity_update_logs_no_credential(
    db: ClinicDatabase,
    credentialed: str,
    staff_ctx: Any,
    client_factory: Any,
    caplog: pytest.LogCaptureFixture,
    capfd: pytest.CaptureFixture[str],
) -> None:
    manager = await client_factory("manager")
    with caplog.at_level(logging.DEBUG):
        await identities.update_identity_settings(
            db,
            staff_ctx("manager"),
            "long",
            IdentityUpdate(label="Long (CSKH)", send_gap_min_s=2, send_gap_max_s=6),
        )
        patched = await manager.patch("/api/v1/identities/long", json={"daily_cap": 9})
    assert patched.status_code == 200
    captured = capfd.readouterr()
    everything = "\n".join([record.getMessage() + repr(record.__dict__) for record in caplog.records])
    everything += captured.out + captured.err
    for marker in SECRETS.values():
        assert marker not in everything
    assert not re.search(r"_enc\b|cookie", everything, re.IGNORECASE)

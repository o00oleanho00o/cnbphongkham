"""Model settings changed at runtime: resolution (database > profile), the encrypted key, the settings-aware
model, the admin operations, the admin HTTP routes and ``agent model``."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from agent_app.cli import main
from agent_app.gateway import GatewaySettings, create_app
from agent_app.model_factory import ModelSettings
from agent_app.model_settings import (
    DynamicModel,
    InMemoryModelSettingsStore,
    ModelAdmin,
    SecretKeyMissingError,
    StoredModelSettings,
    resolve_effective,
)
from agent_app.profile import Profile, load_profile
from agent_app.runtime import build_runtime
from agentcore import AssistantResult, LlmRequest, Message, ModelError, StreamSink, TextBlock
from secretcipher import encrypt_with, mask_secret

DEV_PROFILE = Path(__file__).resolve().parents[1] / "agents" / "dev"
KEY = "a" * 64
OTHER_KEY = "b" * 64
TOKEN = "c" * 40
ADMIN_TOKEN = "d" * 40
ADMIN = {"Authorization": f"Bearer {ADMIN_TOKEN}"}
CHAT = {"Authorization": f"Bearer {TOKEN}"}
PROFILE = Profile.model_validate(
    {"agent": {"name": "dev"}, "model": {"model": "from-profile", "reasoning": "high"}}
)


class NamedModel:
    """Answers with the name of the model it was built for."""

    def __init__(self, settings: ModelSettings, *, error: ModelError | None = None) -> None:
        self.settings = settings
        self.error = error
        self.requests: list[LlmRequest] = []

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        message = Message(role="assistant", blocks=[TextBlock(text=f"model:{self.settings.model}")])
        return AssistantResult(message=message, stop_reason="end")


class Factory:
    def __init__(self, error: ModelError | None = None) -> None:
        self.built: list[NamedModel] = []
        self.error = error

    def __call__(self, settings: ModelSettings) -> NamedModel:
        model = NamedModel(settings, error=self.error)
        self.built.append(model)
        return model


def test_each_field_comes_from_the_database_then_the_profile() -> None:
    stored = StoredModelSettings(
        base_url="https://db.test/v1", api_key_enc=encrypt_with(KEY, "db-key"), version=3
    )

    with_db = resolve_effective(PROFILE, stored, KEY)
    without = resolve_effective(PROFILE, None, KEY)

    assert (with_db.settings.model, with_db.settings.base_url, with_db.settings.api_key) == (
        "from-profile",
        "https://db.test/v1",
        "db-key",
    )
    assert with_db.settings.reasoning == "high"
    assert dict(with_db.sources) == {
        "provider": "profile",
        "model": "profile",
        "base_url": "db",
        "reasoning": "profile",
        "dialect": "profile",
        "api_key": "db",
    }
    assert with_db.version == 3
    assert (without.settings.api_key, without.sources["api_key"], without.version) == ("", "unset", 0)


def test_a_stored_key_that_no_longer_decrypts_is_reported_and_not_used() -> None:
    stored = StoredModelSettings(api_key_enc=encrypt_with(KEY, "db-key"), version=1)

    changed = resolve_effective(PROFILE, stored, OTHER_KEY)
    missing = resolve_effective(PROFILE, stored, None)

    assert (changed.settings.api_key, changed.api_key_broken) == ("", True)
    assert (missing.settings.api_key, missing.api_key_broken) == ("", True)


async def test_the_model_rebuilds_when_the_stored_version_changes_and_fills_only_a_default_effort() -> None:
    now = [0.0]
    store = InMemoryModelSettingsStore()
    factory = Factory()
    model = DynamicModel(
        PROFILE,
        store,
        tenant_id="t",
        secret_key=None,
        factory=factory,
        refresh_s=5.0,
        clock=lambda: now[0],
    )
    request = LlmRequest(system="s", messages=[Message.user("hi")])

    first = await model.complete(request)
    await store.save("t", StoredModelSettings(model="m2"))
    cached = await model.complete(request)
    now[0] = 6.0
    fresh = await model.complete(request.model_copy(update={"reasoning": "off"}))

    assert [first.message.text(), cached.message.text(), fresh.message.text()] == [
        "model:from-profile",
        "model:from-profile",
        "model:m2",
    ]
    assert [r.reasoning for r in factory.built[0].requests] == ["high", "high"]
    assert factory.built[1].requests[0].reasoning == "off"
    assert model.model_name == "m2"


async def test_an_update_changes_only_what_it_names_and_never_logs_the_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    store = InMemoryModelSettingsStore()
    admin = ModelAdmin(PROFILE, store, tenant_id="t", secret_key=KEY)
    caplog.set_level(logging.INFO)

    shown = await admin.update({"model": "m1", "api_key": "sk-abcdefghijklmnop"})
    kept = await admin.update({"api_key": "", "reasoning": "low"})
    back = await admin.update({"model": None, "api_key": None})
    cleared = await admin.clear()

    assert (shown["model"], shown["api_key"], shown["stored"]) == ("m1", "sk-ab...mnop", True)
    assert (kept["api_key"], kept["reasoning"], kept["sources"]["api_key"]) == ("sk-ab...mnop", "low", "db")
    assert (back["model"], back["sources"]["model"], back["api_key"], back["sources"]["api_key"]) == (
        "from-profile",
        "profile",
        mask_secret(""),
        "unset",
    )
    assert (cleared["stored"], cleared["reasoning"], cleared["version"]) == (False, "high", 4)
    assert "sk-abcdefghijklmnop" not in caplog.text
    assert "model settings changed (version 1): model, api_key_enc" in caplog.text


async def test_a_key_cannot_be_stored_without_the_encryption_key() -> None:
    admin = ModelAdmin(PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=None)

    with pytest.raises(SecretKeyMissingError, match="no secret key"):
        await admin.update({"api_key": "sk-abcdefghijklmnop"})
    assert (await admin.update({"model": "m1"}))["model"] == "m1"


async def test_the_test_call_reports_success_or_the_error_kind() -> None:
    store = InMemoryModelSettingsStore()
    ok = await ModelAdmin(PROFILE, store, tenant_id="t", secret_key=None, factory=Factory()).test()
    failing = Factory(error=ModelError("auth", "bad key"))
    failed = await ModelAdmin(PROFILE, store, tenant_id="t", secret_key=None, factory=failing).test()

    assert (ok["ok"], ok["model"]) == (True, "from-profile")
    assert failed == {"ok": False, "model": "from-profile", "error_kind": "auth"}
    assert failing.built[0].requests[0].reasoning == "off"


class Catalog:
    """The provider's model listing (an outside API): records what it was asked with."""

    def __init__(self, error: ModelError | None = None) -> None:
        self.asked: list[ModelSettings] = []
        self.error = error

    async def __call__(self, settings: ModelSettings) -> list[str]:
        self.asked.append(settings)
        if self.error is not None:
            raise self.error
        return ["model-a", "model-b"]


async def test_the_model_list_uses_what_was_typed_and_the_stored_key_otherwise() -> None:
    store = InMemoryModelSettingsStore()
    catalog = Catalog()
    admin = ModelAdmin(PROFILE, store, tenant_id="t", secret_key=KEY, lister=catalog)
    await admin.update({"api_key": "sk-stored-abcdefgh"})

    listed = await admin.list_models({"base_url": "https://api.deepseek.com", "api_key": ""})

    assert listed == {"ok": True, "models": ["model-a", "model-b"]}
    asked = catalog.asked[0]
    assert (asked.base_url, asked.api_key) == ("https://api.deepseek.com", "sk-stored-abcdefgh")
    assert (await admin.show())["base_url"] is None


async def test_the_model_list_of_another_provider_drops_the_stored_base_url() -> None:
    store = InMemoryModelSettingsStore()
    catalog = Catalog()
    admin = ModelAdmin(PROFILE, store, tenant_id="t", secret_key=KEY, lister=catalog)
    await admin.update({"base_url": "https://api.deepseek.com"})

    await admin.list_models({"provider": "anthropic", "api_key": "sk-ant-typed"})

    asked = catalog.asked[0]
    assert (asked.provider, asked.base_url, asked.api_key) == ("anthropic", None, "sk-ant-typed")


async def test_the_model_list_reports_the_providers_refusal_by_kind() -> None:
    catalog = Catalog(error=ModelError("auth", "bad key"))
    admin = ModelAdmin(PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=None, lister=catalog)

    listed = await admin.list_models({})

    assert listed == {"ok": False, "models": [], "error_kind": "auth"}


def _service(
    *, admin_token: str | None = ADMIN_TOKEN, secret_key: str | None = KEY, catalog: Catalog | None = None
) -> httpx.AsyncClient:
    store = InMemoryModelSettingsStore()
    factory = Factory()
    dynamic = DynamicModel(PROFILE, store, tenant_id="default", secret_key=secret_key, factory=factory)
    admin = ModelAdmin(
        PROFILE,
        store,
        tenant_id="default",
        secret_key=secret_key,
        dynamic=dynamic,
        factory=factory,
        lister=catalog or Catalog(),
    )
    runtime = build_runtime(load_profile(DEV_PROFILE), fake=True, env={}, db=None)
    runtime.live.use_model(dynamic)
    app = create_app(runtime.dispatcher(), GatewaySettings(token=TOKEN, admin_token=admin_token), admin=admin)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://agent")


async def test_admin_routes_need_a_caller_with_the_admin_scope() -> None:
    async with _service(admin_token=None) as off, _service() as on:
        nobody = await off.get("/v1/admin/model", headers=ADMIN)
        chat_token = await on.get("/v1/admin/model", headers=CHAT)
        allowed = await on.get("/v1/admin/model", headers=ADMIN)

    assert (nobody.status_code, chat_token.status_code, allowed.status_code) == (401, 403, 200)
    with pytest.raises(ValueError, match="must differ"):
        GatewaySettings(token=TOKEN, admin_token=TOKEN)
    with pytest.raises(ValueError, match="at least 32"):
        GatewaySettings(token=TOKEN, admin_token="short")


async def test_repeated_failed_admin_logins_are_refused_for_a_while() -> None:
    wrong = {"Authorization": f"Bearer {'x' * 40}"}
    async with _service() as client:
        failures = [(await client.get("/v1/admin/model", headers=wrong)).status_code for _ in range(5)]
        blocked = await client.get("/v1/admin/model", headers=ADMIN)

    assert failures == [401] * 5
    assert blocked.status_code == 429


async def test_the_admin_changes_the_model_of_the_next_turn() -> None:
    async with _service() as client:
        before = await client.post(
            "/v1/chat", json={"message_id": "m1", "user_id": "u", "text": "hi"}, headers=CHAT
        )
        changed = await client.patch(
            "/v1/admin/model", json={"model": "m2", "api_key": "sk-abcdefghijklmnop"}, headers=ADMIN
        )
        after = await client.post(
            "/v1/chat", json={"message_id": "m2", "user_id": "u", "text": "hi"}, headers=CHAT
        )
        bad_provider = await client.patch("/v1/admin/model", json={"provider": "bogus"}, headers=ADMIN)
        bad_url = await client.patch("/v1/admin/model", json={"base_url": "ftp://x"}, headers=ADMIN)
        tested = await client.post("/v1/admin/model/test", headers=ADMIN)
        cleared = await client.delete("/v1/admin/model", headers=ADMIN)

    assert (before.json()["text"], after.json()["text"]) == ("model:from-profile", "model:m2")
    assert changed.status_code == 200
    assert (changed.json()["api_key"], changed.json()["sources"]["model"]) == ("sk-ab...mnop", "db")
    assert "sk-abcdefghijklmnop" not in changed.text
    assert (bad_provider.status_code, bad_url.status_code) == (422, 422)
    assert (tested.status_code, tested.json()["model"]) == (200, "m2")
    assert (cleared.json()["model"], cleared.json()["stored"]) == ("from-profile", False)


async def test_the_model_list_route_answers_the_models_or_502_with_the_kind() -> None:
    async with _service() as ok_client, _service(catalog=Catalog(ModelError("auth", "x"))) as bad_client:
        listed = await ok_client.post("/v1/admin/model/list", json={"api_key": "sk-typed"}, headers=ADMIN)
        refused = await bad_client.post("/v1/admin/model/list", json={}, headers=ADMIN)
        bad_url = await ok_client.post("/v1/admin/model/list", json={"base_url": "ftp://x"}, headers=ADMIN)
        chat_token = await ok_client.post("/v1/admin/model/list", json={}, headers=CHAT)

    assert (listed.status_code, listed.json()["models"]) == (200, ["model-a", "model-b"])
    assert (refused.status_code, refused.json()["error_kind"]) == (502, "auth")
    assert (bad_url.status_code, chat_token.status_code) == (422, 403)


async def test_storing_a_key_without_the_encryption_key_is_a_conflict() -> None:
    async with _service(secret_key=None) as client:
        refused = await client.patch(
            "/v1/admin/model", json={"api_key": "sk-abcdefghijklmnop"}, headers=ADMIN
        )

    assert refused.status_code == 409
    assert refused.json()["error"]["kind"] == "no_encryption_key"


def test_the_model_command_needs_the_database(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("AGENT_DATABASE_URL", raising=False)

    assert main(["model", "show", "--profile", str(DEV_PROFILE)]) == 2
    assert "set AGENT_DATABASE_URL" in capsys.readouterr().out

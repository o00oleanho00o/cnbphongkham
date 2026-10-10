"""Model settings changed at runtime: resolution (database > profile), the encrypted key, the settings-aware
model, the admin operations, the admin HTTP routes and ``agent model``."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx
import pytest

from agent_app.cli import main
from agent_app.gateway import GatewaySettings, create_app
from agent_app.model_entries import MAX_ENTRIES
from agent_app.model_factory import ModelSettings
from agent_app.model_settings import (
    DynamicModel,
    InMemoryModelSettingsStore,
    ModelAdmin,
    ModelEntryError,
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


DEEPSEEK = {
    "label": "DeepSeek công ty",
    "provider": "openai-compatible",
    "model": "deepseek-v4-pro",
    "base_url": "https://api.deepseek.com",
    "api_key": "sk-deepseek-abcdefgh",
}


async def test_the_list_keeps_several_models_each_with_its_own_masked_key() -> None:
    admin = ModelAdmin(PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=KEY)

    first = await admin.add_entry(DEEPSEEK)
    second = await admin.add_entry({**DEEPSEEK, "label": "DeepSeek dự phòng", "api_key": "sk-other-12345678"})
    third = await admin.add_entry({"label": "Ollama", "provider": "openai-compatible", "model": "llama3"})
    listed = (await admin.entries())["entries"]

    assert [e["label"] for e in listed] == ["DeepSeek công ty", "DeepSeek dự phòng", "Ollama"]
    assert (first["api_key"], second["api_key"], third["has_key"]) == ("sk-de...efgh", "sk-ot...5678", False)
    assert "sk-deepseek-abcdefgh" not in str(listed)
    assert [e["active"] for e in listed] == [False, False, False]


async def test_using_a_model_gives_the_agent_its_fields_and_key_and_marks_it_in_use() -> None:
    store = InMemoryModelSettingsStore()
    admin = ModelAdmin(PROFILE, store, tenant_id="t", secret_key=KEY)
    entry = await admin.add_entry(DEEPSEEK)

    shown = await admin.use_entry(entry["id"])
    listed = (await admin.entries())["entries"]

    assert (shown["model"], shown["base_url"], shown["api_key"]) == (
        "deepseek-v4-pro",
        "https://api.deepseek.com",
        "sk-de...efgh",
    )
    assert (shown["entry_id"], listed[0]["active"]) == (entry["id"], True)
    assert (await admin.resolved()).settings.api_key == "sk-deepseek-abcdefgh"


async def test_editing_the_model_in_use_applies_to_the_agent_and_other_edits_do_not() -> None:
    admin = ModelAdmin(PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=KEY)
    used = await admin.add_entry(DEEPSEEK)
    other = await admin.add_entry({**DEEPSEEK, "label": "Khác"})
    await admin.use_entry(used["id"])

    await admin.update_entry(used["id"], {"model": "deepseek-chat", "api_key": ""})
    await admin.update_entry(other["id"], {"model": "unused"})

    settings = (await admin.resolved()).settings
    assert (settings.model, settings.api_key) == ("deepseek-chat", "sk-deepseek-abcdefgh")


async def test_changing_the_settings_by_hand_detaches_them_from_the_list() -> None:
    admin = ModelAdmin(PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=KEY)
    entry = await admin.add_entry(DEEPSEEK)
    await admin.use_entry(entry["id"])

    await admin.update({"reasoning": "low"})

    assert (await admin.show())["entry_id"] is None
    assert (await admin.entries())["entries"][0]["active"] is False


async def test_removing_the_model_in_use_leaves_the_agent_its_settings_without_a_list_mark() -> None:
    admin = ModelAdmin(PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=KEY)
    entry = await admin.add_entry(DEEPSEEK)
    await admin.use_entry(entry["id"])

    await admin.delete_entry(entry["id"])

    shown = await admin.show()
    assert (shown["model"], shown["entry_id"]) == ("deepseek-v4-pro", None)
    assert (await admin.entries())["entries"] == []
    with pytest.raises(ModelEntryError) as gone:
        await admin.delete_entry(entry["id"])
    assert gone.value.code == "not_found"


async def test_a_model_of_the_list_is_tested_and_listed_with_its_own_key() -> None:
    catalog = Catalog()
    factory = Factory()
    admin = ModelAdmin(
        PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=KEY, factory=factory, lister=catalog
    )
    entry = await admin.add_entry(DEEPSEEK)

    tested = await admin.test_entry(entry["id"])
    listed = await admin.list_models({"api_key": ""}, entry_id=entry["id"])

    assert (tested["ok"], tested["model"]) == (True, "deepseek-v4-pro")
    assert factory.built[0].settings.api_key == "sk-deepseek-abcdefgh"
    assert listed["ok"] is True
    assert catalog.asked[0].api_key == "sk-deepseek-abcdefgh"
    assert (await admin.show())["model"] == "from-profile"


async def test_the_list_holds_a_limited_number_of_models() -> None:
    admin = ModelAdmin(PROFILE, InMemoryModelSettingsStore(), tenant_id="t", secret_key=KEY)
    for number in range(MAX_ENTRIES):
        await admin.add_entry({**DEEPSEEK, "label": f"m{number}", "api_key": None})

    with pytest.raises(ModelEntryError) as full:
        await admin.add_entry(DEEPSEEK)

    assert full.value.code == "list_full"


async def test_the_entry_routes_add_change_use_test_and_remove_a_model() -> None:
    async with _service() as client:
        added = await client.post("/v1/admin/model/entries", json=DEEPSEEK, headers=ADMIN)
        entry_id = added.json()["id"]
        patched = await client.patch(
            f"/v1/admin/model/entries/{entry_id}", json={"label": "Chính"}, headers=ADMIN
        )
        used = await client.post(f"/v1/admin/model/entries/{entry_id}/use", headers=ADMIN)
        tested = await client.post(f"/v1/admin/model/entries/{entry_id}/test", headers=ADMIN)
        listed = await client.get("/v1/admin/model/entries", headers=ADMIN)
        removed = await client.delete(f"/v1/admin/model/entries/{entry_id}", headers=ADMIN)
        missing = await client.post(f"/v1/admin/model/entries/{entry_id}/use", headers=ADMIN)
        malformed = await client.post("/v1/admin/model/entries/not-an-id/use", headers=ADMIN)

    assert added.status_code == 201
    assert "sk-deepseek-abcdefgh" not in added.text
    assert patched.json()["label"] == "Chính"
    assert (used.status_code, used.json()["model"], used.json()["entry_id"]) == (
        200,
        "deepseek-v4-pro",
        entry_id,
    )
    assert (tested.status_code, tested.json()["ok"]) == (200, True)
    assert [e["active"] for e in listed.json()["entries"]] == [True]
    assert removed.json() == {"deleted": entry_id}
    assert (missing.status_code, missing.json()["error"]["kind"]) == (404, "not_found")
    assert malformed.status_code == 422


async def test_the_entry_routes_refuse_a_bad_body_a_chat_token_and_a_key_without_the_encryption_key() -> None:
    async with _service() as client, _service(secret_key=None) as keyless:
        no_model = await client.post("/v1/admin/model/entries", json={"label": "x"}, headers=ADMIN)
        bad_url = await client.post(
            "/v1/admin/model/entries", json={**DEEPSEEK, "base_url": "ftp://x"}, headers=ADMIN
        )
        chat_token = await client.get("/v1/admin/model/entries", headers=CHAT)
        without_key = await keyless.post("/v1/admin/model/entries", json=DEEPSEEK, headers=ADMIN)

    assert (no_model.status_code, bad_url.status_code, chat_token.status_code) == (422, 422, 403)
    assert (without_key.status_code, without_key.json()["error"]["kind"]) == (409, "no_encryption_key")

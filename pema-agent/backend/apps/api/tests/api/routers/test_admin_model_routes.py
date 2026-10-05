# ported from: src/server/routes/tuning-routes.test.ts, vision-routes.test.ts (+ provider-routes, no original test)
"""The model routes (``/admin/model/provider|vision|tuning``) over an in-memory settings snapshot.

Forced differences: authentication is the session code of package B1 and is wired at mount time, so the
"not logged in -> 401" cases of the originals are not asserted here (the dependency ``provide_clinic_id`` is the
seam, replaced by a fixed clinic); a validation failure is 422 ``validation_failed`` (the original answered 400);
the contract DTOs differ from the original JSON (see the module docstring of ``admin_model``): ``TuningOut``
carries ``items`` with the definition and the value together, ``VisionSettingsOut`` has no ``imageMode`` and there
is no ``/vision/test`` route. Test names are the snake_case form of ``describe_it``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from pema.agent.streaming_model_test_helper import ScriptedModel, tra_loi
from pema.api import errors as api_errors
from pema.api.routers import admin_model
from pema.config.runtime_settings_store import RuntimeSettingsSnapshot
from pema.config.runtime_tuning_settings import get_tuning, install_tuning_provider
from pema.config.testing_settings import SettingsEnv
from pema_contracts.testing import FAKE_CLINIC_ID


class Harness:
    def __init__(self, env: SettingsEnv) -> None:
        self.env = env
        self.audit: list[tuple[str, list[str]]] = []
        app = FastAPI()
        api_errors.install_error_handlers(app)
        app.include_router(admin_model.router)

        async def clinic() -> Any:
            return FAKE_CLINIC_ID

        async def sink() -> Any:
            async def record(action: str, fields: Sequence[str]) -> None:
                self.audit.append((action, list(fields)))

            return record

        app.dependency_overrides[admin_model.provide_clinic_id] = clinic
        app.dependency_overrides[admin_model.provide_audit] = sink
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def stored(self) -> dict[str, str]:
        return await self.env.store.load_all(FAKE_CLINIC_ID)


@pytest.fixture
async def h(settings_env: SettingsEnv) -> AsyncIterator[Harness]:
    settings_env.monkeypatch.setenv("LLM_MAX_STEPS", "8")
    install_tuning_provider(settings_env.snapshot)
    harness = Harness(settings_env)
    yield harness
    await harness.client.aclose()


def item(body: dict[str, Any], key: str) -> dict[str, Any]:
    return next(i for i in body["items"] if i["key"] == key)


# ------------------------------------------------------------------------------------------------ provider


async def test_provider_get_returns_env_config_with_a_masked_key(h: Harness) -> None:
    """GET trả cấu hình env, key đã che"""
    h.env.set_env(LLM_PROVIDER="anthropic", LLM_MODEL="m", LLM_API_KEY="sk-env-key-123456")
    r = await h.client.get("/admin/model/provider")
    assert r.status_code == 200
    body = r.json()
    assert (body["provider"], body["model"], body["has_override"]) == ("anthropic", "m", False)
    assert body["api_key_masked"] == "sk-en...3456"
    assert "sk-env-key-123456" not in r.text


async def test_provider_patch_saves_masks_the_key_and_audits_field_names_only(h: Harness) -> None:
    """PATCH lưu, key trả về luôn che, audit chỉ ghi TÊN field"""
    r = await h.client.patch(
        "/admin/model/provider",
        json={
            "provider": "openai-compatible",
            "base_url": "https://r.test/v1",
            "model": "qwen3",
            "api_key": "sk-secret-xyz-1",
        },
    )
    assert r.status_code == 200
    assert "sk-secret-xyz-1" not in r.text
    assert r.json()["has_override"] is True
    assert "sk-secret-xyz-1" not in str(await h.stored())
    assert h.audit == [("llm_settings.update", ["provider", "base_url", "model", "api_key"])]
    assert "sk-secret-xyz-1" not in str(h.audit)


async def test_provider_patch_empty_fields_keep_what_is_stored(h: Harness) -> None:
    """ô rỗng nghĩa là chưa nhập, không xóa mất cấu hình đã lưu"""
    await h.client.patch(
        "/admin/model/provider",
        json={"base_url": "https://r.test/v1", "model": "m1", "api_key": "sk-keep-me-123"},
    )
    r = await h.client.patch("/admin/model/provider", json={"model": "", "api_key": ""})
    assert r.status_code == 200
    body = r.json()
    assert (body["base_url"], body["model"]) == ("https://r.test/v1", "m1")
    assert body["api_key_masked"] != "chưa cấu hình"


async def test_provider_patch_empty_base_url_clears_and_none_keeps(h: Harness) -> None:
    """base_url rỗng = xóa (về env), bỏ trống = giữ nguyên"""
    h.env.set_env(LLM_BASE_URL="https://env.test/v1")
    await h.client.patch("/admin/model/provider", json={"base_url": "https://router.test/v1"})
    await h.client.patch("/admin/model/provider", json={"model": "x"})
    assert (await h.client.get("/admin/model/provider")).json()["base_url"] == "https://router.test/v1"
    await h.client.patch("/admin/model/provider", json={"base_url": ""})
    assert (await h.client.get("/admin/model/provider")).json()["base_url"] == "https://env.test/v1"


async def test_provider_patch_rejects_a_base_url_that_is_not_http(h: Harness) -> None:
    """base URL không phải http bị chặn kèm câu chỉ đúng ô"""
    r = await h.client.patch("/admin/model/provider", json={"base_url": "ftp://sai"})
    assert r.status_code == 422
    assert "Base URL" in r.json()["error"]["message"]
    assert await h.stored() == {}


async def test_provider_delete_goes_back_to_env_config(h: Harness) -> None:
    """DELETE xóa override, quay về env"""
    h.env.set_env(LLM_MODEL="env-model")
    await h.client.patch("/admin/model/provider", json={"model": "db-model", "api_key": "sk-abcdefghijk"})
    r = await h.client.delete("/admin/model/provider")
    assert r.status_code == 200
    assert r.json()["model"] == "env-model"
    assert r.json()["has_override"] is False


async def test_provider_test_button_runs_one_minimal_completion(
    h: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """nút Test kết nối: một completion tối thiểu, đi đường streaming của bot"""
    model = ScriptedModel([lambda: tra_loi("ok  ")])

    def fake_resolve(_override: object) -> ScriptedModel:
        return model

    monkeypatch.setattr(admin_model, "resolve_language_model", fake_resolve)
    r = await h.client.post("/admin/model/provider/test")
    assert r.json() == {"ok": True, "reply": "ok", "error": None}
    assert model.calls[0].max_output_tokens == 200


async def test_provider_test_button_reports_missing_config_without_a_500(h: Harness) -> None:
    """chưa cấu hình thì báo ok=false kèm lý do, không 500"""
    r = await h.client.post("/admin/model/provider/test")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert "LoiCauHinhLlm" in body["error"]


# -------------------------------------------------------------------------------------------------- vision

SIDECAR = {
    "base_url": "https://gemini.test/v1beta/openai",
    "model": "gemini-3.5-flash-lite",
    "api_key": "AIza-secret-can-xoa",
}


async def test_vision_get_unconfigured(h: Harness) -> None:
    """GET khi chưa cấu hình sidecar"""
    r = await h.client.get("/admin/model/vision")
    body = r.json()
    assert body["provider"] is None
    assert body["enabled"] is True, "model chính có thể tự đọc ảnh (mode auto)"
    assert body["has_override"] is False


async def test_vision_patch_saves_the_sidecar_and_the_key_is_always_masked(h: Harness) -> None:
    """PATCH lưu sidecar; key trả về LUÔN masked, không lộ plaintext"""
    r = await h.client.patch("/admin/model/vision", json=SIDECAR)
    assert r.status_code == 200
    assert SIDECAR["api_key"] not in r.text, "response không được chứa key nguyên văn"
    body = r.json()
    assert (body["provider"], body["model"], body["has_override"]) == (
        "openai-compatible",
        SIDECAR["model"],
        True,
    )
    assert body["api_key_masked"] != SIDECAR["api_key"]
    assert SIDECAR["api_key"] not in str(await h.stored())
    assert h.audit[-1] == ("vision_settings.update", ["base_url", "model", "api_key"])


async def test_vision_patch_without_a_key_keeps_the_old_key(h: Harness) -> None:
    """PATCH bỏ trống key = GIỮ key cũ (vì thế mới cần nút xóa riêng)"""
    await h.client.patch("/admin/model/vision", json=SIDECAR)
    r = await h.client.patch("/admin/model/vision", json={"model": "gemini-3.1-flash-lite"})
    body = r.json()
    assert body["model"] == "gemini-3.1-flash-lite"
    assert body["provider"] == "openai-compatible", "key vẫn còn nên vẫn đủ cấu hình"


async def test_vision_patch_rejects_wrong_data(h: Harness) -> None:
    """PATCH chặn dữ liệu sai (base URL không phải http, provider không phải OpenAI-compatible)"""
    assert (await h.client.patch("/admin/model/vision", json={"base_url": "ftp://sai"})).status_code == 422
    assert (await h.client.patch("/admin/model/vision", json={"provider": "anthropic"})).status_code == 422


async def test_vision_disabled_with_a_sidecar_still_reads_images_through_it(h: Harness) -> None:
    """enabled=false đặt mode off; có sidecar thì ảnh vẫn đọc được qua sidecar"""
    await h.client.patch("/admin/model/vision", json=SIDECAR)
    body = (await h.client.patch("/admin/model/vision", json={"enabled": False})).json()
    assert body["enabled"] is True
    await h.client.delete("/admin/model/vision/sidecar")
    body = (await h.client.get("/admin/model/vision")).json()
    assert body["enabled"] is False, "mode off và không còn sidecar -> bot bỏ ảnh và nói thật"


async def test_vision_delete_sidecar_wipes_everything_including_the_key(h: Harness) -> None:
    """DELETE /sidecar xóa SẠCH cả key - sidecar tắt"""
    await h.client.patch("/admin/model/vision", json=SIDECAR)
    r = await h.client.delete("/admin/model/vision/sidecar")
    assert r.status_code == 204
    body = (await h.client.get("/admin/model/vision")).json()
    assert (body["base_url"], body["model"], body["provider"]) == ("", "", None)
    stored = await h.stored()
    assert not [k for k in stored if k.startswith("vision_sidecar")], (
        "key phải bị gỡ khỏi DB, không chỉ ẩn đi"
    )


# -------------------------------------------------------------------------------------------------- tuning


async def test_tuning_get_returns_the_definition_and_the_value_together(h: Harness) -> None:
    """trả cả định nghĩa lẫn giá trị - web không phải chép lại danh mục"""
    body = (await h.client.get("/admin/model/tuning")).json()
    assert len(body["groups"]) > 0
    assert len(body["items"]) == 72
    steps = item(body, "LLM_MAX_STEPS")
    assert steps["label"]
    assert (steps["value"], steps["default"], steps["overridden"]) == (8, 8, False)
    assert (steps["min"], steps["max"], steps["kind"]) == (1, 30, "number")
    assert item(body, "LLM_REASONING_EFFORT")["kind"] == "select"
    assert item(body, "BOT_TIMEZONE")["kind"] == "text"
    assert item(body, "LLM_MAX_OUTPUT_TOKENS")["presets"] == [4096, 8192, 16384, 32000, 64000, 128000]


async def test_tuning_get_every_item_belongs_to_a_real_group(h: Harness) -> None:
    """mỗi tham số phải thuộc một nhóm CÓ THẬT, không thì nó không hiện trên web"""
    body = (await h.client.get("/admin/model/tuning")).json()
    ids = {g["id"] for g in body["groups"]}
    for i in body["items"]:
        assert i["group"] in ids, f'{i["key"]} thuộc nhóm "{i["group"]}" không tồn tại'


async def test_tuning_get_every_group_has_a_short_nav_hint(h: Harness) -> None:
    """mỗi nhóm phải có nav_hint - thiếu thì mục đó trống chữ ở danh mục bên trái

    The nav is a narrow cell: a long sentence is cut mid-way, the very bug fixed once already.
    """
    body = (await h.client.get("/admin/model/tuning")).json()
    for g in body["groups"]:
        assert g["nav_hint"].strip(), f'nhóm "{g["id"]}" thiếu nav_hint'
        assert len(g["nav_hint"]) <= 40, f'nav_hint của "{g["id"]}" dài {len(g["nav_hint"])} ký tự, sẽ bị cắt'


async def patch_tuning(h: Harness, values: dict[str, Any]) -> httpx.Response:
    return await h.client.patch("/admin/model/tuning", json={"values": values})


async def test_tuning_patch_saves_then_reads_the_new_value_and_marks_it_overridden(h: Harness) -> None:
    """lưu rồi đọc lại thấy giá trị mới và overridden = true"""
    r = await patch_tuning(h, {"LLM_MAX_STEPS": 12})
    assert r.status_code == 200
    steps = item(r.json(), "LLM_MAX_STEPS")
    assert (steps["value"], steps["overridden"]) == (12, True)
    assert get_tuning("LLM_MAX_STEPS") == 12
    assert h.audit[-1] == ("tuning.update", ["LLM_MAX_STEPS"])


async def test_tuning_patch_null_goes_back_to_the_env_value(h: Harness) -> None:
    """null = trả về giá trị trong .env"""
    await patch_tuning(h, {"LLM_MAX_STEPS": 12})
    steps = item((await patch_tuning(h, {"LLM_MAX_STEPS": None})).json(), "LLM_MAX_STEPS")
    assert (steps["value"], steps["overridden"]) == (8, False)


async def test_tuning_patch_unknown_key_is_refused_and_nothing_is_written(h: Harness) -> None:
    """key bịa bị chặn - nếu không sẽ thành rác vĩnh viễn trong runtime_settings"""
    r = await patch_tuning(h, {"KHONG_CO_THAM_SO_NAY": 1})
    assert r.status_code == 422
    assert await h.stored() == {}, "không được ghi gì khi dữ liệu sai"


async def test_tuning_patch_out_of_range_number_is_refused_with_the_range(h: Harness) -> None:
    """số ngoài khoảng cho phép bị chặn kèm câu nói rõ khoảng"""
    r = await patch_tuning(h, {"LLM_MAX_STEPS": 999})
    assert r.status_code == 422
    assert "1 - 30" in r.json()["error"]["message"]


async def test_tuning_patch_wrong_type_is_refused(h: Harness) -> None:
    """sai kiểu bị chặn"""
    assert (await patch_tuning(h, {"LLM_MAX_STEPS": "tam"})).status_code == 422
    assert (await patch_tuning(h, {"AGENT_TRACE_ENABLED": 5})).status_code == 422
    assert (await patch_tuning(h, {"LLM_REASONING_EFFORT": "sieu-cao"})).status_code == 422


async def test_tuning_patch_cross_rule_is_refused_with_a_readable_reason(h: Harness) -> None:
    """ràng buộc chéo bị chặn kèm lý do đọc được"""
    r = await patch_tuning(h, {"LLM_TURN_TIMEOUT_MS": 120_000, "IMAGE_GEN_TIMEOUT_MS": 600_000})
    assert r.status_code == 422
    assert "lớn hơn trần thời gian mỗi ảnh" in r.json()["error"]["message"]


async def test_tuning_patch_one_wrong_field_means_no_field_is_written(h: Harness) -> None:
    """một ô sai thì KHÔNG ô nào được ghi - tránh lưu nửa vời"""
    await patch_tuning(h, {"LLM_MAX_STEPS": 12, "WEB_FETCH_MAX_CHARS": 99_999_999})
    assert await h.stored() == {}


async def test_tuning_reset_all_removes_every_override(h: Harness) -> None:
    """đặt lại TẤT CẢ: xoá sạch phần đè, mọi ô về lại .env"""
    await patch_tuning(h, {"LLM_MAX_STEPS": 12, "WEB_SEARCH_MAX_RESULTS": 9})
    r = await patch_tuning(h, {"LLM_MAX_STEPS": None, "WEB_SEARCH_MAX_RESULTS": None})
    assert r.status_code == 200
    assert item(r.json(), "LLM_MAX_STEPS")["overridden"] is False
    assert item(r.json(), "WEB_SEARCH_MAX_RESULTS")["overridden"] is False

    await patch_tuning(h, {"LLM_MAX_STEPS": 12})
    assert (await h.client.delete("/admin/model/tuning")).status_code == 204
    assert get_tuning("LLM_MAX_STEPS") == 8


async def test_tuning_reset_does_not_touch_other_settings_keys(h: Harness, settings_env: SettingsEnv) -> None:
    """đặt lại KHÔNG đụng tới khoá khác (LLM, vision): chỉ xóa các khoá tuning_*

    The original proved the dashboard password (a separate key) survives "reset all configuration". The same
    guarantee here: only ``tuning_*`` rows are removed.
    """
    await h.client.patch("/admin/model/provider", json={"model": "keep-me"})
    await patch_tuning(h, {"LLM_MAX_STEPS": 12})
    await h.client.delete("/admin/model/tuning")
    assert (await h.stored()) == {"llm_model": "keep-me"}
    assert isinstance(settings_env.snapshot, RuntimeSettingsSnapshot)


async def test_bot_timezone_accepts_a_valid_iana_name(h: Harness) -> None:
    """nhận tên timezone IANA hợp lệ"""
    r = await patch_tuning(h, {"BOT_TIMEZONE": "Europe/Paris"})
    assert r.status_code == 200
    assert item(r.json(), "BOT_TIMEZONE")["value"] == "Europe/Paris"


async def test_bot_timezone_invented_zone_is_refused_at_the_route(h: Harness) -> None:
    """tên zone bịa bị chặn ở route - lọt vào DB thì lịch hẹn lệch giờ không báo gì"""
    r = await patch_tuning(h, {"BOT_TIMEZONE": "Asia/Khong_Co_That"})
    assert r.status_code == 422
    assert "timezone" in r.json()["error"]["message"].lower()


async def test_bot_timezone_a_broken_zone_already_in_the_db_falls_back_to_the_env_value(h: Harness) -> None:
    """zone hỏng SẴN trong DB vẫn không làm lệch giờ - get_tuning tự rơi về giá trị mặc định

    The route blocks it, but the DB can still be broken another way (hand edit, an older version that wrote
    before the check existed): this is the second safety net.
    """
    await h.env.snapshot.set(FAKE_CLINIC_ID, "tuning_BOT_TIMEZONE", "Sao/Hoa")
    assert get_tuning("BOT_TIMEZONE") == "Asia/Ho_Chi_Minh"

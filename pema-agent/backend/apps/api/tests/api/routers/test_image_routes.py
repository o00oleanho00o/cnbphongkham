# ported from: src/server/routes/image-routes.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

API ``/admin/tools/image-gen``: the endpoint settings of the ``create_image`` tool.

Forced deviations: the dashboard password login of the original is the session cookie of package B1 (the 401 case
belongs to B1's auth dependency and is not repeated here); ``400`` is ``422 validation_failed``; ``DELETE`` answers
``204`` as the OpenAPI skeleton says; ``POST /test`` (draws a real picture) is not served: see ``admin_tools``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from pema.agent.tools.testing import make_tool_deps, personal_capabilities
from pema.agent.tools.tool_registry import DefaultToolRegistry
from pema.api.routers.admin_tools import ToolsAdminServices, get_tools_admin_services
from pema.bootstrap import create_app
from pema.config.runtime_settings_kv import reset_runtime_settings_kv
from pema_contracts.channel import ChannelCapabilities, ChannelKind
from pema_contracts.common import JsonObject
from pema_contracts.testing import FAKE_CLINIC_ID, InMemoryAccountStore, InMemoryAgentStore

FULL: JsonObject = {
    "base_url": "https://router.test",
    "model": "cx/gpt-5.5-image",
    "api_key": "sk-bi-mat-can-xoa",
}


class _Channels:
    def capabilities_for(self, kind: ChannelKind) -> ChannelCapabilities:
        return personal_capabilities()


@pytest.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[httpx.AsyncClient]:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "00" * 32)
    monkeypatch.setenv("IMAGE_GEN_BASE_URL", "")
    monkeypatch.setenv("IMAGE_GEN_MODEL", "")
    monkeypatch.setenv("IMAGE_GEN_API_KEY", "")
    reset_runtime_settings_kv()
    services = ToolsAdminServices(
        registry=DefaultToolRegistry(make_tool_deps()),
        accounts=InMemoryAccountStore(),
        agents=InMemoryAgentStore(),
        channels=_Channels(),
        clinic_id=lambda: FAKE_CLINIC_ID,
    )
    app = create_app()
    app.dependency_overrides[get_tools_admin_services] = lambda: services
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c
    reset_runtime_settings_kv()


async def _get(client: httpx.AsyncClient) -> JsonObject:
    return (await client.get("/api/v1/admin/tools/image-gen")).json()


async def test_image_gen_initially_nothing_is_configured(client: httpx.AsyncClient) -> None:
    """lúc đầu chưa cấu hình gì"""
    view = await _get(client)
    assert view["enabled"] is False
    assert view["api_key_masked"] != "" or view["has_override"] is False
    assert view["has_override"] is False


async def test_image_gen_patch_all_three_fields_is_configured_and_the_key_is_masked(
    client: httpx.AsyncClient,
) -> None:
    """PATCH đủ 3 field -> configured, key bị mask"""
    res = await client.patch("/api/v1/admin/tools/image-gen", json=FULL)
    assert res.status_code == 200

    view = await _get(client)
    assert view["base_url"] == "https://router.test"
    assert view["model"] == "cx/gpt-5.5-image"
    assert view["enabled"] is True
    assert view["has_override"] is True
    assert view["api_key_masked"] != FULL["api_key"]


async def test_image_gen_the_api_never_returns_the_key_in_plaintext(client: httpx.AsyncClient) -> None:
    """API KHÔNG BAO GIỜ trả key plaintext"""
    patched = await client.patch("/api/v1/admin/tools/image-gen", json=FULL)
    raw = (await client.get("/api/v1/admin/tools/image-gen")).text
    assert str(FULL["api_key"]) not in raw, "key thật lọt ra response là lỗi bảo mật"
    assert str(FULL["api_key"]) not in patched.text


async def test_image_gen_patch_without_an_api_key_keeps_the_old_key(client: httpx.AsyncClient) -> None:
    """PATCH không kèm apiKey thì GIỮ key cũ"""
    await client.patch("/api/v1/admin/tools/image-gen", json=FULL)
    await client.patch("/api/v1/admin/tools/image-gen", json={"model": "cx/gpt-5.3-image"})
    view = await _get(client)
    assert view["model"] == "cx/gpt-5.3-image"
    assert view["enabled"] is True, "đổi mỗi model mà mất key là bẫy người dùng"


async def test_image_gen_a_base_url_that_is_not_http_is_refused(client: httpx.AsyncClient) -> None:
    """base URL không phải http -> lỗi 422 (gốc: 400)"""
    res = await client.patch("/api/v1/admin/tools/image-gen", json={"base_url": "ftp://sai.test"})
    assert res.status_code == 422


async def test_image_gen_delete_wipes_everything_including_the_key(client: httpx.AsyncClient) -> None:
    """DELETE xóa sạch cả key - đường duy nhất gỡ key vì PATCH quy ước giữ key cũ"""
    await client.patch("/api/v1/admin/tools/image-gen", json=FULL)
    res = await client.delete("/api/v1/admin/tools/image-gen")
    assert res.status_code == 204

    view = await _get(client)
    assert view["has_override"] is False
    assert view["base_url"] == ""
    assert view["model"] == ""
    assert view["enabled"] is False

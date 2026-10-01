# ported from: src/agent/model-vision-detection.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Settings: a fresh in-memory ``RuntimeSettingsSnapshot`` is installed per test and bound to a synthetic clinic
(see ``runtime_settings_store``); the LLM key goes through the real cipher with a synthetic encryption key.
Python additions: the real ``/models`` call through ``http.MockTransport``, and the TTL of the cache.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest

from pema.agent import model_vision_detection as detection
from pema.agent.llm_provider import ModelOverride
from pema.agent.model_vision_detection import (
    classify_model_vision,
    clear_vision_detection_cache,
    make_models_fetcher,
    mark_model_no_vision,
    model_reads_images,
    parse_models_capabilities,
)
from pema.agent.providers.http_flavour import http
from pema.config import env as env_module
from pema.config.runtime_llm_settings import LlmSettingsUpdate, update_llm_settings
from pema.config.runtime_settings_store import (
    InMemoryRuntimeSettingsStore,
    RuntimeSettingsSnapshot,
    get_runtime_settings,
    install_runtime_settings,
    use_settings_clinic,
)
from pema.config.runtime_vision_settings import VisionSettingsUpdate, update_vision_settings
from pema_contracts.agents import LlmProviderKind
from pema_contracts.testing import FAKE_CLINIC_ID

ROUTER_URL = "http://router.test/v1"


@pytest.fixture(autouse=True)
def settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[RuntimeSettingsSnapshot]:
    """Mỗi test bắt đầu từ cấu hình router (openai-compatible) + vision mode auto.

    Không có dòng này thì test nào đổi provider sẽ rò trạng thái sang test sau - đã dính thật.
    """
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "a" * 64)
    env_module.get_settings.cache_clear()
    previous = get_runtime_settings()
    snapshot = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())
    install_runtime_settings(snapshot)
    clear_vision_detection_cache()
    with use_settings_clinic(FAKE_CLINIC_ID):
        yield snapshot
    clear_vision_detection_cache()
    install_runtime_settings(previous)
    env_module.get_settings.cache_clear()


async def configure_llm(
    snapshot: RuntimeSettingsSnapshot,
    *,
    provider: LlmProviderKind = LlmProviderKind.OPENAI_COMPATIBLE,
    model: str = "cx/gpt-5.6-sol",
    base_url: str | None = ROUTER_URL,
) -> None:
    await update_llm_settings(
        FAKE_CLINIC_ID,
        LlmSettingsUpdate(provider=provider, model=model, base_url=base_url, api_key="sk-synthetic-router"),
        snapshot=snapshot,
    )
    await update_vision_settings(FAKE_CLINIC_ID, VisionSettingsUpdate(mode="auto"), snapshot=snapshot)


@pytest.fixture(autouse=True)
async def router_config(settings: RuntimeSettingsSnapshot) -> None:
    await configure_llm(settings)


# Response /models đúng dạng đo được trên 9Router thật (2026-07-26)
router_payload: dict[str, Any] = {
    "data": [
        {"id": "cx/gpt-5.6-sol", "owned_by": "cx", "capabilities": {"vision": True}},
        {"id": "ds/deepseek-v4-pro", "owned_by": "ds", "capabilities": {"vision": False}},
        {"id": "my-combo", "object": "model", "owned_by": "combo"},
    ]
}


async def router_fetcher(_url: str, _api_key: str) -> object:
    return router_payload


class CountingFetcher:
    def __init__(self, payload: object | None = None, *, fail: bool = False) -> None:
        self.calls = 0
        self._payload = router_payload if payload is None else payload
        self._fail = fail

    async def __call__(self, _url: str, _api_key: str) -> object:
        self.calls += 1
        if self._fail:
            raise RuntimeError("router down")
        return self._payload


# --- parseModelsCapabilities -----------------------------------------------------------------------------


def test_parse_models_capabilities_boc_map_vision_nhan_dien_combo_qua_owned_by() -> None:
    """bóc map vision + nhận diện combo qua owned_by"""
    caps = parse_models_capabilities(router_payload)
    assert caps.vision_by_model["cx/gpt-5.6-sol"] is True
    assert caps.vision_by_model["ds/deepseek-v4-pro"] is False
    assert "my-combo" not in caps.vision_by_model
    assert list(caps.combo_ids) == ["my-combo"]


def test_parse_models_capabilities_payload_rac_khong_throw_tra_ket_qua_rong() -> None:
    """payload rác không throw, trả kết quả rỗng"""
    assert len(parse_models_capabilities(None).vision_by_model) == 0
    assert len(parse_models_capabilities({"data": "x"}).combo_ids) == 0


# --- classifyModelVision ---------------------------------------------------------------------------------


async def test_classify_model_vision_mode_on_off_ep_tay_khong_goi_models(
    settings: RuntimeSettingsSnapshot,
) -> None:
    """mode on/off ép tay, không gọi /models"""
    fetcher = CountingFetcher()
    await update_vision_settings(FAKE_CLINIC_ID, VisionSettingsUpdate(mode="on"), snapshot=settings)
    assert await classify_model_vision(None, fetcher) == "vision"
    await update_vision_settings(FAKE_CLINIC_ID, VisionSettingsUpdate(mode="off"), snapshot=settings)
    assert await classify_model_vision(None, fetcher) == "no-vision"
    assert fetcher.calls == 0


async def test_classify_model_vision_auto_vision_theo_router_combo_rieng_model_la_unknown() -> None:
    """auto: vision=true/false theo router, combo nhận diện riêng, model lạ = unknown"""
    assert await classify_model_vision(None, router_fetcher) == "vision"
    assert (
        await classify_model_vision(ModelOverride(model_name="ds/deepseek-v4-pro"), router_fetcher)
        == "no-vision"
    )
    assert await classify_model_vision(ModelOverride(model_name="my-combo"), router_fetcher) == "combo"
    assert (
        await classify_model_vision(ModelOverride(model_name="model-la-hoac-moi"), router_fetcher)
        == "unknown"
    )


async def test_classify_model_vision_auto_models_loi_thi_unknown_va_co_cache_khong_dap_router() -> None:
    """auto: /models lỗi thì unknown và có cache (không đập router)"""
    fetcher = CountingFetcher(fail=True)
    assert await classify_model_vision(None, fetcher) == "unknown"
    assert await classify_model_vision(None, fetcher) == "unknown"
    assert fetcher.calls == 1, "kết quả lỗi cũng phải được cache"


async def test_classify_model_vision_cache_dung_chung_theo_base_url_nhieu_model_chi_goi_models_1_lan() -> (
    None
):
    """cache dùng chung theo baseUrl: nhiều model chỉ gọi /models 1 lần"""
    fetcher = CountingFetcher()
    await classify_model_vision(None, fetcher)
    await classify_model_vision(ModelOverride(model_name="ds/deepseek-v4-pro"), fetcher)
    await classify_model_vision(ModelOverride(model_name="my-combo"), fetcher)
    assert fetcher.calls == 1


async def test_classify_model_vision_provider_anthropic_luon_vision_khong_goi_models(
    settings: RuntimeSettingsSnapshot,
) -> None:
    """provider anthropic luôn vision, không gọi /models

    Anthropic phải là provider ĐANG HIỆU LỰC. Khai qua override trong khi cấu hình chung là router thì override
    bị bỏ qua (chống rò khóa API), nên đây đặt thẳng vào cấu hình chung.
    """
    fetcher = CountingFetcher()
    await configure_llm(settings, provider=LlmProviderKind.ANTHROPIC, model="claude-opus-5", base_url=None)
    assert await classify_model_vision(None, fetcher) == "vision"
    assert fetcher.calls == 0


async def test_classify_model_vision_model_reads_images_chi_no_vision_moi_la_false() -> None:
    """modelReadsImages: chỉ no-vision mới là false"""
    assert await model_reads_images(ModelOverride(model_name="my-combo"), router_fetcher) is True
    assert await model_reads_images(ModelOverride(model_name="ds/deepseek-v4-pro"), router_fetcher) is False


async def test_classify_model_vision_real_models_call_goes_through_the_injected_http_client() -> None:
    """(Python) the default fetcher: GET {base_url}/models with a bearer key, over an injected client"""
    seen: dict[str, Any] = {}

    def handler(request: Any) -> Any:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["authorization"]
        return http.Response(200, content=json.dumps(router_payload).encode())

    client = http.AsyncClient(transport=http.MockTransport(handler))
    kind = await classify_model_vision(
        ModelOverride(model_name="ds/deepseek-v4-pro"), make_models_fetcher(client)
    )
    await client.aclose()
    assert kind == "no-vision"
    assert seen["url"] == f"{ROUTER_URL}/models"
    assert seen["auth"] == "Bearer sk-synthetic-router"


async def test_classify_model_vision_http_error_from_models_counts_as_unknown() -> None:
    """(Python) HTTP 500 from /models -> unknown (and cached)"""
    calls: list[int] = []

    def handler(_request: Any) -> Any:
        calls.append(1)
        return http.Response(500, content=b"boom")

    client = http.AsyncClient(transport=http.MockTransport(handler))
    fetcher = make_models_fetcher(client)
    assert await classify_model_vision(None, fetcher) == "unknown"
    assert await classify_model_vision(None, fetcher) == "unknown"
    await client.aclose()
    assert len(calls) == 1


async def test_classify_model_vision_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """(Python) the /models lookup is cached 10 minutes, then asked again"""
    clock = {"now": 1000.0}
    monkeypatch.setattr(detection, "_now", lambda: clock["now"])
    fetcher = CountingFetcher()
    await classify_model_vision(None, fetcher)
    clock["now"] += detection.CACHE_TTL_S - 1
    await classify_model_vision(None, fetcher)
    assert fetcher.calls == 1
    clock["now"] += 2
    await classify_model_vision(None, fetcher)
    assert fetcher.calls == 2


async def test_classify_model_vision_no_base_url_or_key_is_unknown(settings: RuntimeSettingsSnapshot) -> None:
    """(Python) without a base URL the router cannot be asked"""
    await configure_llm(settings, base_url=None)
    fetcher = CountingFetcher()
    assert await classify_model_vision(None, fetcher) == "unknown"
    assert fetcher.calls == 0


# --- markModelNoVision - cache âm của reactive fallback --------------------------------------------------


async def test_mark_model_no_vision_model_bi_danh_dau_thi_no_vision_thang_ca_models_lac_quan() -> None:
    """model bị đánh dấu thì classify ra no-vision, THẮNG cả kết quả /models lạc quan"""
    # Router bảo unknown (model lạ) -> bình thường là unknown
    assert await classify_model_vision(ModelOverride(model_name="model-cau-am"), router_fetcher) == "unknown"
    # Provider từ chối ảnh thật -> đánh dấu
    mark_model_no_vision(ModelOverride(model_name="model-cau-am"))
    assert (
        await classify_model_vision(ModelOverride(model_name="model-cau-am"), router_fetcher) == "no-vision"
    )
    # Model khác không bị vạ lây
    assert await classify_model_vision(None, router_fetcher) == "vision"


async def test_mark_model_no_vision_duong_anthropic_khong_bao_gio_bi_danh_dau(
    settings: RuntimeSettingsSnapshot,
) -> None:
    """đường anthropic không bao giờ bị đánh dấu (mọi model Claude đều có vision)

    Anthropic phải là provider ĐANG HIỆU LỰC, không chỉ là thứ agent khai: agent khai provider lệch cấu hình
    chung thì override bị bỏ qua lúc dựng client (chống rò khóa API), nên lượt thật vẫn chạy trên provider chung.
    """
    await configure_llm(settings, provider=LlmProviderKind.ANTHROPIC, model="claude-opus-5", base_url=None)
    mark_model_no_vision(ModelOverride(model_name="claude-opus-5"))
    assert await classify_model_vision(ModelOverride(model_name="claude-opus-5"), router_fetcher) == "vision"


async def test_mark_model_no_vision_agent_khai_anthropic_nhung_cau_hinh_chung_la_router_theo_model_that(
    settings: RuntimeSettingsSnapshot,
) -> None:
    """agent KHAI anthropic nhưng cấu hình chung là router: phân loại theo model THẬT, không theo lời khai

    Bất biến đi kèm chốt chặn rò khóa API (`doiProviderAnToan`). Đọc override thô thì đường tắt
    `provider === "anthropic"` trả "vision" ngay, bot đính pixel vì tưởng đang chạy Claude, trong khi lượt thật
    đi tới model router có thể mù ảnh.

    Đặt model chung thành model router KHÔNG có vision để tách bạch hai khả năng: honour lời khai -> "vision";
    phân loại theo model thật -> "no-vision".
    """
    await configure_llm(settings, model="ds/deepseek-v4-pro")
    kq = await classify_model_vision(
        ModelOverride(model_provider=LlmProviderKind.ANTHROPIC, model_name="claude-opus-5"), router_fetcher
    )
    assert kq == "no-vision", "override provider lệch không được cấp đường tắt vision"


async def test_mark_model_no_vision_clear_vision_detection_cache_xoa_ca_cache_am() -> None:
    """clearVisionDetectionCache xóa cả cache âm"""
    mark_model_no_vision(ModelOverride(model_name="model-tam-mu"))
    clear_vision_detection_cache()
    assert await classify_model_vision(ModelOverride(model_name="model-tam-mu"), router_fetcher) == "unknown"


async def test_mark_model_no_vision_negative_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    """(Python) the negative cache lives 10 minutes"""
    clock = {"now": 5.0}
    monkeypatch.setattr(detection, "_now", lambda: clock["now"])
    mark_model_no_vision(ModelOverride(model_name="model-het-han"))
    assert (
        await classify_model_vision(ModelOverride(model_name="model-het-han"), router_fetcher) == "no-vision"
    )
    clock["now"] += detection.CACHE_TTL_S + 1
    assert await classify_model_vision(ModelOverride(model_name="model-het-han"), router_fetcher) == "unknown"


# --- Gemini đọc ảnh được, và `/models` là API riêng của 9Router ------------------------------------------
# Gọi thẳng Google thì không có endpoint đó. Đã dính thật 06/08/2026: lượt Gemini chết vì thiếu
# `thought_signature` (chẳng liên quan gì tới ảnh) nhưng `isImageRejectionError` khớp MỌI 4xx và lịch sử thread
# có ảnh cũ, nên bot ghi nhớ "model mù" rồi bỏ pixel suốt 10 phút sau đó.


async def test_classify_model_vision_provider_google_luon_vision_va_khong_goi_models(
    settings: RuntimeSettingsSnapshot,
) -> None:
    """luôn vision và KHÔNG gọi /models - endpoint đó là của router, không phải của Google"""
    fetcher = CountingFetcher()
    await configure_llm(
        settings, provider=LlmProviderKind.GOOGLE, model="gemini-3.5-flash-lite", base_url=None
    )
    assert await classify_model_vision(None, fetcher) == "vision"
    assert fetcher.calls == 0


async def test_classify_model_vision_provider_google_mot_loi_4xx_khong_lam_gemini_bi_ghi_la_mu(
    settings: RuntimeSettingsSnapshot,
) -> None:
    """một lỗi 4xx KHÔNG làm Gemini bị ghi là mù"""
    await configure_llm(
        settings, provider=LlmProviderKind.GOOGLE, model="gemini-3.5-flash-lite", base_url=None
    )
    mark_model_no_vision(ModelOverride(model_name="gemini-3.5-flash-lite"))
    assert await classify_model_vision(None, router_fetcher) == "vision", (
        "ghi nhầm là bot bỏ pixel suốt 10 phút dù model đọc ảnh được"
    )

# ported from: src/agent/vision-sidecar.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Not translated: ``pruneExpiredImageDescriptions xóa mô tả cũ, GIỮ mô tả mới`` tests the description STORE
(``image-description-store``), which is package D2's (``ImageDescriptionStore``); its retention test belongs there.
The description cache is ``FakeConversation`` here.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.agent import vision_sidecar as sidecar
from pema.agent.history_to_model_messages import StoredImage
from pema.agent.testing_conversation import FakeConversation
from pema.agent.vision_sidecar import SidecarImage, SidecarResult
from pema.config import env as env_module
from pema.config.env_llm import get_llm_env
from pema.config.runtime_settings_store import (
    InMemoryRuntimeSettingsStore,
    RuntimeSettingsSnapshot,
    install_runtime_settings,
    use_settings_clinic,
)
from pema.config.runtime_vision_settings import VisionSettingsUpdate, update_vision_settings
from pema_contracts.testing import FAKE_CLINIC_ID

IMG = SidecarImage(base64="abc", media_type="image/jpeg")


class Env:
    def __init__(self) -> None:
        self.store = FakeConversation()
        self.snapshot = RuntimeSettingsSnapshot(InMemoryRuntimeSettingsStore())

    async def configure(self) -> None:
        await update_vision_settings(
            FAKE_CLINIC_ID,
            VisionSettingsUpdate(
                sidecar_base_url="https://gemini.test/v1beta/openai",
                sidecar_model="gemini-3.5-flash-lite",
                sidecar_api_key="AIza-test",
            ),
            snapshot=self.snapshot,
        )

    async def unconfigure(self) -> None:
        await update_vision_settings(
            FAKE_CLINIC_ID,
            VisionSettingsUpdate(sidecar_base_url="", sidecar_model="", sidecar_api_key=""),
            snapshot=self.snapshot,
        )

    def with_key(self, cache_key: str) -> SidecarImage:
        return SidecarImage(IMG.base64, IMG.media_type, cache_key)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Env]:
    for name in ("VISION_SIDECAR_BASE_URL", "VISION_SIDECAR_MODEL", "VISION_SIDECAR_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "a" * 64)
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()
    e = Env()
    install_runtime_settings(e.snapshot)
    with use_settings_clinic(FAKE_CLINIC_ID):
        yield e
    env_module.get_settings.cache_clear()
    get_llm_env.cache_clear()


async def test_vision_sidecar_chua_cau_hinh_sidecar_tra_none_khong_goi_model(env: Env) -> None:
    """chưa cấu hình sidecar: trả null, KHÔNG gọi model"""
    await env.unconfigure()
    calls = 0

    async def call(*_a: object) -> SidecarResult:
        nonlocal calls
        calls += 1
        return SidecarResult("mô tả", False)

    result = await sidecar.describe_image(
        env.with_key("media/a/t/x-0.jpg"), call, clinic_id=FAKE_CLINIC_ID, store=env.store
    )
    assert result is None
    assert calls == 0


async def test_vision_sidecar_mo_ta_thanh_cong_thi_luu_cache_lan_2_doc_cache_khong_goi_lai(env: Env) -> None:
    """mô tả thành công thì lưu cache; lần 2 đọc cache không gọi lại"""
    await env.configure()
    calls = 0

    async def call(*_a: object) -> SidecarResult:
        nonlocal calls
        calls += 1
        return SidecarResult("vé số Đà Lạt 123456", False)

    first = await sidecar.describe_image(
        env.with_key("media/a/t/ve-0.jpg"), call, clinic_id=FAKE_CLINIC_ID, store=env.store
    )
    assert first == "vé số Đà Lạt 123456"
    assert env.store.descriptions["media/a/t/ve-0.jpg"] == "vé số Đà Lạt 123456"

    second = await sidecar.describe_image(
        env.with_key("media/a/t/ve-0.jpg"), call, clinic_id=FAKE_CLINIC_ID, store=env.store
    )
    assert second == "vé số Đà Lạt 123456"
    assert calls == 1, "lần 2 phải trúng cache"


async def test_vision_sidecar_khong_co_cache_key_van_mo_ta_duoc_khong_ghi_cache(env: Env) -> None:
    """không có cacheKey (ảnh chưa persist) vẫn mô tả được, không ghi cache"""
    await env.configure()

    async def call(*_a: object) -> SidecarResult:
        return SidecarResult("ảnh chụp hóa đơn", False)

    result = await sidecar.describe_image(IMG, call, clinic_id=FAKE_CLINIC_ID, store=env.store)
    assert result == "ảnh chụp hóa đơn"
    assert env.store.descriptions == {}


async def test_vision_sidecar_sidecar_nem_loi_het_quota_chet_mang_tra_none_khong_throw(env: Env) -> None:
    """sidecar ném lỗi (hết quota, chết mạng): trả null, không throw"""
    await env.configure()

    async def call(*_a: object) -> SidecarResult:
        raise RuntimeError("429 quota exceeded")

    result = await sidecar.describe_image(
        env.with_key("media/a/t/err-0.jpg"), call, clinic_id=FAKE_CLINIC_ID, store=env.store
    )
    assert result is None
    assert "media/a/t/err-0.jpg" not in env.store.descriptions


async def test_vision_sidecar_ensure_descriptions_for_bo_qua_anh_da_co_mo_ta_va_anh_mat_file(
    env: Env,
) -> None:
    """ensureDescriptionsFor: bỏ qua ảnh đã có mô tả + ảnh mất file, mô tả phần còn lại"""
    await env.configure()
    env.store.descriptions["media/a/t/cached.jpg"] = "đã có sẵn"
    described: list[str] = []

    async def call(*_a: object) -> SidecarResult:
        described.append("call")
        return SidecarResult("mô tả mới", False)

    def load(rel_path: str) -> StoredImage | None:
        return None if rel_path == "media/a/t/mat-file.jpg" else StoredImage(IMG.base64, IMG.media_type)

    await sidecar.ensure_descriptions_for(
        ["media/a/t/cached.jpg", "media/a/t/moi.jpg", "media/a/t/mat-file.jpg"],
        load,
        call,
        clinic_id=FAKE_CLINIC_ID,
        store=env.store,
    )
    assert len(described) == 1, "chỉ ảnh chưa có mô tả + còn file mới được gọi"
    assert env.store.descriptions["media/a/t/moi.jpg"] == "mô tả mới"
    assert env.store.descriptions["media/a/t/cached.jpg"] == "đã có sẵn"


async def test_vision_sidecar_test_sidecar_chua_cau_hinh_thi_nem_loi_co_huong_dan(env: Env) -> None:
    """testSidecar: chưa cấu hình thì ném lỗi có hướng dẫn"""
    await env.unconfigure()

    async def call(*_a: object) -> SidecarResult:
        return SidecarResult("ok", False)

    with pytest.raises(RuntimeError, match=r"base URL \+ model \+ API key"):
        await sidecar.test_sidecar(call)


async def test_vision_sidecar_ask_about_image_prompt_chua_nguyen_cau_hoi_khong_cache(env: Env) -> None:
    """askAboutImage: prompt chứa nguyên câu hỏi, KHÔNG cache (mỗi câu mỗi khác)"""
    await env.configure()
    prompts: list[str] = []

    async def call(_s: object, _i: object, prompt: str) -> SidecarResult:
        prompts.append(prompt)
        return SidecarResult("2 con cá vàng", False)

    first = await sidecar.ask_about_image(IMG, "Đếm số cá màu vàng", call)  # type: ignore[arg-type]
    second = await sidecar.ask_about_image(IMG, "Đếm số cá màu vàng", call)  # type: ignore[arg-type]
    assert first == "2 con cá vàng"
    assert second == "2 con cá vàng"
    assert len(prompts) == 2, "câu hỏi tùy biến không được cache"
    assert "Đếm số cá màu vàng" in prompts[0]
    assert "không suy diễn" in prompts[0]


async def test_vision_sidecar_ask_about_image_chua_cau_hinh_sidecar_thi_nem_loi(env: Env) -> None:
    """askAboutImage: chưa cấu hình sidecar thì ném lỗi (tool tự diễn giải cho model)"""
    await env.unconfigure()

    async def call(*_a: object) -> SidecarResult:
        return SidecarResult("x", False)

    with pytest.raises(RuntimeError, match=r"base URL \+ model \+ API key"):
        await sidecar.ask_about_image(IMG, "đếm cá", call)


async def test_vision_sidecar_describe_image_truyen_dung_prompt_mo_ta_co_dinh(env: Env) -> None:
    """describeImage truyền đúng prompt mô tả cố định (chép nguyên văn chữ + số)"""
    await env.configure()
    received: list[str] = []

    async def call(_s: object, _i: object, prompt: str) -> SidecarResult:
        received.append(prompt)
        return SidecarResult("mô tả", False)

    await sidecar.describe_image(
        env.with_key("media/a/t/prompt-check.jpg"),
        call,
        clinic_id=FAKE_CLINIC_ID,
        store=env.store,  # type: ignore[arg-type]
    )
    assert "NGUYÊN VĂN" in received[0]


async def test_vision_sidecar_mo_ta_bi_cat_van_dung_cho_luot_nay_nhung_tuyet_doi_khong_cache(
    env: Env,
) -> None:
    """mô tả BỊ CẮT: vẫn dùng cho lượt này nhưng TUYỆT ĐỐI không cache"""
    await env.configure()
    calls = 0

    async def call(*_a: object) -> SidecarResult:
        nonlocal calls
        calls += 1
        return SidecarResult("vé số Đà Lạt 1234", True)

    first = await sidecar.describe_image(
        env.with_key("media/a/t/cut-0.jpg"), call, clinic_id=FAKE_CLINIC_ID, store=env.store
    )
    assert first == "vé số Đà Lạt 1234", "mô tả cụt vẫn dùng được - có còn hơn không"
    assert "media/a/t/cut-0.jpg" not in env.store.descriptions, (
        "bản cụt mà cache thì nó sống vĩnh viễn, mọi lượt sau đọc phải nó"
    )
    # Next time it calls again because there is no cache: a chance to get the full version
    await sidecar.describe_image(
        env.with_key("media/a/t/cut-0.jpg"), call, clinic_id=FAKE_CLINIC_ID, store=env.store
    )
    assert calls == 2, "không cache thì lượt sau phải gọi lại"


async def test_vision_sidecar_ask_about_image_bi_cat_noi_that_cho_model_biet_phan_sau_con_thieu(
    env: Env,
) -> None:
    """askAboutImage bị cắt: nói thật cho model biết phần sau còn thiếu"""
    await env.configure()

    async def call(*_a: object) -> SidecarResult:
        return SidecarResult("Có 3 mục: A, B", True)

    answer = await sidecar.ask_about_image(IMG, "liệt kê hết", call)
    assert "Có 3 mục: A, B" in answer
    assert "bị cắt vì quá dài" in answer, "model phải biết dữ liệu chưa đủ để đừng kết luận chắc nịch"

# ported from: src/agent/tools/draw-image-with-one-retry.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

import pytest

from pema.agent.tools.draw_image_with_one_retry import ve_voi_mot_lan_thu_lai
from pema.images.image_generation_client import GeneratedImage, GenerateImageParams, RefImage
from pema.images.image_retry_policy import ImageGenError, LoiVeHutAnh

ANH = GeneratedImage(data=bytes([0xFF, 0xD8]), ext="jpg")
THAM_SO = GenerateImageParams(prompt="một con mèo đội mũ")


class _Provider:
    """Fake provider: raises along the scripted list, returns an image when the script is empty."""

    def __init__(self, kich_ban: list[Exception | None]) -> None:
        self.kich_ban = list(kich_ban)
        self.lan_goi: list[GenerateImageParams] = []

    async def generate(self, params: GenerateImageParams) -> GeneratedImage:
        self.lan_goi.append(params)
        loi = self.kich_ban.pop(0) if self.kich_ban else None
        if loi is not None:
            raise loi
        return ANH


async def test_ve_voi_mot_lan_thu_lai_runs_fine_calls_the_provider_exactly_once_and_says_nothing_more() -> (
    None
):
    """chạy ngon thì gọi provider ĐÚNG MỘT lần và KHÔNG nhắn gì thêm"""
    provider = _Provider([])
    bao_da_goi: list[str] = []

    ket = await ve_voi_mot_lan_thu_lai(provider.generate, THAM_SO, lambda: bao_da_goi.append("bao"))

    assert ket is ANH
    assert len(provider.lan_goi) == 1
    assert bao_da_goi == [], "vẽ được ngay mà vẫn nhắn 'đang thử lại' là nói dối người dùng"


async def test_ve_voi_mot_lan_thu_lai_first_miss_notifies_then_redraws_and_returns_the_second_image() -> None:
    """hụt ảnh lần đầu -> BÁO rồi vẽ lại, và lần hai được thì trả ảnh"""
    provider = _Provider([LoiVeHutAnh("Provider không trả về ảnh")])
    bao_da_goi: list[str] = []

    ket = await ve_voi_mot_lan_thu_lai(provider.generate, THAM_SO, lambda: bao_da_goi.append("bao"))

    assert ket is ANH
    assert len(provider.lan_goi) == 2, "phải gọi lại provider, không phải trả lỗi luôn"
    assert len(bao_da_goi) == 1, "người dùng đã đợi hơn 2 phút, thử lại âm thầm là bắt họ ngồi im tiếp"


async def test_ve_voi_mot_lan_thu_lai_notifies_before_calling_again_not_after() -> None:
    """báo TRƯỚC khi gọi lại, không phải sau - báo sau thì khỏi báo"""
    thu_tu: list[str] = []

    async def generate(_params: GenerateImageParams) -> GeneratedImage:
        thu_tu.append("goi-provider")
        if thu_tu.count("goi-provider") == 1:
            raise LoiVeHutAnh("Provider không trả về ảnh")
        return ANH

    await ve_voi_mot_lan_thu_lai(generate, THAM_SO, lambda: thu_tu.append("bao"))

    assert thu_tu == ["goi-provider", "bao", "goi-provider"]


async def test_ve_voi_mot_lan_thu_lai_keeps_the_parameters_identical_on_the_redraw() -> None:
    """giữ NGUYÊN tham số ở lần vẽ lại - đổi prompt là vẽ một tấm khác"""
    tham_so_day_du = GenerateImageParams(
        prompt="poster tiếng Việt",
        ref_image=RefImage(base64="AAAA", media_type="image/png"),
        transparent_background=True,
    )
    provider = _Provider([LoiVeHutAnh("hụt")])

    await ve_voi_mot_lan_thu_lai(provider.generate, tham_so_day_du, lambda: None)

    assert provider.lan_goi[0] == tham_so_day_du
    assert provider.lan_goi[1] == tham_so_day_du


async def test_ve_voi_mot_lan_thu_lai_another_class_of_error_is_not_retried_and_flies_out_intact() -> None:
    """lỗi KHÁC lớp thì không gọi lại, và lỗi gốc bay ra nguyên vẹn"""
    qua_han = ImageGenError("Vẽ ảnh quá lâu (hơn 600 giây) nên đã dừng")
    provider = _Provider([qua_han])
    bao_da_goi: list[str] = []

    with pytest.raises(ImageGenError) as info:
        await ve_voi_mot_lan_thu_lai(provider.generate, THAM_SO, lambda: bao_da_goi.append("bao"))

    assert info.value is qua_han
    assert len(provider.lan_goi) == 1, "quá hạn mà gọi lại là tiêu thêm trọn một trần thời gian nữa"
    assert bao_da_goi == [], "không thử lại thì đừng hứa là đang thử lại"


async def test_ve_voi_mot_lan_thu_lai_missing_both_times_stops_at_two_and_the_second_error_flies_out() -> (
    None
):
    """hụt CẢ HAI lần -> dừng ở hai, để lỗi lần hai bay ra cho tool nói thật"""
    lan_hai = LoiVeHutAnh("Provider không trả về ảnh (lần hai)")
    provider = _Provider([LoiVeHutAnh("lần một"), lan_hai])

    with pytest.raises(LoiVeHutAnh) as info:
        await ve_voi_mot_lan_thu_lai(provider.generate, THAM_SO, lambda: None)

    assert info.value is lan_hai
    assert len(provider.lan_goi) == 2, "thử lại lần ba là kéo người dùng chờ tới 6 phút"


async def test_ve_voi_mot_lan_thu_lai_a_failed_notice_must_not_kill_the_drawing() -> None:
    """nhắn hụt KHÔNG được làm chết lượt vẽ - gửi được ảnh quý hơn gửi được lời nhắn"""
    provider = _Provider([LoiVeHutAnh("hụt")])

    def bao_hong() -> None:
        raise RuntimeError("Zalo chối tin nhắn")

    ket = await ve_voi_mot_lan_thu_lai(provider.generate, THAM_SO, bao_hong)

    assert ket is ANH
    assert len(provider.lan_goi) == 2


async def test_ve_voi_mot_lan_thu_lai_an_async_notice_is_awaited() -> None:
    """bao_thu_lai bất đồng bộ cũng được chờ xong trước khi vẽ lại (Python: callback sync hoặc async)"""
    thu_tu: list[str] = []
    provider = _Provider([LoiVeHutAnh("hụt")])

    async def bao() -> None:
        thu_tu.append("bao-xong")

    original = provider.generate

    async def generate(params: GenerateImageParams) -> GeneratedImage:
        thu_tu.append("goi")
        return await original(params)

    await ve_voi_mot_lan_thu_lai(generate, THAM_SO, bao)
    assert thu_tu == ["goi", "bao-xong", "goi"]

# ported from: src/zalo/zalo-image-variant.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring."""

from __future__ import annotations

from pema.channels.zalo_personal.zalo_image_variant import (
    estimate_image_tokens,
    pick_image_variant,
    read_image_size,
)

# Payload thật của tin nhắn ảnh Zalo có đủ 5 biến thể (host synthetic)
FULL_CONTENT: dict[str, object] = {
    "title": "dò vé số này cho tôi nhé",
    "thumb": "https://cdn.example.invalid/thumb.jpg",
    "normalUrl": "https://cdn.example.invalid/normal.jpg",
    "href": "https://cdn.example.invalid/href.jpg",
    "oriUrl": "https://cdn.example.invalid/ori.jpg",
    "hd": "https://cdn.example.invalid/hd.jpg",
}


def test_pick_image_variant_normal_mac_dinh_khong_lay_ban_hd() -> None:
    """normal (mặc định) KHÔNG lấy bản hd - đó là chỗ tốn token nhất"""
    picked = pick_image_variant(FULL_CONTENT, "normal")
    assert picked is not None
    assert picked.variant == "normalUrl"
    assert picked.url == "https://cdn.example.invalid/normal.jpg"


def test_pick_image_variant_hd_giu_hanh_vi_cu() -> None:
    """hd giữ được hành vi cũ khi cần đọc chi tiết rất nhỏ"""
    picked = pick_image_variant(FULL_CONTENT, "hd")
    assert picked is not None
    assert picked.variant == "hd"


def test_pick_image_variant_thumb_lay_ban_nho_nhat() -> None:
    """thumb lấy bản nhỏ nhất"""
    picked = pick_image_variant(FULL_CONTENT, "thumb")
    assert picked is not None
    assert picked.variant == "thumb"


def test_pick_image_variant_thieu_bien_the_thi_lui_sang_co_khac() -> None:
    """thiếu biến thể mong muốn thì lùi sang cỡ khác chứ không bỏ ảnh"""
    only_hd = pick_image_variant({"hd": "https://cdn.example.invalid/hd.jpg"}, "normal")
    assert only_hd is not None
    assert only_hd.variant == "hd"

    only_thumb = pick_image_variant({"thumb": "https://cdn.example.invalid/t.jpg"}, "hd")
    assert only_thumb is not None
    assert only_thumb.variant == "thumb"


def test_pick_image_variant_bo_qua_gia_tri_khong_phai_url_http() -> None:
    """bỏ qua giá trị không phải URL http (Zalo có lúc trả chuỗi rỗng)"""
    messy: dict[str, object] = {"normalUrl": "", "href": "   ", "hd": "https://cdn.example.invalid/hd.jpg"}
    picked = pick_image_variant(messy, "normal")
    assert picked is not None
    assert picked.variant == "hd"
    assert pick_image_variant({"normalUrl": "data:image/png;base64,x"}, "normal") is None


def test_pick_image_variant_content_khong_co_anh_tra_none() -> None:
    """content không có ảnh trả null"""
    assert pick_image_variant({"title": "chỉ có chữ"}, "normal") is None


def test_estimate_image_tokens_anh_ve_so_hd_that_ton_khoang_2772_token() -> None:
    """ảnh vé số HD thật (977x2128) tốn khoảng 2772 token mỗi lần vào context"""
    assert estimate_image_tokens(977, 2128) == 2772


def test_estimate_image_tokens_cung_anh_o_co_normal_re_hon_khoang_4_lan() -> None:
    """cùng ảnh đó ở cỡ normal (một nửa cạnh) rẻ hơn khoảng 4 lần"""
    hd = estimate_image_tokens(977, 2128)
    normal = estimate_image_tokens(489, 1064)
    assert normal < hd / 3.5, f"normal={normal} phải rẻ hơn hẳn hd={hd}"


def test_estimate_image_tokens_kich_thuoc_khong_hop_le_tra_0() -> None:
    """kích thước không hợp lệ trả 0, không NaN"""
    assert estimate_image_tokens(0, 100) == 0
    assert estimate_image_tokens(-5, 10) == 0


def test_read_image_size_doc_duoc_kich_thuoc_png() -> None:
    """đọc được kích thước PNG"""
    png = bytearray(32)
    png[0:4] = (0x89504E47).to_bytes(4, "big")
    png[16:20] = (1920).to_bytes(4, "big")
    png[20:24] = (1080).to_bytes(4, "big")
    assert read_image_size(bytes(png)) == (1920, 1080)


def test_read_image_size_doc_duoc_kich_thuoc_jpeg_qua_marker_sof0() -> None:
    """đọc được kích thước JPEG qua marker SOF0"""
    jpeg = bytes(
        [
            0xFF, 0xD8,
            0xFF, 0xE0, 0x00, 0x04, 0x00, 0x00,
            0xFF, 0xC0, 0x00, 0x11, 0x08, 0x08, 0x50, 0x03, 0xD1, 0x03, 0x00, 0x00, 0x00, 0x00,
        ]
    )  # fmt: skip
    assert read_image_size(jpeg) == (977, 2128)


def test_read_image_size_du_lieu_rac_tra_none_thay_vi_throw_hay_lap_vo_han() -> None:
    """dữ liệu rác trả null thay vì throw hay lặp vô hạn"""
    assert read_image_size(bytes([1, 2, 3])) is None
    assert read_image_size(b"") is None
    # JPEG có segment length = 0 (hỏng) không được làm treo vòng lặp
    broken = bytes([0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x00, 0, 0, 0, 0, 0, 0])
    assert read_image_size(broken) is None

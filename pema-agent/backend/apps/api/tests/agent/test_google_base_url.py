# ported from: src/agent/google-base-url.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

An OLD base URL STAYS in the DB when the user changes the "connection type": the form only hides the field, it
does not clear the value. Two failures come out of that: the "/openai" tail (the OpenAI shim of Google, not the
native API this provider speaks; old users surely have it because the quick "Google Gemini" button used to fill
exactly that URL) and another vendor's URL (OpenRouter, 9Router): sending the Google key there leaks it to a
third party and earns a baffling 401.
"""

from __future__ import annotations

from pema.agent.llm_provider import base_url_cho_google

GOC = "https://generativelanguage.googleapis.com/v1beta"


def test_base_url_cho_google_go_duoi_openai_day_la_lop_gia_tro_vao_la_404() -> None:
    """gỡ đuôi /openai - đó là lớp giả, trỏ vào là 404"""
    assert base_url_cho_google(f"{GOC}/openai") == GOC
    assert base_url_cho_google(f"{GOC}/OpenAI") == GOC


def test_base_url_cho_google_go_ca_gach_cuoi_lan_openai_khi_dan_tu_tai_lieu() -> None:
    """gỡ cả gạch cuối lẫn /openai khi dán từ tài liệu"""
    assert base_url_cho_google(f"{GOC}/openai/") == GOC
    assert base_url_cho_google(f"{GOC}/openai///") == GOC
    assert base_url_cho_google(f"  {GOC}/openai  ") == GOC


def test_base_url_cho_google_url_dung_dang_api_rieng_thi_giu_nguyen() -> None:
    """URL đúng dạng API riêng thì giữ nguyên"""
    assert base_url_cho_google(GOC) == GOC


def test_base_url_cho_google_bo_han_base_url_cua_hang_khac() -> None:
    """BỎ HẲN base URL của hãng khác - không gửi khóa Google sang bên thứ ba"""
    assert base_url_cho_google("https://openrouter.ai/api/v1") is None
    assert base_url_cho_google("https://9router.example.io.vn/v1") is None
    assert base_url_cho_google("https://api.openai.com/v1") is None


def test_base_url_cho_google_khong_bi_lua_boi_host_chi_chua_chuoi_googleapis() -> None:
    """KHÔNG bị lừa bởi host chỉ chứa chuỗi googleapis.com

    Matching by "contains" would let these hosts through and the key would fly there.
    """
    assert base_url_cho_google("https://googleapis.com.evil.example/v1") is None
    assert base_url_cho_google("https://notgoogleapis.com/v1") is None


def test_base_url_cho_google_rong_hoac_khong_phai_url_thi_de_sdk_tu_dung_endpoint_mac_dinh() -> None:
    """rỗng hoặc không phải URL thì để SDK tự dùng endpoint mặc định"""
    assert base_url_cho_google(None) is None
    assert base_url_cho_google("") is None
    assert base_url_cho_google("   ") is None
    assert base_url_cho_google("khong-phai-url") is None

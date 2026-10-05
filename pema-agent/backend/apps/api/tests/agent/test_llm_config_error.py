# ported from: src/agent/llm-config-error.ts
"""Pinning cases for ``llm_config_error`` (the original has no test file of its own). Test names are the
snake_case form of ``describe_it``; the Vietnamese title is the docstring."""

from __future__ import annotations

from pema.agent.llm_config_error import LoiCauHinhLlm


def test_loi_cau_hinh_llm_giu_loai_cau_hinh_va_thong_bao() -> None:
    """lớp lỗi giữ loại cấu hình thiếu và thông báo"""
    err = LoiCauHinhLlm("api_key", "chưa nhập API key")
    assert err.loai_cau_hinh == "api_key"
    assert str(err) == "chưa nhập API key"
    assert isinstance(err, Exception)


def test_loi_cau_hinh_llm_is_instance_nhan_dien_theo_hinh_dang() -> None:
    """is_instance nhận diện theo hình dạng: lớp thật, và bản sao module cùng tên lớp"""
    assert LoiCauHinhLlm.is_instance(LoiCauHinhLlm("model", "x"))

    # A second copy of the class in memory (a reloaded module) is not an ``isinstance`` of ours
    clone = type("LoiCauHinhLlm", (Exception,), {})("x")
    assert not isinstance(clone, LoiCauHinhLlm)
    assert LoiCauHinhLlm.is_instance(clone)


def test_loi_cau_hinh_llm_is_instance_tu_choi_loi_khac_va_gia_tri_rong() -> None:
    """lỗi thường, chuỗi, None đều không phải"""
    assert not LoiCauHinhLlm.is_instance(ValueError("api_key"))
    assert not LoiCauHinhLlm.is_instance("LoiCauHinhLlm")
    assert not LoiCauHinhLlm.is_instance(None)

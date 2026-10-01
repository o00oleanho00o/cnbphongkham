# ported from: src/agent/reasoning-options.test.ts
"""Pure module: no environment setup needed."""

from __future__ import annotations

import pytest

from pema.agent.reasoning_options import ROUTER_PROVIDER_OPTIONS_KEY, reasoning_provider_options
from pema_contracts.agents import LlmProviderKind, ReasoningEffort

OPENAI = LlmProviderKind.OPENAI_COMPATIBLE
ANTHROPIC = LlmProviderKind.ANTHROPIC
GOOGLE = LlmProviderKind.GOOGLE


def test_reasoning_provider_options_openai_compatible_reasoning_effort_nam_duoi_key_dung_ten_provider_cua_router() -> (
    None
):
    """openai-compatible: reasoningEffort nằm dưới key đúng tên provider của router"""
    options = reasoning_provider_options(OPENAI, ReasoningEffort.MEDIUM)
    assert options == {ROUTER_PROVIDER_OPTIONS_KEY: {"reasoningEffort": "medium"}}


def test_reasoning_provider_options_openai_compatible_off_bo_han_tham_so() -> None:
    """openai-compatible + off: bỏ hẳn tham số (mỗi router một kiểu giá trị tắt)"""
    assert reasoning_provider_options(OPENAI, ReasoningEffort.OFF) is None


def test_reasoning_provider_options_anthropic_adaptive_thinking_effort() -> None:
    """anthropic: adaptive thinking + effort"""
    assert reasoning_provider_options(ANTHROPIC, ReasoningEffort.HIGH) == {
        "anthropic": {"thinking": {"type": "adaptive"}, "effort": "high"}
    }


def test_reasoning_provider_options_anthropic_off_tat_thinking_tuong_minh() -> None:
    """anthropic + off: tắt thinking tường minh, không thả về mặc định của provider"""
    assert reasoning_provider_options(ANTHROPIC, ReasoningEffort.OFF) == {
        "anthropic": {"thinking": {"type": "disabled"}}
    }


def test_reasoning_provider_options_key_router_phai_khop_name() -> None:
    """key router phải khớp name trong createOpenAICompatible - lệch là options bị lờ đi im lặng"""
    assert ROUTER_PROVIDER_OPTIONS_KEY == "llmRouter"


def test_reasoning_provider_options_key_phai_la_camel_case() -> None:
    """key phải là camelCase - kebab-case làm SDK in cảnh báo deprecated mỗi request"""
    assert "-" not in ROUTER_PROVIDER_OPTIONS_KEY


def _muc(effort: ReasoningEffort) -> str:
    options = reasoning_provider_options(GOOGLE, effort)
    assert options is not None
    return str(options["google"]["thinkingConfig"]["thinkingLevel"])


def test_reasoning_provider_options_google_ba_muc_trung_ten_di_thang() -> None:
    """ba mức trùng tên đi thẳng"""
    assert _muc(ReasoningEffort.LOW) == "low"
    assert _muc(ReasoningEffort.MEDIUM) == "medium"
    assert _muc(ReasoningEffort.HIGH) == "high"


def test_reasoning_provider_options_google_off_thanh_minimal_khong_bo_tham_so() -> None:
    """ "off" thành "minimal" chứ KHÔNG bỏ tham số - Gemini 3 không tắt hẳn nghĩ được"""
    assert _muc(ReasoningEffort.OFF) == "minimal"
    assert reasoning_provider_options(GOOGLE, ReasoningEffort.OFF) is not None


def test_reasoning_provider_options_google_xhigh_ha_ve_high() -> None:
    """ "xhigh" hạ về "high" - không có nấc nào cao hơn"""
    assert _muc(ReasoningEffort.XHIGH) == "high"


@pytest.mark.parametrize("effort", list(ReasoningEffort))
def test_reasoning_provider_options_google_moi_muc_deu_ra_gia_tri_gemini_nhan(
    effort: ReasoningEffort,
) -> None:
    """MỌI mức đều ra giá trị Gemini nhận, không mức nào lọt ra ngoài danh sách"""
    assert _muc(effort) in {"minimal", "low", "medium", "high"}


def test_reasoning_provider_options_google_khong_dung_key_cua_router() -> None:
    """KHÔNG dùng key của router - lệch key là tham số bị lờ đi im lặng"""
    options = reasoning_provider_options(GOOGLE, ReasoningEffort.MEDIUM)
    assert options is not None
    assert "google" in options
    assert ROUTER_PROVIDER_OPTIONS_KEY not in options

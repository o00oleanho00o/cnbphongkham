# ported from: src/agent/llm-provider-safety.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The API-key LEAK guard. ``api_key`` and ``base_url`` always come from the shared configuration (a per-agent key
does not exist yet), so an agent that declares a ``model_provider`` different from the shared one would make
the key of one party go to the endpoint of the other: a credential leaked to a third party, and a bot silenced
by a 401. A SECURITY invariant, not a convenience: the UI locks the select box, but not before the shared
configuration has loaded, and anyone who calls the API edge directly can save it. The last guard sits where
every path goes through.
"""

from __future__ import annotations

from pema.agent.llm_provider import ModelOverride, ProviderModel, doi_provider_an_toan
from pema_contracts.agents import LlmProviderKind

OPENAI = LlmProviderKind.OPENAI_COMPATIBLE
ANTHROPIC = LlmProviderKind.ANTHROPIC
GOOGLE = LlmProviderKind.GOOGLE

CHUNG = ProviderModel(OPENAI, "gpt-combo")


def test_doi_provider_an_toan_khong_override_gi_thi_giu_nguyen_cau_hinh_chung() -> None:
    """không override gì thì giữ nguyên cấu hình chung"""
    assert doi_provider_an_toan(CHUNG) == CHUNG


def test_doi_provider_an_toan_override_model_ma_khong_doi_provider_thi_duoc_nhan() -> None:
    """override model mà KHÔNG đổi provider thì được nhận"""
    assert doi_provider_an_toan(CHUNG, ModelOverride(model_name="gpt-5.6-sol")) == ProviderModel(
        OPENAI, "gpt-5.6-sol"
    )


def test_doi_provider_an_toan_override_provider_trung_provider_chung_thi_duoc_nhan() -> None:
    """override provider TRÙNG provider chung thì được nhận"""
    assert doi_provider_an_toan(CHUNG, ModelOverride(model_provider=OPENAI, model_name="x")) == ProviderModel(
        OPENAI, "x"
    )


def test_doi_provider_an_toan_override_provider_lech_bi_bo_qua_day_la_chot_chan_ro_khoa() -> None:
    """override provider LỆCH bị bỏ qua - đây là chốt chặn rò khóa"""
    r = doi_provider_an_toan(CHUNG, ModelOverride(model_provider=ANTHROPIC, model_name="claude-opus-5"))
    assert r.provider is OPENAI, "TUYỆT ĐỐI không được đổi sang provider không có khóa"


def test_doi_provider_an_toan_bi_bo_qua_thi_model_cung_roi_ve_chung() -> None:
    """bị bỏ qua thì model cũng rơi về chung - tên model chọn CHO provider kia sẽ 400 ở đây"""
    r = doi_provider_an_toan(CHUNG, ModelOverride(model_provider=ANTHROPIC, model_name="claude-opus-5"))
    assert r.model == "gpt-combo"


def test_doi_provider_an_toan_chieu_nguoc_lai_cung_chan_chung_la_anthropic_agent_khai_router() -> None:
    """chiều ngược lại cũng chặn: chung là anthropic, agent khai router"""
    r = doi_provider_an_toan(ProviderModel(ANTHROPIC, "claude-opus-5"), ModelOverride(model_provider=OPENAI))
    assert r.provider is ANTHROPIC


def test_doi_provider_an_toan_model_provider_none_khong_kich_hoat_nhanh_chan() -> None:
    """modelProvider null (đã bỏ override) không kích hoạt nhánh chặn"""
    assert doi_provider_an_toan(CHUNG, ModelOverride(model_provider=None, model_name="y")) == ProviderModel(
        OPENAI, "y"
    )


# Google is the third provider (added 06/08/2026). The leak guard must cover it like the other two: adding a
# provider and forgetting to widen the guard is exactly the kind of bug that only shows when a real person
# misconfigures.

GOOGLE_CHUNG = ProviderModel(GOOGLE, "gemini-3.5-flash-lite")


def test_doi_provider_an_toan_google_override_provider_trung_google_google_thi_duoc_nhan() -> None:
    """override provider TRÙNG (google/google) thì được nhận"""
    r = doi_provider_an_toan(
        GOOGLE_CHUNG, ModelOverride(model_provider=GOOGLE, model_name="gemini-3.6-flash")
    )
    assert r == ProviderModel(GOOGLE, "gemini-3.6-flash")


def test_doi_provider_an_toan_google_chung_la_router_agent_khai_google_bo_qua() -> None:
    """chung là router, agent khai google -> BỎ QUA, không gửi khóa router sang Google"""
    r = doi_provider_an_toan(CHUNG, ModelOverride(model_provider=GOOGLE, model_name="gemini-3.5-flash-lite"))
    assert r.provider is OPENAI
    assert r.model == "gpt-combo", "tên model của Google gửi sang router chỉ nhận 400"


def test_doi_provider_an_toan_google_chung_la_google_agent_khai_router_bo_qua_chieu_nguoc_lai() -> None:
    """chung là google, agent khai router -> BỎ QUA chiều ngược lại"""
    r = doi_provider_an_toan(GOOGLE_CHUNG, ModelOverride(model_provider=OPENAI, model_name="gpt-combo"))
    assert r.provider is GOOGLE
    assert r.model == "gemini-3.5-flash-lite"

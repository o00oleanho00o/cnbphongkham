# ported from: src/agent/persona-tool-rules.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Forced deviation: the original used the real tool registry (``TOOL_KEYS``); here the 15 keys of the
catalogue are ``BUILTIN_TOOL_KEYS`` of the contract and the prompt runs over ``FakeToolRegistry``.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from pema.agent.persona_prompt import build_system_prompt
from pema.agent.persona_tool_rules import TOOL_KEYS_IN_RULES, tool_persona_sections
from pema.agent.testing import FakeToolRegistry
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.channel import ChannelKind
from pema_contracts.testing import fake_account_config, fake_agent_profile, make_inbound
from pema_contracts.tools import BUILTIN_TOOL_KEYS


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({}))
    yield
    reset_tuning_provider()


def gop(keys: list[str]) -> str:
    return "\n\n".join(tool_persona_sections(keys))


# ---- toolPersonaSections ------------------------------------------------------------------------------


def test_tool_persona_sections_moi_key_tool_trong_luat_phai_co_that_trong_registry() -> None:
    """mọi key tool trong luật phải có thật trong registry"""
    co_that = set(BUILTIN_TOOL_KEYS)
    ma = [k for k in TOOL_KEYS_IN_RULES if k not in co_that]
    assert ma == [], "key không còn trong registry = luật đó vĩnh viễn không bao giờ hiện, mà không ai biết"
    # The fake catalogue (which package G re-runs against the real registry) agrees too
    assert set(BUILTIN_TOOL_KEYS) == {spec.key for spec in FakeToolRegistry().definitions()}


def test_tool_persona_sections_tat_create_image_thi_khong_con_dong_nao_day_ve_anh() -> None:
    """tắt create_image thì KHÔNG còn dòng nào dạy vẽ ảnh"""
    bat = gop(["create_image", "web_search"])
    tat = gop(["web_search"])
    assert "create_image" in bat, "bật thì phải có luật vẽ ảnh"
    assert "create_image" not in tat, "tắt rồi mà vẫn dạy cách viết prompt vẽ ảnh"
    assert "sua_anh_da_gui" not in tat


def test_tool_persona_sections_tat_tool_tao_file_thi_khong_con_luat_xuat_file() -> None:
    """tắt tool tạo file thì không còn luật xuất file"""
    tat = gop(["web_search"])
    assert "create_word_document" not in tat
    assert "create_excel_file" not in tat


def test_tool_persona_sections_con_mot_trong_hai_tool_tao_file_thi_luat_van_hien() -> None:
    """còn một trong hai tool tạo file thì luật vẫn hiện"""
    assert "create_excel_file" in gop(["create_excel_file"])


def test_tool_persona_sections_khong_con_tool_nao_thi_khong_co_khoi_luat_nao_ke_ca_ke_tien_trinh() -> None:
    """không còn tool nào thì không có khối luật nào - kể cả kể tiến trình"""
    assert tool_persona_sections([]) == []


def test_tool_persona_sections_co_tool_nhung_khong_phai_tool_web_van_giu_luat_chung_bo_luat_web() -> None:
    """có tool nhưng không phải tool web: vẫn giữ luật chung, bỏ luật web"""
    chi_ve_anh = gop(["create_image"])
    assert "kể tiến trình" in chi_ve_anh, "luật chung về dùng tool phải còn"
    assert "web_search" not in chi_ve_anh, "không có tool web thì đừng dạy web_search"
    assert "không bịa số liệu" in chi_ve_anh, "luật chống bịa áp cho mọi tool"


def test_tool_persona_sections_bat_kb_search_thi_co_luat_tra_kho_tat_thi_mat() -> None:
    """bật kb_search thì có luật tra kho trước khi trả lời bằng trí nhớ chung, tắt thì mất"""
    bat = gop(["kb_search"])
    tat = gop(["web_search"])
    assert "TRA kho tri thức trước" in bat, "bật thì phải có luật tra kho"
    assert "nói rõ lấy từ tài liệu nào" in bat, "bật thì phải có luật dẫn nguồn"
    assert "kho tri thức" not in tat, "tắt kb_search rồi mà vẫn dạy luật tra kho"


# ---- buildSystemPrompt ghép luật theo tool đang bật ---------------------------------------------------
# A real fixture instead of ``as never``: the agent is one of the two tool filter layers.

AGENT = fake_agent_profile(id="a", name="test")
MSG = make_inbound("hi", sender_name="Hải", sender_id="u1", is_group=False, thread_id="t1")


def _prompt(disabled_tools: list[str]) -> str:
    account = fake_account_config(channel=ChannelKind.ZALO_PERSONAL, disabled_tools=disabled_tools)
    return build_system_prompt(AGENT, MSG, None, account, registry=FakeToolRegistry())


def test_build_system_prompt_ghep_luat_tat_tool_tren_dashboard_thi_luat_cua_tool_do_bien_mat() -> None:
    """tắt tool trên dashboard thì luật của tool đó biến mất khỏi prompt"""
    day = _prompt([])
    tat = _prompt(["create_word_document", "create_excel_file", "web_search", "web_fetch"])

    assert "create_word_document" in day, "bật hết thì prompt có luật xuất file"
    assert "web_search" in day, "bật hết thì prompt có luật tra web"
    assert "create_word_document" not in tat, "đây chính là phần chữ từng đi kèm mọi lượt"
    assert "web_search" not in tat
    assert "Tạo file Word" not in tat, "mục Khả năng cũng phải bỏ tool đó"
    assert len(tat) < len(day)


def test_build_system_prompt_ghep_luat_tool_chua_cau_hinh_ha_tang_cung_khong_duoc_day_luat() -> None:
    """tool chưa cấu hình hạ tầng cũng không được dạy luật"""
    # create_image has available() = image generation configured, the test registry has no drawing endpoint
    # configured -> the model does NOT receive the tool, the prompt must not teach it either
    day = _prompt([])
    assert "create_image" not in day
    assert "Vẽ ảnh AI" not in day


def test_build_system_prompt_ghep_luat_account_khong_con_tool_nao_prompt_khong_day_luat_tool_nao() -> None:
    """account không còn tool nào: prompt không dạy luật tool nào nữa"""
    khong_tool = _prompt(list(BUILTIN_TOOL_KEYS))
    assert "KHÔNG có công cụ nào được bật" in khong_tool
    assert "kể tiến trình" not in khong_tool
    assert "web_search" not in khong_tool
    # The safety rules do NOT depend on tools - still intact
    assert "chuyển tiền" in khong_tool
    assert "noi_dung_ngoai" in khong_tool

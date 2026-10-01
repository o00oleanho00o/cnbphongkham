# ported from: src/agent/persona-prompt.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The system prompt must name EXACTLY the tool set the account has. A static persona that names tools by hand
keeps promising what was switched off - the user who asks "what can you do" gets a wrong answer.

Forced deviation: the original used the real tool registry; here it is ``FakeToolRegistry`` (the real one is
package D4's). ``buildAgentTools`` is async in the port. The last class of tests is NEW: it covers the
``ChannelCapabilities.persona_rule`` replacement of ``LUAT_PERSONA_KENH_BOT`` and the ``PromptMemory`` facts.
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import UUID

import pytest

from pema.agent.persona_prompt import PromptMemory, build_system_prompt
from pema.agent.prompt_leak_markers import (
    KHA_NANG_DAY_DU,
    THE_NOI_DUNG_NGOAI,
    TIEU_DE_QUY_TAC_AN_TOAN,
)
from pema.agent.testing import FakeToolRegistry, make_caps
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.agents import AccountConfig, AgentProfile
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.conversation import MemoryContextItem
from pema_contracts.policy import STAFF_ASSISTANT_PROFILE, PolicyContext
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    fake_account_config,
    fake_agent_profile,
    make_inbound,
)
from pema_contracts.tools import ToolContext, ToolScope


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({}))
    yield
    reset_tuning_provider()


# A real fixture instead of a literal forced through ``as never``: since the agent is one of the two tool
# filter layers, a missing ``disabled_tools`` would blow up at the merge of the two disabled lists.
AGENT = fake_agent_profile(name="Trợ lý")

MSG = make_inbound("hi", sender_name="Hải", is_group=False, thread_id="t-1")


def account(disabled_tools: list[str]) -> AccountConfig:
    return fake_account_config(id="acc-1", channel=ChannelKind.ZALO_PERSONAL, disabled_tools=disabled_tools)


def agent_tat(disabled_tools: list[str]) -> AgentProfile:
    """An agent with some tools already switched off - for the cases that test the agent-side filter layer."""
    return fake_agent_profile(disabled_tools=disabled_tools)


def _prompt(
    agent: AgentProfile,
    msg: InboundMessage = MSG,
    memory: PromptMemory | None = None,
    acc: AccountConfig | None = None,
    isolated: bool = False,
    registry: FakeToolRegistry | None = None,
) -> str:
    return build_system_prompt(agent, msg, memory, acc, isolated, registry=registry or FakeToolRegistry())


def _scope(agent: AgentProfile, acc: AccountConfig) -> ToolScope:
    return ToolScope(
        agent_id=agent.id,
        agent_disabled_tools=agent.disabled_tools,
        account_disabled_tools=acc.disabled_tools,
        channel=make_caps(),
    )


def _listed(
    registry: FakeToolRegistry, agent: AgentProfile, acc: AccountConfig, *, isolated: bool
) -> list[str]:
    return sorted(spec.key for spec in registry.list_available(_scope(agent, acc), isolated=isolated))


async def _built(
    registry: FakeToolRegistry, agent: AgentProfile, acc: AccountConfig, *, isolated: bool = False
) -> list[str]:
    ctx = ToolContext(
        clinic_id=FAKE_CLINIC_ID,
        account=acc,
        agent=agent,
        channel=None,
        message=MSG,
        batch=[],
        policy=PolicyContext(
            clinic_id=UUID(int=1),
            account_id=acc.id,
            agent_id=agent.id,
            channel=acc.channel,
            thread_id="t-1",
            profile=STAFF_ASSISTANT_PROFILE,
            isolated=isolated,
        ),
        isolated=isolated,
    )
    return sorted((await registry.build_agent_tools(ctx)).keys())


# ---- buildSystemPrompt - danh sách tool đang bật ------------------------------------------------------


def test_build_system_prompt_danh_sach_tool_dang_bat_ke_ten_tool_dang_bat_kem_mo_ta_ngan() -> None:
    """kể tên tool đang bật kèm mô tả ngắn"""
    text = _prompt(AGENT, acc=account([]))
    assert "Tìm kiếm web" in text, "phải có nhãn tiếng Việt để bot nói cho người thường nghe"
    assert "Tạo file Excel" in text


def test_build_system_prompt_danh_sach_tool_dang_bat_tool_bi_tat_khong_xuat_hien() -> None:
    """tool bị tắt KHÔNG xuất hiện - bot không hứa thứ nó không có"""
    text = _prompt(AGENT, acc=account(["create_excel_file", "web_search"]))
    assert "Tạo file Excel" not in text
    assert "Tìm kiếm web" not in text
    assert "Tạo file Word" in text, "tool không tắt vẫn phải còn"


def test_build_system_prompt_danh_sach_tool_dang_bat_tool_chua_du_ha_tang_cung_khong_xuat_hien() -> None:
    """tool chưa đủ hạ tầng cũng không xuất hiện (cùng bộ lọc với buildAgentTools)"""
    # create_image has no endpoint configured -> available() is False
    text = _prompt(AGENT, acc=account([]))
    assert "Vẽ ảnh AI" not in text


def test_build_system_prompt_danh_sach_tool_dang_bat_dan_model_tra_loi_cau_hoi_kha_nang() -> None:
    """dặn model trả lời câu hỏi khả năng theo ĐÚNG danh sách này"""
    text = _prompt(AGENT, acc=account([]))
    lowered = text.lower()
    assert "làm được gì" in lowered or "khả năng" in lowered


async def test_build_system_prompt_danh_sach_tool_dang_bat_khop_chinh_xac_bo_tool_build_agent_tools() -> None:
    """danh sách khớp CHÍNH XÁC bộ tool buildAgentTools dựng ra - một nguồn sự thật"""
    registry = FakeToolRegistry()
    acc = account(["send_file", "add_reaction"])
    built = await _built(registry, AGENT, acc)
    listed = _listed(registry, AGENT, acc, isolated=False)
    assert listed == built, "lệch nhau là prompt kể sai bộ tool model thực nhận"


def test_build_system_prompt_danh_sach_tool_dang_bat_tool_bi_agent_tat_cung_khong_xuat_hien() -> None:
    """tool bị AGENT tắt cũng không xuất hiện trong prompt"""
    # The second layer: before this phase only the account could switch a tool off, so the prompt named
    # even the tool the agent itself had switched off.
    text = _prompt(agent_tat(["web_search"]), acc=account([]))
    assert "Tìm kiếm web" not in text
    assert "Đọc trang web" in text, "tool agent không tắt vẫn phải còn"


async def test_build_system_prompt_danh_sach_tool_dang_bat_prompt_khop_schema_ca_khi_hai_lop_tat_hai_tool() -> (
    None
):
    """prompt khớp schema CẢ KHI hai lớp tắt hai tool khác nhau"""
    registry = FakeToolRegistry()
    ag = agent_tat(["web_search"])
    acc = account(["create_excel_file"])
    built = await _built(registry, ag, acc)
    listed = _listed(registry, ag, acc, isolated=False)
    assert listed == built
    assert "web_search" not in built, "agent tắt phải mất"
    assert "create_excel_file" not in built, "account tắt phải mất"

    text = _prompt(ag, acc=acc, registry=registry)
    assert "Tìm kiếm web" not in text
    assert "Tạo file Excel" not in text


def test_build_system_prompt_danh_sach_tool_dang_bat_day_model_ke_tien_trinh_khi_dung_tool() -> None:
    """dạy model kể tiến trình khi dùng tool - nguồn của khối 'Model nói' trong trace"""
    # The user needs to see what the model remarks after every tool round (enough sources yet, what is the
    # next step). OpenAI does not expose chain-of-thought so this SELF-WRITTEN narration is the only road -
    # measured for real: gpt-5.6-sol writes it along with the tool call when told to, and does not narrate
    # on a question that needs no tool.
    text = _prompt(AGENT, acc=account([]))
    assert "tiến trình" in text
    assert "TRƯỚC mỗi lần gọi tool" in text


def test_build_system_prompt_danh_sach_tool_dang_bat_khong_truyen_account_thi_khong_day_luat_tool_nao() -> (
    None
):
    """không truyền account thì KHÔNG dạy luật tool nào - không biết tool nào bật thì đừng đoán"""
    # The old call path (no account) now fails closed: better a missing rule than the rule of a tool the
    # model never received. Production always passes the account.
    text = _prompt(AGENT)
    assert "tiến trình" not in text
    assert "web_search" not in text


def test_build_system_prompt_danh_sach_tool_dang_bat_khong_truyen_account_van_dung_duoc_prompt() -> None:
    """không truyền account thì vẫn dựng được prompt (đường gọi cũ không vỡ)"""
    text = _prompt(AGENT)
    assert "trợ lý ai" in text.lower()


async def test_build_system_prompt_danh_sach_tool_dang_bat_isolated_khong_ke_9_tool_khop_schema_that() -> (
    None
):
    """isolated=true (lượt theo lịch): KHÔNG kể 9 tool bị runsInScheduledTurn:false - khớp CHÍNH XÁC với schema thật (Finding 2)"""
    # Before the fix: build_system_prompt listed the tools without the isolated flag, while
    # build_agent_tools (the agent loop) DID filter - the prompt advertised "Ghi nhớ lâu dài"/"Thả cảm xúc"
    # while the schema sent to the model had neither. The model claimed "I remembered it" and saved
    # nothing - the very invariant bug the test below guards for the NORMAL turn.
    registry = FakeToolRegistry()
    acc = account([])
    text_co_lap = _prompt(AGENT, acc=acc, isolated=True, registry=registry)
    text_thuong = _prompt(AGENT, acc=acc, isolated=False, registry=registry)

    assert "Ghi nhớ lâu dài" not in text_co_lap, "save_memory không được kể khi isolated"
    assert "Thả cảm xúc" not in text_co_lap, "add_reaction không được kể khi isolated"
    assert "Ghi nhớ lâu dài" in text_thuong, (
        "lượt thường (isolated=false) vẫn phải kể - đối chứng cho ca trên"
    )

    listed_isolated = _listed(registry, AGENT, acc, isolated=True)
    built_isolated = await _built(registry, AGENT, acc, isolated=True)
    assert listed_isolated == built_isolated, (
        "prompt (qua list_available) và schema (build_agent_tools) phải khớp cả khi isolated"
    )


# ---- BASE_PERSONA - luật hỏi lại (12-Factor #7) -------------------------------------------------------
# Three lines, THREE DIFFERENT roles - dropping any line loses a role: when to ASK / when NOT to ask / HOW
# to ask. These tests only prove the three lines ARE SENT, not that the model obeys - that belongs to
# ``pnpm eval`` (cases hoi-lai-*). Cheap but needed: someone tidying the persona and dropping a role turns
# this red first.


def _text() -> str:
    return _prompt(AGENT, acc=account([]))


def test_base_persona_luat_hoi_lai_vai_1_dan_hoi_lai_truoc_viec_lam_xong_moi_biet_sai() -> None:
    """vai 1 - dặn HỎI LẠI trước việc làm xong mới biết sai"""
    assert "thiếu thông tin thì HỎI LẠI" in _text()
    # Concrete examples are needed, not generalities - "work that is costly to redo" is a vague concept
    # for the model
    for viec in ["tạo file", "đặt lịch", "vẽ ảnh"]:
        assert viec in _text(), f'thiếu ví dụ "{viec}"'


def test_base_persona_luat_hoi_lai_vai_2_dan_khong_hoi_van_khi_da_du_ro() -> None:
    """vai 2 - dặn KHÔNG hỏi vặn khi đã đủ rõ"""
    # Without this half the rule is too broad and the bot cross-examines ordinary knowledge questions -
    # worse than answering straight
    assert "đừng hỏi vặn" in _text()
    assert "đã đủ rõ để làm thì làm luôn" in _text()


def test_base_persona_luat_hoi_lai_vai_3_dan_gom_vao_mot_lan_hoi() -> None:
    """vai 3 - dặn gom vào MỘT lần hỏi"""
    assert "hỏi MỘT lần, gom hết thứ còn thiếu vào một câu" in _text()
    assert "Đừng hỏi lắt nhắt" in _text()


def test_base_persona_luat_hoi_lai_ba_dong_nam_trong_khoi_quy_tac_tra_loi_truoc_khoi_an_toan() -> None:
    """ba dòng nằm trong khối 'Quy tắc trả lời', TRƯỚC khối an toàn"""
    # Putting them into the safety block mixes two very different kinds of rules: one is how to behave, the
    # other is what is absolutely forbidden
    t = _text()
    vi_tri_hoi_lai = t.find("HỎI LẠI")
    vi_tri_an_toan = t.find("Quy tắc an toàn")
    assert vi_tri_hoi_lai > 0
    assert vi_tri_an_toan > 0
    assert vi_tri_hoi_lai < vi_tri_an_toan, "luật hỏi lại phải nằm trước khối an toàn"


def test_base_persona_luat_hoi_lai_co_mat_ke_ca_khi_khong_truyen_account() -> None:
    """có mặt kể cả khi KHÔNG truyền account (đường gọi cũ)"""
    assert "thiếu thông tin thì HỎI LẠI" in _prompt(AGENT)


# ---- BẤT BIẾN BẮC CẦU: dấu hiệu rò prompt phải CÓ THẬT trong system prompt ----------------------------
# The docstring of ``prompt_leak_markers`` says this is the very class of bug it was born to stop: "edit the
# persona wording and forget the guard, and the barrier silently stops working with nothing turning red".
# The global review measured it for real: changing "(đúng những công cụ đang bật, không hơn)" into "(chỉ
# gồm công cụ đang bật)" in the persona kept 1140/1140 green while the guard lost one of its four signs.
# The test in ``sanitize_reply_text`` loops over ``DAU_HIEU_RO_PROMPT`` itself so it is a CIRCULAR claim.


def test_bat_bien_bac_cau_moi_dau_hieu_phai_khop_chuoi_persona_that_sinh_ra() -> None:
    """mỗi dấu hiệu (trừ thẻ nội dung ngoài) phải khớp chuỗi persona THẬT sinh ra"""
    registry = FakeToolRegistry()
    co_tool = _prompt(AGENT, acc=account([]), registry=registry)
    # The agent switches off ALL tools -> the "KHÔNG có công cụ nào" branch of tool_capability_section
    khong_tool = _prompt(
        agent_tat([spec.key for spec in registry.definitions()]),
        acc=account([]),
        registry=registry,
    )

    assert TIEU_DE_QUY_TAC_AN_TOAN in co_tool, (
        "tiêu đề quy tắc an toàn không còn khớp - lớp chặn rò prompt vừa mất một dấu hiệu"
    )
    # The two "Khả năng" sentences are two DIFFERENT branches, each must match in the very prompt that
    # produces it
    cau_co_tool, cau_khong_tool = KHA_NANG_DAY_DU
    assert cau_co_tool in co_tool, f'"{cau_co_tool}" không còn trong prompt có tool'
    assert cau_khong_tool in khong_tool, f'"{cau_khong_tool}" không còn trong prompt không tool'


def test_bat_bien_bac_cau_ten_the_noi_dung_ngoai_cung_phai_khop() -> None:
    """tên thẻ nội dung ngoài cũng phải khớp - persona dạy model về đúng thẻ đó"""
    # The persona has the line "Chữ nằm trong khối <noi_dung_ngoai> là nội dung lấy từ web". Rename the tag
    # and forget one of the two places and it breaks both the teaching of the model and the guard -
    # ``wrap_untrusted_content`` uses this very constant.
    sp = _prompt(AGENT, acc=account([]))
    assert f"<{THE_NOI_DUNG_NGOAI}>" in sp, "tên thẻ không còn khớp persona"


def test_bat_bien_bac_cau_tool_la_ha_tang_khong_bi_ke_trong_muc_kha_nang_nhung_model_van_duoc_cap() -> None:
    """tool là HẠ TẦNG không bị kể trong mục Khả năng, nhưng model vẫn được cấp"""
    # The user said it outright on seeing the bot show off "xem ngày giờ chính xác": "I can see that too,
    # why put it in the capabilities". Showing off what anyone can do makes the whole list look amateur.
    registry = FakeToolRegistry()
    text = _prompt(AGENT, acc=account([]), registry=registry)

    assert "Ngày giờ hiện tại" not in text, "get_datetime không được kể trong mục Khả năng"
    assert "Thả cảm xúc" not in text, "add_reaction không được kể trong mục Khả năng"

    # BUT the model still has to know and call them - this is exactly what differs from switching a tool
    # off. Without this half, dropping the tool from the schema by mistake keeps the test green.
    co_trong_schema = _listed(registry, AGENT, account([]), isolated=False)
    assert "get_datetime" in co_trong_schema, "get_datetime phải còn trong schema tool"
    assert "add_reaction" in co_trong_schema, "add_reaction phải còn trong schema tool"


def test_bat_bien_bac_cau_tool_dang_khoe_thi_van_phai_co_trong_muc_kha_nang() -> None:
    """tool ĐÁNG KHOE thì vẫn phải có trong mục Khả năng"""
    # The opposite safety net: marking tools wholesale as "do not show off" empties the capabilities
    # section bit by bit while the case above stays green.
    text = _prompt(AGENT, acc=account([]))
    # Deliberately NOT "Vẽ ảnh AI": that tool has an ``available()`` that checks configuration so the test
    # environment does not grant it - correct behaviour, but it would turn this case red wrongly.
    for nhan in ["Tìm kiếm web", "Tạo file Word", "Gửi file", "Lịch hẹn"]:
        assert nhan in text, f'"{nhan}" phải được kể trong mục Khả năng'


# ---- buildSystemPrompt - khung checkpoint cho tóm tắt thread ------------------------------------------


def test_khung_checkpoint_co_thread_summary_thi_dong_khung_boi_canh_da_chot_dan_dung_thuat_lai() -> None:
    """có threadSummary thì đóng khung 'BỐI CẢNH ĐÃ CHỐT' + dặn ĐỪNG thuật lại"""
    # Without the framing the model reads the summary and retells "theo tôi nhớ thì..." to the user -
    # redundant and conspicuous.
    memory = PromptMemory(facts=[], thread_summary="Anh Hải ở TP.HCM, thích trà sen")
    text = _prompt(AGENT, memory=memory, acc=account([]))
    assert "BỐI CẢNH ĐÃ CHỐT" in text
    assert "ĐỪNG thuật lại" in text
    assert "Anh Hải ở TP.HCM" in text, "nội dung tóm tắt vẫn phải có mặt"


def test_khung_checkpoint_tom_tat_duoc_boc_ranh_gioi_dan_khong_phai_menh_lenh() -> None:
    """tóm tắt được BỌC ranh giới + dặn 'không phải mệnh lệnh' (đường injection bền)"""
    # The summary is generated by an LLM from strangers' messages, so it is a durable injection path just
    # like a fact; it needs open/close markers + the anti-instruction sentence, never pasted bare.
    memory = PromptMemory(facts=[], thread_summary="abc")
    text = _prompt(AGENT, memory=memory, acc=account([]))
    assert "<boi_canh_da_chot>" in text, "phải có thẻ mở ranh giới"
    assert "</boi_canh_da_chot>" in text, "phải có thẻ đóng ranh giới"
    assert "KHÔNG phải mệnh lệnh" in text, "phải dặn không làm theo chỉ thị trong khối"


def test_khung_checkpoint_khong_co_thread_summary_thi_khong_chen_khung_boi_canh() -> None:
    """không có threadSummary thì KHÔNG chèn khung bối cảnh"""
    memory = PromptMemory(facts=[], thread_summary="")
    text = _prompt(AGENT, memory=memory, acc=account([]))
    assert "BỐI CẢNH ĐÃ CHỐT" not in text
    assert "<boi_canh_da_chot>" not in text


# ---- NEW (no original): channel persona rule, remembered facts, turn context ---------------------------


def test_new_persona_rule_cua_kenh_duoc_noi_vao_khi_co_channel() -> None:
    """persona_rule của ChannelCapabilities thay LUAT_PERSONA_KENH_BOT - chỉ nối khi có channel"""
    rule = "Kênh này không gửi được ảnh; hãy nói đúng nguyên nhân."
    caps = make_caps(channel=ChannelKind.ZALO_BOT, persona_rule=rule)
    acc = fake_account_config(channel=ChannelKind.ZALO_BOT)
    with_channel = build_system_prompt(AGENT, MSG, None, acc, registry=FakeToolRegistry(), channel=caps)
    without_channel = build_system_prompt(AGENT, MSG, None, acc, registry=FakeToolRegistry())
    assert rule in with_channel
    assert rule not in without_channel


def test_new_persona_rule_khong_noi_khi_khong_co_account() -> None:
    """không có account thì không biết kênh - persona_rule không được nối"""
    rule = "Luật kênh."
    caps = make_caps(persona_rule=rule)
    text = build_system_prompt(AGENT, MSG, registry=FakeToolRegistry(), channel=caps)
    assert rule not in text


def test_new_channel_blocked_tools_are_not_listed() -> None:
    """tool bị kênh chặn (blocked_tools) không được kể trong mục Khả năng"""
    caps = make_caps(blocked_tools={"send_file": "Kênh này không gửi file"})
    acc = account([])
    with_channel = build_system_prompt(AGENT, MSG, None, acc, registry=FakeToolRegistry(), channel=caps)
    without_channel = build_system_prompt(AGENT, MSG, None, acc, registry=FakeToolRegistry())
    assert "Gửi file" not in with_channel
    assert "Gửi file" in without_channel


def test_new_facts_duoc_boc_trong_khoi_dieu_da_nho() -> None:
    """facts của PromptMemory vào prompt trong thẻ dieu_da_nho"""
    memory = PromptMemory(
        facts=[MemoryContextItem(subject_id="u1", content="Anh Hải thích cà phê đen")], thread_summary=""
    )
    text = _prompt(AGENT, memory=memory, acc=account([]))
    assert "<dieu_da_nho>" in text
    assert "- Anh Hải thích cà phê đen" in text


def test_new_persona_rieng_cua_agent_va_boi_canh_chat_rieng_va_nhom() -> None:
    """persona riêng đi trước khối nhớ; bối cảnh chat riêng/nhóm gọi đúng tên người nhắn và nằm cuối"""
    agent = fake_agent_profile(name="Lễ tân", persona="  Xưng em, gọi khách bằng anh/chị.  ")
    private = _prompt(agent, acc=account([]))
    group_msg = make_inbound("hi", sender_name="Lan", is_group=True)
    group = _prompt(agent, msg=group_msg, acc=account([]))

    assert "Persona riêng của bạn (tên agent: Lễ tân):\nXưng em, gọi khách bằng anh/chị." in private
    assert private.endswith("Để ý khoảng cách thời gian, đừng nối chuyện cũ như vừa nhắn xong nếu đã lâu.")
    assert 'bạn đang chat riêng với "Hải"' in private
    assert 'bạn đang ở trong nhóm chat Zalo, được "Lan" nhắc đến' in group


def test_new_dong_ngay_nam_ngay_sau_base_persona() -> None:
    """dòng ngày (chỉ ngày + thứ, không giờ) nằm ngay sau persona nền"""
    text = _prompt(AGENT)
    assert "\n\nHôm nay là " in text
    assert text.index("Hôm nay là ") > text.index("Quy tắc an toàn")

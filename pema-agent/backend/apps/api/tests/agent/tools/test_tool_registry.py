# ported from: src/agent/tools/tool-registry.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

Forced deviations: the ``setupTestEnv`` SQLite database is replaced by the in-memory ``RuntimeSettingsKv`` (image
settings), a ``StaticTuningProvider`` (``SCHEDULER_ENABLED``) and a flag standing for the sidecar of
``runtime-vision-settings`` (``ToolDeps.sidecar_configured``); the ``loai`` of the account is the channel capability
of the channel object (``ToolScope.channel``); ``buildAgentTools`` is async (policy hook).

Plus the new cases of the policy profile (PLAN-AI01 section 5): ``patient_channel`` receives no image, video,
document or web tool, ``staff_assistant`` receives them exactly as in the original.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence

import pytest

from pema.agent.tools.testing import (
    FakeKbAvailability,
    RecordingChannel,
    bot_capabilities,
    make_channel,
    make_scope,
    make_tool_context,
    make_tool_deps,
    personal_capabilities,
)
from pema.agent.tools.tool_catalog import TOOL_KEYS
from pema.agent.tools.tool_policy_tags import TOOL_POLICY_TAGS, tool_keys_blocked_in_patient_channel
from pema.agent.tools.tool_registry import DefaultToolRegistry
from pema.config.runtime_image_settings import (
    ImageSettingsUpdate,
    clear_image_settings,
    update_image_settings,
)
from pema.config.runtime_settings_kv import reset_runtime_settings_kv
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.policy import (
    MEDIA_AND_WEB_TOOL_KEYS,
    PermissivePolicyHooks,
    PolicyContext,
    PolicyProfileKey,
)
from pema_contracts.tools import AgentTool, ToolContext, ToolGroup

GATED_TOOLS = ("read_image", "create_image", "kb_search")
"""Tools that enter the schema only when their own infrastructure is ready. ``kb_search`` is one of them: the test
agent has no Knowledge source bound here, so its ``available()`` is false: the default behaviour (a newly created
agent cannot read any document)."""


class _Sidecar:
    configured = False

    def __call__(self) -> bool:
        return self.configured


class _Env:
    def __init__(self) -> None:
        self.sidecar = _Sidecar()
        self.kb = FakeKbAvailability()
        self.deps = make_tool_deps(sidecar_configured=self.sidecar, kb_availability=self.kb)
        self.registry = DefaultToolRegistry(self.deps)

    async def build(
        self,
        disabled_tools: Sequence[str] = (),
        agent_disabled: Sequence[str] = (),
        *,
        isolated: bool = False,
        channel: RecordingChannel | None = None,
        profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
    ) -> Mapping[str, AgentTool]:
        ctx = self.context(
            disabled_tools, agent_disabled, isolated=isolated, channel=channel, profile=profile
        )
        return await self.registry.build_agent_tools(ctx)

    def context(
        self,
        disabled_tools: Sequence[str] = (),
        agent_disabled: Sequence[str] = (),
        *,
        isolated: bool = False,
        channel: RecordingChannel | None = None,
        profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
    ) -> ToolContext:
        """Two DISJOINT disabled lists, because that is exactly what is being checked: ``disabled_tools`` is the
        POLICY of the Zalo account, ``agent_disabled`` is the CAPABILITY of the agent, and a usable tool is the part
        neither disables."""
        return make_tool_context(
            channel=channel,
            profile=profile,
            isolated=isolated,
            account_patch={"disabled_tools": list(disabled_tools)},
            agent_patch={"disabled_tools": list(agent_disabled)},
        )


@pytest.fixture(autouse=True)
def _cipher_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PEMA_SECRET_ENCRYPTION_KEY", "00" * 32)


@pytest.fixture
async def env() -> AsyncIterator[_Env]:
    reset_runtime_settings_kv()
    reset_tuning_provider()
    yield _Env()
    reset_runtime_settings_kv()
    reset_tuning_provider()


async def _configure_image_gen() -> None:
    await update_image_settings(
        ImageSettingsUpdate(base_url="https://router.test", model="cx/gpt-5.5-image", api_key="sk-x")
    )


async def test_tool_registry_default_builds_the_whole_catalogue_except_tools_without_infrastructure(
    env: _Env,
) -> None:
    """mặc định (không tắt gì) build đủ catalog TRỪ các tool chưa có hạ tầng"""
    tools = await env.build()
    expected = [k for k in TOOL_KEYS if k not in GATED_TOOLS]
    assert sorted(tools) == sorted(expected)
    # The core tools must be present: changing a key makes the model "forget" the tool
    for key in ("get_datetime", "web_search", "web_fetch", "add_reaction", "send_file"):
        assert key in tools, f"thiếu tool {key}"


async def test_tool_registry_read_image_enters_the_schema_only_when_the_sidecar_is_configured(
    env: _Env,
) -> None:
    """read_image chỉ vào schema khi sidecar đã cấu hình (kiểm mỗi lượt, không cần restart)"""
    env.sidecar.configured = True
    assert "read_image" in await env.build(), "có sidecar phải có tool"
    env.sidecar.configured = False
    assert "read_image" not in await env.build()


async def test_tool_registry_read_image_disabled_per_account_stays_out_even_with_a_sidecar(env: _Env) -> None:
    """read_image bị tắt per account thì kể cả có sidecar cũng không vào schema"""
    env.sidecar.configured = True
    assert "read_image" not in await env.build(["read_image"])


async def test_tool_registry_a_disabled_tool_vanishes_from_the_schema_the_model_does_not_know_it_exists(
    env: _Env,
) -> None:
    """tool bị tắt biến mất khỏi schema - model không biết nó tồn tại"""
    tools = await env.build(["web_search", "send_file"])
    assert "web_search" not in tools
    assert "send_file" not in tools
    assert "get_datetime" in tools, "tool không tắt vẫn phải còn"


async def test_tool_registry_create_image_enters_the_schema_only_when_the_endpoint_is_configured(
    env: _Env,
) -> None:
    """create_image chỉ vào schema khi đã cấu hình endpoint vẽ ảnh"""
    await clear_image_settings()
    assert "create_image" not in await env.build()
    await _configure_image_gen()
    assert "create_image" in await env.build(), "có cấu hình phải có tool"
    await clear_image_settings()


async def test_tool_registry_create_image_disabled_per_account_stays_out_even_when_configured(
    env: _Env,
) -> None:
    """create_image bị tắt per account thì kể cả đã cấu hình cũng không vào schema"""
    await _configure_image_gen()
    assert "create_image" not in await env.build(["create_image"])


async def test_tool_registry_schedule_task_enters_the_schema_only_when_scheduler_enabled_is_on(
    env: _Env,
) -> None:
    """schedule_task chỉ vào schema khi SCHEDULER_ENABLED bật (kiểm mỗi lượt, không cần restart)"""
    assert "schedule_task" in await env.build(), "mặc định SCHEDULER_ENABLED=true phải có tool"
    install_tuning_provider(StaticTuningProvider({"SCHEDULER_ENABLED": False}))
    assert "schedule_task" not in await env.build(), "tắt cờ thì tool phải biến mất"


async def test_tool_registry_an_unknown_key_in_disabled_tools_does_not_crash_nor_affect_other_tools(
    env: _Env,
) -> None:
    """key lạ trong disabledTools không làm crash, không ảnh hưởng tool khác"""
    tools = await env.build(["khong-ton-tai"])
    # 3 conditional tools are absent for lack of configuration, the rest is complete
    assert len(tools) == len(TOOL_KEYS) - len(GATED_TOOLS)


# ===== Two filter layers: the agent declares capability, the account applies policy =====
# Invariant: a usable tool is the part NEITHER disables. Neither can switch the other back on: adding a new agent
# can never widen the rights of an account, even when that agent was created carelessly.


async def test_tool_registry_agent_disables_a_tool_it_is_gone_even_if_the_account_enables_it(
    env: _Env,
) -> None:
    """agent tắt tool thì mất, dù account bật"""
    tools = await env.build([], ["web_search"])
    assert "web_search" not in tools, "agent tắt phải thắng"
    assert "web_fetch" in tools, "tool agent không tắt vẫn phải còn"


async def test_tool_registry_account_disables_a_tool_it_is_gone_even_if_the_agent_enables_it(
    env: _Env,
) -> None:
    """account tắt tool thì mất, dù agent bật"""
    tools = await env.build(["web_search"], [])
    assert "web_search" not in tools, "account tắt phải thắng"


async def test_tool_registry_both_disabling_the_same_tool_loses_it_once_without_error(env: _Env) -> None:
    """cả hai cùng tắt một tool cũng chỉ mất một lần, không lỗi"""
    tools = await env.build(["web_search"], ["web_search"])
    assert "web_search" not in tools
    assert "get_datetime" in tools, "phần còn lại không bị ảnh hưởng"


async def test_tool_registry_two_sides_disabling_two_different_tools_loses_both_an_intersection_not_an_override(
    env: _Env,
) -> None:
    """hai bên tắt hai tool KHÁC nhau thì mất cả hai - đây là phép giao, không phải ghi đè"""
    tools = await env.build(["send_file"], ["web_search"])
    assert "send_file" not in tools, "account tắt send_file"
    assert "web_search" not in tools, "agent tắt web_search"
    # Proof it is not "one side overrides the other": if it were, one of the two tools above would still be alive.
    assert len(tools) == len(TOOL_KEYS) - len(GATED_TOOLS) - 2, "phải mất ĐÚNG 2 tool"


async def test_tool_registry_nobody_disabling_anything_gives_the_full_set_the_control_for_the_4_cases_above(
    env: _Env,
) -> None:
    """không bên nào tắt thì đủ bộ - đối chứng cho 4 ca trên"""
    tools = await env.build([], [])
    assert len(tools) == len(TOOL_KEYS) - len(GATED_TOOLS)


async def test_tool_registry_an_unknown_key_in_the_agent_disabled_list_does_not_crash_either(
    env: _Env,
) -> None:
    """key lạ trong danh sách tắt của AGENT cũng không làm crash"""
    tools = await env.build([], ["khong-ton-tai-2"])
    assert len(tools) == len(TOOL_KEYS) - len(GATED_TOOLS)


# 10 tools are removed from a scheduled turn, 2 groups of reasons (see ToolSpec.runs_in_scheduled_turn): missing
# infrastructure for an isolated turn (add_reaction, read_image, save_memory, schedule_task) and sending straight
# through the queue so they could dodge the daily cap (send_file, create_word_document, create_excel_file,
# create_image, tai_video, tag_member).
TOOL_LOAI_KHOI_LICH = [
    "add_reaction",
    "read_image",
    "save_memory",
    "schedule_task",
    "send_file",
    "create_word_document",
    "create_excel_file",
    "create_image",
    "tai_video",
    "tag_member",
]


async def test_tool_registry_isolated_true_scheduled_turn_removes_all_10_even_when_infrastructure_is_ready(
    env: _Env,
) -> None:
    """isolated:true (lượt theo lịch) loại đủ 10 tool kể cả khi hạ tầng/cấu hình đã sẵn sàng

    Configure the sidecar and the image endpoint FIRST to prove ``read_image`` / ``create_image`` are removed
    because of ``runs_in_scheduled_turn``, not for lack of configuration: otherwise this test could not tell the two
    causes apart.
    """
    env.sidecar.configured = True
    await _configure_image_gen()
    tools = await env.build([], isolated=True)
    for key in TOOL_LOAI_KHOI_LICH:
        assert key not in tools, f"lượt theo lịch không được có tool {key}"
    assert "get_datetime" in tools, "tool không liên quan tới isolated vẫn phải có mặt"
    assert "web_search" in tools, "web_search không nằm trong danh sách loại"


async def test_tool_registry_isolated_absent_or_false_gives_all_10_message_turn_behaviour_unchanged(
    env: _Env,
) -> None:
    """isolated không truyền (mặc định) hoặc false thì đủ cả 10 tool - hành vi lượt tin nhắn không đổi"""
    env.sidecar.configured = True
    await _configure_image_gen()
    for tools in (await env.build([]), await env.build([], isolated=False)):
        for key in TOOL_LOAI_KHOI_LICH:
            assert key in tools, f"{key} phải còn khi không cô lập (đã cấu hình đủ hạ tầng)"


async def test_tool_registry_runs_in_scheduled_turn_is_false_for_exactly_those_10_tools(env: _Env) -> None:
    """runsInScheduledTurn khai đúng false cho đúng 10 tool, còn lại mặc định undefined (coi như true)"""
    bi_loai = [t.key for t in env.registry.definitions() if not t.runs_in_scheduled_turn]
    assert sorted(bi_loai) == sorted(TOOL_LOAI_KHOI_LICH)


async def test_tool_registry_catalogue_unique_keys_ui_metadata_and_a_valid_group(env: _Env) -> None:
    """catalog: key duy nhất, đủ metadata cho UI, nhóm hợp lệ"""
    keys = [t.key for t in env.registry.definitions()]
    assert len(set(keys)) == len(keys), "key tool phải duy nhất"
    for spec in env.registry.definitions():
        assert spec.label
        assert spec.description, f"tool {spec.key} thiếu label/description cho UI"
        assert spec.group in (ToolGroup.READ, ToolGroup.ACTION)


async def test_tool_registry_catalogue_keys_equal_the_builtin_tool_keys_of_the_contract(env: _Env) -> None:
    """tên tool không đổi: catalog khớp BUILTIN_TOOL_KEYS của contract (ca bổ sung cho Python)"""
    assert sorted(t.key for t in env.registry.definitions()) == sorted(TOOL_KEYS)
    assert len(TOOL_KEYS) == 15


# ===== The channel: a platform limit beats every configuration (kiemTraKhaDung) =====


async def test_tool_registry_a_bot_channel_turn_never_receives_the_8_tools_it_cannot_run(env: _Env) -> None:
    """kênh BOT: 8 tool không chạy được bị loại trước mọi cấu hình, hint nói lý do"""
    env.sidecar.configured = True
    await _configure_image_gen()
    channel = RecordingChannel(caps=bot_capabilities())
    tools = await env.build([], channel=channel)
    for key in bot_capabilities().blocked_tools:
        assert key not in tools, f"kênh bot không được có {key}"
    assert "get_datetime" in tools
    availability = env.registry.check_availability(
        next(t for t in env.registry.definitions() if t.key == "send_file"),
        make_scope(channel=bot_capabilities()),
    )
    assert availability.usable is False
    assert availability.hint == "Zalo Bot API không hỗ trợ"


async def test_tool_registry_check_availability_reports_the_hint_of_missing_infrastructure(env: _Env) -> None:
    """check_availability trả hint khi thiếu hạ tầng, là nguồn duy nhất cho GET /admin/tools"""
    spec = next(t for t in env.registry.definitions() if t.key == "read_image")
    scope = make_scope(channel=personal_capabilities())
    off = env.registry.check_availability(spec, scope)
    assert off.usable is False
    assert off.hint == "Bấm Settings để cấu hình model sidecar đọc ảnh"
    env.sidecar.configured = True
    assert env.registry.check_availability(spec, scope).usable is True


# ===== NEW: policy profiles (PLAN-AI01 section 5) =====


async def test_tool_registry_patient_channel_receives_no_media_or_web_tool_even_when_everything_is_configured(
    env: _Env,
) -> None:
    """patient_channel: không nhận tool ảnh/video/tài liệu/web dù hạ tầng đã sẵn sàng và hook là mặc định"""
    env.sidecar.configured = True
    await _configure_image_gen()
    tools = await env.build([], profile=PolicyProfileKey.PATIENT_CHANNEL)
    for key in MEDIA_AND_WEB_TOOL_KEYS:
        assert key not in tools, f"patient_channel không được có {key}"
    # Text-only tools stay: nothing is deleted from the feature set, the profile only filters
    for key in (
        "get_datetime",
        "save_memory",
        "schedule_task",
        "add_reaction",
        "tag_member",
        "get_group_info",
    ):
        assert key in tools


async def test_tool_registry_staff_assistant_receives_the_media_and_web_tools_like_zalo_agent(
    env: _Env,
) -> None:
    """staff_assistant: nhận đủ tool ảnh/video/tài liệu/web như zalo-agent gốc"""
    env.sidecar.configured = True
    await _configure_image_gen()
    tools = await env.build([], profile=PolicyProfileKey.STAFF_ASSISTANT)
    for key in MEDIA_AND_WEB_TOOL_KEYS:
        assert key in tools


async def test_tool_registry_policy_tags_cover_the_catalogue_and_match_the_profile_data(env: _Env) -> None:
    """metadata chính sách: mọi tool có thẻ, và tập media|web trùng MEDIA_AND_WEB_TOOL_KEYS của hồ sơ"""
    assert set(TOOL_POLICY_TAGS) == set(TOOL_KEYS)
    assert tool_keys_blocked_in_patient_channel() == MEDIA_AND_WEB_TOOL_KEYS


class _NarrowingHooks(PermissivePolicyHooks):
    """A policy hook that removes one more key (what package P may do beyond the profile data)."""

    async def filter_tool_keys(self, ctx: PolicyContext, keys: frozenset[str]) -> frozenset[str]:
        return keys - {"save_memory"}


async def test_tool_registry_the_policy_hook_can_narrow_the_tool_set_further(env: _Env) -> None:
    """hook filter_tool_keys của gói P có thể loại thêm tool"""
    registry = DefaultToolRegistry(make_tool_deps(policy=_NarrowingHooks()))
    tools = await registry.build_agent_tools(make_tool_context(channel=make_channel()))
    assert "save_memory" not in tools
    assert "get_datetime" in tools


async def test_tool_registry_every_built_tool_has_the_name_of_its_key_and_a_root_object_schema(
    env: _Env,
) -> None:
    """tool dựng ra mang đúng tên key, và tham số gốc là object (ca bổ sung cho Python)"""
    env.sidecar.configured = True
    env.kb.agents.add("agent-test")
    await _configure_image_gen()
    tools = await env.build()
    assert sorted(tools) == sorted(TOOL_KEYS)
    for key, tool in tools.items():
        assert tool.name == key
        assert tool.parameters["type"] == "object"
        assert tool.description

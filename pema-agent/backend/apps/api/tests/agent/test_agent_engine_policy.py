# ported from: none (new: the policy hook call sites and the engine contract of package D1)
"""The engine's side of the policy contract (``pema_contracts.policy`` hook call sites, CONTRACTS section 3) and
of ``AgentEngine`` (``AgentTurnError``, turn row, hand-off), plus the real ``TextGenerator``.

The hooks here are a recording fake: package P's real ``ClinicPolicyHooks`` is tested in its own package; what
this file pins is WHEN the engine calls a hook and what it does with the answer.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

from pema.agent.agent_loop import AgentEngineDeps, DefaultAgentEngine
from pema.agent.model_types import ModelCompletion
from pema.agent.providers.errors import ProviderCallError
from pema.agent.streaming_model_test_helper import ScriptedModel, goi_tool, prompt_text, rong, tra_loi
from pema.agent.testing_engine import ACCOUNT_ID, EngineHarness, fake_account, no_sleep, tin_nhan
from pema.agent.text_generator import ProviderTextGenerator
from pema.config.runtime_tuning_settings import (
    StaticTuningProvider,
    install_tuning_provider,
    reset_tuning_provider,
)
from pema_contracts.agent_turn import AgentTurnRequest, TurnCallbacks
from pema_contracts.channel import ChannelKind, InboundMessage
from pema_contracts.policy import (
    BeforeLlmAction,
    BeforeLlmDecision,
    PermissivePolicyHooks,
    PolicyContext,
    PolicyProfileKey,
)
from pema_contracts.testing import FAKE_CLINIC_ID
from pema_contracts.turn_errors import AgentTurnError, ProviderErrorKind


@pytest.fixture(autouse=True)
def _tuning() -> Iterator[None]:
    install_tuning_provider(StaticTuningProvider({"LLM_MAX_STEPS": 2}))
    yield
    reset_tuning_provider()


@dataclass
class RecordingPolicy(PermissivePolicyHooks):
    """Records every call; ``before`` decides what ``before_llm`` answers (a list: one answer per call)."""

    before: list[BeforeLlmDecision] = field(default_factory=list[BeforeLlmDecision])
    before_calls: list[tuple[PolicyContext, list[str]]] = field(
        default_factory=list[tuple[PolicyContext, list[str]]]
    )
    after_calls: list[tuple[str, str | None]] = field(default_factory=list[tuple[str, str | None]])
    identity_calls: list[tuple[ChannelKind, str]] = field(default_factory=list[tuple[ChannelKind, str]])
    masking: bool = False

    async def before_llm(self, ctx: PolicyContext, batch: Sequence[InboundMessage]) -> BeforeLlmDecision:
        self.before_calls.append((ctx, [m.text for m in batch]))
        index = len(self.before_calls) - 1
        return self.before[index] if index < len(self.before) else BeforeLlmDecision()

    async def after_llm(self, ctx: PolicyContext, text: str, mask_token: str | None) -> str:
        self.after_calls.append((text, mask_token))
        return text.replace("<TEN_1>", "Hải")

    async def verify_identity(self, ctx: PolicyContext, channel: ChannelKind, external_user_id: str) -> Any:
        from pema_contracts.policy import IdentityStatus

        self.identity_calls.append((channel, external_user_id))
        return IdentityStatus(verified=True, patient_id=uuid4())

    # The optional masking methods package P's real hooks expose next to the eight
    def mask_text(self, ctx: PolicyContext, text: str) -> str:
        return text.replace("Hải", "<TEN_1>").replace("Thứ tư", "<NGAY>") if self.masking else text

    def mask_name(self, ctx: PolicyContext, name: str) -> str:
        return "<TEN_1>" if self.masking and name == "Hải" else name


HAND_OFF = BeforeLlmDecision(action=BeforeLlmAction.HAND_OFF, reason="red_flag", red_flags=["sot"])


async def test_before_llm_hand_off_stops_the_turn_before_any_model_call() -> None:
    """HAND_OFF: không gọi model, trả handed_off, caller giữ hand-off"""
    policy = RecordingPolicy(before=[HAND_OFF])
    harness = EngineHarness(policy=policy)
    run = await harness.run([lambda: tra_loi("không được gọi")])
    assert run.model.count == 0
    assert run.result.handed_off is True
    assert run.result.hand_off_reason == "red_flag"
    assert run.result.text == ""
    assert run.result.turn_id == 1
    assert len(policy.before_calls) == 1


async def test_masked_text_replaces_the_batch_text_the_model_sees() -> None:
    """text đã che thay cho text gốc trong prompt gửi model"""
    original = "tôi là Nguyễn Văn Anh số 0900000000"
    policy = RecordingPolicy(
        before=[
            BeforeLlmDecision(masked_text_by_msg_id={"m1": "tôi là <TEN_1> số <SDT_1>"}, mask_token="tok-1")
        ]
    )
    run = await EngineHarness(policy=policy).run([lambda: tra_loi("chào <TEN_1>")], [tin_nhan(original)])
    prompt = prompt_text(run.model.calls[0])
    assert "<TEN_1>" in prompt
    assert "Nguyễn Văn Anh" not in prompt
    assert "0900000000" not in prompt
    # after_llm gets the final text and the mask token of before_llm, and its answer is what is returned
    assert policy.after_calls == [("chào <TEN_1>", "tok-1")]
    assert run.result.text == "chào Hải"


async def test_after_llm_also_covers_the_wrap_up_answer() -> None:
    """after_llm áp cả lên câu trả lời của lượt chốt"""
    policy = RecordingPolicy()
    run = await EngineHarness(policy=policy).run([goi_tool, goi_tool, lambda: tra_loi("Chốt <TEN_1>")])
    assert run.result.text == "Chốt Hải"
    assert policy.after_calls[-1][0] == "Chốt <TEN_1>"


async def test_pii_mask_covers_history_sender_name_facts_summary_and_tool_results() -> None:
    """mask_text/mask_name phủ lịch sử, tên người gửi, fact, tóm tắt và kết quả tool"""
    from pema_contracts.conversation import MemoryContextItem

    policy = RecordingPolicy(masking=True)
    harness = EngineHarness(policy=policy)
    harness.conversation.add_message(
        ACCOUNT_ID, "thread-1", content="Hải nhắn hôm trước", sender_name="Hải", sender_id="user-1"
    )
    harness.conversation.memories = [MemoryContextItem(subject_id="user-1", content="Hải thích thứ bảy")]
    harness.conversation.summaries[(ACCOUNT_ID, "thread-1")] = "Hải đã đặt lịch"
    run = await harness.run([goi_tool, lambda: tra_loi("xong")])
    first = prompt_text(run.model.calls[0])
    assert "Hải" not in first, (
        "tên thật không được tới model: lịch sử, tên người gửi, fact, tóm tắt đều qua mask"
    )
    assert "<TEN_1>" in first
    second = json.dumps(run.model.calls[1].messages, ensure_ascii=False)
    assert "Thứ tư" not in second, "kết quả tool cũng phải qua mask"
    assert "<NGAY>" in second


async def test_verify_identity_is_called_only_when_the_profile_demands_it() -> None:
    """verify_identity chỉ gọi khi hồ sơ đòi xác minh, và kết quả vào PolicyContext của tool"""
    # staff_assistant: no call
    staff = RecordingPolicy()
    await EngineHarness(policy=staff).run([lambda: tra_loi("ok")])
    assert staff.identity_calls == []

    # patient_channel (the restrictive one of account/agent wins): one call, answer carried to the tools
    patient = RecordingPolicy()
    harness = EngineHarness(
        policy=patient,
        account=fake_account(policy_profile=PolicyProfileKey.PATIENT_CHANNEL),
    )
    seen: list[PolicyContext] = []

    registry = harness.registry
    original = registry.build_agent_tools

    async def spy(ctx: Any) -> Any:
        seen.append(ctx.policy)
        return await original(ctx)

    registry.build_agent_tools = spy  # type: ignore[method-assign]
    await harness.run([lambda: tra_loi("ok")])
    assert patient.identity_calls == [(ChannelKind.ZALO_PERSONAL, "user-1")]
    assert len(seen) >= 1
    assert seen[0].identity_verified is True
    assert seen[0].patient_id is not None
    assert seen[0].profile.key is PolicyProfileKey.PATIENT_CHANNEL


async def test_scheduled_turn_does_not_verify_identity() -> None:
    """lượt theo lịch không có người nhắn nên không xác minh danh tính"""
    patient = RecordingPolicy()
    harness = EngineHarness(
        policy=patient, account=fake_account(policy_profile=PolicyProfileKey.PATIENT_CHANNEL)
    )
    await harness.run([lambda: tra_loi("ok")], isolated=True)
    assert patient.identity_calls == []


async def test_mid_turn_message_goes_through_before_llm_and_its_mask() -> None:
    """tin chèn giữa lượt cũng qua before_llm và dùng text đã che"""
    policy = RecordingPolicy(
        before=[
            BeforeLlmDecision(),
            BeforeLlmDecision(masked_text_by_msg_id={"m-chen": "đổi sang <TEN_1> nhé"}),
        ]
    )
    state = {"n": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["n"] += 1
        return [tin_nhan("đổi sang Nguyễn Văn Anh nhé", msg_id="m-chen")] if state["n"] == 2 else []

    run = await EngineHarness(policy=policy).run([goi_tool, lambda: tra_loi("ok")], fetch_injected=fetch)
    assert len(policy.before_calls) == 2
    assert policy.before_calls[1][1] == ["đổi sang Nguyễn Văn Anh nhé"]
    later = prompt_text(run.model.calls[1])
    assert "đổi sang <TEN_1> nhé" in later
    assert "Nguyễn Văn Anh" not in later


async def test_mid_turn_hand_off_discards_the_model_answer() -> None:
    """tin chen kích hoạt HAND_OFF: dừng lượt, bỏ câu trả lời của model"""
    policy = RecordingPolicy(before=[BeforeLlmDecision(), HAND_OFF])
    state = {"n": 0}

    async def fetch() -> Sequence[InboundMessage]:
        state["n"] += 1
        return [tin_nhan("chảy máu nhiều", msg_id="m-chen")] if state["n"] == 2 else []

    run = await EngineHarness(policy=policy).run(
        [goi_tool, lambda: tra_loi("không được gửi đi")], fetch_injected=fetch
    )
    assert run.result.handed_off is True
    assert run.result.text == ""
    assert "chảy máu nhiều" not in "".join(prompt_text(c) for c in run.model.calls)
    assert run.model.count == 1, "lượt dừng ngay sau step có tool, không gọi model thêm"


# ------------------------------------------------------------------------------------ the engine contract


async def test_turn_row_is_opened_and_returned_and_a_caller_turn_id_is_respected() -> None:
    """lượt được mở ở usage và trả turn_id; caller đã mở sẵn thì engine không mở thêm"""
    harness = EngineHarness()
    run = await harness.run([lambda: tra_loi("ok")])
    assert run.result.turn_id == 1
    assert [(a, t) for a, t, _source in harness.conversation.opened_turns] == [(ACCOUNT_ID, "thread-1")]

    harness2 = EngineHarness()
    engine = DefaultAgentEngine(harness2.deps(ScriptedModel([lambda: tra_loi("ok")])))
    result = await engine.run_turn(
        AgentTurnRequest(clinic_id=FAKE_CLINIC_ID, account_id=ACCOUNT_ID, batch=[tin_nhan()], turn_id=77)
    )
    assert result.turn_id == 77
    assert harness2.conversation.opened_turns == []


async def test_failure_carries_the_turn_id_the_kind_and_the_original_cause() -> None:
    """lỗi mang turn_id, kind đã phân loại và nguyên nhân gốc"""
    with pytest.raises(AgentTurnError) as caught:
        await EngineHarness().run([lambda: ProviderCallError("sai key", status_code=401)])
    assert caught.value.turn_id == 1
    assert caught.value.kind is ProviderErrorKind.AUTH
    assert isinstance(caught.value.__cause__, ProviderCallError)
    assert "sai key" in caught.value.safe_message


async def test_unknown_account_is_a_config_error() -> None:
    """account không tồn tại là lỗi cấu hình, không phải lỗi lạ"""
    harness = EngineHarness()
    deps: AgentEngineDeps = harness.deps(ScriptedModel([lambda: tra_loi("ok")]))
    engine = DefaultAgentEngine(deps)
    with pytest.raises(AgentTurnError) as caught:
        await engine.run_turn(
            AgentTurnRequest(clinic_id=FAKE_CLINIC_ID, account_id="khong-co", batch=[tin_nhan()])
        )
    assert caught.value.kind is ProviderErrorKind.CONFIG


async def test_trace_is_appended_to_the_callers_list_and_survives_a_failure() -> None:
    """trace do caller sở hữu: engine chỉ nối vào, lượt hỏng vẫn còn"""
    cb = TurnCallbacks()
    state = {"n": 0}

    def step() -> ModelCompletion | Exception:
        state["n"] += 1
        return (
            goi_tool() if state["n"] == 1 else ProviderCallError("hỏng", status_code=500, is_retryable=False)
        )

    with pytest.raises(AgentTurnError):
        await EngineHarness().run([step], callbacks=cb)
    assert len(cb.trace) == 1


# ------------------------------------------------------------------------------------ TextGenerator


def _generator(model: ScriptedModel) -> ProviderTextGenerator:
    return ProviderTextGenerator(
        resolve_model=lambda _o, _t: model, sleep=no_sleep, retry_initial_delay_s=0.0
    )


async def test_text_generator_returns_text_and_flags_truncation() -> None:
    """TextGenerator trả text và cờ truncated khi chạm trần token"""
    cut = ModelCompletion(text="dở dang", finish_reason="length", model_id="m")
    out = await _generator(ScriptedModel([lambda: cut])).generate_text("tóm tắt giúp", max_output_tokens=512)
    assert (out.text, out.truncated) == ("dở dang", True)
    ok = await _generator(ScriptedModel([lambda: tra_loi("gọn")])).generate_text("tóm tắt giúp")
    assert (ok.text, ok.truncated) == ("gọn", False)


async def test_text_generator_sends_a_toolless_single_step_request_with_the_original_limits() -> None:
    """TextGenerator: không tool, không system, max 1024 mặc định, streaming qua chay_stream"""
    model = ScriptedModel([lambda: tra_loi("x")])
    await _generator(model).generate_text("prompt")
    request = model.calls[0]
    assert request.tools == []
    assert request.system == ""
    assert request.max_output_tokens == 1024
    assert request.messages == [{"role": "user", "content": "prompt"}]


async def test_text_generator_retries_exactly_once() -> None:
    """maxRetries=1: lỗi tạm thử lại đúng một lần rồi mới ném AgentTurnError"""
    model = ScriptedModel([lambda: ProviderCallError("503", status_code=503)])
    with pytest.raises(AgentTurnError) as caught:
        await _generator(model).generate_text("p")
    assert model.count == 2
    assert caught.value.kind is ProviderErrorKind.TRANSIENT

    state = {"n": 0}

    def flaky() -> ModelCompletion | Exception:
        state["n"] += 1
        return ProviderCallError("503", status_code=503) if state["n"] == 1 else tra_loi("được rồi")

    assert (await _generator(ScriptedModel([flaky])).generate_text("p")).text == "được rồi"


async def test_empty_router_completion_after_retry_answers_with_the_fallback_and_no_policy_after_call() -> (
    None
):
    """router rỗng hai lần: câu báo lỗi chung, không đi qua after_llm"""
    policy = RecordingPolicy()
    run = await EngineHarness(policy=policy).run([rong])
    assert run.result.text
    assert policy.after_calls == []

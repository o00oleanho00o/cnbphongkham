"""Depth classifier D1-D5 (package M, step M2b). New tests (no zalo-agent original).

No database and no real model: the "model" is ``FakeDepthLlm``, which counts its calls. Every text is
synthetic. The point of most tests is the ORDER: red flags first and without a model, rules for D1, the model
last, and a safe fallback when the model is missing.
"""

from __future__ import annotations

import json

import pytest

from pema.care.depth import (
    EVENT_DEPTH,
    DepthClassifier,
    DepthSource,
    TextGeneratorDepthLlm,
    administrative_intent,
    text_signals,
)
from pema.care.events import CareEvent, EventKind, Initiator
from pema.care.handoff_types import Depth, DepthLlmOutput
from pema.care.testing import FakeDepthLlm, vn
from pema.policy.text_normalize import fold_text
from pema_contracts.agent_turn import GeneratedText


def message() -> CareEvent:
    return CareEvent(
        kind=EventKind.PATIENT_MESSAGE,
        initiator=Initiator.PATIENT,
        patient_ref="P900",
        occurred_at=vn(2026, 10, 3, 9, 0),
    )


def answer(depth: Depth = Depth.D2, confidence: float = 0.9, **extra: object) -> DepthLlmOutput:
    return DepthLlmOutput.model_validate({"depth": depth.value, "confidence": confidence, **extra})


# ---------------------------------------------------------------------------------- red flags
@pytest.mark.parametrize(
    "text",
    [
        "em bị chảy máu nhiều ở vết tiêm",
        "chay mau khong ngung",
        "sau laser em bị sốt 39 độ",
        "em khó thở quá",
    ],
)
async def test_a_red_flag_is_d5_at_once_and_the_model_is_not_called(text: str) -> None:
    llm = FakeDepthLlm(answer(Depth.D1))
    result = await DepthClassifier(llm).classify(message(), [text])
    assert result.depth is Depth.D5
    assert result.source is DepthSource.RED_FLAG
    assert result.confidence == 1.0
    assert result.red_flags
    assert llm.calls == []


async def test_a_red_flag_in_any_message_of_the_batch_makes_it_d5() -> None:
    llm = FakeDepthLlm(answer(Depth.D1))
    result = await DepthClassifier(llm).classify(
        message(), ["cho em hỏi giờ mở cửa", "vết thương mưng mủ rồi"]
    )
    assert result.depth is Depth.D5
    assert llm.calls == []


async def test_a_red_flag_beats_an_administrative_question_in_the_same_message() -> None:
    llm = FakeDepthLlm()
    result = await DepthClassifier(llm).classify(message(), ["đặt lịch giúp em, em đang chảy máu"])
    assert result.depth is Depth.D5


async def test_a_negated_red_flag_is_not_d5() -> None:
    llm = FakeDepthLlm(answer(Depth.D2))
    result = await DepthClassifier(llm).classify(message(), ["em không sốt, da bình thường ạ"])
    assert result.depth is not Depth.D5


async def test_the_model_can_never_produce_d5() -> None:
    llm = FakeDepthLlm(answer(Depth.D5, 0.99))
    result = await DepthClassifier(llm).classify(message(), ["em muốn biết thêm về kem dưỡng này"])
    assert result.depth is Depth.D4  # clamped: D5 belongs to the red-flag rules
    assert result.source is DepthSource.LLM


# -------------------------------------------------------------------------------------- D1 rules
@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("cho em đặt lịch tái khám thứ 6", "booking"),
        ("phòng khám mấy giờ mở cửa vậy ạ", "info"),
        ("địa chỉ phòng khám ở đâu", "info"),
        ("em cần xuất hóa đơn", "payment"),
        ("bảng giá liệu trình nám", "info"),
    ],
)
async def test_administrative_questions_are_d1_by_rules_without_the_model(text: str, intent: str) -> None:
    llm = FakeDepthLlm(answer(Depth.D4))
    result = await DepthClassifier(llm).classify(message(), [text])
    assert (result.depth, result.source, result.intent) == (Depth.D1, DepthSource.RULES, intent)
    assert result.confidence == 1.0
    assert llm.calls == []


async def test_a_booking_question_with_a_symptom_word_is_not_d1() -> None:
    llm = FakeDepthLlm(answer(Depth.D1, 0.95))
    result = await DepthClassifier(llm).classify(message(), ["em muốn đặt lịch, mặt em đang bị sưng và ngứa"])
    assert llm.calls  # rules stepped aside
    assert result.depth is Depth.D3  # the safety floor: symptom words mean at least D3
    assert result.signals.symptom_words


async def test_the_floor_does_not_lower_a_higher_depth() -> None:
    llm = FakeDepthLlm(answer(Depth.D4, 0.9))
    result = await DepthClassifier(llm).classify(message(), ["da em bị đỏ rát sau khi bôi thuốc"])
    assert result.depth is Depth.D4


def test_the_intent_rules_work_on_folded_text() -> None:
    assert administrative_intent(fold_text("ĐẶT LỊCH")) == "booking"
    assert administrative_intent(fold_text("trời hôm nay đẹp")) is None


def test_cheap_signals_are_read_from_the_words() -> None:
    signals = text_signals(fold_text("cho em gặp nhân viên đi, tôi rất bực"))
    assert signals.asks_for_human
    assert signals.negative_sentiment
    assert not text_signals(fold_text("cảm ơn phòng khám")).asks_for_human


# ----------------------------------------------------------------------------------- the model
async def test_the_model_decides_d2_to_d4_and_its_flags_are_merged_with_the_rules() -> None:
    llm = FakeDepthLlm(
        answer(Depth.D2, 0.8, intent="aftercare", required_skill="laser", repeated_question=True)
    )
    result = await DepthClassifier(llm).classify(
        message(), ["sau khi triệt lông em nên tránh nắng bao lâu ạ"]
    )
    assert (result.depth, result.source, result.confidence) == (Depth.D2, DepthSource.LLM, 0.8)
    assert (result.intent, result.required_skill) == ("aftercare", "laser")
    assert result.signals.repeated_question


async def test_the_text_given_to_the_model_has_been_through_the_pii_mask() -> None:
    llm = FakeDepthLlm(answer(Depth.D2))
    await DepthClassifier(llm).classify(
        message(), ["em là Nguyễn Văn An, sđt 0901234567, kem này dùng buổi tối được không"]
    )
    (seen,) = llm.calls
    assert "0901234567" not in seen
    assert "Nguyễn Văn An" not in seen


@pytest.mark.parametrize("llm", [None, FakeDepthLlm(None), FakeDepthLlm(fail=True)])
async def test_a_missing_or_failed_model_is_d4_with_zero_confidence_not_a_pass(
    llm: FakeDepthLlm | None,
) -> None:
    result = await DepthClassifier(llm).classify(message(), ["kem này dùng buổi tối được không ạ"])
    assert (result.depth, result.confidence, result.source) == (Depth.D4, 0.0, DepthSource.FALLBACK)


async def test_a_message_without_text_is_d3_with_zero_confidence() -> None:
    llm = FakeDepthLlm(answer(Depth.D1))
    result = await DepthClassifier(llm).classify(message(), [])
    assert (result.depth, result.confidence, result.source) == (Depth.D3, 0.0, DepthSource.NO_TEXT)
    assert llm.calls == []


# --------------------------------------------------------------------------------------- events
@pytest.mark.parametrize("kind", [k for k in EventKind if k is not EventKind.PATIENT_MESSAGE])
async def test_an_event_without_patient_text_needs_no_model(kind: EventKind) -> None:
    llm = FakeDepthLlm()
    event = CareEvent(
        kind=kind, initiator=Initiator.SYSTEM, patient_ref="P900", occurred_at=vn(2026, 10, 3, 9, 0)
    )
    result = await DepthClassifier(llm).classify(event, ["ignored"])
    assert result.depth is EVENT_DEPTH[kind]
    assert result.source is DepthSource.EVENT
    assert llm.calls == []


# ------------------------------------------------------------------------------ model adapter
class _Generator:
    def __init__(self, reply: str, *, truncated: bool = False) -> None:
        self.reply = reply
        self.truncated = truncated
        self.prompts: list[str] = []

    async def generate_text(self, prompt: str, *, max_output_tokens: int | None = None) -> GeneratedText:
        self.prompts.append(prompt)
        return GeneratedText(text=self.reply, truncated=self.truncated)


async def test_the_adapter_validates_the_json_reply_against_the_schema() -> None:
    reply = 'Đây là kết quả: {"depth": "D3", "confidence": 0.7, "asks_for_human": true} hết.'
    generator = _Generator(reply)
    out = await TextGeneratorDepthLlm(generator).classify("tin nhắn đã che", instruction="chỉ dẫn")
    assert out is not None
    assert (out.depth, out.confidence, out.asks_for_human) == (Depth.D3, 0.7, True)
    assert "tin nhắn đã che" in generator.prompts[0]
    assert "chỉ dẫn" in generator.prompts[0]


@pytest.mark.parametrize(
    "reply",
    [
        "không phải JSON",
        json.dumps({"depth": "D9", "confidence": 0.5}),
        json.dumps({"depth": "D2", "confidence": 1.5}),
        json.dumps({"confidence": 0.5}),
    ],
)
async def test_the_adapter_returns_none_for_an_invalid_reply(reply: str) -> None:
    assert await TextGeneratorDepthLlm(_Generator(reply)).classify("x", instruction="") is None


async def test_the_adapter_returns_none_for_a_cut_reply() -> None:
    cut = _Generator('{"depth": "D2", "confidence": 0.9}', truncated=True)
    assert await TextGeneratorDepthLlm(cut).classify("x", instruction="") is None

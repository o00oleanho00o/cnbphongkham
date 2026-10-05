# ported from: src/conversation/thread-summarizer.test.ts
"""Test names are the snake_case form of ``describe_it`` (English); the original Vietnamese title is the docstring.

The original injected a mock LANGUAGE MODEL (``MockLanguageModelV4``) to reach the truncation gate of
``chayTomTat``; here the seam is ``TextGenerator`` and ``FakeTextGenerator`` plays the model (the Vercel AI SDK
finish reason ``length`` is D1's mapping onto ``GeneratedText.truncated``).
"""

from __future__ import annotations

import re

import pytest

from pema.config.runtime_tuning_settings import StaticTuningProvider, install_tuning_provider
from pema.conversation.history_store import HistoryStoreImpl
from pema.conversation.pg_testing import ClinicEnv
from pema.conversation.thread_store import ThreadStoreImpl
from pema.conversation.thread_summarizer import (
    BacklogRow,
    SummaryResult,
    ThreadSummarizer,
    build_summary_prompt,
    run_summary,
)
from pema_contracts.conversation import StoredMessage
from pema_contracts.testing import FakeTextGenerator

# window = 5, trigger = 6 để test không phải bơm hàng chục tin
WINDOW = 5
TRIGGER = 6


@pytest.fixture(autouse=True)
def _tuning() -> None:  # pyright: ignore[reportUnusedFunction]
    install_tuning_provider(
        StaticTuningProvider(
            {
                "HISTORY_CONTEXT_LIMIT": WINDOW,
                "SUMMARY_TRIGGER_MESSAGES": TRIGGER,
                "HISTORY_MAX_MESSAGES_PER_THREAD": 500,
            }
        )
    )


async def _seed_thread(env: ClinicEnv, thread_id: str, count: int) -> None:
    await ThreadStoreImpl(env.db).record_thread_activity(
        env.clinic_id,
        account_id="acc-1",
        thread_id=thread_id,
        thread_type=0,
        display_name="Hải",
        sender_name="Hải",
    )
    await _append_messages(env, thread_id, range(1, count + 1))


async def _append_messages(env: ClinicEnv, thread_id: str, numbers: range) -> None:
    history = HistoryStoreImpl(env.db)
    for i in numbers:
        await history.append_message(
            env.clinic_id,
            "acc-1",
            thread_id,
            StoredMessage(role="user", content=f"tin-{i}", sender_name="Hải"),
        )


def _generator(texts: list[str], prompts: list[str], *, truncated: bool = False):
    async def generate(prompt: str) -> SummaryResult:
        prompts.append(prompt)
        return SummaryResult(text=texts.pop(0), truncated=truncated)

    return generate


@pytest.mark.db
async def test_thread_summarizer_backlog_is_the_messages_outside_the_replay_window_not_yet_covered(
    env: ClinicEnv,
) -> None:
    """backlog = tin ngoài cửa sổ replay chưa được summary phủ"""
    await _seed_thread(env, "t-backlog", 12)  # 12 tin, window 5 -> 7 tin ngoài window
    collected = await ThreadSummarizer(env.db).collect_summary_backlog(env.clinic_id, "acc-1", "t-backlog")
    assert len(collected.backlog) == 7
    assert collected.backlog[0].content == "tin-1"
    assert collected.backlog[6].content == "tin-7"


@pytest.mark.db
async def test_thread_summarizer_below_the_trigger_does_not_call_the_llm(env: ClinicEnv) -> None:
    """chưa đủ trigger thì không gọi LLM"""
    await _seed_thread(env, "t-it", WINDOW + 2)  # backlog 2 < trigger 6
    prompts: list[str] = []
    ran = await ThreadSummarizer(env.db).maybe_summarize_thread(
        env.clinic_id, "acc-1", "t-it", _generator(["summary"], prompts)
    )
    assert ran is False
    assert prompts == []


@pytest.mark.db
async def test_thread_summarizer_at_the_trigger_folds_the_backlog_into_the_summary(env: ClinicEnv) -> None:
    """đủ trigger: gộp backlog vào summary, prompt chứa summary cũ + tin mới"""
    await _seed_thread(env, "t-gop", 12)
    threads = ThreadStoreImpl(env.db)
    await threads.set_thread_summary(env.clinic_id, "acc-1", "t-gop", "Summary cũ: đã bàn về X", 0)

    prompts: list[str] = []
    ran = await ThreadSummarizer(env.db).maybe_summarize_thread(
        env.clinic_id, "acc-1", "t-gop", _generator(["Summary mới sau khi gộp"], prompts)
    )

    assert ran is True
    assert "Summary cũ: đã bàn về X" in prompts[0]
    assert "tin-1" in prompts[0]
    assert "tin-7" in prompts[0]
    assert "tin-8" not in prompts[0], "tin trong window không được đem đi tóm tắt"

    stored = await threads.get_thread_summary(env.clinic_id, "acc-1", "t-gop")
    assert stored.summary == "Summary mới sau khi gộp"
    assert stored.covers_to_message_id > 0


@pytest.mark.db
async def test_thread_summarizer_next_time_only_the_new_part_is_folded(env: ClinicEnv) -> None:
    """lần sau chỉ gộp phần mới, không tóm tắt lại từ đầu"""
    await _seed_thread(env, "t-gop", 12)
    summarizer = ThreadSummarizer(env.db)
    await summarizer.maybe_summarize_thread(
        env.clinic_id, "acc-1", "t-gop", _generator(["Summary mới sau khi gộp"], [])
    )

    # t-gop đã covers tới tin-7; thêm 8 tin nữa -> backlog mới bắt đầu từ tin-8
    await _append_messages(env, "t-gop", range(13, 21))
    prompts: list[str] = []
    ran = await summarizer.maybe_summarize_thread(
        env.clinic_id, "acc-1", "t-gop", _generator(["Summary lần 2"], prompts)
    )

    assert ran is True
    assert "tin-7\n" not in prompts[0], "phần đã phủ không được gộp lại"
    assert "tin-8" in prompts[0]
    assert "Summary mới sau khi gộp" in prompts[0], "summary cũ phải là đầu vào"


@pytest.mark.db
async def test_thread_summarizer_llm_failure_is_swallowed_and_the_summary_is_kept(env: ClinicEnv) -> None:
    """LLM lỗi thì nuốt, không throw, summary giữ nguyên"""
    await _seed_thread(env, "t-gop", 12)
    threads = ThreadStoreImpl(env.db)
    await threads.set_thread_summary(env.clinic_id, "acc-1", "t-gop", "Bản cũ", 0)

    async def failing(prompt: str) -> SummaryResult:
        raise RuntimeError("router chết")

    ran = await ThreadSummarizer(env.db).maybe_summarize_thread(env.clinic_id, "acc-1", "t-gop", failing)
    assert ran is False
    assert (await threads.get_thread_summary(env.clinic_id, "acc-1", "t-gop")).summary == "Bản cũ"


@pytest.mark.db
async def test_thread_summarizer_truncated_summary_is_not_saved_and_covers_to_does_not_advance(
    env: ClinicEnv,
) -> None:
    """summary CẮT CỤT (truncated) thì KHÔNG lưu, coversTo không tiến - giữ trí nhớ"""
    # Bản cụt mà lưu + tiến coversTo thì đám tin đó bị đánh dấu "đã phủ", không bao giờ tóm tắt lại -> mất trí nhớ
    # im lặng vĩnh viễn.
    await _seed_thread(env, "t-cut", 12)
    threads = ThreadStoreImpl(env.db)
    await threads.set_thread_summary(env.clinic_id, "acc-1", "t-cut", "Bản tốt cũ", 0)
    before = await threads.get_thread_summary(env.clinic_id, "acc-1", "t-cut")

    ran = await ThreadSummarizer(env.db).maybe_summarize_thread(
        env.clinic_id,
        "acc-1",
        "t-cut",
        _generator(["Bản mới nhưng bị cắt giữa chừng vì chạm cap"], [], truncated=True),
    )

    assert ran is False
    after = await threads.get_thread_summary(env.clinic_id, "acc-1", "t-cut")
    assert after.summary == before.summary, "summary tốt cũ phải còn nguyên"
    assert after.covers_to_message_id == before.covers_to_message_id, (
        "coversTo KHÔNG được tiến khi bỏ bản cụt"
    )


async def test_thread_summarizer_prompt_has_a_soft_length_cap_so_the_hard_cap_is_rarely_hit() -> None:
    """prompt có trần mềm độ dài để hiếm khi chạm cap gây cắt cụt"""
    prompt = build_summary_prompt("", [BacklogRow(id=1, role="user", sender_name="Hải", content="x")])
    assert re.search(r"400 từ", prompt), "phải có trần mềm ~400 từ trong prompt"


@pytest.mark.db
async def test_thread_summarizer_prompt_has_a_fixed_section_structure_and_the_three_rules(
    env: ClinicEnv,
) -> None:
    """prompt có CẤU TRÚC mục cố định + luật không-bỏ-mục/đính-chính/hợp-nhất"""
    # Prompt tự do để LLM tự chọn giữ gì thì qua nhiều vòng nó lặng lẽ đánh rơi một khía cạnh. Ép điền đủ mục +
    # "(không có)" làm mất mát nhìn thấy được.
    await _seed_thread(env, "t-struct", 12)
    prompts: list[str] = []
    await ThreadSummarizer(env.db).maybe_summarize_thread(
        env.clinic_id, "acc-1", "t-struct", _generator(["tóm tắt"], prompts)
    )
    for section in (
        "NGƯỜI & QUAN HỆ",
        "QUYẾT ĐỊNH & ĐÃ HỨA",
        "SỞ THÍCH & THÓI QUEN",
        "VIỆC ĐANG DỞ",
        "CÂU HỎI TREO",
    ):
        assert section in prompts[0], f"prompt thiếu mục cố định: {section}"
    assert re.search(r"\(không có\)", prompts[0]), "phải dặn mục rỗng ghi (không có), không bỏ mục"
    assert re.search(r"ĐÍNH CHÍNH", prompts[0]), "phải dặn giữ đính chính của người dùng"
    assert re.search(r"HỢP NHẤT", prompts[0]), "phải dặn gộp vào MỘT bản, không chép nguyên bản cũ"


async def test_thread_summarizer_build_prompt_still_carries_the_old_summary_and_the_backlog() -> None:
    """buildSummaryPrompt vẫn mang summary cũ + tin backlog (không mất đầu vào)"""
    prompt = build_summary_prompt(
        "Nền cũ: đã bàn X", [BacklogRow(id=1, role="user", sender_name="Hải", content="câu mới của Hải")]
    )
    assert re.search(r"Nền cũ: đã bàn X", prompt)
    assert re.search(r"câu mới của Hải", prompt)


async def test_thread_summarizer_build_prompt_names_the_bot_and_falls_back_for_an_unnamed_user() -> None:
    """(thêm) người nói: assistant là 'Bot', user không tên là 'Người dùng'"""
    prompt = build_summary_prompt(
        "",
        [
            BacklogRow(id=1, role="assistant", sender_name=None, content="chào bạn"),
            BacklogRow(id=2, role="user", sender_name=None, content="cho mình hỏi"),
        ],
    )
    assert "Bot: chào bạn" in prompt
    assert "Người dùng: cho mình hỏi" in prompt


# Cửa PHÁT HIỆN bản cụt (``finishReason === "length"`` -> ``truncated``). Mọi test ở trên TIÊM sẵn ``truncated``
# qua generator giả nên KHÔNG chạm cửa này - đổi nhầm nó là hồi quy CÂM. ``run_summary`` (chayTomTat) được tách
# riêng chính để đo cửa này bằng model giả.


async def test_chay_tom_tat_finish_reason_length_means_truncated_so_the_caller_keeps_the_old_one() -> None:
    """chayTomTat - cửa phát hiện bản cụt: finishReason 'length' -> truncated:true (bản cụt, caller phải giữ bản cũ)"""
    generator = FakeTextGenerator(reply=lambda prompt: "tóm tắt cụt giữa chừng", truncated=True)
    result = await run_summary(generator, "prompt")
    assert result.truncated is True


async def test_chay_tom_tat_finish_reason_stop_means_not_truncated_and_the_text_is_trimmed() -> None:
    """chayTomTat - cửa phát hiện bản cụt: finishReason 'stop' -> truncated:false, và text đã trim"""
    generator = FakeTextGenerator(reply=lambda prompt: "  tóm tắt trọn vẹn  ", truncated=False)
    result = await run_summary(generator, "prompt")
    assert result.truncated is False
    assert result.text == "tóm tắt trọn vẹn"
    assert generator.prompts == ["prompt"]


@pytest.mark.db
async def test_thread_summarizer_default_generator_uses_the_injected_text_generator(env: ClinicEnv) -> None:
    """(thêm) không truyền generator thì dùng TextGenerator của ThreadSummarizer (D1 cấp model thật)"""
    await _seed_thread(env, "t-default", 12)
    text_generator = FakeTextGenerator(reply=lambda prompt: "tóm tắt từ model giả")
    summarizer = ThreadSummarizer(env.db, text_generator=text_generator)

    assert await summarizer.maybe_summarize_thread(env.clinic_id, "acc-1", "t-default") is True
    stored = await ThreadStoreImpl(env.db).get_thread_summary(env.clinic_id, "acc-1", "t-default")
    assert stored.summary == "tóm tắt từ model giả"


@pytest.mark.db
async def test_thread_summarizer_without_any_generator_does_nothing(env: ClinicEnv) -> None:
    """(thêm) chưa cấu hình model tóm tắt thì bỏ qua, không ném, summary giữ nguyên"""
    await _seed_thread(env, "t-nogen", 12)
    assert await ThreadSummarizer(env.db).maybe_summarize_thread(env.clinic_id, "acc-1", "t-nogen") is False
    stored = await ThreadStoreImpl(env.db).get_thread_summary(env.clinic_id, "acc-1", "t-nogen")
    assert (stored.summary, stored.covers_to_message_id) == ("", 0)

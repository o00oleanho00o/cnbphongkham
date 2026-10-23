"""The rules of following up, pure code: the hours, the words that mean "stop", what a judgement becomes inside
the limits, when a message may go, how the chat model's and Jev's answers are read, and what the judges read."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from agentcore import Message, TextBlock
from plugins.follow_up.rules import (
    DEFAULT_POLICY,
    INSTRUCTION_MARK,
    JEV_QUESTION,
    FollowUpPolicy,
    Verdict,
    asks_to_stop,
    decide,
    instruction_for,
    last_words,
    next_day,
    next_window,
    parse_verdict,
    read_jev,
    render_transcript,
    send_at,
    window_open,
)

# 12:00 in Vietnam (UTC+7), inside the window
NOW = datetime(2026, 10, 17, 5, 0, tzinfo=UTC)


def vn(hour: int, minute: int = 0, day: int = 17) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC) - timedelta(hours=7)


# --- the window and the clock ---


@pytest.mark.parametrize(
    ("hour", "minute", "open_"),
    [
        (7, 59, False),
        (8, 0, True),
        (12, 0, True),
        (19, 59, True),
        (20, 0, False),
        (23, 30, False),
        (3, 0, False),
    ],
)
def test_the_window_is_8_to_20_in_vietnam(hour: int, minute: int, open_: bool) -> None:
    assert window_open(vn(hour, minute)) is open_


def test_a_time_outside_the_window_moves_to_its_next_opening() -> None:
    assert next_window(vn(12)) == vn(12)
    assert next_window(vn(5, 30)) == vn(8)
    assert next_window(vn(20)) == vn(8, day=18)
    assert next_window(vn(23, 59)) == vn(8, day=18)
    assert next_day(vn(12)) == vn(8, day=18)


# --- the safety net of words ---


@pytest.mark.parametrize(
    "text",
    [
        "đừng nhắn nữa nhé",
        "Dung nhan nua",
        "KHÔNG CẦN NỮA đâu",
        "chị bị làm phiền quá",
        "spam",
        "em block số này",
        "chặn số giúp chị",
        "không quan tâm",
    ],
)
def test_a_customer_who_asks_to_stop_is_caught_with_or_without_diacritics(text: str) -> None:
    assert asks_to_stop(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "chân em hơi đau",
        "nhắn lại cho em thứ sáu nhé",
        "em cần nhắn lịch",
        "cho chị hỏi giá",
        "phiền em xem giúp chị",
    ],
)
def test_ordinary_sentences_are_not_taken_for_a_request_to_stop(text: str) -> None:
    assert asks_to_stop(text) is False


# --- the verdict becomes a plan inside the limits ---


def test_done_plans_nothing() -> None:
    outcome = decide(Verdict(state="done", reason="Đã đặt lịch"), NOW, None)

    assert (outcome.next_at, outcome.paused_until, outcome.stopped) == (None, None, False)


@pytest.mark.parametrize("state", ["hesitant", "call_back"])
def test_a_hesitant_customer_is_written_to_after_the_wait_the_model_chose(state: str) -> None:
    outcome = decide(Verdict(state=state, after_h=3, reason="x"), NOW, None)  # type: ignore[arg-type]

    assert outcome.next_at == NOW + timedelta(hours=3)
    assert outcome.stopped is False


@pytest.mark.parametrize(
    ("after_h", "expected_wait"),
    [
        (0.1, timedelta(hours=1)),
        (1000, timedelta(days=14)),
        (None, timedelta(hours=24)),
        (0, timedelta(hours=24)),
    ],
)
def test_the_wait_is_kept_between_one_hour_and_fourteen_days(
    after_h: float | None, expected_wait: timedelta
) -> None:
    outcome = decide(Verdict(state="hesitant", after_h=after_h), NOW, None)

    assert outcome.next_at == next_window(NOW + expected_wait)


def test_a_time_that_falls_at_night_moves_to_the_morning() -> None:
    outcome = decide(Verdict(state="hesitant", after_h=5), vn(17), None)

    assert outcome.next_at == vn(8, day=18)


def test_two_messages_are_never_closer_than_a_day() -> None:
    last = NOW - timedelta(hours=2)

    outcome = decide(Verdict(state="hesitant", after_h=1), NOW, last)

    assert outcome.next_at == next_window(last + timedelta(hours=24))


def test_a_polite_no_pauses_for_the_days_the_model_chose_within_limits() -> None:
    week = decide(Verdict(state="soft_decline", pause_days=7), NOW, None)
    default = decide(Verdict(state="soft_decline"), NOW, None)
    huge = decide(Verdict(state="soft_decline", pause_days=500), NOW, None)

    assert week.paused_until == NOW + timedelta(days=7)
    assert week.next_at == next_window(NOW + timedelta(days=7))
    assert default.paused_until == NOW + timedelta(days=14)
    assert huge.paused_until == NOW + timedelta(days=60)
    assert [week.stopped, default.stopped, huge.stopped] == [False, False, False]


@pytest.mark.parametrize("state", ["hard_decline", "negative"])
def test_a_plain_no_and_an_upset_customer_stop_the_case(state: str) -> None:
    outcome = decide(Verdict(state=state, after_h=2, reason="Khách bực"), NOW, None)  # type: ignore[arg-type]

    assert (outcome.stopped, outcome.next_at, outcome.paused_until) == (True, None, None)


def test_a_reason_is_cut_to_what_fits() -> None:
    assert len(decide(Verdict(state="done", reason="x" * 2000), NOW, None).reason) == 300


# --- when a message may go ---


def test_a_due_message_inside_the_window_may_go_now() -> None:
    assert send_at(NOW, NOW - timedelta(minutes=1), None, None) == NOW


@pytest.mark.parametrize(
    ("now", "next_at", "paused_until", "last_sent_at", "expected"),
    [
        (NOW, NOW + timedelta(hours=1), None, None, NOW + timedelta(hours=1)),
        (NOW, NOW, NOW + timedelta(days=1), None, NOW + timedelta(days=1)),
        (vn(21), vn(20, 30), None, None, vn(8, day=18)),
        (NOW, NOW, None, NOW - timedelta(hours=23), NOW + timedelta(hours=1)),
    ],
    ids=["not due", "paused", "outside the hours", "too soon after the last one"],
)
def test_a_message_waits_for_each_limit(
    now: datetime,
    next_at: datetime,
    paused_until: datetime | None,
    last_sent_at: datetime | None,
    expected: datetime,
) -> None:
    assert send_at(now, next_at, paused_until, last_sent_at) == expected


def test_the_defaults_are_the_agreed_ones() -> None:
    assert (DEFAULT_POLICY.quiet_after, DEFAULT_POLICY.min_gap) == (timedelta(hours=2), timedelta(hours=24))
    assert (DEFAULT_POLICY.window_start.hour, DEFAULT_POLICY.window_end.hour) == (8, 20)


# --- reading the chat model's answer ---


def test_a_verdict_is_read_from_plain_json() -> None:
    verdict = parse_verdict(
        '{"state": "hesitant", "after_h": 24, "pause_days": null, "reason": "hỏi giá rồi im"}'
    )

    assert verdict == Verdict(state="hesitant", after_h=24, pause_days=None, reason="hỏi giá rồi im")


def test_a_verdict_is_found_inside_a_fenced_answer_with_words_around_it() -> None:
    answer = 'Đây là kết quả:\n```json\n{"state": "soft_decline", "pause_days": 10, "reason": "để em suy nghĩ"}\n```'

    verdict = parse_verdict(answer)

    assert verdict is not None
    assert (verdict.state, verdict.pause_days) == ("soft_decline", 10)


@pytest.mark.parametrize(
    "answer",
    [
        "",
        "tôi nghĩ là khách còn phân vân",
        '{"state": "angry"}',
        '{"state": "hesitant", "after_h": -4}',
        '["done"]',
        '{"state": ',
        "{}",
    ],
)
def test_an_answer_that_is_not_a_usable_verdict_is_none(answer: str) -> None:
    assert parse_verdict(answer) is None


def test_a_very_long_reason_is_cut_instead_of_refusing_the_verdict() -> None:
    verdict = parse_verdict('{"state": "done", "reason": "' + "x" * 3000 + '"}')

    assert verdict is not None
    assert len(verdict.reason) == 300


# --- reading Jev's answer ---


def _jev(choice: Any, confidence: Any) -> dict[str, Any]:
    return {"state": {"type": "choice", "choice": choice, "confidence": confidence, "probabilities": {}}}


def test_jev_is_asked_one_choice_over_the_six_states_with_the_rules_of_the_prompt() -> None:
    question = JEV_QUESTION["state"]

    assert question["type"] == "choice"
    assert set(question["criteria"]) == {
        "done",
        "hesitant",
        "call_back",
        "soft_decline",
        "hard_decline",
        "negative",
    }
    assert "chị hỏi chồng đã" in question["criteria"]["hesitant"]


def test_a_sure_answer_of_jev_is_the_verdict_with_the_default_waits() -> None:
    verdict, why = read_jev(_jev("hesitant", 0.82), 0.6)

    assert verdict == Verdict(state="hesitant", reason="Jev: hesitant (82%).")
    assert why == "hesitant 82%"
    assert verdict is not None
    plan = decide(verdict, NOW, None)
    assert plan.next_at == next_window(NOW + timedelta(hours=24))


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        (_jev("hesitant", 0.4), "hesitant 40% < 60%"),
        (_jev("call_back", 0.95), "call_back needs a time"),
        (_jev("angry", 0.9), "unreadable"),
        (_jev("done", "lots"), "unreadable"),
        (_jev("done", 1.5), "unreadable"),
        ({"other": {}}, "unreadable"),
    ],
)
def test_the_chat_model_judges_when_jev_is_unsure_reads_no_time_or_answers_oddly(
    answer: dict[str, Any], why: str
) -> None:
    assert read_jev(answer, 0.6) == (None, why)


# --- what the agent is told, and what the judges read ---


def test_the_instruction_says_what_to_write_and_how_to_decline() -> None:
    text = instruction_for("hesitant", "hỏi giá rồi im")

    assert text.startswith(INSTRUCTION_MARK)
    assert "hesitant (hỏi giá rồi im)" in text
    assert "SKIP" in text
    assert "MỘT tin" in text


def test_the_transcript_names_who_spoke_and_leaves_tool_traffic_out() -> None:
    messages = [
        Message.user("Cho chị hỏi giá"),
        Message(role="assistant", blocks=[TextBlock(text="Dạ giá 500k ạ")]),
        Message(role="tool", blocks=[]),
        Message(role="assistant", blocks=[TextBlock(text="  ")]),
    ]

    assert render_transcript(messages) == "Khách: Cho chị hỏi giá\nAgent: Dạ giá 500k ạ"


def test_the_transcript_keeps_the_newest_messages_within_its_limits() -> None:
    messages = [Message.user(f"tin {n} " + "x" * 90) for n in range(30)]
    policy = FollowUpPolicy(transcript_messages=5, transcript_chars=250, message_chars=40)

    lines = render_transcript(messages, policy).split("\n")

    assert lines[-1].startswith("Khách: tin 29")
    assert len(lines) <= 5
    assert all(len(line) <= len("Khách: ") + 40 for line in lines)
    assert sum(len(line) + 1 for line in lines) <= 250 + 60


def test_the_judge_does_not_read_the_harness_instructions_nor_a_skip() -> None:
    history = [
        Message.user("giá bao nhiêu?"),
        Message(role="assistant", blocks=[TextBlock(text="Dạ 500k ạ")]),
        Message.user("[Case · follow_up] Goal: ..."),
        Message(role="assistant", blocks=[TextBlock(text="SKIP")]),
        Message.user("ok em"),
        Message(role="assistant", blocks=[TextBlock(text="Dạ vâng")]),
        Message.user(instruction_for("hesitant", "")),
        Message(role="assistant", blocks=[TextBlock(text="Chị còn quan tâm không ạ?")]),
    ]

    assert render_transcript(history).split("\n") == [
        "Khách: giá bao nhiêu?",
        "Agent: Dạ 500k ạ",
        "Khách: ok em",
        "Agent: Dạ vâng",
        "Agent: Chị còn quan tâm không ạ?",
    ]


def test_the_judge_leaves_out_an_answer_that_was_never_sent_because_the_customer_wrote_again() -> None:
    history = [
        Message.user("hours?"),
        Message(role="assistant", blocks=[TextBlock(text="draft nobody saw")]),
        Message.user("[System] The person wrote again before your last answer was sent."),
        Message.user("and the price?"),
        Message(role="assistant", blocks=[TextBlock(text="hours and price in one answer")]),
    ]

    assert render_transcript(history).split("\n") == [
        "Khách: hours?",
        "Khách: and the price?",
        "Agent: hours and price in one answer",
    ]


def test_the_last_words_are_what_the_customer_said_before_the_last_answers() -> None:
    transcript = "Khách: giá?\nAgent: 500k\nKhách: thôi\nKhách: đừng nhắn nữa\nAgent: Dạ\nAgent: Vâng ạ"

    assert last_words(transcript) == ["thôi", "đừng nhắn nữa"]
    assert last_words("Agent: chào") == []


def test_a_stop_phrase_on_the_second_line_of_a_message_is_heard() -> None:
    history = [
        Message(role="assistant", blocks=[TextBlock(text="Chị còn quan tâm không ạ?")]),
        Message.user("cảm ơn em\nđừng nhắn nữa nhé"),
    ]

    words = last_words(render_transcript(history))

    assert words == ["cảm ơn em đừng nhắn nữa nhé"]
    assert any(asks_to_stop(text) for text in words)

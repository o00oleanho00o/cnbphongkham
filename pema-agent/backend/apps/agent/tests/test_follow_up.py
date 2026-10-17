"""The follow-up loop, first half: the hard limits (plain code), the reading of the model's opinion, and the pass
that judges conversations gone quiet. The model is a script and the queue an in-memory stand-in."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from agent_app.follow_up import (
    DEFAULT_POLICY,
    FollowUp,
    FollowUpConfig,
    FollowUpPolicy,
    FollowUps,
    InMemoryFollowUpStore,
    Quiet,
    Verdict,
    asks_to_stop,
    decide,
    may_send,
    next_window,
    parse_verdict,
    render_transcript,
    window_open,
)
from agentcore import (
    AssistantResult,
    InMemorySessionStore,
    LlmRequest,
    Message,
    ModelError,
    StreamSink,
    TextBlock,
)

# 12:00 in Vietnam (UTC+7), inside the window
NOW = datetime(2026, 10, 17, 5, 0, tzinfo=UTC)
TENANT = "t"
CONFIG = FollowUpConfig(enabled=True, channels=("zalo-a1",))


def vn(hour: int, minute: int = 0, day: int = 17) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC) - timedelta(hours=7)


def _row(**kw: object) -> FollowUp:
    base = FollowUp(channel="zalo-a1", conversation_id="c1", user_id="u1", session_id="s1")
    return replace(base, **kw)  # type: ignore[arg-type]


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
    row = _row(last_sent_at=NOW - timedelta(hours=2))

    outcome = decide(Verdict(state="hesitant", after_h=1), NOW, row)

    assert outcome.next_at == next_window(row.last_sent_at + timedelta(hours=24))  # type: ignore[operator]


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
def test_a_plain_no_and_an_upset_customer_stop_the_loop_for_good(state: str) -> None:
    outcome = decide(Verdict(state=state, after_h=2, reason="Khách bực"), NOW, None)  # type: ignore[arg-type]

    assert (outcome.stopped, outcome.next_at, outcome.paused_until) == (True, None, None)


def test_after_two_unanswered_messages_the_loop_stops_whatever_the_model_says() -> None:
    row = _row(unanswered=2)

    outcome = decide(Verdict(state="hesitant", after_h=2, reason="Còn phân vân"), NOW, row)

    assert outcome.stopped is True
    assert outcome.next_at is None
    assert "tự ngưng" in outcome.reason
    assert "Còn phân vân" in outcome.reason


def test_a_reason_is_cut_to_what_fits() -> None:
    assert len(decide(Verdict(state="done", reason="x" * 2000), NOW, None).reason) == 300


# --- may a message go out now ---


def _due(**kw: object) -> FollowUp:
    return _row(next_at=NOW - timedelta(minutes=1), state="hesitant", **kw)


def test_a_due_message_inside_the_window_may_go() -> None:
    assert may_send(_due(), NOW) == (True, "")


@pytest.mark.parametrize(
    ("row", "now", "why"),
    [
        (_row(stopped=True, next_at=NOW), NOW, "stopped"),
        (_due(unanswered=2), NOW, "too many unanswered"),
        (_row(), NOW, "not due"),
        (_row(next_at=NOW + timedelta(hours=1)), NOW, "not due"),
        (_due(paused_until=NOW + timedelta(days=1)), NOW, "paused"),
        (_due(), vn(21), "outside the hours"),
        (_due(last_sent_at=NOW - timedelta(hours=23)), NOW, "too soon after the last one"),
    ],
)
def test_a_message_is_held_back_for_each_limit(row: FollowUp, now: datetime, why: str) -> None:
    assert may_send(row, now) == (False, why)


def test_the_policy_can_be_tightened_but_the_defaults_are_the_agreed_ones() -> None:
    assert (DEFAULT_POLICY.quiet_after, DEFAULT_POLICY.min_gap, DEFAULT_POLICY.max_unanswered) == (
        timedelta(hours=2),
        timedelta(hours=24),
        2,
    )
    assert (DEFAULT_POLICY.window_start.hour, DEFAULT_POLICY.window_end.hour) == (8, 20)


# --- reading the model's answer ---


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


# --- the pass ---


class ScriptedModel:
    def __init__(self, *answers: str | ModelError) -> None:
        self.answers = list(answers)
        self.requests: list[LlmRequest] = []

    async def complete(self, request: LlmRequest, *, sink: StreamSink | None = None) -> AssistantResult:
        self.requests.append(request)
        answer = self.answers.pop(0) if self.answers else '{"state": "done"}'
        if isinstance(answer, ModelError):
            raise answer
        return AssistantResult(
            message=Message(role="assistant", blocks=[TextBlock(text=answer)]), stop_reason="end"
        )


class Setup:
    def __init__(
        self,
        *answers: str | ModelError,
        config: FollowUpConfig = CONFIG,
        policy: FollowUpPolicy | None = None,
    ):
        self.store = InMemoryFollowUpStore()
        self.sessions = InMemorySessionStore()
        self.model = ScriptedModel(*answers)
        self.loop = FollowUps(
            self.store,
            self.sessions,
            lambda: self.model,
            lambda: config,
            tenant_id=TENANT,
            policy=policy or DEFAULT_POLICY,
            clock=lambda: NOW,
        )

    async def quiet(
        self,
        last_id: int = 10,
        texts: tuple[str, ...] = ("giá bao nhiêu?",),
        *,
        channel: str = "zalo-a1",
        conv: str = "c1",
    ) -> Quiet:
        for text in texts or ("",):
            if text:
                await self.sessions.append(TENANT, f"s-{conv}", Message.user(text))
        await self.sessions.append(
            TENANT, f"s-{conv}", Message(role="assistant", blocks=[TextBlock(text="Dạ 500k ạ")])
        )
        item = Quiet(channel, conv, "u1", f"s-{conv}", last_id, texts)
        self.store.add_quiet(item)
        return item


async def test_nothing_is_judged_until_the_loop_is_switched_on_for_a_channel() -> None:
    off = Setup(config=FollowUpConfig(enabled=False, channels=("zalo-a1",)))
    no_channel = Setup(config=FollowUpConfig(enabled=True, channels=()))
    for setup in (off, no_channel):
        await setup.quiet()

    assert (await off.loop.review_pass(), await no_channel.loop.review_pass()) == (0, 0)
    assert (off.model.requests, no_channel.model.requests) == ([], [])


async def test_a_quiet_conversation_is_judged_once_and_the_plan_is_kept() -> None:
    setup = Setup('{"state": "hesitant", "after_h": 3, "reason": "hỏi giá rồi im"}')
    await setup.quiet(last_id=10)

    first = await setup.loop.review_pass()
    second = await setup.loop.review_pass()

    row = await setup.store.get(TENANT, "zalo-a1", "c1")
    assert (first, second) == (1, 0)
    assert row is not None
    assert (row.state, row.reason, row.reviewed_through) == ("hesitant", "hỏi giá rồi im", 10)
    assert row.next_at == NOW + timedelta(hours=3)
    assert (row.stopped, row.unanswered) == (False, 0)
    assert len(setup.model.requests) == 1


async def test_the_model_is_given_the_conversation_and_the_rules_of_judging_it() -> None:
    setup = Setup()
    await setup.quiet(texts=("cho chị hỏi giá",))

    await setup.loop.review_pass()

    request = setup.model.requests[0]
    assert "Khách: cho chị hỏi giá\nAgent: Dạ 500k ạ" in request.messages[0].text()
    assert "12:00" in request.messages[0].text()
    assert "soft_decline" in request.system
    assert "để em suy nghĩ thêm" in request.system
    assert (request.reasoning, request.tools) == ("off", [])


async def test_only_the_channels_an_admin_chose_are_judged() -> None:
    setup = Setup()
    await setup.quiet(channel="zalo-other", conv="c9")

    assert await setup.loop.review_pass() == 0
    assert setup.model.requests == []


async def test_a_customer_who_asks_to_stop_is_stopped_without_asking_the_model() -> None:
    setup = Setup()
    await setup.quiet(texts=("giá bao nhiêu", "thôi đừng nhắn nữa nhé"))

    await setup.loop.review_pass()

    row = await setup.store.get(TENANT, "zalo-a1", "c1")
    assert row is not None
    assert (row.stopped, row.state, row.next_at) == (True, "hard_decline", None)
    assert setup.model.requests == []


async def test_an_answer_the_model_cannot_give_is_done_and_the_conversation_is_not_judged_again() -> None:
    setup = Setup("không biết")
    await setup.quiet()

    judged = await setup.loop.review_pass()

    row = await setup.store.get(TENANT, "zalo-a1", "c1")
    assert (judged, row.state if row else None, row.next_at if row else 1) == (1, "done", None)
    assert await setup.loop.review_pass() == 0


async def test_a_failing_model_stops_the_pass_and_leaves_the_conversation_to_be_judged_later() -> None:
    setup = Setup(ModelError("transient", "busy"), '{"state": "done"}')
    await setup.quiet(last_id=10, conv="c1")
    await setup.quiet(last_id=11, conv="c2")

    first = await setup.loop.review_pass()
    second = await setup.loop.review_pass()

    assert (first, second) == (0, 2)
    assert len(setup.model.requests) == 3  # the failed call, then both conversations


async def test_a_customer_who_writes_again_lifts_a_stop_and_starts_the_count_over() -> None:
    setup = Setup('{"state": "hesitant", "after_h": 2}')
    await setup.store.save(
        TENANT,
        _row(state="hard_decline", stopped=True, unanswered=2, reviewed_through=10, next_at=None),
    )
    await setup.quiet(last_id=14, texts=("chị muốn đặt lịch lại",))

    await setup.loop.review_pass()

    row = await setup.store.get(TENANT, "zalo-a1", "c1")
    assert row is not None
    assert (row.stopped, row.unanswered, row.state, row.reviewed_through) == (False, 0, "hesitant", 14)
    assert row.next_at == NOW + timedelta(hours=2)


async def test_with_no_new_words_from_the_customer_the_unanswered_count_stays_and_the_cap_applies() -> None:
    setup = Setup('{"state": "hesitant", "after_h": 2}')
    await setup.store.save(
        TENANT, _row(state="hesitant", unanswered=2, reviewed_through=10, last_sent_at=NOW)
    )
    await setup.quiet(last_id=12, texts=())  # only the loop's own message since the last judgement

    await setup.loop.review_pass()

    row = await setup.store.get(TENANT, "zalo-a1", "c1")
    assert row is not None
    assert (row.stopped, row.unanswered, row.next_at) == (True, 2, None)


async def test_a_polite_no_pauses_and_a_later_message_may_come_after_the_pause() -> None:
    setup = Setup('{"state": "soft_decline", "pause_days": 7, "reason": "để em suy nghĩ thêm"}')
    await setup.quiet(texts=("để em suy nghĩ thêm nha",))

    await setup.loop.review_pass()

    row = await setup.store.get(TENANT, "zalo-a1", "c1")
    assert row is not None
    assert (row.state, row.stopped) == ("soft_decline", False)
    assert row.paused_until == NOW + timedelta(days=7)
    assert row.next_at == next_window(NOW + timedelta(days=7))


async def test_the_cost_of_a_pass_is_bounded() -> None:
    setup = Setup(policy=replace(DEFAULT_POLICY, per_pass=2))
    for n in range(5):
        await setup.quiet(last_id=10 + n, conv=f"c{n}")

    assert await setup.loop.review_pass() == 2
    assert len(setup.model.requests) == 2


async def test_the_admin_sees_what_was_judged() -> None:
    setup = Setup('{"state": "call_back", "after_h": 48, "reason": "hẹn thứ sáu"}')
    await setup.quiet()
    await setup.loop.review_pass()

    shown = await setup.loop.status()

    assert len(shown) == 1
    assert (shown[0]["state"], shown[0]["reason"], shown[0]["stopped"]) == ("call_back", "hẹn thứ sáu", False)
    assert shown[0]["next_at"] == (NOW + timedelta(hours=48)).isoformat()
    assert shown[0]["last_sent_at"] is None

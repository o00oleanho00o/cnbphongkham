"""Following up as a case on the real case engine (docs/PLAN-case-loop.md 7): the agent's answer opens the case,
the silence is judged once, a message goes once at its time and only inside the limits, a customer who writes
first sends the case back to waiting for silence, "stop" words end it, two unanswered messages end it, a send
that raised is checked again, and Jev judges when it is on and sure. The engine is the real one with its memory
store; a fake outbox stands for the chat's queue."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from agent_app.cases import CaseEngine, CasesConfig, InMemoryCaseStore
from agent_app.plugins import Cases, ProactiveSent
from agentcore import Message, TextBlock
from agentcore.cases import CaseRecord
from agentcore.channels import PROACTIVE, InboundMessage, ObservedMessage
from agentcore.harness.model.scripted import ScriptedModel, reply
from plugin_kit import JudgeUnavailableError
from plugins.follow_up.case import KIND, FollowUps, FollowUpSettings, follow_up_case
from plugins.follow_up.rules import INSTRUCTION_MARK

CHANNEL = "zalo-a"


def vn(hour: int, minute: int = 0, day: int = 17) -> datetime:
    return datetime(2026, 10, day, hour, minute, tzinfo=UTC) - timedelta(hours=7)


HESITANT = '{"state": "hesitant", "after_h": 3, "reason": "hỏi giá rồi im"}'


class Outbox:
    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []
        self.fail = 0

    async def send_to(self, **message: str) -> ProactiveSent:
        if self.fail:
            self.fail -= 1
            raise ConnectionError("the queue is unreachable")
        self.sent.append(message)
        return ProactiveSent(True)


class Jev:
    def __init__(self, *answers: Mapping[str, Any] | Exception, ready: bool = True) -> None:
        self.answers = list(answers)
        self.asked: list[str] = []
        self.on = ready

    async def ready(self) -> bool:
        return self.on

    async def ask(
        self, states: Sequence[Any], questions: Mapping[str, Mapping[str, Any]], *, timeout_s: float
    ) -> list[dict[str, Any]]:
        self.asked.extend(states)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return [dict(answer)]


def _jev(choice: str, confidence: float) -> dict[str, Any]:
    return {"state": {"type": "choice", "choice": choice, "confidence": confidence}}


class World:
    """The plugin's nodes, the engine with its memory store, one outbox, one clock and one chat."""

    def __init__(
        self,
        *answers: str,
        jev: Jev | None = None,
        settings: FollowUpSettings | None = None,
        per_day: int = 2,
        now: datetime = vn(9),
    ) -> None:
        self.now = now
        self.outbox = Outbox()
        self.model = ScriptedModel([reply(a) for a in answers])
        self.jev = jev
        self.config = CasesConfig(enabled=True, per_person_per_day=per_day)
        self.chat: list[Message] = [
            Message.user("giá khám bao nhiêu?"),
            Message(role="assistant", blocks=[TextBlock(text="Dạ 200k ạ")]),
        ]
        self.cases = InMemoryCaseStore()
        self.follow_ups = FollowUps(
            lambda: Cases(self.engine, "follow_up"),
            self._history,
            lambda: self.model,
            lambda: self.jev,
            settings or FollowUpSettings(channels=frozenset({CHANNEL})),
        )
        spec = follow_up_case(self.follow_ups)
        self.engine = CaseEngine(
            self.cases,
            lambda: {KIND: ("follow_up", spec)},
            config=lambda: self.config,
            zone=lambda: ZoneInfo("Asia/Ho_Chi_Minh"),
            clock=lambda: self.now,
        )

        async def session_for(channel: str, conversation_id: str) -> str:
            return f"session-{conversation_id}"

        self.engine.attach(self.outbox, session_for)

    async def _history(self, channel: str, conversation_id: str, limit: int) -> list[Message]:
        return self.chat[-limit:]

    async def answered(self, *, channel: str = CHANNEL, **metadata: str) -> None:
        """The agent answered the customer (who had just written) at ``now``."""
        await self.follow_ups.heard(
            ObservedMessage(
                channel=channel,
                conversation_id="c1",
                sender_id="",
                user_id="u1",
                message_id="m#reply",
                text="Dạ 200k ạ",
                origin="agent",
                at=self.now,
                metadata=metadata,
            )
        )

    async def at(self, when: datetime) -> None:
        self.now = when
        await self.engine.pass_once()

    async def case(self) -> CaseRecord:
        (found,) = await self.cases.list()
        return found


async def test_a_quiet_chat_is_judged_once_after_two_hours_and_written_to_once_at_its_time() -> None:
    world = World(HESITANT)
    await world.answered()

    await world.at(vn(10))
    assert (await world.case()).node == "quiet"
    await world.at(vn(11))
    await world.at(vn(11, 30))

    case = await world.case()
    assert (case.node, case.status, case.wake_at) == ("check", "waiting", vn(14))
    assert case.state["state"] == "hesitant"
    assert world.outbox.sent == []

    await world.at(vn(14))
    await world.at(vn(14, 5))

    (sent,) = world.outbox.sent
    assert (sent["channel"], sent["conversation_id"], sent["user_id"]) == (CHANNEL, "c1", "u1")
    assert sent["message_id"] == f"case:{case.id}:0"
    assert INSTRUCTION_MARK in sent["instruction"]
    assert "hesitant (hỏi giá rồi im)" in sent["instruction"]
    after = await world.case()
    assert (after.node, after.wait_for, after.wake_at) == ("quiet", "customer", vn(16))


async def test_a_customer_with_nothing_more_to_ask_is_left_alone_and_a_plain_no_stops_the_case() -> None:
    done = World('{"state": "done", "reason": "đã đặt lịch"}')
    no = World('{"state": "hard_decline", "reason": "không có nhu cầu"}')
    for world in (done, no):
        await world.answered()
        await world.at(vn(11))

    assert ((await done.case()).status, (await no.case()).status) == ("done", "stopped")
    assert done.outbox.sent == no.outbox.sent == []


async def test_a_customer_who_writes_before_the_appointment_sends_the_case_back_to_wait_for_silence() -> None:
    world = World(HESITANT, '{"state": "done"}')
    await world.answered()
    await world.at(vn(11))  # judged: write at 14:00

    world.now = vn(12)
    await world.answered()  # the customer wrote, the agent answered
    await world.at(vn(12))
    assert (await world.case()).node == "quiet"

    await world.at(vn(14))  # silent two hours since 12:00: judged again, done this time

    assert (await world.case()).status == "done"
    assert world.outbox.sent == []


async def test_words_that_mean_stop_end_the_case_without_asking_any_judge() -> None:
    waiting = World(HESITANT)
    await waiting.answered()
    await waiting.at(vn(10))  # waiting for the silence
    await waiting.engine.on_inbound(
        InboundMessage(
            channel=CHANNEL, conversation_id="c1", user_id="u1", message_id="x", text="đừng nhắn nữa"
        )
    )
    in_chat = World()
    in_chat.chat += [
        Message.user("thôi đừng nhắn nữa"),
        Message(role="assistant", blocks=[TextBlock(text="Dạ")]),
    ]
    await in_chat.answered()
    await in_chat.at(vn(11))

    for world in (waiting, in_chat):
        assert (await world.case()).status == "stopped"
        assert world.outbox.sent == []
    assert in_chat.model.requests == []


async def test_two_messages_without_an_answer_end_the_case() -> None:
    world = World(HESITANT, HESITANT)
    await world.answered()
    await world.at(vn(11))
    await world.at(vn(14))  # first message
    await world.at(vn(16))  # no answer: judged again; a day must pass since the first
    assert (await world.case()).wake_at == vn(14, day=18)

    await world.at(vn(14, day=18))

    assert len(world.outbox.sent) == 2
    case = await world.case()
    assert (case.status, case.end_reason) == ("stopped", "unanswered reached 2")


async def test_outside_the_hours_and_without_room_today_the_message_waits() -> None:
    late = World('{"state": "hesitant", "after_h": 9}')
    full = World(HESITANT, per_day=0)
    for world in (late, full):
        await world.answered()
        await world.at(vn(11))
    await late.at(vn(20))
    await full.at(vn(14))

    assert late.outbox.sent == full.outbox.sent == []
    assert (await late.case()).wake_at == vn(8, day=18)
    case = await full.case()
    assert (case.node, case.wake_at) == ("check", vn(8, day=18))


async def test_a_send_that_raised_is_checked_again_and_then_sent_once() -> None:
    world = World(HESITANT)
    world.outbox.fail = 1
    await world.answered()
    await world.at(vn(11))
    await world.at(vn(14))
    assert world.outbox.sent == []
    assert (await world.case()).node == "check"

    await world.at(vn(14, 10))

    assert len(world.outbox.sent) == 1


async def test_nothing_happens_while_the_cases_are_off_and_no_case_opens_where_it_should_not() -> None:
    off = World(HESITANT)
    off.config = CasesConfig(enabled=False)
    await off.answered()
    await off.at(vn(11))
    assert off.outbox.sent == []
    assert off.model.requests == []

    elsewhere = World()
    await elsewhere.answered(channel="zalo-b")
    await elsewhere.answered(thread_type="group")
    await elsewhere.answered(**{PROACTIVE: "1"})
    assert await elsewhere.cases.list() == []


async def test_jev_judges_when_it_is_sure_and_the_chat_model_only_when_it_is_not() -> None:
    sure = World(jev=Jev(_jev("hesitant", 0.9)))
    unsure = World(HESITANT, jev=Jev(_jev("hesitant", 0.3)))
    down = World(HESITANT, jev=Jev(JudgeUnavailableError("hết hạn mức")))
    off = World(
        HESITANT,
        jev=Jev(_jev("done", 0.99)),
        settings=FollowUpSettings(channels=frozenset({CHANNEL}), judge_with_jev=False),
    )
    for world in (sure, unsure, down, off):
        await world.answered()
        await world.at(vn(11))

    assert sure.model.requests == []
    assert "Khách: giá khám bao nhiêu?" in sure.jev.asked[0]  # type: ignore[union-attr]
    case = await sure.case()
    assert (case.state["state"], case.state["reason"]) == ("hesitant", "Jev: hesitant (90%).")
    assert case.wake_at == vn(11, day=18)  # Jev reads no time: the default wait of a day
    for world in (unsure, down, off):
        assert len(world.model.requests) == 1
        assert (await world.case()).state["state"] == "hesitant"
    assert off.jev.asked == []  # type: ignore[union-attr]


def test_the_waits_are_settings_in_minutes_within_their_bounds() -> None:
    default = FollowUpSettings.of({}).policy
    assert (default.quiet_after, default.min_after, default.max_after) == (
        timedelta(hours=2),
        timedelta(hours=1),
        timedelta(days=14),
    )
    quick = FollowUpSettings.of({"quiet_after_min": 1, "min_after_min": 1, "max_after_min": 2}).policy
    assert (quick.quiet_after, quick.min_after, quick.max_after) == (
        timedelta(minutes=1),
        timedelta(minutes=1),
        timedelta(minutes=2),
    )
    for wrong in (
        {"quiet_after_min": 0},
        {"max_after_min": 20_161},
        {"min_after_min": 30, "max_after_min": 10},
    ):
        with pytest.raises(ValueError, match="must"):
            FollowUpSettings.of(wrong)


async def test_with_short_waits_a_quiet_chat_is_written_to_within_minutes() -> None:
    w = World(
        '{"state": "hesitant", "after_h": 24, "reason": "hỏi giá rồi im"}',
        "Dạ chị còn quan tâm gói khám không ạ?",
        settings=FollowUpSettings.of(
            {"channels": CHANNEL, "quiet_after_min": 1, "min_after_min": 1, "max_after_min": 2}
        ),
    )
    await w.answered()
    await w.at(w.now + timedelta(minutes=1))
    await w.at(w.now + timedelta(minutes=2))
    assert len(w.outbox.sent) == 1


async def test_a_test_send_skips_the_waits_and_the_hours_and_the_follow_up_stays_as_it_was() -> None:
    w = World(
        '{"state": "hesitant", "after_h": 24, "reason": "hỏi giá rồi im"}',
        "Dạ chị còn quan tâm gói khám không ạ?",
        now=vn(21),
    )
    await w.answered()
    before = await w.case()

    outcome = await w.engine.try_now(before.id)

    assert outcome is not None
    assert outcome.sent
    assert len(w.outbox.sent) == 1
    after = await w.case()
    assert (after.status, after.node, after.wake_at, after.state) == (
        before.status,
        before.node,
        before.wake_at,
        before.state,
    )

"""Following up as a case on the agent's case engine (docs/PLAN-case-loop.md 7), in the owner's frame of a
loop (docs/IDEAS-agent-loops.md 5):

* trigger: the agent's answer to a customer in a followed one-to-one chat opens the case (or wakes the one
  that is there); the clock does the rest;
* goal: a customer who went quiet hears from the clinic once, at the right time, if they still care, and is
  left alone otherwise;
* verify: ``check`` reads the state again right before each send, also before a send tried again after an
  error (the error edge leads back to it);
* stop: the judgement (done, a plain no, an upset customer), the words that mean "stop" (``stop_if``), two
  messages in a row without an answer (the counter ``unanswered``), the hours, the gap, the day's cap;
* memory: the case's own record and log (``agent_case``); the conversation is read from the chat itself.

``quiet`` waits for the silence, ``judge`` asks Jev (when it is on and sure) or the chat model what state the
customer is in, ``check`` waits for the time a message may go, ``write`` is the model's one turn. A customer
who writes again sends the case back to ``quiet``: the agent's answer to them wakes it.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from pydantic import BaseModel

from agent_app.plugins import Cases, PluginError
from agentcore import LlmRequest, Message, ModelClient
from agentcore.cases import Budget, CaseSpec, CodeNode, Edge, Graph, StopRules, Trigger, TurnNode
from agentcore.cases import Decision as Step
from agentcore.channels import PROACTIVE, ObservedMessage, in_group
from plugin_kit import JudgeService, JudgeUnavailableError

from .rules import (
    DEFAULT_POLICY,
    JEV_QUESTION,
    MAX_REASON_CHARS,
    SYSTEM_PROMPT,
    FollowUpPolicy,
    State,
    Verdict,
    asks_to_stop,
    decide,
    instruction_for,
    judged_text,
    last_words,
    next_day,
    parse_verdict,
    read_jev,
    render_transcript,
    send_at,
)

KIND: Final = "follow_up"
EVENT: Final = "replied"
HISTORY: Final = 60
"""Messages read for a judgement (tool traffic included); the transcript keeps the newest of what was said."""
STOP_WORDS: Final = "Khách nhắn đừng liên hệ nữa (từ khóa)."

logger = logging.getLogger(__name__)
History = Callable[[str, str, int], Awaitable[list[Message]]]


@dataclass(frozen=True, slots=True)
class FollowUpSettings:
    channels: frozenset[str] = frozenset()
    policy: FollowUpPolicy = DEFAULT_POLICY
    judge_with_jev: bool = True
    jev_min_confidence: float = 0.6
    jev_timeout_s: float = 4.0

    @classmethod
    def of(cls, config: Mapping[str, Any]) -> FollowUpSettings:
        channels = frozenset(c.strip() for c in str(config.get("channels") or "").split(",") if c.strip())
        confidence = float(config.get("jev_min_confidence", 0.6))
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("jev_min_confidence must be between 0 and 1")
        return cls(
            channels=channels,
            policy=FollowUpPolicy(timezone=str(config.get("timezone") or DEFAULT_POLICY.timezone)),
            judge_with_jev=bool(config.get("judge_with_jev", True)),
            jev_min_confidence=confidence,
        )


class FollowUpCase(BaseModel):
    """The state of a follow-up: the chat, the last answer of the agent, the judgement and its appointment."""

    channel: str
    conversation_id: str
    user_id: str
    replied_at: datetime
    """When the agent last answered the customer (the customer had just written)."""
    judged_at: datetime | None = None
    state: State = "done"
    reason: str = ""
    next_at: datetime | None = None
    paused_until: datetime | None = None
    sending_at: datetime | None = None
    """When ``check`` let the last message go; ``quiet`` makes it ``last_sent_at`` once the turn is over."""
    last_sent_at: datetime | None = None
    unanswered: int = 0
    looks: int = 0
    retries: int = 0


def case_key(channel: str, conversation_id: str) -> str:
    return f"{channel}:{conversation_id}"


class FollowUps:
    """The case's code nodes (``quiet``, ``judge``, ``check``) and what opens and wakes it (``heard``)."""

    def __init__(
        self,
        cases: Callable[[], Cases],
        history: History,
        model: Callable[[], ModelClient],
        judge: Callable[[], JudgeService | None],
        settings: FollowUpSettings,
    ) -> None:
        self._cases = cases
        self._history = history
        self._model = model
        self._judge = judge
        self.settings = settings

    async def heard(self, message: ObservedMessage) -> None:
        """The agent's answer to a customer opens the case of the chat, or wakes the one there with the
        customer's silence starting again. A message of the agent's own (this case's turn, a reminder) is
        not an answer: the turn's ``look_again`` times the next look."""
        if (
            message.origin != "agent"
            or message.channel not in self.settings.channels
            or message.is_group
            or in_group(message.metadata)
            or message.metadata.get(PROACTIVE) == "1"
            or not message.user_id
        ):
            return
        try:
            cases = self._cases()
        except PluginError:
            return  # outside ``agent serve``
        key = case_key(message.channel, message.conversation_id)
        try:
            if await cases.wake(KIND, key, {"replied_at": message.at, "unanswered": 0}):
                return
            state = FollowUpCase(
                channel=message.channel,
                conversation_id=message.conversation_id,
                user_id=message.user_id,
                replied_at=message.at,
            )
            await cases.open(
                KIND,
                key,
                channel=message.channel,
                conversation_id=message.conversation_id,
                user_id=message.user_id,
                state=state,
            )
        except Exception as err:  # the answer is out; a follow-up missed is not worth failing it
            logger.warning("the follow-up of a chat was not opened (%s)", type(err).__name__)

    async def quiet(self, case: FollowUpCase, now: datetime) -> Step:
        """Waits until the customer has been silent long enough since the last answer or message."""
        policy = self.settings.policy
        patch: dict[str, Any] = {}
        if case.sending_at is not None:
            patch = {"last_sent_at": case.sending_at, "sending_at": None}
        since = max(case.replied_at, case.sending_at or case.replied_at)
        if now < since + policy.quiet_after:
            return Step(next="quiet", wait_for="clock", wake_at=since + policy.quiet_after, patch=patch)
        if now - since > policy.quiet_after + policy.max_age:
            return Step(done="Im quá lâu trước khi được xét (dịch vụ dừng?): bỏ.", patch=patch)
        return Step(next="judge", patch=patch)

    async def judge(self, case: FollowUpCase, now: datetime) -> Step:
        """Reads the conversation and asks what state the customer is in; the limits make the rest."""
        policy = self.settings.policy
        messages = await self._history(case.channel, case.conversation_id, HISTORY)
        transcript = render_transcript(messages, policy)
        if any(asks_to_stop(text) for text in last_words(transcript)):
            return Step(stop=STOP_WORDS, patch={"judged_at": now, "state": "hard_decline"})
        verdict, how = await self._verdict(judged_text(transcript, now, policy))
        outcome = decide(verdict, now, case.last_sent_at, policy)
        patch = {
            "judged_at": now,
            "state": outcome.state,
            "reason": outcome.reason,
            "next_at": outcome.next_at,
            "paused_until": outcome.paused_until,
        }
        why = f"{outcome.state}: {outcome.reason}".strip()[:MAX_REASON_CHARS]
        if outcome.stopped:
            return Step(stop=why, patch=patch, note=how)
        if outcome.next_at is None:
            return Step(done=why, patch=patch, note=how)
        return Step(next="check", patch=patch, note=how)

    async def check(self, case: FollowUpCase, now: datetime) -> Step:
        """Right before a message: has the customer written since the judgement, is it time, are the hours,
        the gap and the day's cap kept."""
        policy = self.settings.policy
        if case.judged_at is not None and case.replied_at > case.judged_at:
            return Step(
                next="quiet", patch={"next_at": None}, note="the customer wrote before the appointment"
            )
        if case.next_at is None:
            return Step(done="Không còn hẹn.")
        if now - case.next_at > policy.max_late:
            return Step(done="Hẹn quá hạn, bỏ.")
        at = send_at(now, case.next_at, case.paused_until, case.last_sent_at, policy)
        if at > now:
            return Step(next="check", wait_for="clock", wake_at=at)
        if await self._cases().room_today(KIND, case.channel, case.user_id) <= 0:
            return Step(next="check", wait_for="clock", wake_at=next_day(now, policy), note="daily_cap")
        return Step(next="write", patch={"sending_at": now})

    async def _verdict(self, text: str) -> tuple[Verdict, str]:
        """Jev's judgement when it is on and sure, else the chat model's; and who judged, for the log."""
        note = "jev off"
        judge = self._judge() if self.settings.judge_with_jev else None
        if judge is not None:
            try:
                if await judge.ready():
                    answers = await judge.ask([text], JEV_QUESTION, timeout_s=self.settings.jev_timeout_s)
                    verdict, why = read_jev(answers[0], self.settings.jev_min_confidence)
                    if verdict is not None:
                        return verdict, f"jev: {why}"
                    note = f"jev: {why}"
                else:
                    note = "jev: not ready"
            except JudgeUnavailableError as err:
                note = f"jev: {err.message}"
            except (IndexError, KeyError, TypeError, ValueError):
                note = "jev: unreadable"
        request = LlmRequest(
            system=SYSTEM_PROMPT,
            messages=[Message.user(text)],
            max_output_tokens=400,
            reasoning="off",
        )
        result = await self._model().complete(request)
        verdict = parse_verdict(result.message.text())
        if verdict is None:
            logger.warning("follow-up judgement unreadable; taken as done")
            verdict = Verdict(state="done", reason="Không đọc được phán đoán của AI.")
        return verdict, f"{note}; model"


def follow_up_case(follow_ups: FollowUps) -> CaseSpec:
    """``quiet`` → ``judge`` → ``check`` → ``write``; back to ``quiet`` after a message (``unanswered``, two
    end the case) or when the customer wrote first; a send that raised goes back through ``check``."""
    policy = follow_ups.settings.policy

    def goal(case: FollowUpCase) -> str:
        return "Khách im lặng được nhắn lại một lần đúng lúc nếu còn quan tâm, không thì để yên"

    def verify(case: FollowUpCase) -> str:
        return "agent_case_event: phán đoán và tin đã gửi; cuộc chat: khách trả lời sau tin"

    def instruction(case: FollowUpCase, now: datetime) -> str:
        return instruction_for(case.state, case.reason)

    def stop_if(case: FollowUpCase, text: str) -> str | None:
        return STOP_WORDS if asks_to_stop(text) else None

    return CaseSpec(
        kind=KIND,
        state_model=FollowUpCase,
        goal=goal,
        triggers=(Trigger("clock"), Trigger("event", EVENT)),
        graph=Graph(
            start="quiet",
            nodes=(
                CodeNode("quiet", follow_ups.quiet),
                CodeNode("judge", follow_ups.judge),
                CodeNode("check", follow_ups.check),
                TurnNode("write", instruction, look_again=policy.quiet_after),
            ),
            edges=(
                Edge("quiet", "judge"),
                Edge("quiet", "quiet", counter="looks"),
                Edge("judge", "check"),
                Edge("judge", "quiet", counter="retries", on="error"),
                Edge("check", "write"),
                Edge("check", "check", counter="looks"),
                Edge("check", "quiet", counter="looks"),
                Edge("write", "quiet", counter="unanswered"),
                Edge("write", "check", counter="retries", on="error"),
            ),
        ),
        verify=verify,
        stop=StopRules(
            max_turns=4,
            max_proactive=4,
            # the longest pause and then the furthest appointment still fall inside the case's life
            max_age=policy.max_pause + policy.max_after,
            counters={"unanswered": 2, "looks": 50, "retries": 3},
        ),
        budget=Budget(per_person_per_day=1),
        stop_if=stop_if,
    )

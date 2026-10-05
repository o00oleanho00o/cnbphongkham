"""Test doubles for the seams of the scheduler (new module, no zalo-agent source).

Import in tests only. Nothing here talks to a network. They stand in for the parts other packages own
(``pema.scheduler.ports``, the conversation stores, the agent engine, ``AgentFacingClinicActions``), so the
scheduler is tested alone on a real Postgres; package G replaces them with the real objects.

``FakeOutbound`` implements just enough of the C2 pipeline to keep the ported tests meaningful: markdown
markers are stripped and turned into style spans, a text longer than the channel's ``max_text_length`` is cut
at a space into several parts, a text that contains a known system-prompt marker is blocked.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from pema.scheduler.ports import ReplyResult, ReplyTarget, SanitizedText
from pema_contracts.actions import ActionContext
from pema_contracts.agent_turn import (
    AgentTurnRequest,
    AgentTurnResult,
    StepTrace,
    TokenUsage,
    TurnCallbacks,
    TurnSource,
)
from pema_contracts.channel import ChannelPort, SendStatus, TextStyle
from pema_contracts.common import now_vn
from pema_contracts.conversation import StoredMessage
from pema_contracts.review import ReviewItemCreate, ReviewItemOut, ReviewStatus, RiskLevel

LEAK_MARKER = "Quy tắc an toàn (tuyệt đối, không có ngoại lệ)"
"""A fragment of the system prompt: ``FakeOutbound.sanitize_for_config`` blocks any text containing it."""


def fake_wrap_untrusted(content: str, label: str) -> str:
    """The shape of D4's ``wrapUntrustedContent``: a nonce-bounded block, closing tags defused."""
    import secrets

    nonce = secrets.token_hex(4)
    safe = content.replace("</noi_dung_ngoai>", "</noi_dung_ngoai-->")
    return f'<noi_dung_ngoai_{nonce} nguon="{label}">\n{safe}\n</noi_dung_ngoai_{nonce}>'


_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")
_HEADING = re.compile(r"^#{1,6} +(.+)$", re.MULTILINE)


class FakeOutbound:
    def sanitize_for_config(self, text: str) -> SanitizedText:
        if LEAK_MARKER in text:
            return SanitizedText(text="", chan=True)
        return SanitizedText(text=text.strip())

    def format_if_enabled(self, text: str) -> tuple[str, list[TextStyle]]:
        spans: list[tuple[int, int]] = []  # (start, length) in the CURRENT text, kept right after each edit
        out = _CODE.sub(lambda m: m.group(1), text)
        for pattern in (_HEADING, _BOLD):
            while True:
                match = pattern.search(out)
                if match is None:
                    break
                inner = match.group(1)
                removed = (match.end() - match.start()) - len(inner)
                spans = [(st + 0 if st < match.start() else st - removed, ln) for st, ln in spans]
                out = out[: match.start()] + inner + out[match.end() :]
                spans.append((match.start(), len(inner)))
        return out, [TextStyle(start=st, length=ln, style="b") for st, ln in sorted(spans)]

    async def send_reply_in_parts(
        self, target: ReplyTarget, text: str, styles: Sequence[TextStyle] = ()
    ) -> ReplyResult:
        caps = target.channel.capabilities()
        parts = _split(text, caps.max_text_length)
        keep_styles = list(styles) if caps.supports_formatting and len(parts) == 1 else []
        result = ReplyResult()
        delivered: list[str] = []
        for part in parts:
            try:
                sent = await target.channel.send_text(
                    target.thread_id,
                    part,
                    thread_kind=target.thread_kind,
                    styles=keep_styles,
                    proactive=True,
                )
            except Exception as err:
                result.error = err
                break
            if sent.status is SendStatus.REJECTED:
                result.error = RuntimeError(sent.detail or "rejected")
                break
            delivered.append(part)
            result.sent_parts += 1
        result.delivered_text = "".join(delivered)
        return result


def _split(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts: list[str] = []
    rest = text
    while len(rest) > limit:
        cut = rest.rfind(" ", 0, limit)
        cut = limit if cut <= 0 else cut + 1
        parts.append(rest[:cut])
        rest = rest[cut:]
    if rest:
        parts.append(rest)
    return parts


@dataclass
class FakeHistory:
    """``HistoryStore.append_message`` only; ``fail`` makes it raise ("send ok, bookkeeping failed")."""

    messages: list[tuple[UUID, str, str, StoredMessage]] = field(
        default_factory=list[tuple[UUID, str, str, StoredMessage]]
    )
    fail: bool = False

    async def append_message(
        self, clinic_id: UUID, account_id: str, thread_id: str, message: StoredMessage
    ) -> int:
        if self.fail:
            raise RuntimeError("history store is down")
        self.messages.append((clinic_id, account_id, thread_id, message))
        return len(self.messages)

    def contents(self, account_id: str, thread_id: str) -> list[str]:
        return [m.content for (_, a, t, m) in self.messages if a == account_id and t == thread_id]


@dataclass
class FakeUsage:
    """``UsageStore`` turn bookkeeping: counts how many times each step happened."""

    opened: list[tuple[int, TurnSource]] = field(default_factory=list[tuple[int, TurnSource]])
    finished: dict[int, list[TokenUsage]] = field(default_factory=dict[int, list[TokenUsage]])
    traces: dict[int, list[list[StepTrace]]] = field(default_factory=dict[int, list[list[StepTrace]]])

    async def open_agent_turn(
        self, clinic_id: UUID, account_id: str, thread_id: str, source: TurnSource = TurnSource.MESSAGE
    ) -> int:
        turn_id = len(self.opened) + 1
        self.opened.append((turn_id, source))
        return turn_id

    async def finish_agent_turn(self, clinic_id: UUID, turn_id: int, usage: TokenUsage) -> None:
        self.finished.setdefault(turn_id, []).append(usage)

    async def save_turn_trace(self, clinic_id: UUID, turn_id: int, steps: list[StepTrace]) -> None:
        self.traces.setdefault(turn_id, []).append(list(steps))


@dataclass
class FakeEngine:
    """``AgentEngine`` with scripted answers: a string or an exception to raise (last entry repeats)."""

    script: list[str | BaseException] = field(default_factory=list[str | BaseException])
    requests: list[AgentTurnRequest] = field(default_factory=list[AgentTurnRequest])
    handed_off: str | None = None
    on_run: Callable[[], None] | None = None
    """Called inside ``run_turn``, for example to stop the account in the middle of the turn."""
    usage: TokenUsage = field(
        default_factory=lambda: TokenUsage(input_tokens=60, output_tokens=15, total_tokens=75, steps=1)
    )

    async def run_turn(
        self, request: AgentTurnRequest, callbacks: TurnCallbacks | None = None
    ) -> AgentTurnResult:
        self.requests.append(request)
        if self.on_run is not None:
            self.on_run()
        index = min(len(self.requests) - 1, len(self.script) - 1)
        entry: str | BaseException = self.script[index] if self.script else ""
        if isinstance(entry, BaseException):
            raise entry
        if callbacks is not None:
            callbacks.trace.append(StepTrace(step_number=1, text=entry, finish_reason="stop"))
        if self.handed_off is not None:
            return AgentTurnResult(
                text="", usage=self.usage, handed_off=True, hand_off_reason=self.handed_off
            )
        return AgentTurnResult(text=entry, usage=self.usage)


@dataclass
class FakeClinicActions:
    """``AgentFacingClinicActions.create_review_item`` only, idempotent on ``job_id`` (like the SQL)."""

    items: dict[str, ReviewItemCreate] = field(default_factory=dict[str, ReviewItemCreate])
    fail: bool = False

    async def create_review_item(self, ctx: ActionContext, request: ReviewItemCreate) -> ReviewItemOut:
        if self.fail:
            raise RuntimeError("review service is down")
        self.items.setdefault(request.job_id, request)
        stored = self.items[request.job_id]
        return ReviewItemOut(
            id=uuid4(),
            kind=stored.kind,
            origin=stored.origin,
            status=ReviewStatus.PENDING,
            conversation_id=None,
            patient_id=None,
            patient_code=stored.patient_ref,
            draft_text=stored.draft_text,
            risk_level=RiskLevel.NORMAL,
            requires_doctor=False,
            created_at=now_vn(),
            version=1,
        )


def sent_texts(channel: ChannelPort) -> list[str]:
    """Texts a ``FakeChannel`` recorded (typing helper for the tests)."""
    sent = getattr(channel, "sent", [])
    return [part.text for part in sent]

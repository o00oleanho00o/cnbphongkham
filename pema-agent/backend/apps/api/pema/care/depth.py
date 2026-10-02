"""Depth classifier D1-D5 of the skill ``handoff`` (PLAN-AI01-M section 6). New module (not a port).

Order, and the reason for it (recipe M2b, step 2):

1. Red flags (``pema.policy.redflags``, package P) on the patient's own words: a hit is D5, ``critical``, at
   once. NO model is called, and no other rule can lower it. D5 is decided by these rules and by nothing else:
   a model that says "D5" is clamped to D4 (urgent) so the red-flag list stays the only door to D5.
2. Rules for D1 (administrative: booking, opening hours, address, price, payment) on the diacritic-folded
   text. They fire only when the message carries no symptom word; a message about booking AND "bị đỏ" goes to
   step 3.
3. A schema-constrained model call for D2-D4 (``DepthLlm``; the text has been through the PII mask first). A
   missing, failed or invalid answer is NOT "fine": it becomes D4 with confidence 0 (a person looks), source
   ``fallback``.

After 3, a safety floor: when the symptom words were found the depth is at least D3, whatever the model said.

Events that carry no patient text (a milestone, a birthday, the daily tick, a staff command) need no model:
``EVENT_DEPTH`` gives their depth by kind (a message the agent writes because of them is administrative or
standard care; the patient did not ask a question).

The cheap signals the plan lists (the patient asks for a person, is upset) are also read from the text by
rules, so they work when the model is down; the model's flags are OR-ed in. The lexicons are rules, not
thresholds; every number lives in ``HandoffConfig``.

Nothing here logs or stores message text.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pema.care.events import CareEvent, EventKind
from pema.care.handoff_types import Depth, DepthLlmOutput
from pema.care.ports import DepthLlm
from pema.policy.pii import mask_pii
from pema.policy.redflags import detect_red_flags_in_batch
from pema.policy.text_normalize import fold_text, to_nfc
from pema_contracts.agent_turn import TextGenerator

logger = logging.getLogger(__name__)

MAX_OUTPUT_TOKENS = 256
"""One small JSON object; a reply that hits this limit is cut and therefore invalid."""
MAX_LLM_CHARS = 1500
"""Longest masked text given to the model; the rest is cut (the red-flag scan already saw all of it)."""


class DepthSource(StrEnum):
    RED_FLAG = "red_flag"
    EVENT = "event"
    RULES = "rules"
    LLM = "llm"
    FALLBACK = "fallback"
    NO_TEXT = "no_text"


@dataclass(frozen=True)
class DepthSignals:
    asks_for_human: bool = False
    negative_sentiment: bool = False
    repeated_question: bool = False
    answer_rejected: bool = False
    symptom_words: bool = False


@dataclass(frozen=True)
class DepthResult:
    depth: Depth
    confidence: float
    source: DepthSource
    intent: str | None = None
    required_skill: str | None = None
    signals: DepthSignals = DepthSignals()
    red_flags: tuple[str, ...] = ()
    """Category codes of the red flags (``bleeding``, ...); never text."""


EVENT_DEPTH: dict[EventKind, Depth] = {
    EventKind.SESSION_COMPLETED: Depth.D2,
    EventKind.MILESTONE_DUE: Depth.D2,
    EventKind.VISIT_OVERDUE: Depth.D1,
    EventKind.NO_SHOW: Depth.D1,
    EventKind.DORMANT: Depth.D1,
    EventKind.BIRTHDAY: Depth.D1,
    EventKind.STAFF_COMMAND: Depth.D1,
    EventKind.DOCTOR_EDIT: Depth.D1,
    EventKind.DAILY_TICK: Depth.D1,
}
"""Depth of an event that has no patient text. A ``patient_message`` is never in here."""


def _rx(*parts: str) -> re.Pattern[str]:
    return re.compile("|".join(parts))


# folded (no diacritics, lower case) text. A word boundary is spelled ``(?<![a-z])...(?![a-z])``.
def _w(body: str) -> str:
    return rf"(?<![a-z])(?:{body})(?![a-z])"


_BOOKING = _rx(
    _w(
        r"dat\s*(?:lich|hen)|hen\s*lich|doi\s*lich|huy\s*lich|doi\s*hen|huy\s*hen|lich\s*hen|tai\s*kham\s*(?:khi\s*nao|ngay)"
    )
)
_PAYMENT = _rx(_w(r"thanh\s*toan|hoa\s*don|chuyen\s*khoan|xuat\s*hoa\s*don|dat\s*coc|hoan\s*tien"))
_INFO = _rx(
    _w(
        r"gio\s*(?:lam\s*viec|mo\s*cua|dong\s*cua)|may\s*gio\s*(?:mo|dong)\s*cua|dia\s*chi\s*(?:phong\s*kham)?|"
        r"o\s*dau|duong\s*di|gui\s*xe|hotline|so\s*dien\s*thoai\s*phong\s*kham|bang\s*gia|gia\s*bao\s*nhieu|"
        r"bao\s*nhieu\s*tien|chi\s*phi"
    )
)

_SYMPTOM = _rx(
    _w(
        r"bi\s*do|da\s*do|do\s*(?:len|rat|ruc|vung|chan|mat)|ngua|man\s*(?:ngua|do)|noi\s*(?:mun|man|me\s*day|ban|rop|bong\s*nuoc)|"
        r"bi\s*rat|rat\s*(?:rat|ngua|da|mat|vung)|bong\s*(?:rat|troc|nuoc)|troc\s*da|nut\s*ne|phong\s*(?:rop|nuoc)|"
        r"sung|bi\s*dau|dau\s*(?:rat|nhuc|da|mat|vung|qua|lam|chan|tay|mui|bung|dau)|nhuc|buot|cham\s*chich|"
        r"nong\s*(?:rat|da|mat|vung|len)|kich\s*ung|di\s*ung|bam\s*tim|tham\s*(?:tim|den|vung|da|mat|len|nhieu)|"
        r"nam\s*(?:len|nhieu)|mun|vet\s*thuong|chong\s*mat|buon\s*non|"
        r"co\s*sao\s*khong|binh\s*thuong\s*khong|bi\s*lam\s*sao|tac\s*dung\s*phu|"
        r"uong\s*thuoc|boi\s*thuoc|thuoc\s*(?:nay|gi|nao)|trieu\s*chung|chong\s*chi\s*dinh|mang\s*thai|cho\s*con\s*bu"
    )
)

_ASKS_FOR_HUMAN = _rx(
    _w(
        r"gap\s*(?:nguoi|nhan\s*vien|bac\s*si|tu\s*van\s*vien|quan\s*ly)|noi\s*chuyen\s*voi\s*(?:nguoi|nhan\s*vien|bac\s*si)|"
        r"cho\s*(?:em|toi|minh)\s*(?:gap|noi\s*chuyen)|nhan\s*vien\s*(?:tra\s*loi|ho\s*tro)|goi\s*(?:lai\s*)?cho\s*(?:em|toi|minh)|"
        r"khong\s*phai\s*(?:bot|may)|bot\s*(?:ha|a)\b|tu\s*van\s*vien"
    )
)
_NEGATIVE = _rx(
    _w(
        r"buc\s*(?:minh|qua|boi)?|te\s*qua|khong\s*hai\s*long|that\s*vong|khieu\s*nai|lua\s*dao|tuc\s*gian|phan\s*nan|"
        r"qua\s*tre|khong\s*ai\s*tra\s*loi|bo\s*mac|chan\s*qua|met\s*moi\s*qua"
    )
)
_ANSWER_REJECTED = _rx(
    _w(
        r"khong\s*phai\s*(?:cai\s*)?(?:em\s*)?hoi|tra\s*loi\s*sai|khong\s*dung|khong\s*giai\s*quyet|"
        r"van\s*chua\s*(?:ro|duoc)|chua\s*tra\s*loi|noi\s*lai"
    )
)

_ROLE_BY_INTENT = (
    ("booking", _BOOKING),
    ("payment", _PAYMENT),
    ("info", _INFO),
)


def _fold(texts: Sequence[str]) -> str:
    return fold_text(to_nfc(" \n ".join(t for t in texts if t)))


def administrative_intent(folded: str) -> str | None:
    """``booking``, ``payment`` or ``info`` when the folded text is an administrative question."""
    for intent, pattern in _ROLE_BY_INTENT:
        if pattern.search(folded):
            return intent
    return None


def text_signals(folded: str) -> DepthSignals:
    """The signals a rule can read from the words alone."""
    return DepthSignals(
        asks_for_human=_ASKS_FOR_HUMAN.search(folded) is not None,
        negative_sentiment=_NEGATIVE.search(folded) is not None,
        answer_rejected=_ANSWER_REJECTED.search(folded) is not None,
        symptom_words=_SYMPTOM.search(folded) is not None,
    )


class DepthClassifier:
    """Rules first, then (for text the rules cannot place) one model call with a JSON schema."""

    def __init__(self, llm: DepthLlm | None = None) -> None:
        self._llm = llm

    async def classify(self, event: CareEvent, texts: Sequence[str], *, instruction: str = "") -> DepthResult:
        if event.kind is not EventKind.PATIENT_MESSAGE:
            return DepthResult(EVENT_DEPTH.get(event.kind, Depth.D1), 1.0, DepthSource.EVENT)

        flags = detect_red_flags_in_batch(texts)
        if flags.triggered:
            return DepthResult(Depth.D5, 1.0, DepthSource.RED_FLAG, red_flags=flags.flags)

        folded = _fold(texts)
        if not folded.strip():
            # a sticker, a file: nothing to read, nothing to answer on; a person looks.
            return DepthResult(Depth.D3, 0.0, DepthSource.NO_TEXT)

        signals = text_signals(folded)
        intent = administrative_intent(folded)
        if intent is not None and not signals.symptom_words:
            return DepthResult(Depth.D1, 1.0, DepthSource.RULES, intent=intent, signals=signals)

        return await self._by_model(texts, signals, instruction)

    async def _by_model(self, texts: Sequence[str], signals: DepthSignals, instruction: str) -> DepthResult:
        verdict = await self._ask(texts, instruction)
        if verdict is None:
            return DepthResult(Depth.D4, 0.0, DepthSource.FALLBACK, signals=signals)
        depth = verdict.depth
        if depth is Depth.D5:
            depth = Depth.D4  # D5 belongs to the red-flag rules
        if signals.symptom_words and depth.rank < Depth.D3.rank:
            depth = Depth.D3
        merged = DepthSignals(
            asks_for_human=signals.asks_for_human or verdict.asks_for_human,
            negative_sentiment=signals.negative_sentiment or verdict.negative_sentiment,
            repeated_question=verdict.repeated_question,
            answer_rejected=signals.answer_rejected or verdict.answer_rejected,
            symptom_words=signals.symptom_words,
        )
        return DepthResult(
            depth,
            verdict.confidence,
            DepthSource.LLM,
            intent=verdict.intent,
            required_skill=verdict.required_skill,
            signals=merged,
        )

    async def _ask(self, texts: Sequence[str], instruction: str) -> DepthLlmOutput | None:
        if self._llm is None:
            return None
        masked = "\n".join(mask_pii(t).text for t in texts if t.strip())[:MAX_LLM_CHARS]
        try:
            return await self._llm.classify(masked, instruction=instruction)
        except Exception as exc:  # a failing model must not take the turn down: fall back to "a person looks"
            logger.warning("depth model failed", extra={"error": type(exc).__name__})
            return None


# ----------------------------------------------------------------------------- the model adapter
DEPTH_PROMPT = """{instruction}

Phân loại tin nhắn của khách (đã che thông tin cá nhân) và CHỈ trả về một đối tượng JSON,
không thêm chữ nào khác. Giá trị "depth": "D1" hành chính, "D2" chăm sóc chuẩn,
"D3" triệu chứng nhẹ trong dự kiến, "D4" phán đoán y khoa.
Nếu không chắc, chọn độ sâu cao hơn và hạ "confidence".
Schema: {schema}

Tin nhắn:
{text}
"""


def _json_object(text: str) -> str | None:
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    return text[start : end + 1]


class TextGeneratorDepthLlm:
    """``DepthLlm`` over D1's ``TextGenerator`` (a single-shot completion with no tools).

    Deviation, stated plainly: the generator takes a prompt and returns text, it has no ``response_format``.
    The schema is therefore given in the prompt and ENFORCED here by validating the reply with
    ``DepthLlmOutput`` (unknown depth, confidence outside 0..1, or no JSON means ``None``, i.e. the fallback).
    """

    def __init__(self, generator: TextGenerator, *, max_output_tokens: int = MAX_OUTPUT_TOKENS) -> None:
        self._generator = generator
        self._max_output_tokens = max_output_tokens

    async def classify(self, masked_text: str, *, instruction: str) -> DepthLlmOutput | None:
        schema = DepthLlmOutput.model_json_schema()
        prompt = DEPTH_PROMPT.format(instruction=instruction, schema=schema, text=masked_text)
        result = await self._generator.generate_text(prompt, max_output_tokens=self._max_output_tokens)
        if result.truncated:
            return None
        body = _json_object(result.text)
        if body is None:
            return None
        try:
            return DepthLlmOutput.model_validate_json(body)
        except ValueError:
            return None

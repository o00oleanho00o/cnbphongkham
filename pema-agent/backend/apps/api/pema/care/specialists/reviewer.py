"""ReviewerAgent: read-only scoring of a draft against the doctor's checklist (PLAN-AI01-M section 9).

New module (not a port). Source of the rules: ``recipes/M/06-M4-specialists.md`` step 5. The checklist is
DATA: one row of ``agent.skills`` named ``review_checklist`` (``classifier_config`` below). The default
checklist is TEMPORARY and flagged ``pending_doctor_approval``: the doctor decides the final wording of the
terms and which checks are blocking (PLAN-M section 15, decision 1).

Why no model call. Every check is a deterministic rule over the draft and a few structured facts the care
agent passes in ``context`` (the cited sources, the template it claims, the depth it claims): a phone number
or a diagnosis phrase must be caught the same way every time, and the Reviewer is switched on for every
draft, so it must be cheap and fast. The Reviewer is still an ``agent.agents`` record (``reviewer_spec``,
persona and an EMPTY tool allowlist, read only) so it has its own kill switch (``KillSwitchState.agents``)
and its own ``agent.tasks`` rows; ``ChecklistRunner`` is its runner.

The five checks (each can be switched off in the row):

``has_sources``          the draft rests on at least one knowledge-base citation, for the action types that
                         need it (``sources_required_for``);
``no_diagnosis``         no diagnosis or prescription phrase (``diagnosis_terms``, matched on the diacritic
                         folded text with word boundaries);
``no_pii``               no phone number, id number, e-mail, address, birth date or self-introduced name in
                         the draft (``pema.policy.pii.find_pii_spans``; only the KINDS are reported, never
                         the matched text);
``template_respected``   a draft that claims a template matches the approved template body (the
                         ``{variables}`` of the template match any text);
``depth_classified``     the depth the care agent claims is not shallower than the one M2b's classifier gives
                         (skipped when no classifier is wired).

A failed check makes ``needs_human`` true; ``confidence`` is the share of evaluated checks that passed.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from pema.care.autonomy import DEPTH_ORDER
from pema.care.specialists.spec import REVIEWER_ID, SpecialistCall, SpecialistRun, SpecialistSpec
from pema.care.task_result import TaskResult
from pema.policy.pii import find_pii_spans
from pema.policy.text_normalize import fold_text, to_nfc
from pema_contracts.common import JsonObject
from pema_contracts.policy import PolicyProfileKey

logger = logging.getLogger(__name__)

CHECKLIST_SKILL_NAME = "review_checklist"

CHECK_HAS_SOURCES = "has_sources"
CHECK_NO_DIAGNOSIS = "no_diagnosis"
CHECK_NO_PII = "no_pii"
CHECK_TEMPLATE = "template_respected"
CHECK_DEPTH = "depth_classified"
CHECK_IDS: tuple[str, ...] = (
    CHECK_HAS_SOURCES,
    CHECK_NO_DIAGNOSIS,
    CHECK_NO_PII,
    CHECK_TEMPLATE,
    CHECK_DEPTH,
)

REVIEWER_PERSONA = (
    "Bạn là người rà soát bản nháp, chỉ đọc, làm việc phía sau agent chăm sóc khách hàng. Bạn chấm bản "
    "nháp theo "
    "checklist của bác sĩ (có nguồn, có chẩn đoán, có thông tin cá nhân, đúng template, phân loại độ sâu "
    "đúng) "
    "và không sửa gì, không gửi gì, không gọi tool nào."
)

# TEMPORARY, awaiting doctor. Lower case WITH diacritics; matched on the folded text, word boundaries.
DEFAULT_DIAGNOSIS_TERMS: tuple[str, ...] = (
    "chẩn đoán",
    "bạn bị",
    "chị bị",
    "anh bị",
    "em bị",
    "bị viêm",
    "bị nhiễm trùng",
    "chắc chắn là",
    "kết luận là",
    "kê đơn",
    "đơn thuốc",
    "tăng liều",
    "giảm liều",
    "uống thêm thuốc",
)

type ClassifyDepth = Callable[[str], Awaitable[str | None]]
"""M2b's depth classifier as a function of the draft text (``D1``..``D5`` or ``None``)."""


class ReviewChecklist(BaseModel):
    """The ``classifier_config`` of the skill row ``review_checklist``."""

    model_config = ConfigDict(frozen=True, extra="ignore")

    pending_doctor_approval: bool = True
    enabled: dict[str, bool] = Field(default_factory=lambda: dict.fromkeys(CHECK_IDS, True))
    sources_required_for: tuple[str, ...] = ("faq_kb_answer",)
    diagnosis_terms: tuple[str, ...] = DEFAULT_DIAGNOSIS_TERMS

    def is_enabled(self, check_id: str) -> bool:
        return self.enabled.get(check_id, True)

    @classmethod
    def from_config(cls, config: Mapping[str, Any] | None) -> ReviewChecklist:
        """The stored configuration, or the (pending) default when it is missing or unreadable."""
        if not config:
            return cls()
        try:
            return cls.model_validate(config)
        except ValidationError:
            logger.warning("review checklist config unreadable, using the default")
            return cls()

    def to_config(self) -> JsonObject:
        return self.model_dump(mode="json")


DEFAULT_CHECKLIST = ReviewChecklist()

CHECKLIST_INSTRUCTION = (
    "Checklist rà soát bản nháp (MẶC ĐỊNH, chờ bác sĩ duyệt): 1) có nguồn trích dẫn khi trả lời kiến thức; "
    "2) không có chẩn đoán hay đơn thuốc; 3) không có thông tin cá nhân (số điện thoại, CCCD, email, địa "
    "chỉ, "
    "ngày sinh); 4) đúng nội dung template đã duyệt nếu nhận là template; 5) độ sâu D1-D5 khai báo không "
    "nhẹ hơn "
    "độ sâu bộ phân loại cho ra."
)


def reviewer_spec() -> SpecialistSpec:
    return SpecialistSpec(
        agent_id=REVIEWER_ID,
        name="Người rà soát nháp",
        icon="🔎",
        persona=REVIEWER_PERSONA,
        allowed_tools=frozenset(),
        policy_profile=PolicyProfileKey.STAFF_ASSISTANT,
        read_only=True,
    )


# ------------------------------------------------------------------------------------- the checks
@dataclass(frozen=True)
class CheckOutcome:
    check_id: str
    status: str
    """``passed``, ``failed`` or ``skipped``."""
    detail: str = ""

    def to_json(self) -> JsonObject:
        return {"id": self.check_id, "status": self.status, "detail": self.detail}


def _has_term(folded_text: str, folded_term: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(folded_term)}(?!\w)", folded_text) is not None


def _check_sources(checklist: ReviewChecklist, action_type: str | None, citations: int) -> CheckOutcome:
    if action_type is None or action_type not in checklist.sources_required_for:
        return CheckOutcome(CHECK_HAS_SOURCES, "passed", "not required for this action type")
    if citations >= 1:
        return CheckOutcome(CHECK_HAS_SOURCES, "passed", f"{citations} source(s)")
    return CheckOutcome(CHECK_HAS_SOURCES, "failed", "no knowledge-base citation")


def _check_diagnosis(checklist: ReviewChecklist, draft: str) -> CheckOutcome:
    folded = fold_text(to_nfc(draft))
    hits = [t for t in checklist.diagnosis_terms if _has_term(folded, fold_text(to_nfc(t)))]
    if hits:
        return CheckOutcome(CHECK_NO_DIAGNOSIS, "failed", f"{len(hits)} diagnosis or prescription phrase(s)")
    return CheckOutcome(CHECK_NO_DIAGNOSIS, "passed")


def _check_pii(draft: str) -> CheckOutcome:
    kinds = sorted({span.kind.value for span in find_pii_spans(draft)})
    if kinds:
        return CheckOutcome(CHECK_NO_PII, "failed", "personal data of kind: " + ", ".join(kinds))
    return CheckOutcome(CHECK_NO_PII, "passed")


_VARIABLE = re.compile(r"\{[a-zA-Z0-9_]+\}")


def _template_pattern(body: str) -> re.Pattern[str]:
    normalized = " ".join(to_nfc(body).split())
    return re.compile(".+?".join(re.escape(part) for part in _VARIABLE.split(normalized)), re.DOTALL)


def _check_template(template_id: str | None, template_body: str | None, draft: str) -> CheckOutcome:
    if template_id is None:
        return CheckOutcome(CHECK_TEMPLATE, "passed", "no template claimed")
    if template_body is None:
        return CheckOutcome(CHECK_TEMPLATE, "failed", "template claimed but its body is unknown")
    normalized_draft = " ".join(to_nfc(draft).split())
    if _template_pattern(template_body).fullmatch(normalized_draft):
        return CheckOutcome(CHECK_TEMPLATE, "passed")
    return CheckOutcome(CHECK_TEMPLATE, "failed", "the text differs from the approved template")


def _depth_rank(depth: str | None) -> int | None:
    return DEPTH_ORDER.index(depth) if depth in DEPTH_ORDER else None


def _check_depth(claimed: str | None, classified: str | None, *, has_classifier: bool) -> CheckOutcome:
    if not has_classifier:
        return CheckOutcome(CHECK_DEPTH, "skipped", "no depth classifier wired (M2b)")
    claimed_rank = _depth_rank(claimed)
    classified_rank = _depth_rank(classified)
    if classified_rank is None:
        return CheckOutcome(CHECK_DEPTH, "skipped", "classifier gave no depth")
    if claimed_rank is None:
        return CheckOutcome(CHECK_DEPTH, "failed", "no valid depth claimed")
    if claimed_rank < classified_rank:
        return CheckOutcome(CHECK_DEPTH, "failed", f"claimed {claimed}, classified {classified}")
    return CheckOutcome(CHECK_DEPTH, "passed")


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _citation_count(context: Mapping[str, Any]) -> int:
    value = context.get("citations")
    if isinstance(value, list):
        return len(cast("list[object]", value))
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


async def review_draft(
    draft: str,
    context: Mapping[str, Any],
    checklist: ReviewChecklist,
    *,
    classify_depth: ClassifyDepth | None = None,
) -> TaskResult:
    """Score ``draft``. ``context`` keys (all optional): ``action_type``, ``citations`` (list or count),
    ``template_id``, ``template_body``, ``claimed_depth``."""
    outcomes: list[CheckOutcome] = []
    if checklist.is_enabled(CHECK_HAS_SOURCES):
        outcomes.append(
            _check_sources(checklist, _str_or_none(context.get("action_type")), _citation_count(context))
        )
    if checklist.is_enabled(CHECK_NO_DIAGNOSIS):
        outcomes.append(_check_diagnosis(checklist, draft))
    if checklist.is_enabled(CHECK_NO_PII):
        outcomes.append(_check_pii(draft))
    if checklist.is_enabled(CHECK_TEMPLATE):
        outcomes.append(
            _check_template(
                _str_or_none(context.get("template_id")), _str_or_none(context.get("template_body")), draft
            )
        )
    if checklist.is_enabled(CHECK_DEPTH):
        classified = await classify_depth(draft) if classify_depth is not None else None
        outcomes.append(
            _check_depth(
                _str_or_none(context.get("claimed_depth")),
                classified,
                has_classifier=classify_depth is not None,
            )
        )
    evaluated = [o for o in outcomes if o.status != "skipped"]
    failed = [o for o in evaluated if o.status == "failed"]
    score = (len(evaluated) - len(failed)) / len(evaluated) if evaluated else 0.0
    flags = [o.check_id for o in failed]
    artifact: JsonObject = {
        "kind": "review",
        "pending_doctor_approval": checklist.pending_doctor_approval,
        "score": round(score, 3),
        "flags": cast("Any", flags),
        "checks": cast("Any", [o.to_json() for o in outcomes]),
    }
    summary = f"Nháp đạt {len(evaluated) - len(failed)}/{len(evaluated)} mục" + (
        f"; vướng: {', '.join(flags)}" if flags else ""
    )
    return TaskResult(
        summary=summary,
        artifacts=[artifact],
        # nothing evaluated means nothing was checked: a person looks
        needs_human=bool(failed) or not evaluated,
        confidence=score,
    )


class ChecklistSource(Protocol):
    async def get_checklist(self) -> ReviewChecklist: ...


class StaticChecklist:
    """A fixed checklist (tests, and the default while the doctor has not stored one)."""

    def __init__(self, checklist: ReviewChecklist = DEFAULT_CHECKLIST) -> None:
        self._checklist = checklist

    async def get_checklist(self) -> ReviewChecklist:
        return self._checklist


class ChecklistRunner:
    """``SpecialistRunner`` of the Reviewer: no model, no tool, the checklist of the skill row."""

    def __init__(
        self, checklist_source: ChecklistSource, classify_depth: ClassifyDepth | None = None
    ) -> None:
        self._source = checklist_source
        self._classify_depth = classify_depth

    async def run(self, call: SpecialistCall) -> SpecialistRun:
        checklist = await self._source.get_checklist()
        result = await review_draft(call.task, call.context, checklist, classify_depth=self._classify_depth)
        return SpecialistRun(result=result, tokens=0, steps=0)

"""How the agent answers from the store when the setting "Trả lời có kiểm" is on: a turn graph
(``agentcore.turns``, docs/PLAN-rag-graph.md section 5).

    search (code) ─found──────────────────────────────► answer (model)
       └─not found, once ─► rewrite (model, private) ──┘ back to search
    answer ─► check (code) ─ok──► send
                 ├─stray numbers, once ─► answer again, told why
                 └─again ─► safe_answer (model, no numbers) ─► check_safe ─ok─► send
                                                                    └─────────► send_fixed (the setting's sentence)

Code searches first, so the model only writes; code checks every number of the draft against what was found,
what the tools of the turn returned, what the person wrote and today's date, so no number the store does not
hold reaches the person (rules H4, H5). The model still has every tool: it may search again or read a whole
document while it answers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field

from agentcore.cases import Edge
from agentcore.loop.run_turn import SYSTEM_NOTE_PREFIX
from agentcore.turns import (
    CodeStep,
    ModelOutcome,
    ModelStep,
    SendStep,
    Step,
    TurnGraph,
    TurnGraphSpec,
    TurnView,
)

from .search import tool_text

if TYPE_CHECKING:
    from .plugin import KnowledgePlugin

REWRITES: Final = 1
REVISIONS: Final = 1
SHORT_WORDS: Final = 6
"""A message this short is read with the person's message before it (a follow-up: "còn gói 10 buổi?")."""
UNSURE_REPLY: Final = "Dạ em chưa có thông tin chắc chắn cho câu này, em chuyển nhân viên hỗ trợ mình ạ."

NUMBER: Final = re.compile(
    r"(?<![\d.,])(\d{1,3}(?:[.,]\d{3})+|\d+(?:[.,]\d+)?)(?:\s*(triệu|tr|tỷ|nghìn|ngàn|k)\b|\s*(%))?",
    re.IGNORECASE,
)
SCALE: Final = {"triệu": 1e6, "tr": 1e6, "tỷ": 1e9, "nghìn": 1e3, "ngàn": 1e3, "k": 1e3}

FACTS_NOTE: Final = """## Dữ kiện tìm được cho lượt này
Code đã tìm trong kho tri thức cho câu hỏi này; không cần gọi `kb_search` lại cho cùng câu hỏi (chỉ gọi khi cần ý khác,
hay `kb_read` khi cần cả tài liệu).

{facts}

Quy tắc: chỉ nêu con số (giá, số buổi, số ngày, phần trăm, ngày tháng) có đúng trong dữ kiện trên hoặc trong kết quả
công cụ của lượt này, không tự tính ra số mới. Câu trả lời được code kiểm từng con số trước khi gửi."""
NO_FACTS_NOTE: Final = """## Không tìm thấy dữ kiện
Code đã tìm trong kho tri thức (cả cách hỏi khác) mà không thấy đoạn nào cho câu này. Câu hỏi cần thông tin của cơ sở
(giá, dịch vụ, chính sách, quy trình) thì nói thật là chưa có thông tin, không đoán, không nêu con số nào, và mời khách
để lại liên lạc. Câu chào hay câu không cần tra thì trả lời bình thường."""
REWRITE_NOTE: Final = """## Viết lại câu tìm
Tìm trong kho tri thức với câu "{query}" không thấy gì. Dựa vào cuộc chat, viết lại điều khách đang hỏi cho đủ ý (ghép
dịch vụ hay chủ đề đang nói), và tối đa hai cách hỏi khác dùng từ tài liệu hay dùng (tên dịch vụ, tên chính sách).
Chỉ trả về một dòng JSON, không gì khác: {{"query": "...", "alternatives": ["..."]}}"""
SAFE_NOTE: Final = """## Trả lời không có con số
Hai lần trả lời trước nêu con số không có trong dữ kiện. Viết lại câu trả lời mà KHÔNG nêu bất kỳ chữ số nào (giá, số
buổi, ngày, phần trăm): nói bằng lời điều chắc chắn có trong dữ kiện, và mời khách để lại liên lạc để nhân viên báo
con số chính xác."""


class AnswerState(BaseModel):
    query: str = ""
    variants: list[str] = Field(default_factory=list[str])
    facts: str = ""
    found: bool = False
    ok: bool = False
    rewrites: int = 0
    revisions: int = 0
    unsure_reply: str = UNSURE_REPLY


def answer_graph(plugin: KnowledgePlugin) -> TurnGraphSpec:
    zone = plugin.zone

    async def active() -> bool:
        return (await plugin.settings())["answer"]["graph"] == "on"

    async def search(state: AnswerState, view: TurnView) -> Step:
        question = state.query or asked(view)
        settings = await plugin.settings()
        result = await plugin.search_for(question, state.variants, view.now, view.channel or "")
        found = bool(result.final)
        return Step(
            patch={
                "query": question,
                "facts": tool_text(result) if found else "",
                "found": found,
                "unsure_reply": str(settings["answer"]["unsure_reply"]).strip() or UNSURE_REPLY,
            },
            note=f"{len(result.final)} đoạn",
        )

    async def check(state: AnswerState, view: TurnView) -> Step:
        held = numbers(" ".join([state.facts, *view.tool_texts, view.user_text, day_text(view.now, zone)]))
        stray = [raw for raw, value in drafted_numbers(view.draft) if value not in held]
        if not stray:
            return Step(patch={"ok": True})
        listed = ", ".join(dict.fromkeys(stray))
        return Step(
            patch={"ok": False},
            note=f"Các số {listed} không có trong dữ kiện tìm được: chỉ nêu con số có trong dữ kiện, hoặc không nêu.",
        )

    def answer_note(state: AnswerState) -> str:
        return FACTS_NOTE.format(facts=state.facts) if state.found else NO_FACTS_NOTE

    def rewritten(_state: AnswerState, outcome: ModelOutcome) -> dict[str, Any]:
        found = re.search(r"\{.*\}", outcome.text, re.DOTALL)
        try:
            data = json.loads(found.group(0)) if found else {}
        except ValueError:
            data = {}
        query = data.get("query") if isinstance(data, dict) else None
        if not isinstance(query, str) or len(query.strip()) < 2:
            return {}
        others = data.get("alternatives")
        variants = [v.strip()[:300] for v in others if isinstance(v, str) and len(v.strip()) >= 2] if isinstance(others, list) else []
        return {"query": query.strip()[:300], "variants": variants[:2]}

    return TurnGraphSpec(
        name="knowledge_answer",
        state_model=AnswerState,
        counters={"rewrites": REWRITES, "revisions": REVISIONS},
        active=active,
        graph=TurnGraph(
            start="search",
            nodes=(
                CodeStep("search", search),
                ModelStep(
                    "rewrite",
                    lambda s: REWRITE_NOTE.format(query=s.query),
                    tools=(),
                    max_steps=1,
                    keep=False,
                    after=rewritten,
                ),
                ModelStep("answer", answer_note, max_steps=3),
                CodeStep("check", check),
                ModelStep("safe_answer", lambda _s: SAFE_NOTE, tools=(), max_steps=1),
                CodeStep("check_safe", check),
                SendStep("send"),
                SendStep("send_fixed", text=lambda s: s.unsure_reply),
            ),
            edges=(
                Edge("search", "answer", when=lambda s: s.found),
                Edge("search", "rewrite", when=lambda s: s.rewrites < REWRITES),
                Edge("search", "answer"),
                Edge("search", "answer", on="error"),
                Edge("rewrite", "search", counter="rewrites"),
                Edge("answer", "check"),
                Edge("check", "send", when=lambda s: s.ok),
                Edge("check", "answer", counter="revisions"),
                Edge("check", "safe_answer"),
                Edge("check", "send_fixed", on="error"),
                Edge("safe_answer", "check_safe"),
                Edge("check_safe", "send", when=lambda s: s.ok),
                Edge("check_safe", "send_fixed"),
                Edge("check_safe", "send_fixed", on="error"),
            ),
        ),
    )


def asked(view: TurnView) -> str:
    """What to search for: the person's message, with their message before it when this one is short."""
    text = view.user_text.strip()
    if len(text.split()) >= SHORT_WORDS:
        return text[:300]
    theirs = [
        m.text().strip()
        for m in view.history
        if m.role == "user" and m.text().strip() and not m.text().startswith(SYSTEM_NOTE_PREFIX)
    ]
    before = theirs[-2] if len(theirs) >= 2 else ""
    # shortcut: only one message back is joined; a follow-up of a follow-up loses the topic (plan, question 2)
    return f"{before}\n{text}".strip()[:300] if before else text[:300]


def _value(raw: str, scale: str | None) -> float:
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", raw):
        number = float(re.sub(r"[.,]", "", raw))
    else:
        number = float(raw.replace(",", "."))
    return round(number * SCALE.get((scale or "").lower(), 1.0), 2)


def numbers(text: str) -> set[float]:
    """Every value a number of ``text`` may stand for (with and without its unit)."""
    held: set[float] = set()
    for match in NUMBER.finditer(text):
        held.add(_value(match.group(1), match.group(2)))
        held.add(_value(match.group(1), None))
    return held


def drafted_numbers(text: str) -> list[tuple[str, float]]:
    """The numbers of an answer, as written and as values; a list's numbering (``1.``, ``2)``) is left out."""
    found: list[tuple[str, float]] = []
    for match in NUMBER.finditer(text):
        line_start = text.rfind("\n", 0, match.start()) + 1
        after = text[match.end(1) : match.end(1) + 1]
        if not text[line_start : match.start()].strip() and after in (".", ")") and match.group(2) is None:
            continue
        found.append((match.group(0).strip(), _value(match.group(1), match.group(2))))
    return found


def day_text(now: datetime, zone: ZoneInfo) -> str:
    """Today's date and time where the store is, so a reply may say them."""
    local = now.astimezone(zone)
    return f"{local.day}/{local.month}/{local.year} {local.hour}:{local.minute}"

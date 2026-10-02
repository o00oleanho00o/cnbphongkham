"""KnowledgeAgent: looks up the knowledge base WITH sources, ingests documents, lists them (PLAN-M section 9).

New module (not a port). Config factory only: ``knowledge_spec()`` is the data of the ``care-knowledge``
record; ``kb_search`` / ``kb_ingest`` / ``kb_list`` are built by ``pema.care.specialists.toolkit`` over D3's
``KnowledgeStore``.

The rule that matters is enforced by code, not by the persona: ``finalize_knowledge_result`` replaces the
citations the model wrote with the sources the run REALLY received from ``kb_search`` and forces
``needs_human=True`` when there are none. An answer with no citation is never a ``faq_kb_answer`` that can be
auto-sent (M3 also needs ``kb_citations >= 1``).
"""

from __future__ import annotations

from pema.care.specialists.spec import (
    KNOWLEDGE_ID,
    TOOL_KB_INGEST,
    TOOL_KB_LIST,
    TOOL_KB_SEARCH,
    RunState,
    SpecialistSpec,
)
from pema.care.task_result import Citation, TaskResult
from pema_contracts.policy import PolicyProfileKey

NO_CITATION_SUMMARY = "Không tìm thấy nguồn tài liệu phù hợp; cần nhân viên trả lời."

KNOWLEDGE_PERSONA = (
    "Bạn là chuyên viên tra cứu kho tri thức của phòng khám, làm việc phía sau agent chăm sóc khách hàng. "
    "Bạn "
    "không nói chuyện với khách. Mọi câu trả lời phải dựa trên kết quả kb_search; không có kết quả thì "
    "nói thẳng "
    "là không có nguồn, đừng bịa. Không chẩn đoán, không kê đơn, không đổi liều thuốc. Tóm tắt ngắn gọn "
    "nội dung "
    "tìm được; hệ thống tự gắn nguồn trích dẫn từ kết quả tra cứu thật. Chỉ dùng kb_ingest khi được yêu "
    "cầu nạp "
    "tài liệu, kb_list khi cần biết kho có gì. Kết thúc bằng submit_result và đánh giá confidence trung thực."
)


def knowledge_spec() -> SpecialistSpec:
    return SpecialistSpec(
        agent_id=KNOWLEDGE_ID,
        name="Chuyên viên tri thức",
        icon="📚",
        persona=KNOWLEDGE_PERSONA,
        allowed_tools=frozenset({TOOL_KB_SEARCH, TOOL_KB_INGEST, TOOL_KB_LIST}),
        policy_profile=PolicyProfileKey.STAFF_ASSISTANT,
    )


def finalize_knowledge_result(result: TaskResult, state: RunState) -> TaskResult:
    """Citations come from the tool, never from the model; none -> a person answers."""
    seen = state.citations
    claimed = [c for c in result.citations if c.source_id in seen]
    cited = claimed or [Citation(source_id=sid, title=title) for sid, title in seen.items()]
    # A model that cites a source it never received is dropped above; one that cites nothing but DID
    # receive hits keeps the hits (the facts), never an invented source.
    if not cited:
        return result.model_copy(update={"citations": [], "confidence": 0.0}).with_needs_human(
            NO_CITATION_SUMMARY
        )
    return result.model_copy(update={"citations": cited})

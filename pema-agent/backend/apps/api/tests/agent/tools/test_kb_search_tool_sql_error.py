# ported from: src/agent/tools/kb-search-tool-sql-error.test.ts
"""A test ISOLATED to one file - forces the outer ``except`` branch of ``kb_search_tool`` with a failure of the
infrastructure under the knowledge port.

Forced deviation: the original DROPped the ``kb_chunks_fts`` table so that ``db.prepare(...)`` raised a REAL
SQLite error ("no such table: kb_chunks_fts"). Here the store is behind the async ``KnowledgeSearch`` port, so
the fake port raises an arbitrary exception. The original also asserted that the sentence carried the raw SQL
message; the Python tool deliberately does NOT leak it (a Postgres driver error can carry query parameters and
rows, i.e. personal data) and gives the model the exception class name instead. The assertions keep the spirit:
a marked failure, readable by the model, never an exception into the agent loop.
"""

from __future__ import annotations

import re
from uuid import UUID

from pema.agent.tools.kb_search_tool import create_kb_search_tool
from pema.agent.tools.testing import make_tool_context, make_tool_deps
from pema.agent.tools.tool_failure_result_test_helper import loi_cua_tool
from pema_contracts.knowledge import KbHit

AGENT_ID = "agent-loi-sql"
SECRET_DETAIL = "relation kb_chunks DETAIL Key (agent_id)=(secret-agent-123) does not exist"


class KbDownError(RuntimeError):
    """Stands for a driver error (the table is gone)."""


class BrokenKnowledge:
    """Every call raises, like a dropped table."""

    async def search(self, clinic_id: UUID, *, question: str, agent_id: str, limit: int = 5) -> list[KbHit]:
        raise KbDownError(SECRET_DETAIL)


async def test_kb_search_loi_ha_tang_tra_ve_chuoi_loi_cho_model_doc_khong_throw_ra_agent_loop() -> None:
    """trả về chuỗi lỗi cho model đọc, KHÔNG throw ra agent loop"""
    ctx = make_tool_context(agent_patch={"id": AGENT_ID})
    tool = create_kb_search_tool(ctx, make_tool_deps(knowledge=BrokenKnowledge()))

    # If the try/except of the tool were misplaced or missing, the ``await`` here would raise by itself and this
    # test would fail (no separate ``pytest.raises`` needed).
    result = await tool.execute({"cau_hoi": "bảo hành"})

    loi = loi_cua_tool(result)
    assert re.search("thất bại", loi, re.IGNORECASE), (
        "phải là câu lỗi đọc được cho model, không phải chuỗi rỗng hay JSON lỗi thô"
    )
    assert "KbDownError" in loi, "phải nêu loại lỗi hạ tầng thật, không phải câu chung chung bịa ra"
    assert "secret-agent-123" not in loi, "không được lộ chi tiết nội bộ của driver ra cho model"

# ported from: src/agent/tools/tool-catalog-read.test.ts
"""Test names are the snake_case form of ``describe_it``; the original Vietnamese title is the docstring.

The original needed ``setupTestEnv()`` because ``tool-catalog-read.ts`` opened the database at module scope; here the
catalogue is built from a ``ToolDeps`` of fakes, nothing touches a database.
"""

from __future__ import annotations

import re

from pema.agent.tools.testing import FakeKbAvailability, make_scope, make_tool_deps
from pema.agent.tools.tool_catalog_read import read_tool_definitions


def _kb_spec(kb: FakeKbAvailability | None = None):
    deps = make_tool_deps(kb_availability=kb or FakeKbAvailability())
    return next(t for t in read_tool_definitions(deps) if t.key == "kb_search")


def test_kb_search_unavailable_hint_i18_does_not_point_to_the_knowledge_tab_to_assign() -> None:
    """kb_search.unavailableHint (I18): không chỉ sang tab Kho tri thức để GÁN - tab đó không có ô gán nào"""
    spec = _kb_spec()
    hint = spec.unavailable_hint
    assert hint, "kb_search phải có unavailableHint - agent chưa gán nguồn cần được chỉ đường"
    assert not re.search(r"tab Kho tri thức để.*gán", hint, re.IGNORECASE), (
        "câu cũ đẩy người vận hành sang tab Kho tri thức để 'gán', nhưng tab đó chỉ NẠP tài liệu - ngõ cụt tròn"
    )
    assert re.search(r"ngay bên dưới|trang Agents|khối Kho tri thức", hint, re.IGNORECASE), (
        "phải chỉ đúng chỗ có ô gán thật: khối Kho tri thức trên trang Agents"
    )


def test_kb_search_available_asks_the_agent_scope_or_the_account_wide_scope_for_an_empty_agent_id() -> None:
    """available: id agent thật hỏi 'nguồn ĐÃ GÁN cho agent này'; id rỗng (trang Tools) hỏi 'kho đã có nguồn nào'"""
    spec = _kb_spec(FakeKbAvailability({"agent-a"}, any_source=False))
    assert spec.available is not None
    assert spec.available(make_scope(agent_id="agent-a")) is True
    assert spec.available(make_scope(agent_id="agent-b")) is False
    assert spec.available(make_scope(agent_id="")) is False, "kho chưa có nguồn nào"

    spec = _kb_spec(FakeKbAvailability(set(), any_source=True))
    assert spec.available is not None
    assert spec.available(make_scope(agent_id="")) is True, (
        "kho đã có nguồn: trang Tools không biết agent nào"
    )
    assert spec.available(make_scope(agent_id="agent-b")) is False, "hai nhánh không bao giờ lẫn nhau"

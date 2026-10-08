# ported from: src/index-startup-order.test.ts
"""Startup order of the API process (C2 of the original: "nguồn Kho tri thức treo/chết worker thì người vận hành
không vào được dashboard để xóa nó").

Branch feat/agent-v2: the worker process is gone and the API process runs the knowledge-base ingest itself. The
invariant of the original holds structurally: the ingest runs as its own background task, started after the
lifespan has built everything and never awaited inline, and every extraction runs in an isolated child process
with a timeout and a RAM ceiling (``pema.knowledge``). A poisoned KB source can therefore hang one ingest pass but
not the dashboard.

Like the original it does not run the process; it reads the source and asserts the structure.
"""

from __future__ import annotations

import re
from pathlib import Path

PEMA = Path(__file__).resolve().parents[1] / "pema"


def _source(relative: str) -> str:
    return (PEMA / relative).read_text(encoding="utf-8")


def test_the_app_factory_never_runs_the_kb_ingest_inline() -> None:
    """hàm tạo app không chạy ingest Kho tri thức trực tiếp, chỉ giao cho vòng đời nền"""
    text = _source("bootstrap.py")
    assert "KbIngestWorker" not in text
    assert "bat_dau_worker" not in text
    assert "chay_mot_vong_an_toan" not in text


def test_the_kb_ingest_runs_as_its_own_task_and_is_never_awaited_by_start() -> None:
    """ingest Kho tri thức là task nền riêng, hàm start không chờ nó"""
    text = _source("composition/app_runtime.py")
    assert re.search(r'create_task\(self\._kb_loop\(\), name="kb-ingest"\)', text)
    start = text[text.index("    async def start(self)") : text.index("    async def _crm_loop(")]
    assert "await self._kb_loop()" not in start
    assert "bat_dau_worker" not in start

# ported from: src/index-startup-order.test.ts
"""Startup order of the processes (C2 of the original: "nguồn Kho tri thức treo/chết worker thì người vận hành
không vào được dashboard để xóa nó").

Forced deviation: the original was ONE Node process (``index.ts``) that started the dashboard server and the
knowledge-base ingest worker, so the invariant was a source ORDER (``startDashboardServer()`` before
``batDauKbIngestWorker()``). Pema runs the API and the worker as TWO processes, so the same invariant is
structural: the API process (``pema.bootstrap`` and the API lifecycle of ``pema.composition.api_wiring``) never
starts the ingest worker at all, and inside the worker process the ingest runs as its own task, never awaited
inline before the turn worker is up. A poisoned KB source can therefore hang the ingest but not the
dashboard.

Like the original it does not run the processes (starting them has real side effects: channels, database); it
reads the source and asserts the structure, which is the cheapest thing that observes this invariant.
"""

from __future__ import annotations

import re
from pathlib import Path

PEMA = Path(__file__).resolve().parents[1] / "pema"


def _source(relative: str) -> str:
    return (PEMA / relative).read_text(encoding="utf-8")


def test_the_api_process_never_starts_the_kb_ingest_worker_a_poisoned_source_cannot_lock_the_dashboard() -> (
    None
):
    """tiến trình API không bao giờ khởi động worker Kho tri thức, nên nguồn độc không khóa được dashboard"""
    for relative in ("bootstrap.py", "composition/api_wiring.py", "composition/intake.py"):
        text = _source(relative)
        assert "KbIngestWorker" not in text, f"{relative} must not run the ingest worker"
        assert "pema.workers" not in text.replace("pema.workers.main", ""), (
            f"{relative} must not import the worker package"
        )


def test_the_worker_runs_kb_ingest_as_its_own_task_and_never_inline() -> None:
    """worker chạy ingest KB thành task riêng, không chờ nó trước khi turn worker và scheduler lên"""
    text = _source("workers/main.py")
    task_line = re.search(r"create_task\(\s*chay_mai_mai\(", text)
    assert task_line is not None, "the KB ingest loop must be created as a task"
    assert not re.search(r"await\s+chay_mai_mai\(", text), "the KB ingest loop must never be awaited inline"
    turn_worker = text.index('name="turn-worker"')
    kb_ingest = text.index('name="kb-ingest"')
    # the tasks are created in one block: the turn worker is scheduled before the ingest can start to run
    assert turn_worker < kb_ingest, "the turn worker is created before the KB ingest"

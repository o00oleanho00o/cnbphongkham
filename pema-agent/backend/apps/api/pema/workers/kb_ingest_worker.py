# ported from: src/knowledge/kb-ingest-worker.ts (``batDauWorker``: the boot work and the timer)
"""Process entry of the knowledge-base ingest worker: ``python -m pema.workers.kb_ingest_worker``.

The logic of one pass (claim, extract in an isolated child process, embed, save, release stuck sources) is
``pema.knowledge.kb_ingest_worker.KbIngestWorker``; THIS module is what the original ``batDauWorker`` did
around it - the boot sweep, the immediate first pass and the repeating timer - adapted to a worker process
of a single-tenant installation (one clinic, one database):

* connects as the ``agent_worker`` role (``Settings.worker_database_url``): no privilege on ``clinic.*``, only
  ``agent.*`` - which is all the knowledge base needs;
* every ``TICK_MS`` it runs one safe pass (the pass itself takes ONE advisory lock, so several worker
  processes can run side by side; there is no loop over clinics);
* refuses to start on a ``KB_EXTRACT_TIMEOUT_MS`` that is below the floor (``kb_extract_timeout_boot_guard``);
* stops cleanly on SIGINT/SIGTERM: the pass in progress finishes, the loop does not start another.

The tuning values come from ``get_tuning`` (the defaults and the environment until package D1 installs the
database-backed provider in the composition root).
"""

from __future__ import annotations

import asyncio
import contextlib
import signal

from pema.config.env import get_settings
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.core.event_loop import ensure_selector_event_loop_policy
from pema.knowledge.embedding_client import EmbeddingSettings, OllamaEmbeddingClient
from pema.knowledge.kb_extract_timeout_boot_guard import kiem_tra_kb_extract_timeout
from pema.knowledge.kb_ingest_worker import TICK_MS, KbIngestWorker
from pema.shared.logger import configure_logging, create_logger
from pema_contracts.knowledge import EmbeddingClient

log = create_logger("workers.kb_ingest")


async def chay_mot_luot(worker: KbIngestWorker) -> None:
    """One pass of the installation. A failing pass is logged; the loop goes on with the next tick."""
    try:
        await worker.chay_mot_vong_an_toan()
    except Exception as err:
        log.error("vòng xử lý kho tri thức thất bại", err=err)


async def chay_mai_mai(
    worker: KbIngestWorker,
    db: ClinicDatabase,
    stop: asyncio.Event,
    *,
    tick_s: float = TICK_MS / 1000,
) -> None:
    """Boot sweep + first pass AT ONCE (a source uploaded while the worker was restarting does not wait for
    the first tick; that first pass also releases every ``dang_xu_ly`` stuck from the previous run), then one
    pass per tick until ``stop`` is set."""
    await get_installation_clinic_id(db)
    await worker.bat_dau_worker()
    while not stop.is_set():
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=tick_s)
        if stop.is_set():
            break
        await chay_mot_luot(worker)


def tao_embedder() -> EmbeddingClient | None:
    cai_dat = EmbeddingSettings()
    if not cai_dat.enabled:
        log.info("embedding tắt: kho tri thức chỉ tìm theo từ khóa")
        return None
    return OllamaEmbeddingClient(cai_dat)


async def main() -> None:
    settings = get_settings()
    configure_logging(
        settings.log_level,
        file_enabled=settings.log_file_enabled,
        log_dir=settings.log_dir,
        keep_days=settings.log_file_keep_days,
    )
    kiem_tra_kb_extract_timeout()
    db = ClinicDatabase(settings.worker_database_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows loops cannot add signal handlers
            loop.add_signal_handler(sig, stop.set)
    worker = KbIngestWorker(db, embedder=tao_embedder(), data_dir=settings.data_dir)
    log.info("kb ingest worker bắt đầu", tick_ms=TICK_MS)
    try:
        await chay_mai_mai(worker, db, stop)
    finally:
        await db.dispose()
        log.info("kb ingest worker đã dừng")


def main_cli() -> None:
    ensure_selector_event_loop_policy()
    asyncio.run(main())


if __name__ == "__main__":
    main_cli()

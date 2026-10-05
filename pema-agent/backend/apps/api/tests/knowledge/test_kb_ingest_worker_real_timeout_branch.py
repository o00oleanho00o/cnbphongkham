# ported from: src/knowledge/kb-ingest-worker-real-timeout-branch.test.ts
"""Its own file because it needs a setting the other tests must not have: ``han_ms`` BELOW the operator-facing
floor of ``KB_EXTRACT_TIMEOUT_MS`` (5000 ms in ``tuning_specs``) so a REAL overrun can be built through
``xu_ly_mot_vong()`` - not simulated by hand as ``test_kb_ingest_worker_attempt_limit`` does.

The seam: ``KbIngestWorker`` accepts a ``CaiDatIngest`` built by hand (the original lowered the floor of the
environment schema for ``NODE_ENV=test``; ``get_tuning`` here rejects anything under the floor, so the test
bypasses the tuning instead and the real floor for the operator stays).

Purpose: prove the branch "a worker killed by its deadline KEEPS ``dang_xu_ly``, NOT marked hong at once" is
really reached - turning that branch into "mark hong" leaves every other test of the phase green, only this
one flips.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pema.knowledge.kb_file_store import luu_file
from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_slow_docx_test_fixture import bom_quay_cpu_docx
from pema.knowledge.kb_source_store import lay_nguon, tao_nguon
from pema.knowledge.kb_test_support import KbHarness

pytestmark = pytest.mark.db


async def test_nhanh_terminate_vi_qua_han_a_worker_really_over_the_deadline_keeps_dang_xu_ly_not_hong(
    kb: KbHarness, tmp_path: Path
) -> None:
    """nguồn làm worker quá KB_EXTRACT_TIMEOUT_MS thật sự (không mô phỏng) GIỮ NGUYÊN dang_xu_ly, không bị đánh hong ngay"""
    async with kb.session() as s:
        n = await tao_nguon(
            s,
            kb.clinic_id,
            ten="chậm thật",
            loai="file",
            dinh_dang="docx",
            duong_dan=luu_file("cham-that", "docx", bom_quay_cpu_docx(), data_dir=tmp_path),
        )
    # 300 ms: far below the real extraction time of ``bom_quay_cpu_docx()`` (seconds in Python), so it
    # surely overruns - not a fragile threshold.
    cai_dat = CaiDatIngest(tran_lan_thu=2, co_doan_toi_da=1200, chong_lan=10, han_ms=300, tran_ram_mb=192)

    await KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=cai_dat).xu_ly_mot_vong()

    async with kb.session() as s:
        sau = await lay_nguon(s, kb.clinic_id, n.id)
    assert sau is not None
    # The worker was killed by its deadline: we do NOT KNOW whether the document is truly broken or the
    # machine was slow - it must stay dang_xu_ly for ``go_nguon_ket_dau_tick`` (periodic, each tick) to judge,
    # not be marked hong at once like an ordinary content error (junk file, odd format).
    assert sau.trang_thai == "dang_xu_ly"
    assert sau.so_lan_thu == 1, "đã giành đúng 1 lần trước khi bị buộc dừng"
    assert sau.so_doan == 0, "chưa hề ghi đoạn nào - worker bị cắt giữa chừng"

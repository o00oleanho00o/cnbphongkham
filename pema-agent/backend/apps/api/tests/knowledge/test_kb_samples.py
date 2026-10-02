"""The fictional documents of ``kb-samples/``: every one carries the "needs a doctor" banner and goes through
the real ingest + keyword search. New tests (no original)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_test_support import KbHarness
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore

SAMPLES = Path(__file__).resolve().parents[5] / "kb-samples"
BANNER = "NỘI DUNG GIẢ LẬP, CẦN BÁC SĨ DUYỆT"
CAI_DAT = CaiDatIngest(tran_lan_thu=2, co_doan_toi_da=1200, chong_lan=10, han_ms=60_000, tran_ram_mb=192)


def test_every_sample_document_carries_the_needs_a_doctor_banner() -> None:
    """mọi tài liệu mẫu đều ghi rõ 'nội dung giả lập, cần bác sĩ duyệt'"""
    files = sorted(SAMPLES.glob("*.md"))
    assert {f.name for f in files} >= {
        "cham-soc-sau-laser.md",
        "thuoc-boi-thuong-gap.md",
        "khi-nao-can-kham-lai.md",
    }
    for f in files:
        if f.name != "README.md":
            assert BANNER in f.read_text(encoding="utf-8"), f.name


@pytest.mark.db
async def test_the_samples_ingest_and_are_found_by_a_customer_style_question(
    kb: KbHarness, tmp_path: Path
) -> None:
    """tài liệu mẫu nạp được và tìm ra đúng bằng câu hỏi kiểu bệnh nhân"""
    store = PostgresKnowledgeStore(kb.db, data_dir=tmp_path)
    kb.kb_database.add_agent("tro-ly")
    ids: dict[str, str] = {}
    for f in sorted(SAMPLES.glob("*.md")):
        if f.name == "README.md":
            continue
        nguon = await store.create_file_source(kb.clinic_id, name=f.stem, format="md", data=f.read_bytes())
        ids[f.name] = nguon.id
    await KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CAI_DAT).xu_ly_mot_vong()
    await store.set_sources_for_agent(kb.clinic_id, "tro-ly", list(ids.values()))

    for cau_hoi, mong in (
        ("sau laser cần tránh nắng bao lâu", "cham-soc-sau-laser.md"),
        ("chảy máu mưng mủ sốt thì làm gì", "khi-nao-can-kham-lai.md"),
        ("kem chống nắng thoa thế nào", "thuoc-boi-thuong-gap.md"),
    ):
        hits = await store.search(kb.clinic_id, question=cau_hoi, agent_id="tro-ly", limit=1)
        assert hits, cau_hoi
        assert hits[0].source_id == ids[mong], f"{cau_hoi!r} -> {hits[0].source_name}"

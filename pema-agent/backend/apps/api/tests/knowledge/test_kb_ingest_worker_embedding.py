"""The new step of the ingest worker: embed the chunks after extraction (bge-m3 through ``EmbeddingClient``).
No original - zalo-agent had no vectors. Everything runs with FAKE clients."""

from __future__ import annotations

from pathlib import Path

import pytest

from pema.knowledge.embedding_client import EmbeddingError, HashingEmbeddingClient
from pema.knowledge.kb_ingest_worker import CaiDatIngest, KbIngestWorker
from pema.knowledge.kb_source_store import lay_nguon, tao_nguon
from pema.knowledge.kb_test_support import KbHarness
from pema_contracts.knowledge import KB_EMBEDDING_DIMENSIONS

pytestmark = pytest.mark.db

CAI_DAT = CaiDatIngest(tran_lan_thu=2, co_doan_toi_da=1200, chong_lan=10, han_ms=60_000, tran_ram_mb=192)


class DownEmbedder:
    @property
    def dimensions(self) -> int:
        return KB_EMBEDDING_DIMENSIONS

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("máy embedding đang tắt")


async def test_the_worker_stores_one_vector_per_chunk_when_an_embedder_is_configured(
    kb: KbHarness, tmp_path: Path
) -> None:
    """có embedder thì mỗi đoạn có đúng một vector 1024 chiều"""
    async with kb.session() as s:
        n = await tao_nguon(
            s,
            kb.clinic_id,
            ten="Sau laser",
            loai="text",
            noi_dung_goc="# Da\n\nTránh nắng.\n\n# Thuốc\n\nThoa kem.",
        )
    await KbIngestWorker(
        kb.db, data_dir=tmp_path, embedder=HashingEmbeddingClient(), cai_dat=CAI_DAT
    ).xu_ly_mot_vong()
    assert (
        kb.kb_database.scalar("SELECT status FROM agent.kb_document WHERE id = :id", {"id": n.id})
        == "san_sang"
    )
    assert kb.kb_database.scalar("SELECT count(*) FROM agent.kb_chunk WHERE embedding IS NOT NULL") == 2
    assert (
        kb.kb_database.scalar("SELECT vector_dims(embedding) FROM agent.kb_chunk LIMIT 1")
        == KB_EMBEDDING_DIMENSIONS
    )


async def test_a_down_embedding_service_does_not_fail_the_source_chunks_are_stored_without_vectors(
    kb: KbHarness, tmp_path: Path
) -> None:
    """máy embedding tắt: nguồn vẫn san_sang, đoạn lưu không có vector (từ khóa vẫn tìm được)"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="# A\n\nthân bài")
    await KbIngestWorker(kb.db, data_dir=tmp_path, embedder=DownEmbedder(), cai_dat=CAI_DAT).xu_ly_mot_vong()
    async with kb.session() as s:
        sau = await lay_nguon(s, kb.clinic_id, n.id)
    assert sau is not None
    assert sau.trang_thai == "san_sang"
    assert kb.kb_database.scalar("SELECT count(*) FROM agent.kb_chunk WHERE embedding IS NULL") == 1


async def test_a_successful_pass_clears_the_old_error_text_of_a_source_that_failed_before(
    kb: KbHarness, tmp_path: Path
) -> None:
    """(thêm) xử lý xong thì xóa câu lỗi cũ - không để nguồn san_sang mang lỗi của lần trước"""
    async with kb.session() as s:
        n = await tao_nguon(s, kb.clinic_id, ten="x", loai="text", noi_dung_goc="# A\n\nthân bài")
    kb.kb_database.execute("UPDATE agent.kb_document SET error = 'lỗi cũ' WHERE id = :id", {"id": n.id})
    await KbIngestWorker(kb.db, data_dir=tmp_path, cai_dat=CAI_DAT).xu_ly_mot_vong()
    assert kb.kb_database.scalar("SELECT error FROM agent.kb_document WHERE id = :id", {"id": n.id}) == ""

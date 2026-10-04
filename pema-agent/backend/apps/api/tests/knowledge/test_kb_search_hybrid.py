"""Hybrid search (keyword + vector, fused by RRF) with a FAKE embedding client. New tests, no original: the
vector side is the one extension over zalo-agent.

The fake maps words to CONCEPT axes by hand, so "similar meaning without a shared word" can be built
exactly: the question "tránh gì sau khi bắn laser" and the document "Kiêng nắng và không nên bôi acid sau
laser" share no keyword that the full-text side can use (after folding, only ``laser`` and ``sau``... the
fixture below avoids even those), yet land on the same concept axis.
"""

from __future__ import annotations

import pytest

from pema.knowledge.chunk_text import DoanMoi
from pema.knowledge.embedding_client import EmbeddingError, HashingEmbeddingClient
from pema.knowledge.kb_agent_binding import dat_nguon_cho_agent
from pema.knowledge.kb_chunk_store import luu_doan, van_ban_de_nhung
from pema.knowledge.kb_search import tim_trong_kho_tri_thuc
from pema.knowledge.kb_source_store import tao_nguon
from pema.knowledge.kb_test_support import KbHarness
from pema.knowledge.postgres_knowledge_store import PostgresKnowledgeStore
from pema.shared.bo_dau_tieng_viet import bo_dau_tieng_viet
from pema_contracts.knowledge import KB_EMBEDDING_DIMENSIONS

pytestmark = pytest.mark.db

AGENT = "agent-lam-sang"

CONCEPTS: dict[int, tuple[str, ...]] = {
    0: ("kieng", "tranh", "khong nen", "han che"),  # abstain
    1: ("nang", "anh sang", "uv"),  # sun
    2: ("hen", "kham lai", "tai kham"),  # follow-up
    3: ("thuoc boi", "kem", "thoa"),  # topical
}


class ConceptEmbedder:
    """A fake with MEANING by hand: each concept axis lights up when one of its words appears."""

    @property
    def dimensions(self) -> int:
        return KB_EMBEDDING_DIMENSIONS

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            folded = bo_dau_tieng_viet(t).lower()
            vector = [0.0] * KB_EMBEDDING_DIMENSIONS
            for axis, words in CONCEPTS.items():
                if any(w in folded for w in words):
                    vector[axis] = 1.0
            out.append(vector)
        return out


class DownEmbedder:
    @property
    def dimensions(self) -> int:
        return KB_EMBEDDING_DIMENSIONS

    async def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbeddingError("máy embedding đang tắt")


async def nap(kb: KbHarness, ten: str, noi_dung: str, embedder: ConceptEmbedder | None) -> str:
    async with kb.session() as s:
        nguon = await tao_nguon(s, kb.clinic_id, ten=ten, loai="text", noi_dung_goc=noi_dung)
        doan = [DoanMoi(0, "", noi_dung)]
        vectors = await embedder.embed([van_ban_de_nhung(ten, d) for d in doan]) if embedder else None
        await luu_doan(s, kb.clinic_id, nguon.id, doan, ten, vectors)
    return nguon.id


async def gan(kb: KbHarness, source_ids: list[str]) -> None:
    kb.kb_database.add_agent(AGENT)
    async with kb.session() as s:
        await dat_nguon_cho_agent(s, kb.clinic_id, AGENT, source_ids)


async def test_hybrid_vector_side_finds_a_paraphrase_the_keyword_side_cannot(kb: KbHarness) -> None:
    """vector tìm ra đoạn đồng nghĩa mà từ khóa không thể (không chung từ nào)"""
    embedder = ConceptEmbedder()
    id_kieng = await nap(
        kb, "Hướng dẫn sau thủ thuật", "Hạn chế tiếp xúc ánh sáng mặt trời trong một tuần.", embedder
    )
    id_khac = await nap(kb, "Giờ làm việc", "Phòng khám mở cửa từ tám giờ sáng.", embedder)
    await gan(kb, [id_kieng, id_khac])

    cau_hoi = "tôi cần tránh điều gì"
    async with kb.session() as s:
        chi_tu_khoa = await tim_trong_kho_tri_thuc(s, kb.clinic_id, cau_hoi=cau_hoi, agent_id=AGENT)
        vector = (await embedder.embed([cau_hoi]))[0]
        lai = await tim_trong_kho_tri_thuc(
            s, kb.clinic_id, cau_hoi=cau_hoi, agent_id=AGENT, vector_cau_hoi=vector
        )
    assert chi_tu_khoa == [], "tiền đề: câu hỏi không chung từ nào với tài liệu"
    assert [k.source_id for k in lai] == [id_kieng]


async def test_hybrid_an_item_found_by_both_sides_outranks_an_item_found_by_one(kb: KbHarness) -> None:
    """mục tìm thấy ở CẢ HAI phía xếp trên mục chỉ một phía (RRF)"""
    embedder = ConceptEmbedder()
    ca_hai = await nap(kb, "Chăm sóc sau laser", "Tránh nắng và không nên bôi acid sau laser.", embedder)
    chi_tu_khoa = await nap(kb, "Ghi chú", "Sau laser cần theo dõi da mỗi ngày.", embedder)
    await gan(kb, [ca_hai, chi_tu_khoa])

    cau_hoi = "sau laser tránh gì"
    async with kb.session() as s:
        vector = (await embedder.embed([cau_hoi]))[0]
        kq = await tim_trong_kho_tri_thuc(
            s, kb.clinic_id, cau_hoi=cau_hoi, agent_id=AGENT, vector_cau_hoi=vector
        )
    assert kq[0].source_id == ca_hai
    assert {k.source_id for k in kq} == {ca_hai, chi_tu_khoa}
    assert kq[0].diem > kq[1].diem


async def test_hybrid_vector_search_is_confined_to_the_sources_of_the_agent_default_deny(
    kb: KbHarness,
) -> None:
    """vector cũng chỉ tìm trong nguồn được gán cho agent (mặc định đóng)"""
    embedder = ConceptEmbedder()
    cua_agent = await nap(kb, "Của agent", "Thoa kem dưỡng ẩm hai lần mỗi ngày.", embedder)
    cua_nguoi_khac = await nap(kb, "Của người khác", "Thoa thuốc bôi kháng sinh theo đơn.", embedder)
    del cua_nguoi_khac
    await gan(kb, [cua_agent])
    async with kb.session() as s:
        vector = (await embedder.embed(["loại thuốc bôi nào"]))[0]
        kq = await tim_trong_kho_tri_thuc(
            s, kb.clinic_id, cau_hoi="loại thuốc bôi nào", agent_id=AGENT, vector_cau_hoi=vector
        )
    assert [k.source_id for k in kq] == [cua_agent]
    kb.kb_database.add_agent("agent-chua-gan")
    async with kb.session() as s:
        assert (
            await tim_trong_kho_tri_thuc(
                s,
                kb.clinic_id,
                cau_hoi="loại thuốc bôi nào",
                agent_id="agent-chua-gan",
                vector_cau_hoi=vector,
            )
            == []
        )


async def test_hybrid_chunks_without_a_vector_are_still_found_by_the_keyword_side(kb: KbHarness) -> None:
    """đoạn chưa có vector (embedding tắt lúc nạp) vẫn tìm được bằng từ khóa"""
    embedder = ConceptEmbedder()
    khong_vector = await nap(kb, "Không có vector", "Hẹn tái khám sau hai tuần.", None)
    await gan(kb, [khong_vector])
    async with kb.session() as s:
        vector = (await embedder.embed(["hẹn tái khám"]))[0]
        kq = await tim_trong_kho_tri_thuc(
            s, kb.clinic_id, cau_hoi="hẹn tái khám", agent_id=AGENT, vector_cau_hoi=vector
        )
    assert [k.source_id for k in kq] == [khong_vector]


async def test_postgres_store_search_survives_a_down_embedding_service(kb: KbHarness) -> None:
    """store.search: máy embedding tắt thì rơi về tìm từ khóa, không lỗi"""
    id_ = await nap(kb, "Thuốc bôi", "Thoa thuốc bôi hai lần mỗi ngày.", ConceptEmbedder())
    await gan(kb, [id_])
    store = PostgresKnowledgeStore(kb.db, embedder=DownEmbedder())
    hits = await store.search(kb.clinic_id, question="thuốc bôi", agent_id=AGENT)
    assert [h.source_id for h in hits] == [id_]
    assert hits[0].source_name == "Thuốc bôi"


async def test_hash_fake_embedder_is_deterministic_and_has_the_contract_width() -> None:
    """(thêm) embedding giả dùng cho dev/test: ổn định và đúng 1024 chiều"""
    fake = HashingEmbeddingClient()
    a, b = await fake.embed(["chăm sóc da sau laser", "chăm sóc da sau laser"])
    assert a == b
    assert len(a) == fake.dimensions == KB_EMBEDDING_DIMENSIONS

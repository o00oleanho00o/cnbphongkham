# ported from: src/knowledge/kb-search.ts
"""Assemble the knowledge-base search layer: the sources an agent is ALLOWED to read -> keyword ranking AND
vector ranking -> RRF fusion -> content dedup -> look the chunks back up (with the source name) to give to
the model.

Forced deviation / the only extension over zalo-agent: the original had ONE ranker (bm25 by keyword) and
passed it through ``hop_nhat_rrf`` anyway "so adding a second list later is just one more element". Here
that second list exists: ``tim_theo_vector`` (pgvector cosine distance on the bge-m3 embedding of the
question). When there is no embedding (no embedder configured, or the endpoint is down) the vector list is
simply empty and the result is the keyword ranking alone - exactly the original behaviour.

Two clinic rules on top:
* the knowledge base never holds patient data (see ``pema_contracts.knowledge``), and the question is
  embedded locally (``embedding_client``);
* an agent of the ``patient_channel`` profile may cite ONLY documents a doctor has signed off
  (``approved_by_clinical_owner``). ``chi_da_duyet=None`` reads the profile of the agent itself
  (``agent.agents.policy_profile``, default ``patient_channel`` = fail safe); a caller that knows the
  effective profile of the account (the more restrictive of agent and account) passes it explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from pema.config.runtime_tuning_settings import get_tuning_int
from pema.knowledge.hop_nhat_rrf import hop_nhat_rrf
from pema.knowledge.kb_agent_binding import nguon_cua_agent
from pema.knowledge.kb_chunk_store import lay_doan_theo_id, vector_literal
from pema.knowledge.kb_fts_query import KetQuaFts, tim_theo_tu_khoa
from pema.shared.bo_dau_tieng_viet import bo_dau_tieng_viet
from pema.shared.logger import create_logger
from pema_contracts.knowledge import EmbeddingClient

log = create_logger("knowledge.search")


@dataclass(frozen=True, slots=True)
class KetQuaKb:
    source_id: str
    ten_nguon: str
    tieu_de: str
    noi_dung: str
    diem: float


HE_SO_LAY_DU: Final = 3
"""Take MORE than needed before dedup (I3): ``tim_theo_tu_khoa`` LIMITs exactly in SQL, so deduplicating AFTER
that (two sources copied verbatim keep only 1) comes up short unless we over-fetch - a duplicate pair takes 2
of the few slots, and after dedup a slot is lost instead of being refilled with another chunk that sits
beyond the LIMIT. x3 is enough room for the most realistic case (a few duplicates); over-fetching TOO much
only costs one more cheap query (the ``agent.kb_chunk`` table of a clinic is not large).

The real number of duplicates in a real knowledge base has NOT been measured (no user data to measure) - x3
is reasoning, not a measurement. The failure if the reasoning is wrong: the store has MORE than
``so_luong * (HE_SO_LAY_DU - 1)`` tied duplicates for one question, and dedup is short in the way I3
describes, only at a much smaller scale than the original bug (LIMIT = so_luong, x1). If that happens for
real, raise ``HE_SO_LAY_DU``, do not change the architecture."""


KHOANG_CACH_VECTOR_TOI_DA: Final = 0.6
"""Largest cosine DISTANCE (1 - similarity) at which a chunk still counts as a vector match. Without a cut-off
a nearest-neighbour search ALWAYS returns ``so_luong`` chunks, however unrelated, so the ``kb_search`` tool
could never say "nothing found" (the keyword side returns only real matches, which is what the original did).
[ESTIMATE] NOT measured on bge-m3 with real clinic text: it must be calibrated against a real Ollama before
the pilot (open item); a vector that is NaN (an all-zero vector) never passes."""


async def tim_theo_vector(
    session: AsyncSession,
    clinic_id: UUID,
    vector_cau_hoi: list[float],
    source_ids: list[str],
    so_luong: int,
    khoang_cach_toi_da: float = KHOANG_CACH_VECTOR_TOI_DA,
) -> list[KetQuaFts]:
    """The VECTOR ranking: nearest chunks by cosine distance, only inside ``source_ids`` (filtered in the
    WHERE, same lesson as ``tim_theo_tu_khoa``). Chunks without a stored vector are not candidates.

    ``+ 0`` in ``ORDER BY`` keeps the planner from walking the HNSW index: an approximate index scan applies
    the ``WHERE`` AFTER it has taken its nearest candidates and can return fewer rows than asked (or none)
    when a restrictive filter such as "only the sources of this agent" removes them - the I3/"filter in SQL"
    lesson in another form. A clinic knowledge base is small (hundreds to a few thousand chunks), so an exact
    scan is both correct and fast; the index stays for the day the corpus outgrows that."""
    if not source_ids or not vector_cau_hoi:
        return []
    rows = (
        await session.execute(
            text(
                "SELECT c.id FROM agent.kb_chunk c "
                "WHERE c.clinic_id = :c AND c.source_id = ANY(:ids) AND c.embedding IS NOT NULL "
                "AND (c.embedding <=> CAST(:v AS vector)) <= :max_d "
                "ORDER BY (c.embedding <=> CAST(:v AS vector)) + 0, c.id LIMIT :n"
            ),
            {
                "c": clinic_id,
                "ids": source_ids,
                "v": vector_literal(vector_cau_hoi),
                "n": so_luong,
                "max_d": khoang_cach_toi_da,
            },
        )
    ).all()
    return [KetQuaFts(chunk_id=int(r[0])) for r in rows]


async def nhung_cau_hoi(embedder: EmbeddingClient | None, cau_hoi: str) -> list[float] | None:
    """Embed the question; ``None`` when there is no embedder or the endpoint fails. NEVER raises: a down
    embedding service must not take the search down with it (the keyword side still answers). Logs the error
    TYPE only, never the question."""
    if embedder is None:
        return None
    try:
        vectors = await embedder.embed([cau_hoi])
    except Exception as err:
        log.warning("embedding câu hỏi thất bại, chỉ tìm theo từ khóa", err=err)
        return None
    return vectors[0] if vectors else None


async def _chi_da_duyet_mac_dinh(session: AsyncSession, clinic_id: UUID, agent_id: str) -> bool:
    row = (
        await session.execute(
            text("SELECT policy_profile FROM agent.agents WHERE clinic_id = :c AND id = :a"),
            {"c": clinic_id, "a": agent_id},
        )
    ).first()
    # An agent we cannot find has no bindings either; the answer only matters for the fail-safe default.
    return row is None or row[0] != "staff_assistant"


async def tim_trong_kho_tri_thuc(
    session: AsyncSession,
    clinic_id: UUID,
    *,
    cau_hoi: str,
    agent_id: str,
    so_luong: int | None = None,
    vector_cau_hoi: list[float] | None = None,
    chi_da_duyet: bool | None = None,
) -> list[KetQuaKb]:
    # DEFAULT-DENY: an agent with no source bound yet (nothing configured, see kb_agent_binding) reads NO
    # source, NOT everything - reversing this leaks the documents of another agent.
    da_duyet = (
        chi_da_duyet
        if chi_da_duyet is not None
        else await _chi_da_duyet_mac_dinh(session, clinic_id, agent_id)
    )
    source_ids = await nguon_cua_agent(session, clinic_id, agent_id, chi_da_duyet=da_duyet)
    if not source_ids:
        return []

    so_luong = so_luong if so_luong is not None else get_tuning_int("KB_TOP_K")
    lay_du = so_luong * HE_SO_LAY_DU
    fts_ket_qua = await tim_theo_tu_khoa(session, clinic_id, cau_hoi, source_ids, lay_du)
    vector_ket_qua = (
        await tim_theo_vector(session, clinic_id, vector_cau_hoi, source_ids, lay_du)
        if vector_cau_hoi
        else []
    )
    if not fts_ket_qua and not vector_ket_qua:
        return []

    k = get_tuning_int("KB_RRF_K")
    # NO ``[:so_luong]`` here - the fused list holds the over-fetched count; cutting to ``so_luong`` must wait
    # for AFTER dedup, or the very surplus fetched to be kept in reserve is lost.
    hop_nhat = hop_nhat_rrf([fts_ket_qua, vector_ket_qua], lambda x: str(x.chunk_id), k)

    diem_theo_chunk_id = {h.item.chunk_id: h.diem for h in hop_nhat}
    # ``lay_doan_theo_id`` returns EXACTLY the order of the ids passed in - the RRF rank is kept
    doan = await lay_doan_theo_id(session, clinic_id, [h.item.chunk_id for h in hop_nhat])

    # Dedup (I3): two DIFFERENT sources copied verbatim must not take 2 slots of the top-k the model sees.
    # Compare by the NORMALISED content (heading + body, diacritics folded) - deliberately NOT the source
    # name: two sources with different names must still dedupe if the content is identical, that is exactly
    # the case to remove. Keep the HIGHEST ranked copy (first met, ``doan`` is already in RRF order), drop
    # the later duplicates.
    da_gap: set[str] = set()
    ket_qua: list[KetQuaKb] = []
    for d in doan:
        chu_ky = bo_dau_tieng_viet(f"{d.tieu_de} {d.noi_dung}".strip())
        if chu_ky in da_gap:
            continue
        da_gap.add(chu_ky)
        ket_qua.append(
            KetQuaKb(
                source_id=d.source_id,
                ten_nguon=d.ten_nguon,
                tieu_de=d.tieu_de,
                noi_dung=d.noi_dung,
                diem=diem_theo_chunk_id.get(d.id, 0.0),
            )
        )
        if len(ket_qua) >= so_luong:
            break
    return ket_qua

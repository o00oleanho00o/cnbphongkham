"""Knowledge-base contract (package D3 implements; ``kb_search`` tool, admin API and ingest worker use it).

Port of src/knowledge: ``KbSource`` (kb-source-store.ts), ``KetQuaKb`` (kb-search.ts) and the agent
binding (kb-agent-binding.ts). Storage is Postgres (``agent.kb_document``, ``agent.kb_chunk`` with a
``tsvector`` column and a ``vector(1024)`` embedding, ``agent.agent_kb_document``); search is
Postgres FTS + pgvector fused with RRF (``hop_nhat_rrf``). The vector side is the only extension
over zalo-agent.

Normative rules kept from the original:

* DEFAULT-DENY: an agent with no source bound reads NOTHING (it does NOT read everything).
* Parsing is safe by construction: zip-bomb ceilings, a worker timeout and a bounded attempt count
  (``attempts`` = ``so_lan_thu``) so a poison file cannot wedge the worker forever.
* The KB holds clinic procedure/FAQ text written by the clinic. It never holds patient data and
  patient data is never embedded. Documents need a doctor's sign-off flag before an agent in the
  ``patient_channel`` profile may cite them (``approved_by_clinical_owner``).

The status values are the original Vietnamese ones (they are stored and shown verbatim):
``cho_xu_ly`` pending, ``dang_xu_ly`` processing, ``san_sang`` ready, ``hong`` failed.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol
from uuid import UUID

from pydantic import Field

from pema_contracts.common import ApiModel, VnDatetime


class KbSourceStatus(StrEnum):
    PENDING = "cho_xu_ly"
    PROCESSING = "dang_xu_ly"
    READY = "san_sang"
    FAILED = "hong"


class KbSourceKind(StrEnum):
    FILE = "file"
    TEXT = "text"


class KbSource(ApiModel):
    id: str
    name: str = Field(description="``ten``")
    kind: KbSourceKind = Field(description="``loai``")
    format: str = Field(default="", description="``dinh_dang``: docx, xlsx, pdf, txt, md, ...")
    path: str = Field(default="", description="``duong_dan``: object-storage key for a file source.")
    raw_text: str = Field(default="", description="``noi_dung_goc``: body of a text source.")
    status: KbSourceStatus = Field(description="``trang_thai``")
    error: str = Field(default="", description="``loi``")
    chunk_count: int = Field(default=0, description="``so_doan``")
    byte_size: int = Field(default=0, description="``so_byte``")
    attempts: int = Field(default=0, description="``so_lan_thu``: times the worker claimed it.")
    approved_by_clinical_owner: bool = False
    created_at: VnDatetime
    updated_at: VnDatetime


class KbChunk(ApiModel):
    order: int = Field(description="``thu_tu``")
    title: str = Field(default="", description="``tieu_de``")
    content: str = Field(description="``noi_dung``")


class KbHit(ApiModel):
    """``KetQuaKb``."""

    source_id: str
    source_name: str
    title: str
    content: str
    score: float


class KnowledgeSearch(Protocol):
    """What the ``kb_search`` tool needs."""

    async def search(self, clinic_id: UUID, *, question: str, agent_id: str, limit: int = 5) -> list[KbHit]:
        """Hybrid FTS + vector + RRF over the sources bound to ``agent_id`` (default-deny), de-duplicated
        by content. ``question`` is diacritics-folded for the FTS side exactly like zalo-agent."""
        ...


class KnowledgeStore(KnowledgeSearch, Protocol):
    """Everything package D3 provides."""

    async def create_text_source(self, clinic_id: UUID, *, name: str, text: str) -> KbSource: ...

    async def create_file_source(self, clinic_id: UUID, *, name: str, format: str, data: bytes) -> KbSource:
        """Stores the bytes and queues the source (``cho_xu_ly``); parsing runs in the ingest worker."""
        ...

    async def get_source(self, clinic_id: UUID, source_id: str) -> KbSource | None: ...

    async def list_sources(self, clinic_id: UUID) -> list[KbSource]: ...

    async def set_status(
        self,
        clinic_id: UUID,
        source_id: str,
        status: KbSourceStatus,
        *,
        error: str = "",
        chunk_count: int | None = None,
    ) -> None: ...

    async def delete_source(self, clinic_id: UUID, source_id: str) -> int:
        """Returns the number of chunks removed; also removes the stored file and agent bindings."""
        ...

    async def reindex_source(self, clinic_id: UUID, source_id: str) -> None: ...

    async def list_chunks(
        self, clinic_id: UUID, source_id: str, *, offset: int, limit: int
    ) -> list[KbChunk]: ...

    async def set_approved(
        self, clinic_id: UUID, source_id: str, approved: bool, *, by_user: UUID
    ) -> None: ...

    async def sources_of_agent(self, clinic_id: UUID, agent_id: str) -> list[str]: ...

    async def agents_of_source(self, clinic_id: UUID, source_id: str) -> list[str]: ...

    async def set_sources_for_agent(self, clinic_id: UUID, agent_id: str, source_ids: list[str]) -> None: ...

    async def set_agents_for_source(self, clinic_id: UUID, source_id: str, agent_ids: list[str]) -> None: ...


class EmbeddingClient(Protocol):
    """bge-m3 (1024 dimensions) through an OpenAI-compatible ``/embeddings`` endpoint (Ollama or
    llama-server). Package D3 owns the real client; consumers and tests inject a fake."""

    @property
    def dimensions(self) -> int: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...


KB_EMBEDDING_DIMENSIONS = 1024
"""Width of ``agent.kb_chunk.embedding`` (bge-m3). Changing the model means a migration."""

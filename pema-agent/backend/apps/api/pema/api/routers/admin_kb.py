"""Knowledge base sources, chunks, agent bindings and preview search (package D3 implements).

Port of kb-routes.ts and kb-inspect-routes.ts. Uploads are size-capped before parsing (zip-bomb ceilings
live in the parser). Bindings are default-deny: an agent with no source reads nothing.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import File, Form, UploadFile, status

from pema.api.deps import Limit, Offset, admin_router, not_implemented
from pema_contracts.admin_agent import (
    IdList,
    KbApprove,
    KbSearchRequest,
    KbSearchResponse,
    KbTextSourceCreate,
)
from pema_contracts.knowledge import KbChunk, KbSource

router = admin_router("kb", "admin-kb")


@router.get("/sources", response_model=list[KbSource], summary="Sources with status")
async def list_kb_sources() -> list[KbSource]:
    not_implemented()


@router.post(
    "/sources/text",
    response_model=KbSource,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Add a text source",
)
async def create_kb_text_source(body: KbTextSourceCreate) -> KbSource:
    not_implemented()


@router.post(
    "/sources/file",
    response_model=KbSource,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload docx/xlsx/pdf/txt/md; parsing runs in the ingest worker",
)
async def upload_kb_file_source(
    file: Annotated[UploadFile, File(description="docx, xlsx, pdf, txt or md.")],
    name: Annotated[str | None, Form(max_length=200)] = None,
) -> KbSource:
    not_implemented()


@router.post("/sources/{source_id}/reindex", response_model=KbSource, summary="Parse and index again")
async def reindex_kb_source(source_id: str) -> KbSource:
    not_implemented()


@router.patch("/sources/{source_id}/approval", response_model=KbSource, summary="Doctor sign-off")
async def approve_kb_source(source_id: str, body: KbApprove) -> KbSource:
    not_implemented()


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a source, its chunks, file and bindings",
)
async def delete_kb_source(source_id: str) -> None:
    not_implemented()


@router.get("/sources/{source_id}/chunks", response_model=list[KbChunk], summary="Chunks of a source")
async def list_kb_chunks(source_id: str, limit: Limit = 50, offset: Offset = 0) -> list[KbChunk]:
    not_implemented()


@router.get("/sources/{source_id}/agents", response_model=IdList, summary="Agents allowed to read a source")
async def get_agents_of_kb_source(source_id: str) -> IdList:
    not_implemented()


@router.put("/sources/{source_id}/agents", response_model=IdList, summary="Set the agents of a source")
async def set_agents_of_kb_source(source_id: str, body: IdList) -> IdList:
    not_implemented()


@router.get("/agents/{agent_id}/sources", response_model=IdList, summary="Sources an agent may read")
async def get_kb_sources_of_agent(agent_id: str) -> IdList:
    not_implemented()


@router.put("/agents/{agent_id}/sources", response_model=IdList, summary="Set the sources of an agent")
async def set_kb_sources_of_agent(agent_id: str, body: IdList) -> IdList:
    not_implemented()


@router.post("/search", response_model=KbSearchResponse, summary="Hybrid search preview for staff")
async def search_kb(body: KbSearchRequest) -> KbSearchResponse:
    not_implemented()

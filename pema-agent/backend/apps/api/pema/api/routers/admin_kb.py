# ported from: src/server/routes/kb-routes.ts and src/server/routes/kb-inspect-routes.ts
"""Knowledge base sources, chunks, agent bindings and preview search (package D3 implements).

Port of kb-routes.ts and kb-inspect-routes.ts. Uploads are size-capped before parsing (zip-bomb ceilings
live in the parser). Bindings are default-deny: an agent with no source bound reads nothing.

Processing of the content (reading the file, cutting chunks) is NOT here - a route only writes the file and
the row in ``cho_xu_ly`` and answers at once; ``kb_ingest_worker`` processes it in the next background round.

Forced deviations:
* the paths and DTOs are the contract of the OpenAPI skeleton (package A), not the ``/api/kb`` of the
  original: ``name``/``text`` instead of ``ten``/``noiDung``, ``IdList.ids`` instead of ``sourceIds`` /
  ``agentIds``, ``204`` for a delete, ``DomainError`` codes (``ErrorCode`` -> HTTP status of the contract:
  422 for invalid input, 404, 409, 413) instead of the original 400/404/409/413;
* every route needs a session context (``lay_ngu_canh_kb``) and a permission (``kb.read`` to read,
  ``kb.manage`` to change); the doctor's sign-off (``PATCH .../approval``) is for the roles ``doctor`` and
  ``owner`` only. The response of a source NEVER carries its raw text (``raw_text`` is always empty);
* the original's list also returned ``soAgent`` (how many agents may read a source); the contract DTO has no
  such field, so it is not in the response (open item: an additive optional field in ``KbSource``).
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Annotated

from fastapi import File, Form, Request, UploadFile, status

from pema.api.deps import Limit, Offset, admin_router
from pema.api.kb_route_guards import (
    KbBodyLimitRoute,
    KbRequestContext,
    cap_quyen,
    lay_ngu_canh_kb,
    lay_store,
)
from pema.knowledge.doc_text_extract import DINH_DANG_HO_TRO
from pema_contracts.admin_agent import (
    IdList,
    KbApprove,
    KbSearchRequest,
    KbSearchResponse,
    KbTextSourceCreate,
)
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.knowledge import KbChunk, KbSource
from pema_contracts.roles import Permission

router = admin_router("kb", "admin-kb")
router.route_class = KbBodyLimitRoute

SO_DOAN_TOI_DA_MOI_TRANG = 100
"""``chunksQuerySchema``: a page of chunks is at most 100 - a limit with no ceiling lets one query parameter
pull the whole ``kb_chunk`` table of a source at once, the OOM the upload path already blocks."""
ROLE_DUYET_NGUON = frozenset({"doctor", "owner"})
"""Roles that may sign a source off for the ``patient_channel`` profile (the doctor of the team, or the
clinic owner)."""


def _ngu_canh(request: Request, permission: Permission) -> KbRequestContext:
    ctx = lay_ngu_canh_kb(request)
    cap_quyen(ctx, permission)
    return ctx


@router.get("/sources", response_model=list[KbSource], summary="Sources with status")
async def list_kb_sources(request: Request) -> list[KbSource]:
    ctx = _ngu_canh(request, Permission.KB_READ)
    return await lay_store(request).list_sources(ctx.clinic_id)


@router.post(
    "/sources/text",
    response_model=KbSource,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Add a text source",
)
async def create_kb_text_source(request: Request, body: KbTextSourceCreate) -> KbSource:
    ctx = _ngu_canh(request, Permission.KB_MANAGE)
    return await lay_store(request).create_text_source(ctx.clinic_id, name=body.name, text=body.text)


@router.post(
    "/sources/file",
    response_model=KbSource,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload docx/xlsx/pdf/txt/md; parsing runs in the ingest worker",
)
async def upload_kb_file_source(
    request: Request,
    file: Annotated[UploadFile, File(description="docx, xlsx, pdf, txt or md.")],
    name: Annotated[str | None, Form(max_length=200)] = None,
) -> KbSource:
    ctx = _ngu_canh(request, Permission.KB_MANAGE)
    ten_file = PurePosixPath((file.filename or "").replace("\\", "/")).name
    dinh_dang = PurePosixPath(ten_file).suffix.removeprefix(".").lower()
    # The name defaults to the file name without its extension; ``tenNguonSchema`` (1-200 characters) is
    # enforced by the store for both routes alike.
    ten = (name or PurePosixPath(ten_file).stem).strip()
    if dinh_dang not in DINH_DANG_HO_TRO:
        raise DomainError(
            ErrorCode.KB_SOURCE_INVALID,
            f'Định dạng ".{dinh_dang or "?"}" chưa hỗ trợ - dùng {", ".join(DINH_DANG_HO_TRO)}',
        )
    data = await file.read()
    return await lay_store(request).create_file_source(ctx.clinic_id, name=ten, format=dinh_dang, data=data)


@router.post("/sources/{source_id}/reindex", response_model=KbSource, summary="Parse and index again")
async def reindex_kb_source(request: Request, source_id: str) -> KbSource:
    ctx = _ngu_canh(request, Permission.KB_MANAGE)
    store = lay_store(request)
    await store.reindex_source(ctx.clinic_id, source_id)
    nguon = await store.get_source(ctx.clinic_id, source_id)
    if nguon is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy nguồn")
    return nguon


@router.patch("/sources/{source_id}/approval", response_model=KbSource, summary="Doctor sign-off")
async def approve_kb_source(request: Request, source_id: str, body: KbApprove) -> KbSource:
    ctx = _ngu_canh(request, Permission.KB_READ)
    if ctx.role not in ROLE_DUYET_NGUON:
        raise DomainError(ErrorCode.FORBIDDEN, "Chỉ bác sĩ hoặc chủ phòng khám mới được duyệt nội dung.")
    store = lay_store(request)
    await store.set_approved(ctx.clinic_id, source_id, body.approved, by_user=ctx.user_id)
    nguon = await store.get_source(ctx.clinic_id, source_id)
    if nguon is None:
        raise DomainError(ErrorCode.NOT_FOUND, "Không tìm thấy nguồn")
    return nguon


@router.delete(
    "/sources/{source_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a source, its chunks, file and bindings",
)
async def delete_kb_source(request: Request, source_id: str) -> None:
    ctx = _ngu_canh(request, Permission.KB_MANAGE)
    await lay_store(request).delete_source(ctx.clinic_id, source_id)


@router.get("/sources/{source_id}/chunks", response_model=list[KbChunk], summary="Chunks of a source")
async def list_kb_chunks(
    request: Request, source_id: str, limit: Limit = 50, offset: Offset = 0
) -> list[KbChunk]:
    ctx = _ngu_canh(request, Permission.KB_READ)
    if limit > SO_DOAN_TOI_DA_MOI_TRANG:
        raise DomainError(
            ErrorCode.VALIDATION_FAILED,
            f"Tham số phân trang không hợp lệ (limit tối đa {SO_DOAN_TOI_DA_MOI_TRANG})",
        )
    return await lay_store(request).list_chunks(ctx.clinic_id, source_id, offset=offset, limit=limit)


@router.get("/sources/{source_id}/agents", response_model=IdList, summary="Agents allowed to read a source")
async def get_agents_of_kb_source(request: Request, source_id: str) -> IdList:
    ctx = _ngu_canh(request, Permission.KB_READ)
    return IdList(ids=await lay_store(request).agents_of_source(ctx.clinic_id, source_id))


@router.put("/sources/{source_id}/agents", response_model=IdList, summary="Set the agents of a source")
async def set_agents_of_kb_source(request: Request, source_id: str, body: IdList) -> IdList:
    ctx = _ngu_canh(request, Permission.KB_MANAGE)
    store = lay_store(request)
    await store.set_agents_for_source(ctx.clinic_id, source_id, body.ids)
    return IdList(ids=await store.agents_of_source(ctx.clinic_id, source_id))


@router.get("/agents/{agent_id}/sources", response_model=IdList, summary="Sources an agent may read")
async def get_kb_sources_of_agent(request: Request, agent_id: str) -> IdList:
    ctx = _ngu_canh(request, Permission.KB_READ)
    return IdList(ids=await lay_store(request).sources_of_agent(ctx.clinic_id, agent_id))


@router.put("/agents/{agent_id}/sources", response_model=IdList, summary="Set the sources of an agent")
async def set_kb_sources_of_agent(request: Request, agent_id: str, body: IdList) -> IdList:
    ctx = _ngu_canh(request, Permission.KB_MANAGE)
    store = lay_store(request)
    await store.set_sources_for_agent(ctx.clinic_id, agent_id, body.ids)
    return IdList(ids=await store.sources_of_agent(ctx.clinic_id, agent_id))


@router.post("/search", response_model=KbSearchResponse, summary="Hybrid search preview for staff")
async def search_kb(request: Request, body: KbSearchRequest) -> KbSearchResponse:
    ctx = _ngu_canh(request, Permission.KB_READ)
    hits = await lay_store(request).search(
        ctx.clinic_id, question=body.query, agent_id=body.agent_id, limit=body.limit
    )
    return KbSearchResponse(hits=hits)

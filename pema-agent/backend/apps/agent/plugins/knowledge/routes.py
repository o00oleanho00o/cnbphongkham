"""Admin routes of the knowledge store, under ``/v1/plugins/knowledge`` (admin token): the calls of the pages
"Kho tri thức" (``ui/src/client.ts``). Every route answers 503 with what to run while the plugin's tables are
missing."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status

from agent_app.plugins import PluginError

from .ingest import ADMIN, new_id
from .models import (
    BulkBody,
    ChunkPatch,
    ConfirmBody,
    GapPatch,
    GapState,
    ImportBody,
    PreviewBody,
    Processing,
    RestoreBody,
    SearchBody,
    Service,
    ServiceBody,
    ServicePatch,
    Source,
    SourceFilter,
    SourcePatch,
    SplitBody,
    StructureBody,
    as_mapping,
)
from .plugin import MAX_CHAR_BUDGET, KnowledgePlugin
from .search import debug_view
from .text import Audience, Lifecycle, fold, outline, sections, split_head

ID_PATTERN: Final = r"^[a-z]+-[0-9a-f]{12}$"
CHUNK_PATTERN: Final = r"^[a-z]+-[0-9a-f]{12}-c\d{1,6}$"
SourceId = Annotated[str, Path(pattern=ID_PATTERN)]
ServiceId = Annotated[str, Path(pattern=ID_PATTERN)]
GapId = Annotated[str, Path(pattern=ID_PATTERN)]
ChunkId = Annotated[str, Path(pattern=CHUNK_PATTERN)]
PAGE_SIZE: Final = 30
CHUNK_PAGE: Final = 20
# a patch may clear these dates; the other fields are left as they are when sent as null
NULLABLE: Final = frozenset({"effective_from", "effective_to"})
KEYWORD_ONLY: Final = "Embedding chưa kết nối: đang tìm bằng từ khóa."


def knowledge_routes(plugin: KnowledgePlugin) -> APIRouter:
    async def ready() -> None:
        try:
            await plugin.ready()
        except PluginError as err:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(err)) from err

    router = APIRouter(dependencies=[Depends(ready)])
    store = plugin.store

    async def found(source_id: str) -> Source:
        source = await store.get(source_id)
        if source is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có nguồn này.")
        return source

    def now() -> datetime:
        return datetime.now(UTC)

    @router.get("/status")
    async def get_status() -> dict[str, Any]:
        return {"embedding_connected": False, "embedding_model": None, "queue": 0, "warnings": [KEYWORD_ONLY]}

    @router.get("/sources")
    async def list_sources(
        q: Annotated[str, Query(max_length=200)] = "",
        processing: Processing | None = None,
        audience: Audience | None = None,
        service: Annotated[str | None, Query(max_length=40)] = None,
        lifecycle: Lifecycle | None = None,
        approved: bool | None = None,
        page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    ) -> dict[str, Any]:
        query = SourceFilter(q, processing, audience, service, lifecycle, approved, page, PAGE_SIZE)
        items, total = await store.find(query)
        everything = await store.all_sources()
        chunks = sum(s.chunk_count for s in everything)
        embedded = sum(s.embedded for s in everything)
        summary = {
            "ready": sum(1 for s in everything if s.processing == "ready"),
            "chunks": chunks,
            "embedded_percent": round(embedded * 100 / chunks) if chunks else 0,
            "errors": sum(1 for s in everything if s.processing == "error"),
            "unapproved": 0,
            "processing": sum(1 for s in everything if s.processing in ("queued", "processing")),
        }
        warnings = [KEYWORD_ONLY] if everything else []
        return {
            "items": [s.shown() for s in items],
            "total": total,
            "page": page,
            "page_size": PAGE_SIZE,
            "summary": summary,
            "warnings": warnings,
        }

    @router.post("/sources/bulk")
    async def bulk(body: BulkBody) -> dict[str, Any]:
        failed: list[dict[str, str]] = []
        done = 0
        for source_id in body.ids:
            source = await store.get(source_id)
            if source is None:
                failed.append({"id": source_id, "message": "Không có nguồn này."})
                continue
            await _bulk_one(plugin, source, body)
            done += 1
        return {"done": done, "failed": failed}

    @router.post("/sources/preview")
    async def preview(body: PreviewBody) -> dict[str, Any]:
        settings = await plugin.settings()
        return await plugin.ingest.preview(body.inputs, benchmark=bool(settings["benchmark_mode"]))

    @router.post("/sources/confirm")
    async def confirm(body: ConfirmBody) -> dict[str, Any]:
        settings = await plugin.settings()
        try:
            return await plugin.ingest.confirm(
                body.preview_id,
                body.items,
                await store.services(),
                benchmark=bool(settings["benchmark_mode"]),
            )
        except LookupError as err:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(err)) from err

    @router.get("/sources/{source_id}")
    async def get_source(source_id: SourceId) -> dict[str, Any]:
        return (await found(source_id)).shown()

    @router.patch("/sources/{source_id}")
    async def patch_source(source_id: SourceId, body: SourcePatch) -> dict[str, Any]:
        source = await found(source_id)
        given = {
            key: value
            for key, value in body.model_dump(exclude_unset=True).items()
            if value is not None or key in NULLABLE
        }
        changed = replace(source, **given, updated_at=now())
        await store.save(changed)
        await plugin.ingest.event(source_id, "edited", ", ".join(given))
        return changed.shown()

    @router.delete("/sources/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_source(source_id: SourceId) -> Response:
        if not await store.delete(source_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có nguồn này.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/sources/{source_id}/reindex")
    async def reindex(source_id: SourceId) -> dict[str, Any]:
        source = await plugin.ingest.rechunk(await found(source_id), await store.services())
        await plugin.ingest.event(source_id, "reindexed")
        return source.shown()

    @router.post("/sources/{source_id}/approve")
    async def approve(source_id: SourceId) -> dict[str, Any]:
        source = replace(await found(source_id), approved=True, approved_by=ADMIN, approved_at=now())
        await store.save(source)
        await plugin.ingest.event(source_id, "approved")
        return source.shown()

    @router.post("/sources/{source_id}/unapprove")
    async def unapprove(source_id: SourceId) -> dict[str, Any]:
        source = replace(await found(source_id), approved=False, approved_by=None, approved_at=None)
        await store.save(source)
        await plugin.ingest.event(source_id, "unapproved")
        return source.shown()

    @router.post("/sources/{source_id}/expire")
    async def expire(source_id: SourceId) -> dict[str, Any]:
        source = replace(await found(source_id), lifecycle="expired", updated_at=now())
        await store.save(source)
        await plugin.ingest.event(source_id, "expired")
        return source.shown()

    @router.get("/sources/{source_id}/structure")
    async def structure(source_id: SourceId) -> dict[str, Any]:
        source = await found(source_id)
        return {"markdown": source.markdown, "outline": _outline(source.markdown)}

    @router.put("/sources/{source_id}/structure")
    async def save_structure(source_id: SourceId, body: StructureBody) -> dict[str, Any]:
        source = await plugin.ingest.rechunk(await found(source_id), await store.services(), body.markdown)
        await plugin.ingest.event(source_id, "edited", "Sửa bản dựng cấu trúc")
        return source.shown()

    @router.post("/sources/{source_id}/split")
    async def split(source_id: SourceId, body: SplitBody) -> dict[str, Any]:
        source = await found(source_id)
        kept, moved = _split(source.markdown, set(body.sections))
        if not moved.strip():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Chưa chọn mục nào để tách.")
        services = await store.services()
        await plugin.ingest.rechunk(source, services, kept)
        created_at = now()
        new_source = replace(
            source,
            id=new_id("src"),
            title=body.title,
            doc_code=None,
            version=None,
            supersedes=None,
            created_at=created_at,
            updated_at=created_at,
        )
        made = await plugin.ingest.rechunk(new_source, services, f"# {body.title}\n\n{moved}")
        await plugin.ingest.event(source_id, "edited", f'Tách mục sang "{body.title}"')
        await plugin.ingest.event(made.id, "uploaded", f'Tách từ "{source.title}"')
        return made.shown()

    @router.get("/sources/{source_id}/chunks")
    async def list_chunks(
        source_id: SourceId,
        q: Annotated[str, Query(max_length=200)] = "",
        page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    ) -> dict[str, Any]:
        await found(source_id)
        items, total = await store.chunks(source_id, q, page, CHUNK_PAGE, None)
        return {"items": [c.shown() for c in items], "total": total, "page": page, "page_size": CHUNK_PAGE}

    @router.patch("/chunks/{chunk_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def patch_chunk(chunk_id: ChunkId, body: ChunkPatch) -> Response:
        if not await store.update_chunk(chunk_id, body.services, body.kind):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có đoạn này.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/sources/{source_id}/events")
    async def events(source_id: SourceId) -> list[dict[str, Any]]:
        await found(source_id)
        return [e.shown() for e in await store.events(source_id)]

    @router.post("/sources/{source_id}/restore")
    async def restore(source_id: SourceId, body: RestoreBody) -> dict[str, Any]:
        await found(source_id)
        raise HTTPException(status.HTTP_409_CONFLICT, "Bản này chưa giữ các phiên bản cũ để khôi phục.")

    @router.get("/services")
    async def list_services() -> list[dict[str, Any]]:
        counts = await store.service_chunks()
        return [s.shown(counts.get(s.code, 0)) for s in await store.services()]

    @router.post("/services", status_code=status.HTTP_201_CREATED)
    async def create_service(body: ServiceBody) -> dict[str, Any]:
        if any(s.code == body.code for s in await store.services()):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Đã có dịch vụ mã {body.code}.")
        service = Service(new_id("svc"), **body.model_dump())
        await store.save_service(service)
        return service.shown(0)

    @router.patch("/services/{service_id}")
    async def patch_service(service_id: ServiceId, body: ServicePatch) -> dict[str, Any]:
        services = await store.services()
        current = next((s for s in services if s.id == service_id), None)
        if current is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có dịch vụ này.")
        given = body.model_dump(exclude_unset=True)
        if "code" in given and any(s.code == given["code"] and s.id != service_id for s in services):
            raise HTTPException(status.HTTP_409_CONFLICT, f"Đã có dịch vụ mã {given['code']}.")
        changed = replace(current, **given)
        await store.save_service(changed)
        return changed.shown((await store.service_chunks()).get(changed.code, 0))

    @router.delete("/services/{service_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_service(service_id: ServiceId) -> Response:
        if not await store.delete_service(service_id):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có dịch vụ này.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.post("/services/import")
    async def import_services(body: ImportBody) -> list[dict[str, Any]]:
        return [s.shown(0) for s in parse_service_table(body.text)]

    @router.post("/search/debug")
    async def search_debug(body: SearchBody) -> dict[str, Any]:
        settings = (await plugin.settings())["search"]
        result = await plugin.searcher.search(
            body.question,
            body.as_of,
            results=int(settings["results"]),
            char_budget=int(settings["char_budget"]),
            services=await store.services(),
        )
        return debug_view(result)

    @router.get("/gaps")
    async def list_gaps(state: GapState = "open") -> list[dict[str, Any]]:
        return [g.shown() for g in await store.gaps(state)]

    @router.patch("/gaps/{gap_id}")
    async def patch_gap(gap_id: GapId, body: GapPatch) -> dict[str, Any]:
        gap = await store.set_gap(gap_id, body.state)
        if gap is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Không có câu hỏi này.")
        return gap.shown()

    @router.get("/settings")
    async def get_settings() -> dict[str, Any]:
        return await _with_counts(plugin)

    @router.patch("/settings")
    async def patch_settings(body: dict[str, Any]) -> dict[str, Any]:
        await plugin.save_settings(_checked_settings(body))
        return await _with_counts(plugin)

    @router.post("/settings/test-embedding")
    async def test_embedding() -> dict[str, Any]:
        return {
            "ok": False,
            "dimensions": None,
            "normalised": None,
            "ms": None,
            "message": "Bản này chưa dùng embedding: agent đang tìm bằng từ khóa.",
        }

    @router.post("/settings/reembed")
    async def reembed() -> dict[str, Any]:
        return {"queued": 0}

    @router.post("/settings/test-parser")
    async def test_parser() -> dict[str, Any]:
        return {"ok": True, "ms": 0, "message": "Bộ đọc đơn giản (.md, .txt) sẵn sàng."}

    return router


async def _bulk_one(plugin: KnowledgePlugin, source: Source, body: BulkBody) -> None:
    store = plugin.store
    stamp = datetime.now(UTC)
    if body.action == "delete":
        await store.delete(source.id)
    elif body.action == "reindex":
        await plugin.ingest.rechunk(source, await store.services())
        await plugin.ingest.event(source.id, "reindexed")
    elif body.action == "approve":
        await store.save(replace(source, approved=True, approved_by=ADMIN, approved_at=stamp))
    elif body.action == "unapprove":
        await store.save(replace(source, approved=False, approved_by=None, approved_at=None))
    elif body.audience is not None:
        await store.save(replace(source, audience=body.audience, updated_at=stamp))


def _outline(markdown: str) -> list[dict[str, Any]]:
    _, body = split_head(markdown)
    return [{"level": n.level, "title": n.title, "chunks": n.chunks, "chars": n.chars} for n in outline(body)]


def _split(markdown: str, chosen: set[int]) -> tuple[str, str]:
    """The Markdown without the chosen outline positions (and their text), and those sections on their own.
    Positions count as ``_outline`` counts them, after the YAML head; the head stays with the kept part."""
    head = markdown[: len(markdown) - len(split_head(markdown)[1])]
    cut = [section for section in sections(markdown[len(head) :]) if section.level > 0 or section.text]
    headed = [section for section in cut if section.level > 0]
    picked = {id(section) for index, section in enumerate(headed) if index in chosen}

    def render(section: Any) -> str:
        heading = f"{'#' * section.level} {section.title}\n" if section.level > 0 else ""
        return f"{heading}{section.text}".strip()

    kept = head + "\n\n".join(render(s) for s in cut if id(s) not in picked)
    moved = "\n\n".join(render(s) for s in cut if id(s) in picked)
    return kept, moved


def parse_service_table(raw: str) -> list[Service]:
    """Services from a pasted table: CSV or Markdown, columns code, name, other names (``;``), description."""
    rows = [_cells(line) for line in raw.splitlines() if line.strip() and not re.fullmatch(r"[\s|:-]+", line)]
    body = rows[1:] if rows and fold(rows[0][0]) in ("code", "ma", "ma dich vu") else rows
    found: list[Service] = []
    for cells in body:
        code = (cells[0] if cells else "").strip().upper()
        name = cells[1].strip() if len(cells) > 1 else ""
        if not re.fullmatch(r"[A-Z0-9_]{1,40}", code) or not name:
            continue
        aliases = [a.strip() for a in (cells[2] if len(cells) > 2 else "").split(";") if a.strip()]
        found.append(Service(new_id("svc"), code, name, aliases, cells[3].strip() if len(cells) > 3 else ""))
    return found


def _cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in (stripped.split("|") if "|" in line else stripped.split(","))]


async def _with_counts(plugin: KnowledgePlugin) -> dict[str, Any]:
    settings = await plugin.settings()
    chunks = sum(s.chunk_count - s.embedded for s in await plugin.store.all_sources())
    settings["embedding"]["chunks_without_vector"] = chunks
    return settings


def _checked_settings(body: dict[str, Any]) -> dict[str, Any]:
    search = as_mapping(body.get("search"))
    if search:
        if "results" in search and not (isinstance(search["results"], int) and 1 <= search["results"] <= 20):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Số kết quả phải từ 1 đến 20.")
        budget = search.get("char_budget")
        if budget is not None and not (isinstance(budget, int) and 500 <= budget <= MAX_CHAR_BUDGET):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"Ngân sách ký tự phải từ 500 đến {MAX_CHAR_BUDGET}."
            )
    return body

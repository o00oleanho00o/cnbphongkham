"""Adding documents: read them first without storing anything (preview), then add the ones a person
confirmed.

Markdown and plain text are read here; PDF, Word and Excel are refused with a sentence until the reader for
them is added (Docling, a later step). A source is cut into chunks at once and is ready to be searched by
keyword as soon as it is added; there is no queue yet.
"""

from __future__ import annotations

import re
import secrets
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final

from .models import Chunk, ConfirmItem, Event, PreviewInput, Service, Source, SourceFormat
from .store import KnowledgeStore
from .text import (
    Head,
    Piece,
    Warning,
    chunk,
    content_hash,
    content_warnings,
    count_tables,
    fold,
    outline,
    split_head,
)

PREVIEW_TTL_S: Final = 3600.0
MAX_PREVIEWS: Final = 200
READABLE: Final[dict[str, SourceFormat]] = {".md": "md", ".markdown": "md", ".txt": "txt"}
LATER: Final[dict[str, SourceFormat]] = {".pdf": "pdf", ".docx": "docx", ".xlsx": "xlsx"}
NOT_YET: Final = (
    "Bản này đọc được .md và .txt. PDF, Word và Excel sẽ đọc được ở bước sau; tạm thời hãy dán nội dung."
)
ADMIN: Final = "Quản trị"
MAX_TEXT_CHARS: Final = 2_000_000


@dataclass(frozen=True, slots=True)
class Parsed:
    key: str
    name: str
    format: SourceFormat
    kind: str
    size: int
    head: Head
    body: str
    pieces: tuple[Piece, ...]
    hash: str
    error: str | None
    shown: dict[str, Any]


@dataclass(slots=True)
class _Preview:
    expires: float
    items: dict[str, Parsed] = field(default_factory=dict[str, Parsed])
    # what each confirmed key became: confirming it again (a retry, a double click) adds nothing
    added: dict[str, dict[str, Any]] = field(default_factory=dict[str, dict[str, Any]])


def new_id(prefix: str) -> str:
    return f"{prefix}-{secrets.token_hex(6)}"


class Ingest:
    def __init__(
        self,
        store: KnowledgeStore,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        today: Callable[[], date] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._store = store
        self._clock = clock
        self._today = today or (lambda: clock().date())
        self._monotonic = monotonic
        self._previews: dict[str, _Preview] = {}

    async def preview(self, inputs: Sequence[PreviewInput], *, benchmark: bool) -> dict[str, Any]:
        self._drop_old()
        parsed = [await self._parse(item, benchmark=benchmark) for item in inputs]
        preview_id = new_id("pv")
        self._previews[preview_id] = _Preview(
            self._monotonic() + PREVIEW_TTL_S, {item.key: item for item in parsed}
        )
        return {"preview_id": preview_id, "items": [item.shown for item in parsed], "benchmark": benchmark}

    async def confirm(
        self, preview_id: str, items: Sequence[ConfirmItem], services: Sequence[Service], *, benchmark: bool
    ) -> dict[str, Any]:
        preview = self._previews.get(preview_id)
        if preview is None:
            raise LookupError("Bản xem trước đã hết hạn hoặc không còn; hãy chọn tệp lại.")
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        for item in items:
            if item.key in preview.added:
                created.append(preview.added[item.key])
                continue
            parsed = preview.items.get(item.key)
            reason = await self._refusal(parsed, item, benchmark=benchmark)
            if reason is not None or parsed is None:
                skipped.append({"key": item.key, "reason": reason or "Không có trong bản xem trước."})
                continue
            shown = (await self._add(parsed, item, services)).shown()
            preview.added[item.key] = shown
            created.append(shown)
        return {"batch_id": new_id("batch"), "created": created, "skipped": skipped}

    async def rechunk(
        self, source: Source, services: Sequence[Service], markdown: str | None = None
    ) -> Source:
        """Cuts the source again (after its Markdown or the services changed) and stores the new chunks."""
        text = source.markdown if markdown is None else markdown
        _, body = split_head(text)
        chunks = make_chunks(source.id, chunk(body, source.title), services)
        changed = replace(
            source,
            markdown=text,
            content_hash=content_hash(text),
            chunk_count=len(chunks),
            chunks=len(chunks),
            labelled=len(chunks),
            processing="ready",
            error=None,
            services=source.services or labels_of(chunks),
            updated_at=self._clock(),
        )
        await self._store.save(changed)
        await self._store.replace_chunks(source.id, chunks)
        return changed

    async def event(self, source_id: str, kind: str, note: str = "") -> None:
        await self._store.add_event(Event(new_id("ev"), source_id, self._clock(), kind, ADMIN, note))

    async def _parse(self, item: PreviewInput, *, benchmark: bool) -> Parsed:
        extension = _extension(item.name)
        source_format: SourceFormat = (
            "text" if item.kind == "text" else READABLE.get(extension, LATER.get(extension, "txt"))
        )
        if item.kind == "file" and extension not in READABLE:
            return self._failed(item, source_format, NOT_YET)
        if item.text is None:
            return self._failed(item, source_format, "Không đọc được nội dung tệp.")
        if len(item.text) > MAX_TEXT_CHARS:
            return self._failed(
                item, source_format, f"Tệp dài hơn {MAX_TEXT_CHARS:,} ký tự; hãy tách thành nhiều tệp."
            )
        head, body = split_head(item.text)
        nodes = outline(body)
        title = head.title or _stem(item.name)
        pieces = tuple(chunk(body, title))
        digest = content_hash(item.text)
        same_code = await self._store.by_code(head.doc_code) if head.doc_code else None
        same_content = await self._store.by_hash(digest)
        warnings = [*content_warnings(body, nodes), *_head_warnings(head, benchmark=benchmark)]
        if same_content is not None:
            warnings.append(
                Warning(
                    "same_content",
                    "warn",
                    f'Trùng hệt nội dung với nguồn "{same_content.title}".',
                    "Bỏ qua tệp này.",
                )
            )
        sizes = [len(piece.text) for piece in pieces]
        shown: dict[str, Any] = {
            "key": item.key,
            "name": item.name,
            "format": source_format,
            "size": item.size,
            "meta": _meta(head),
            "outline": [
                {"level": n.level, "title": n.title, "chunks": n.chunks, "chars": n.chars} for n in nodes
            ],
            "chunk_count": len(pieces),
            "avg_chars": round(sum(sizes) / len(sizes)) if sizes else 0,
            "tables_split": count_tables(body),
            "warnings": [_warning(w) for w in warnings],
            "same_code_as": None
            if same_code is None
            else {"id": same_code.id, "title": same_code.title, "version": same_code.version},
            "same_content_as": None
            if same_content is None
            else {"id": same_content.id, "title": same_content.title},
            "error": None,
        }
        return Parsed(
            item.key,
            item.name,
            source_format,
            item.kind,
            item.size,
            head,
            item.text,
            pieces,
            digest,
            None,
            shown,
        )

    def _failed(self, item: PreviewInput, source_format: SourceFormat, error: str) -> Parsed:
        shown: dict[str, Any] = {
            "key": item.key,
            "name": item.name,
            "format": source_format,
            "size": item.size,
            "meta": _meta(Head()),
            "outline": [],
            "chunk_count": 0,
            "avg_chars": 0,
            "tables_split": 0,
            "warnings": [],
            "same_code_as": None,
            "same_content_as": None,
            "error": error,
        }
        return Parsed(
            item.key, item.name, source_format, item.kind, item.size, Head(), "", (), "", error, shown
        )

    async def _refusal(self, parsed: Parsed | None, item: ConfirmItem, *, benchmark: bool) -> str | None:
        if parsed is None:
            return None
        if parsed.error is not None:
            return parsed.error
        if parsed.head.ingest_role == "challenge" and not benchmark:
            return "Tài liệu thử thách chỉ nạp được khi bật chế độ benchmark."
        if item.on_same_code == "skip":
            return "Bỏ qua theo lựa chọn."
        return None

    async def _add(self, parsed: Parsed, item: ConfirmItem, services: Sequence[Service]) -> Source:
        now = self._clock()
        source_id = new_id("src")
        chunks = make_chunks(source_id, list(parsed.pieces), services)
        source = Source(
            id=source_id,
            title=item.title,
            doc_code=item.doc_code or None,
            kind="text" if parsed.kind == "text" else "file",
            format=parsed.format,
            size=parsed.size,
            audience=item.audience,
            lifecycle=item.lifecycle,
            content_hash=parsed.hash,
            created_by=ADMIN,
            markdown=parsed.body,
            services=item.services or labels_of(chunks),
            processing="ready",
            chunks=len(chunks),
            labelled=len(chunks),
            version=item.version,
            effective_from=item.effective_from,
            effective_to=item.effective_to,
            approved=True,
            approved_by=ADMIN,
            approved_at=now,
            chunk_count=len(chunks),
            note=item.note,
            supersedes=item.supersedes,
            created_at=now,
            updated_at=now,
        )
        replaced = await self._replaced(item)
        await self._store.add_source(source, chunks)
        await self.event(source_id, "uploaded", parsed.name)
        if replaced is not None and item.lifecycle == "active":
            await self._retire(replaced, item, now)
        return source

    async def _retire(self, old: Source, item: ConfirmItem, now: datetime) -> None:
        """The old version stops where the new one starts: at once, or (a version that starts later) on the
        day before it, staying in use until then."""
        starts = item.effective_from
        if starts is None or starts <= self._today():
            await self._store.save(replace(old, lifecycle="superseded", updated_at=now))
            await self.event(old.id, "replaced", f'Thay bằng "{item.title}"')
            return
        last_day = starts - timedelta(days=1)
        ends = last_day if old.effective_to is None else min(old.effective_to, last_day)
        await self._store.save(replace(old, effective_to=ends, updated_at=now))
        await self.event(old.id, "replaced", f'Dùng đến {ends.isoformat()}, sau đó thay bằng "{item.title}"')

    async def _replaced(self, item: ConfirmItem) -> Source | None:
        if item.supersedes:
            return await self._store.get(item.supersedes)
        if item.doc_code and item.on_same_code == "version":
            return await self._store.by_code(item.doc_code)
        return None

    def _drop_old(self) -> None:
        now = self._monotonic()
        for preview_id in [key for key, value in self._previews.items() if value.expires < now]:
            del self._previews[preview_id]
        while len(self._previews) > MAX_PREVIEWS:
            del self._previews[next(iter(self._previews))]


def make_chunks(source_id: str, pieces: Sequence[Piece], services: Sequence[Service]) -> list[Chunk]:
    return [
        Chunk(
            id=f"{source_id}-c{index}",
            source_id=source_id,
            ordinal=index,
            path=piece.path,
            body=piece.text,
            services=tuple(recognise(f"{piece.path}\n{piece.text}", services)),
        )
        for index, piece in enumerate(pieces, start=1)
    ]


def recognise(text: str, services: Sequence[Service]) -> list[str]:
    """The codes of the services whose name or another name appears in the text (as whole words)."""
    folded = f" {' '.join(re.findall(r'[a-z0-9]+', fold(text)))} "
    return [
        service.code
        for service in services
        if service.enabled and any(f" {name} " in folded for name in _names(service))
    ]


def _names(service: Service) -> list[str]:
    raw = [service.name, *service.aliases]
    return [" ".join(re.findall(r"[a-z0-9]+", fold(name))) for name in raw if fold(name).strip()]


def labels_of(chunks: Sequence[Chunk]) -> list[str]:
    return list(dict.fromkeys(code for item in chunks for code in item.services))


def _head_warnings(head: Head, *, benchmark: bool) -> list[Warning]:
    found: list[Warning] = []
    if head.ingest_role == "challenge":
        found.append(
            Warning(
                "challenge",
                "info" if benchmark else "error",
                "Tài liệu thử thách (giá cũ, nháp, tấn công thử).",
                None if benchmark else "Chỉ nạp được khi bật chế độ benchmark trong Cài đặt.",
            )
        )
    if head.lifecycle in ("draft", "adversarial", "superseded"):
        found.append(
            Warning(
                "lifecycle",
                "info",
                f"Tài liệu ghi trạng thái {head.lifecycle}: agent sẽ không dùng nó để trả lời.",
            )
        )
    return found


def _meta(head: Head) -> dict[str, Any]:
    return {
        "doc_code": head.doc_code,
        "title": head.title,
        "tenant_id": head.tenant_id,
        "version": head.version,
        "lifecycle": head.lifecycle,
        "effective_from": head.effective_from.isoformat() if head.effective_from else None,
        "effective_to": head.effective_to.isoformat() if head.effective_to else None,
        "audience": head.audience,
        "ingest_role": head.ingest_role,
    }


def _warning(warning: Warning) -> dict[str, Any]:
    shown: dict[str, Any] = {"code": warning.code, "level": warning.level, "text": warning.text}
    if warning.fix:
        shown["fix"] = warning.fix
    return shown


def _extension(name: str) -> str:
    dot = name.rfind(".")
    return name[dot:].lower() if dot >= 0 else ""


def _stem(name: str) -> str:
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    dot = base.rfind(".")
    return (base[:dot] if dot > 0 else base) or "Tài liệu"

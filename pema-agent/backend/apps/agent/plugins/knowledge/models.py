"""What the knowledge store keeps and what its admin routes send and take (the shapes of the pages'
``ui/src/types.ts``)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from .text import Audience, Lifecycle, text_hash

Processing = Literal["queued", "processing", "ready", "error"]
SourceFormat = Literal["md", "txt", "docx", "xlsx", "pdf", "text"]
GapState = Literal["open", "ignored", "answered"]


@dataclass(slots=True)
class Source:
    id: str
    title: str
    doc_code: str | None
    kind: Literal["file", "text"]
    format: SourceFormat
    size: int
    audience: Audience
    lifecycle: Lifecycle
    content_hash: str
    created_by: str
    markdown: str = ""
    services: list[str] = field(default_factory=list[str])
    processing: Processing = "ready"
    chunks: int = 0
    labelled: int = 0
    embedded: int = 0
    error: str | None = None
    version: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    approved: bool = True
    approved_by: str | None = None
    approved_at: datetime | None = None
    chunk_count: int = 0
    note: str = ""
    supersedes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def shown(self) -> dict[str, Any]:
        """As the pages read it (``Source`` of types.ts): no Markdown, dates as ISO text."""
        data = asdict(self)
        for key in ("markdown", "content_hash", "supersedes", "chunks", "labelled", "embedded"):
            data.pop(key)
        data["progress"] = {"chunks": self.chunks, "labelled": self.labelled, "embedded": self.embedded}
        return {key: _iso(value) for key, value in data.items()}


@dataclass(frozen=True, slots=True)
class Chunk:
    id: str
    source_id: str
    ordinal: int
    path: str
    body: str
    services: tuple[str, ...] = ()
    kind: str = "info"
    embedded: bool = False
    """Whether it has a vector in the space in use; the store fills it when it reads."""
    embed_text: str = ""
    """What it is embedded as (``text.embed_text_of``); empty for a chunk made without it."""

    @property
    def embed_hash(self) -> str:
        return text_hash(self.embed_text) if self.embed_text else ""

    def shown(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ordinal": self.ordinal,
            "path": self.path,
            "text": self.body,
            "chars": len(self.body),
            "services": list(self.services),
            "kind": self.kind,
            "embedded": self.embedded,
        }


@dataclass(frozen=True, slots=True)
class Hit:
    """A chunk a search found, with its source's name and code and a score (higher is better)."""

    chunk: Chunk
    source_title: str
    doc_code: str | None
    score: float


@dataclass(frozen=True, slots=True)
class Event:
    id: str
    source_id: str
    at: datetime
    kind: str
    by: str
    note: str

    def shown(self) -> dict[str, Any]:
        return {"id": self.id, "at": self.at.isoformat(), "kind": self.kind, "by": self.by, "note": self.note}


@dataclass(slots=True)
class Service:
    id: str
    code: str
    name: str
    aliases: list[str] = field(default_factory=list[str])
    description: str = ""
    branches: list[str] = field(default_factory=list[str])
    enabled: bool = True

    def shown(self, chunk_count: int) -> dict[str, Any]:
        return {**asdict(self), "chunk_count": chunk_count}


@dataclass(slots=True)
class Gap:
    id: str
    folded: str
    question: str
    count: int
    channel: str
    last_asked_at: datetime
    state: GapState = "open"

    def shown(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "question": self.question,
            "count": self.count,
            "channel": self.channel,
            "last_asked_at": self.last_asked_at.isoformat(),
            "state": self.state,
        }


@dataclass(frozen=True, slots=True)
class SourceFilter:
    q: str = ""
    processing: Processing | None = None
    audience: Audience | None = None
    service: str | None = None
    lifecycle: Lifecycle | None = None
    approved: bool | None = None
    page: int = 1
    page_size: int = 30


def as_mapping(value: object) -> dict[str, Any]:
    """A JSON object as a dict with text keys; anything else as an empty one."""
    if not isinstance(value, dict):
        return {}
    items = cast("dict[object, Any]", value).items()  # a JSON object: its keys are text
    return {str(key): item for key, item in items}


def _iso(value: object) -> object:
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


# -- request bodies -----------------------------------------------------------------------------------------


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PreviewInput(_Body):
    """One file or pasted text. Its length is checked per item (an error on that item, not on the batch);
    the gateway's body limit bounds the call."""

    key: str = Field(min_length=1, max_length=2000)
    name: str = Field(min_length=1, max_length=1000)
    kind: Literal["file", "text"]
    size: int = Field(ge=0)
    text: str | None = None
    base64: str | None = Field(default=None, max_length=40_000_000)


class PreviewBody(_Body):
    inputs: list[PreviewInput] = Field(min_length=1, max_length=50)


class ConfirmItem(_Body):
    key: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=300)
    doc_code: str | None = Field(default=None, max_length=120)
    audience: Audience = "patient"
    approved: bool = True
    services: list[str] = Field(default_factory=list[str], max_length=50)
    lifecycle: Lifecycle = "active"
    version: str | None = Field(default=None, max_length=40)
    effective_from: date | None = None
    effective_to: date | None = None
    supersedes: str | None = Field(default=None, max_length=100)
    note: str = Field(default="", max_length=2000)
    on_same_code: Literal["version", "skip"] = "version"


class ConfirmBody(_Body):
    preview_id: str = Field(min_length=1, max_length=100)
    items: list[ConfirmItem] = Field(min_length=1, max_length=50)


class SourcePatch(_Body):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    audience: Audience | None = None
    services: list[str] | None = Field(default=None, max_length=50)
    effective_from: date | None = None
    effective_to: date | None = None
    note: str | None = Field(default=None, max_length=2000)


class BulkBody(_Body):
    ids: list[str] = Field(min_length=1, max_length=200)
    action: Literal["approve", "unapprove", "audience", "reindex", "delete"]
    audience: Audience | None = None


class StructureBody(_Body):
    markdown: str = Field(min_length=1, max_length=1_000_000)


class SplitBody(_Body):
    sections: list[int] = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)


class ChunkPatch(_Body):
    services: list[str] | None = Field(default=None, max_length=50)
    kind: str | None = Field(default=None, max_length=40)


class ServiceBody(_Body):
    code: str = Field(pattern=r"^[A-Z0-9_]{1,40}$")
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list[str], max_length=50)
    description: str = Field(default="", max_length=2000)
    branches: list[str] = Field(default_factory=list[str], max_length=20)
    enabled: bool = True


class ServicePatch(_Body):
    code: str | None = Field(default=None, pattern=r"^[A-Z0-9_]{1,40}$")
    name: str | None = Field(default=None, min_length=1, max_length=200)
    aliases: list[str] | None = Field(default=None, max_length=50)
    description: str | None = Field(default=None, max_length=2000)
    branches: list[str] | None = Field(default=None, max_length=20)
    enabled: bool | None = None


class ImportBody(_Body):
    text: str = Field(min_length=1, max_length=200_000)


class SearchBody(_Body):
    question: str = Field(min_length=1, max_length=1000)
    channel: Literal["patient", "staff"] = "patient"
    as_of: date


class GapPatch(_Body):
    state: GapState


class RestoreBody(_Body):
    event: str = Field(min_length=1, max_length=100)

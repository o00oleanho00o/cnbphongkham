# ported from: src/agent/tools/tool-catalog-types.ts (the imports of the tool files, made explicit)
"""``ToolDeps``: every collaborator a tool needs that lives in ANOTHER package.

Forced deviation (one synchronous process with module singletons -> separate worktrees / async services):
the original tools imported the stores, the rate limiter, the Zalo helpers and the sidecar directly
(``import { saveMemoryFact } from "../../conversation/memory-store.js"``). In the Python port those belong
to packages that are built in parallel (D1 sidecar, D2 stores, C1 rate limiter, C2 text cleaning, S
scheduler parser, D3 knowledge availability), so each one is a ``Protocol`` here and the registry receives
the real object when package G wires the process. Tests inject the fakes of
``tests/agent/tools/fakes.py``.

What is NOT here because the contracts already give it: the channel (``ToolContext.channel`` with the
optional ``MediaChannel`` / ``ReactionChannel`` / ``GroupChannel`` abilities), ``HistoryStore``,
``MemoryStore``, ``SchedulerPort``, ``KnowledgeSearch``, ``PolicyHooks`` (all from ``pema_contracts``).

Contract gaps found while porting (reported to package G, each has a Protocol below so the tools do not wait):

* ``MemoryEditPort``: ``suaFactTheoDoanChu`` / ``xoaFactTheoDoanChu`` (``memory-edit-store.ts``): now in
  ``pema_contracts.conversation``, implemented by D2.
* ``JobUpdater``: ``updateJob`` of ``scheduled-job-store.ts``: now in ``pema_contracts.scheduler``,
  implemented by S.
* ``ScheduleParser``: ``parseSchedule`` of ``schedule-parser.ts`` is a pure function owned by package S.
* ``ReplyTextCleaner`` / ``MarkdownStyler`` / ``SendQueue``: ``sanitize-reply-text.ts``,
  ``markdown-to-zalo-styles.ts`` (C2) and ``rate-limiter.ts#enqueueSend`` (C1)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from pema.video.gui_video_qua_zalo import ZaloVideoApi
from pema_contracts.channel import TextStyle
from pema_contracts.conversation import HistoryStore, MemoryEditPort, MemoryStore
from pema_contracts.knowledge import KnowledgeSearch
from pema_contracts.policy import PermissivePolicyHooks, PolicyHooks
from pema_contracts.scheduler import JobUpdater, ParsedSchedule, ScheduleInput, SchedulerPort
from pema_contracts.tools import ToolContext

# ------------------------------------------------------------------ text cleaning (C2)


@dataclass(frozen=True)
class CleanedReply:
    """``KetQuaLamSach``: cleaned ``text``; ``blocked`` (``chan``) when it looks like a leaked prompt."""

    text: str
    blocked: bool


class ReplyTextCleaner(Protocol):
    """``lamSachTraLoi`` and ``lamSachGiuDinhDang`` of ``sanitize-reply-text.ts`` (package C2)."""

    def clean_reply(self, text: str) -> CleanedReply: ...

    def clean_keep_formatting(self, text: str) -> CleanedReply: ...


@dataclass(frozen=True)
class StyledText:
    """``KetQuaDinhDang``."""

    text: str
    styles: list[TextStyle] = field(default_factory=list[TextStyle])


class MarkdownStyler(Protocol):
    """``markdownSangStyleZalo`` of ``markdown-to-zalo-styles.ts`` (package C2)."""

    def markdown_to_styles(self, text: str) -> StyledText: ...


# ------------------------------------------------------------------ sending (C1)


class SendQueue(Protocol):
    """``enqueueSend`` of ``middleware/rate-limiter.ts`` (package C1): ONE send at a time per thread key
    (``<account_id>:<thread_id>``), with the random human-like gap between messages."""

    async def enqueue_send[T](self, thread_key: str, send: Callable[[], Awaitable[T]]) -> T: ...


# ------------------------------------------------------------------ images and vision (D2, D1)


@dataclass(frozen=True)
class StoredImage:
    """``{base64, mediaType}`` returned by ``loadStoredImage``."""

    base64: str
    media_type: str


class StoredImageLoader(Protocol):
    """``loadStoredImage`` of ``conversation/media-store.ts`` (package D2). ``None`` when the file was
    already swept by the retention job."""

    async def load_stored_image(self, rel_path: str) -> StoredImage | None: ...


class VisionSidecar(Protocol):
    """``askAboutImage`` of ``agent/vision-sidecar.ts`` (package D1)."""

    async def ask_about_image(self, image: StoredImage, question: str) -> str: ...


# ------------------------------------------------------------------ memory edit (D2)


# ``MemoryEditScope``, ``MemoryEditOk``, ``MemoryEditFailed``, ``MemoryEditResult`` and
# ``MemoryEditPort`` live in ``pema_contracts.conversation`` (package D2 implements the port).

# ------------------------------------------------------------------ scheduler (S)


@dataclass(frozen=True)
class ParseScheduleResult:
    """``ParseScheduleResult``: ``schedule`` when ``ok``, else a Vietnamese ``error`` for the model."""

    ok: bool
    schedule: ParsedSchedule | None = None
    error: str = ""


class ScheduleParser(Protocol):
    """``parseSchedule`` of ``scheduler/schedule-parser.ts`` (package S): pure and synchronous. It rejects
    ``every`` / ``cron`` denser than ``min_interval_minutes`` and a ``once`` in the past."""

    def parse_schedule(
        self, schedule: ScheduleInput, *, time_zone: str, min_interval_minutes: int
    ) -> ParseScheduleResult: ...


# ------------------------------------------------------------------ knowledge availability (D3)


class KbAvailability(Protocol):
    """``nguonCuaAgent(agent_id).length > 0`` and ``coNguonNao()`` of the knowledge package, as SYNC
    probes because ``ToolSpec.available`` is synchronous (it runs on every turn and on the Tools page).
    The real implementation reads an in-memory snapshot that package D3 refreshes when sources or bindings
    change."""

    def agent_has_sources(self, agent_id: str) -> bool: ...

    def any_source(self) -> bool: ...


# ------------------------------------------------------------------ video upload road (C2)


def no_video_api(_ctx: ToolContext) -> ZaloVideoApi | None:
    """Default of ``ToolDeps.video_api_for``: no adapter wired, ``tai_video`` answers a marked failure."""
    return None


# ------------------------------------------------------------------ the bundle


@dataclass(frozen=True)
class ToolDeps:
    """Everything the 15 tools (plus the ``availability`` probes of the catalog) need from other packages."""

    history: HistoryStore
    memory: MemoryStore
    memory_edit: MemoryEditPort
    scheduler: SchedulerPort
    job_updater: JobUpdater
    schedule_parser: ScheduleParser
    knowledge: KnowledgeSearch
    kb_availability: KbAvailability
    send_queue: SendQueue
    reply_cleaner: ReplyTextCleaner
    markdown_styler: MarkdownStyler
    stored_images: StoredImageLoader
    vision: VisionSidecar
    sidecar_configured: Callable[[], bool]
    """``isSidecarConfigured`` of ``runtime-vision-settings.ts`` (package D1)."""
    policy: PolicyHooks = field(default_factory=PermissivePolicyHooks)
    video_api_for: Callable[[ToolContext], ZaloVideoApi | None] = no_video_api
    """The zca-js style upload/send road for ``tai_video`` (``ZaloVideoApi`` of ``pema.video``): the
    contract's ``MediaChannel.send_video(url)`` cannot upload bytes, and a video must be uploaded to Zalo
    to play on a phone (see ``gui_video_qua_zalo``). Package C2/G wires an adapter over the Node bridge
    for the personal channel and returns ``None`` for the others."""

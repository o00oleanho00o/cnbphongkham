# ported from: src/shared/fake-agent-profile.ts (and the stub contexts of the tool tests)
"""Test doubles for the tools. Import in tests only (``from pema.agent.tools.testing import ...``).

Nothing here touches a network or a database. The fakes follow the Protocols of ``tool_deps`` and of
``pema_contracts`` so ``isinstance`` / pyright keep them honest. The original tests built a stub
``ToolContext`` with ``api: {} as API``; here the channel is a ``RecordingChannel`` that implements every
optional ability (media, reactions, group) and records what was sent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID

from pema.agent.tools.tool_deps import (
    CleanedReply,
    ParseScheduleResult,
    StoredImage,
    StyledText,
    ToolDeps,
)
from pema_contracts.channel import (
    ChannelCapabilities,
    ChannelKind,
    ChannelPort,
    InboundMessage,
    SendResult,
    SendStatus,
    TextStyle,
    ThreadKind,
)
from pema_contracts.common import JsonObject, now_vn
from pema_contracts.conversation import (
    MemoryEditOk,
    MemoryEditResult,
    MemoryEditScope,
    SaveMemoryResult,
    StoredMessage,
)
from pema_contracts.knowledge import KbHit
from pema_contracts.policy import (
    DEFAULT_PROFILES,
    PolicyContext,
    PolicyProfile,
    PolicyProfileKey,
)
from pema_contracts.scheduler import (
    CreateScheduledJobInput,
    CronInput,
    CronSchedule,
    EveryInput,
    EverySchedule,
    OnceInMinutesInput,
    OnceSchedule,
    ParsedSchedule,
    ScheduledJob,
    ScheduleInput,
    ScheduleKind,
    thread_kind_of,
)
from pema_contracts.testing import (
    FAKE_CLINIC_ID,
    FakeChannel,
    fake_account_config,
    fake_agent_profile,
    make_inbound,
)
from pema_contracts.tools import ToolContext, ToolScope

# ------------------------------------------------------------------ channel


def personal_capabilities(**patch: object) -> ChannelCapabilities:
    """Capabilities of the personal channel: everything the 15 tools need is available."""
    data: dict[str, object] = {
        "channel": ChannelKind.ZALO_PERSONAL,
        "can_send_proactive": True,
        "supports_reactions": True,
        "supports_send_image": True,
        "supports_send_file": True,
        "supports_send_video": True,
        "supports_group_info": True,
        "supports_tag_member": True,
        **patch,
    }
    return ChannelCapabilities.model_validate(data)


def bot_capabilities(**patch: object) -> ChannelCapabilities:
    """Capabilities of the Bot API channel: the 8 tools it cannot run are listed in ``blocked_tools``."""
    blocked = dict.fromkeys(
        (
            "add_reaction",
            "send_file",
            "create_word_document",
            "create_excel_file",
            "create_image",
            "tai_video",
            "tag_member",
            "get_group_info",
        ),
        "Zalo Bot API không hỗ trợ",
    )
    data: dict[str, object] = {
        "channel": ChannelKind.ZALO_BOT,
        "can_send_proactive": False,
        "blocked_tools": blocked,
        **patch,
    }
    return ChannelCapabilities.model_validate(data)


@dataclass
class SentMedia:
    kind: str
    thread_id: str
    filename: str
    data: bytes
    caption: str


@dataclass
class RecordingChannel(FakeChannel):
    """``FakeChannel`` plus the optional abilities. ``fail_media`` makes every media send raise (a
    transport error), ``reject_media`` makes it answer a rejected ``SendResult``."""

    media: list[SentMedia] = field(default_factory=list[SentMedia])
    videos: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])
    reactions: list[tuple[str, str]] = field(default_factory=list[tuple[str, str]])
    tags: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])
    group_info: JsonObject = field(default_factory=dict[str, object])
    fail_media: Exception | None = None
    reject_media: SendResult | None = None

    def _media_result(self) -> SendResult:
        if self.fail_media is not None:
            raise self.fail_media
        if self.reject_media is not None:
            return self.reject_media
        return SendResult(status=SendStatus.SENT, external_message_id="m-media", sent_at=now_vn())

    async def send_image(
        self, thread_id: str, thread_kind: ThreadKind, data: bytes, caption: str
    ) -> SendResult:
        result = self._media_result()
        self.media.append(SentMedia("image", thread_id, "", data, caption))
        return result

    async def send_file(
        self, thread_id: str, thread_kind: ThreadKind, filename: str, data: bytes, caption: str
    ) -> SendResult:
        result = self._media_result()
        self.media.append(SentMedia("file", thread_id, filename, data, caption))
        return result

    async def send_video(self, thread_id: str, thread_kind: ThreadKind, url: str, caption: str) -> SendResult:
        result = self._media_result()
        self.videos.append((thread_id, url, caption))
        return result

    async def react(self, message: InboundMessage, icon: str) -> SendResult:
        if self.fail_media is not None:
            raise self.fail_media
        self.reactions.append((message.msg_id, icon))
        return SendResult(status=SendStatus.SENT)

    async def get_group_info(self, thread_id: str) -> JsonObject:
        if self.fail_media is not None:
            raise self.fail_media
        return self.group_info

    async def tag_member(self, thread_id: str, member_id: str, text: str) -> SendResult:
        if self.fail_media is not None:
            raise self.fail_media
        self.tags.append((thread_id, member_id, text))
        return SendResult(status=SendStatus.SENT)


def make_channel(**patch: object) -> RecordingChannel:
    caps = personal_capabilities()
    return RecordingChannel(caps=caps, **patch)  # pyright: ignore[reportArgumentType]


# ------------------------------------------------------------------ the small fakes


class ImmediateSendQueue:
    """``SendQueue`` without the human-like delay; records the keys it was used with."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    async def enqueue_send[T](self, thread_key: str, send: Callable[[], Awaitable[T]]) -> T:
        self.keys.append(thread_key)
        return await send()


class FakeReplyCleaner:
    """Blocks any text containing ``LEAK`` (stands for the leaked-prompt detector); otherwise trims."""

    def clean_reply(self, text: str) -> CleanedReply:
        if "LEAK" in text:
            return CleanedReply(text="", blocked=True)
        return CleanedReply(text=text.replace("**", "").replace("`", "").strip(), blocked=False)

    def clean_keep_formatting(self, text: str) -> CleanedReply:
        if "LEAK" in text:
            return CleanedReply(text="", blocked=True)
        return CleanedReply(text=text, blocked=False)


class FakeMarkdownStyler:
    """Turns ``**x**`` into a bold span, nothing else."""

    def markdown_to_styles(self, text: str) -> StyledText:
        out: list[str] = []
        styles: list[TextStyle] = []
        pos = 0
        while True:
            start = text.find("**", pos)
            end = text.find("**", start + 2) if start >= 0 else -1
            if start < 0 or end < 0:
                out.append(text[pos:])
                break
            out.append(text[pos:start])
            inner = text[start + 2 : end]
            offset = sum(len(p) for p in out)
            if inner:
                styles.append(TextStyle(start=offset, length=len(inner), style="b"))
            out.append(inner)
            pos = end + 2
        return StyledText(text="".join(out), styles=styles)


class FakeStoredImages:
    def __init__(self, images: dict[str, StoredImage] | None = None) -> None:
        self.images = images or {}

    async def load_stored_image(self, rel_path: str) -> StoredImage | None:
        return self.images.get(rel_path)


class FakeVision:
    def __init__(self, answer: str = "mô tả ảnh", error: Exception | None = None) -> None:
        self.answer = answer
        self.error = error
        self.calls: list[tuple[StoredImage, str]] = []

    async def ask_about_image(self, image: StoredImage, question: str) -> str:
        self.calls.append((image, question))
        if self.error is not None:
            raise self.error
        return self.answer


class FakeHistory:
    """``HistoryStore`` over a list; only ``get_recent_messages`` is used by the tools."""

    def __init__(self, messages: list[StoredMessage] | None = None) -> None:
        self.messages = messages or []

    async def append_message(
        self, clinic_id: UUID, account_id: str, thread_id: str, message: StoredMessage
    ) -> int:
        self.messages.append(message)
        return len(self.messages)

    async def set_message_images(self, clinic_id: UUID, message_id: int, images: list[str]) -> None:
        return None

    async def get_recent_messages(
        self, clinic_id: UUID, account_id: str, thread_id: str, limit: int | None = None
    ) -> list[StoredMessage]:
        return list(self.messages)

    async def list_messages_paged(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[StoredMessage]:
        return list(self.messages)


@dataclass
class SavedFact:
    account_id: str
    subject_id: str
    content: str
    learned_in_thread_id: str
    learned_in_group: bool


class FakeMemory:
    """``MemoryStore`` that saves facts into a list and answers ``duplicate`` for an identical one."""

    def __init__(self) -> None:
        self.saved: list[SavedFact] = []

    async def save_memory_fact(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        subject_id: str,
        content: str,
        learned_in_thread_id: str,
        learned_in_group: bool,
    ) -> SaveMemoryResult:
        if any(f.subject_id == subject_id and f.content == content.strip() for f in self.saved):
            return SaveMemoryResult(saved=False, reason="duplicate")
        self.saved.append(
            SavedFact(account_id, subject_id, content.strip(), learned_in_thread_id, learned_in_group)
        )
        return SaveMemoryResult(saved=True)

    async def get_memories_for_context(self, *args: object, **kwargs: object) -> list[object]:
        return []

    async def list_memories(self, *args: object, **kwargs: object) -> list[object]:
        return []

    async def delete_memory_fact(self, clinic_id: UUID, account_id: str, fact_id: int) -> bool:
        return False


class FakeMemoryEdit:
    """``MemoryEditPort`` with a scripted result."""

    def __init__(self, result: MemoryEditResult | None = None) -> None:
        self.result: MemoryEditResult = result or MemoryEditOk(old_content="điều cũ")
        self.calls: list[tuple[str, MemoryEditScope, str, str]] = []

    async def edit_fact_by_fragment(
        self, clinic_id: UUID, scope: MemoryEditScope, fragment: str, new_content: str
    ) -> MemoryEditResult:
        self.calls.append(("edit", scope, fragment, new_content))
        return self.result

    async def delete_fact_by_fragment(
        self, clinic_id: UUID, scope: MemoryEditScope, fragment: str
    ) -> MemoryEditResult:
        self.calls.append(("delete", scope, fragment, ""))
        return self.result


class FakeKnowledge:
    def __init__(self, hits: list[KbHit] | None = None, error: Exception | None = None) -> None:
        self.hits = hits or []
        self.error = error
        self.calls: list[tuple[str, str, int]] = []

    async def search(self, clinic_id: UUID, *, question: str, agent_id: str, limit: int = 5) -> list[KbHit]:
        self.calls.append((question, agent_id, limit))
        if self.error is not None:
            raise self.error
        return self.hits


class FakeKbAvailability:
    def __init__(self, agents: set[str] | None = None, any_source: bool = False) -> None:
        self.agents = agents or set()
        self.has_any = any_source

    def agent_has_sources(self, agent_id: str) -> bool:
        return agent_id in self.agents

    def any_source(self) -> bool:
        return self.has_any


class FakeScheduleParser:
    """Understands the four ``ScheduleInput`` kinds, fixed clock; rejects ``every`` below the minimum."""

    def __init__(self, now_utc: str = "2026-09-20T02:00:00Z") -> None:
        self.now_utc = now_utc

    def parse_schedule(
        self, schedule: ScheduleInput, *, time_zone: str, min_interval_minutes: int
    ) -> ParseScheduleResult:
        if isinstance(schedule, EveryInput):
            if schedule.minutes < min_interval_minutes:
                return ParseScheduleResult(
                    ok=False, error=f"Lịch lặp quá dày: tối thiểu {min_interval_minutes} phút một lần."
                )
            return ParseScheduleResult(ok=True, schedule=EverySchedule(minutes=schedule.minutes))
        if isinstance(schedule, CronInput):
            return ParseScheduleResult(
                ok=True, schedule=CronSchedule(expr=schedule.expr, time_zone=time_zone)
            )
        if isinstance(schedule, OnceInMinutesInput):
            base = datetime.fromisoformat(self.now_utc.replace("Z", "+00:00"))
            run_at = (base + timedelta(minutes=schedule.in_minutes)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            return ParseScheduleResult(ok=True, schedule=OnceSchedule(run_at_utc=run_at))
        return ParseScheduleResult(
            ok=True, schedule=OnceSchedule(run_at_utc=f"{schedule.date}T{schedule.time}:00.000Z")
        )


class FakeScheduler:
    """``SchedulerPort`` + ``JobUpdater`` over a dict (only the methods the tools use)."""

    def __init__(self) -> None:
        self.jobs: dict[str, ScheduledJob] = {}
        self.created: list[CreateScheduledJobInput] = []
        self._seq = 0

    async def create_job(self, job: CreateScheduledJobInput) -> ScheduledJob:
        self._seq += 1
        self.created.append(job)
        schedule = job.schedule
        record = ScheduledJob(
            id=f"job-{self._seq}",
            clinic_id=job.clinic_id,
            account_id=job.account_id,
            thread_id=job.thread_id,
            thread_type=job.thread_type,
            name=job.name,
            kind=job.kind,
            payload=job.payload,
            schedule_kind=schedule.kind,
            run_at=getattr(schedule, "run_at_utc", None),
            every_minutes=getattr(schedule, "minutes", None),
            cron_expr=getattr(schedule, "expr", None),
            timezone=job.timezone,
            next_run_at=getattr(schedule, "run_at_utc", None) or "2026-09-20T03:00:00.000Z",
            max_runs=1 if schedule.kind is ScheduleKind.ONCE else job.max_runs,
            created_by=job.created_by,
            origin=job.origin,
        )
        self.jobs[record.id] = record
        return record

    async def get_job(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str
    ) -> ScheduledJob | None:
        job = self.jobs.get(job_id)
        if job is None or job.account_id != account_id or job.thread_id != thread_id:
            return None
        return job

    async def list_jobs_for_thread(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> list[ScheduledJob]:
        return [j for j in self.jobs.values() if j.account_id == account_id and j.thread_id == thread_id]

    async def delete_job(self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str) -> bool:
        if await self.get_job(clinic_id, account_id, thread_id, job_id) is None:
            return False
        del self.jobs[job_id]
        return True

    async def set_enabled(
        self, clinic_id: UUID, account_id: str, thread_id: str, job_id: str, enabled: bool
    ) -> bool:
        job = await self.get_job(clinic_id, account_id, thread_id, job_id)
        if job is None:
            return False
        self.jobs[job_id] = job.model_copy(update={"enabled": enabled})
        return True

    async def update_job(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        job_id: str,
        *,
        name: str | None = None,
        payload: str | None = None,
        schedule: ParsedSchedule | None = None,
    ) -> ScheduledJob | None:
        job = await self.get_job(clinic_id, account_id, thread_id, job_id)
        if job is None:
            return None
        patch: dict[str, object] = {}
        if name is not None:
            patch["name"] = name
        if payload is not None:
            patch["payload"] = payload
        if schedule is not None:
            patch.update(
                schedule_kind=schedule.kind,
                run_at=getattr(schedule, "run_at_utc", None),
                every_minutes=getattr(schedule, "minutes", None),
                cron_expr=getattr(schedule, "expr", None),
                next_run_at=getattr(schedule, "run_at_utc", None) or "2026-09-20T03:00:00.000Z",
            )
        updated = job.model_copy(update=patch)
        self.jobs[job_id] = updated
        return updated


# ------------------------------------------------------------------ builders


def make_tool_deps(**override: object) -> ToolDeps:
    """A ``ToolDeps`` of fakes; ``override`` replaces any field (``vision=FakeVision(...)``)."""
    scheduler = FakeScheduler()
    data: dict[str, object] = {
        "history": FakeHistory(),
        "memory": FakeMemory(),
        "memory_edit": FakeMemoryEdit(),
        "scheduler": scheduler,
        "job_updater": scheduler,
        "schedule_parser": FakeScheduleParser(),
        "knowledge": FakeKnowledge(),
        "kb_availability": FakeKbAvailability(),
        "send_queue": ImmediateSendQueue(),
        "reply_cleaner": FakeReplyCleaner(),
        "markdown_styler": FakeMarkdownStyler(),
        "stored_images": FakeStoredImages(),
        "vision": FakeVision(),
        "sidecar_configured": lambda: True,
        **override,
    }
    return ToolDeps(**data)  # pyright: ignore[reportArgumentType]


def make_policy_context(
    profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
    *,
    isolated: bool = False,
    channel: ChannelKind = ChannelKind.ZALO_PERSONAL,
) -> PolicyContext:
    profile_data: PolicyProfile = DEFAULT_PROFILES[profile]
    return PolicyContext(
        clinic_id=FAKE_CLINIC_ID,
        account_id="acc-test",
        agent_id="agent-test",
        channel=channel,
        thread_id="t-1",
        profile=profile_data,
        isolated=isolated,
    )


def make_tool_context(
    *,
    channel: ChannelPort | None = None,
    message: InboundMessage | None = None,
    batch: Sequence[InboundMessage] = (),
    profile: PolicyProfileKey = PolicyProfileKey.STAFF_ASSISTANT,
    isolated: bool = False,
    record_sent: Callable[[str], None] | None = None,
    account_patch: dict[str, object] | None = None,
    agent_patch: dict[str, object] | None = None,
) -> ToolContext:
    """The stub context of the tool tests (``makeContext`` of the originals)."""
    msg = message or make_inbound(
        "xin chào",
        channel=ChannelKind.ZALO_PERSONAL,
        account_id="acc-test",
        thread_id="t-1",
        msg_id="m-1",
        cli_msg_id="c-1",
    )
    return ToolContext(
        clinic_id=FAKE_CLINIC_ID,
        account=fake_account_config(
            **{
                "id": "acc-test",
                "channel": ChannelKind.ZALO_PERSONAL,
                "agent_id": "agent-test",
                **(account_patch or {}),
            }
        ),
        agent=fake_agent_profile(**(agent_patch or {})),
        channel=channel if channel is not None else make_channel(),
        message=msg,
        batch=list(batch),
        policy=make_policy_context(profile, isolated=isolated),
        isolated=isolated,
        record_sent=record_sent,
    )


def make_scope(
    *,
    agent_id: str = "agent-test",
    agent_disabled: Sequence[str] = (),
    account_disabled: Sequence[str] = (),
    channel: ChannelCapabilities | None = None,
) -> ToolScope:
    return ToolScope(
        agent_id=agent_id,
        agent_disabled_tools=agent_disabled,
        account_disabled_tools=account_disabled,
        channel=channel or personal_capabilities(),
    )


__all__ = [
    "FakeHistory",
    "FakeKbAvailability",
    "FakeKnowledge",
    "FakeMarkdownStyler",
    "FakeMemory",
    "FakeMemoryEdit",
    "FakeReplyCleaner",
    "FakeScheduleParser",
    "FakeScheduler",
    "FakeStoredImages",
    "FakeVision",
    "ImmediateSendQueue",
    "MemoryEditScope",
    "RecordingChannel",
    "SavedFact",
    "SentMedia",
    "StoredImage",
    "bot_capabilities",
    "make_channel",
    "make_inbound",
    "make_policy_context",
    "make_scope",
    "make_tool_context",
    "make_tool_deps",
    "personal_capabilities",
    "thread_kind_of",
]

"""Conversation store contract (package D2 implements; D1, C1, C2, S, the admin API consume).

Port of the stores in zalo-agent ``src/conversation``: history-store, memory-store (+ memory-edit),
thread-store (+ summary and ``context_epoch``), usage-store, contact-store, image-description-store.
They run on Postgres tables ``agent.history``, ``agent.memories``, ``agent.threads``, ``agent.usage``,
``agent.usage_steps``, ``agent.contacts``, ``agent.image_descriptions``, all with ``clinic_id`` + RLS.

Conventions:

* every method is ``async``; the implementation takes its session from ``pema.core.db`` and sets the
  clinic context from ``clinic_id`` (the first argument of every method);
* timestamps are UTC ``datetime`` objects inside the store and ISO 8601 +07:00 on the wire;
* ``history`` is the LLM context store. It is NOT the Inbox of record: ``clinic.message`` is. The
  channel layer writes both (the Inbox through ``pema.clinic.actions``);
* ``history`` content in ``patient_channel`` has already passed ``before_llm`` masking only where it is
  shown to the model; what is stored is the original, inside the clinic database.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol
from uuid import UUID

from pydantic import Field

from pema_contracts.agent_turn import StepTrace, TokenUsage, TurnSource
from pema_contracts.common import ApiModel, VnDatetime


class StoredMessage(ApiModel):
    id: int | None = Field(default=None, description="Row id; set on read, absent on write.")
    role: Literal["user", "assistant"]
    content: str
    sender_name: str | None = None
    sender_id: str | None = None
    images: list[str] = Field(default_factory=list[str], description="Paths in the media store.")
    created_at: VnDatetime | None = Field(
        default=None,
        description="On write: the instant the sender pressed send (msg.sent_at); omitted = now().",
    )


class MemoryFact(ApiModel):
    id: int
    account_id: str
    subject_id: str
    content: str
    learned_in_thread_id: str
    learned_in_group: bool
    created_at: VnDatetime


class SaveMemoryResult(ApiModel):
    saved: bool
    reason: Literal["duplicate"] | None = Field(
        default=None, description="'duplicate': an identical fact (trimmed) already exists."
    )


class MemoryContextItem(ApiModel):
    subject_id: str
    content: str


class ThreadRow(ApiModel):
    account_id: str
    thread_id: str
    thread_type: int
    display_name: str
    bot_enabled: bool
    message_count: int
    last_message_at: VnDatetime | None = None
    last_sender_name: str | None = None


class ThreadSummary(ApiModel):
    summary: str = ""
    covers_to_message_id: int = 0


class ContactRow(ApiModel):
    account_id: str
    user_id: str
    display_name: str
    first_seen: VnDatetime
    last_seen: VnDatetime
    message_count: int


class ThreadUsageTotals(ApiModel):
    turns: int
    total_tokens: int


class DailyUsage(ApiModel):
    day: str = Field(description="YYYY-MM-DD in the requested time zone, not UTC.")
    turns: int
    input_tokens: int
    output_tokens: int


class AccountStats(ApiModel):
    """Counters of one account for the overview page (overview-stats.ts ``getAccountStats``)."""

    account_id: str
    threads: int = 0
    messages_today: int = 0
    turns_today: int = 0
    tokens_today: int = 0


class TraceStepRow(StepTrace):
    id: int
    turn_id: int
    created_at: VnDatetime


class HistoryStore(Protocol):
    async def append_message(
        self, clinic_id: UUID, account_id: str, thread_id: str, message: StoredMessage
    ) -> int:
        """Returns the new row id. Prunes the thread to ``HISTORY_MAX_MESSAGES_PER_THREAD``."""
        ...

    async def set_message_images(self, clinic_id: UUID, message_id: int, images: list[str]) -> None: ...

    async def get_recent_messages(
        self, clinic_id: UUID, account_id: str, thread_id: str, limit: int | None = None
    ) -> list[StoredMessage]:
        """Oldest first, the N newest."""
        ...

    async def list_messages_paged(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        *,
        limit: int = 50,
        before_id: int | None = None,
    ) -> list[StoredMessage]:
        """Keyset pagination by id (stable while new messages arrive)."""
        ...


class MemoryStore(Protocol):
    async def save_memory_fact(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        subject_id: str,
        content: str,
        learned_in_thread_id: str,
        learned_in_group: bool,
    ) -> SaveMemoryResult: ...

    async def get_memories_for_context(
        self, clinic_id: UUID, *, account_id: str, thread_id: str, sender_id: str, is_group: bool
    ) -> list[MemoryContextItem]:
        """Asymmetric rule: a fact learned in private never surfaces in a group."""
        ...

    async def list_memories(
        self,
        clinic_id: UUID,
        *,
        account_id: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[MemoryFact]: ...

    async def delete_memory_fact(self, clinic_id: UUID, account_id: str, fact_id: int) -> bool: ...


@dataclass(frozen=True)
class MemoryEditScope:
    """``PhamViSuaFact``: narrow exactly like the set the model can SEE. In a group, what is remembered
    about a PERSON can only be touched when it was learned in that group (``only_group_learned``)."""

    account_id: str
    subject_id: str
    only_group_learned: bool


@dataclass(frozen=True)
class MemoryEditOk:
    old_content: str
    """``noiDungCu``."""


@dataclass(frozen=True)
class MemoryEditFailed:
    kind: Literal["khong_khop", "khop_nhieu"]
    existing_facts: list[str] = field(default_factory=list[str])
    """``factHienCo``: for ``khong_khop``."""
    matching_facts: list[str] = field(default_factory=list[str])
    """``factKhop``: for ``khop_nhieu``."""


type MemoryEditResult = MemoryEditOk | MemoryEditFailed


class MemoryEditPort(Protocol):
    """``suaFactTheoDoanChu`` / ``xoaFactTheoDoanChu`` of ``memory-edit-store.ts``. Implemented by package D2
    (``PostgresConversationStore.memory_edits``), used by the ``save_memory`` tool (D4)."""

    async def edit_fact_by_fragment(
        self, clinic_id: UUID, scope: MemoryEditScope, fragment: str, new_content: str
    ) -> MemoryEditResult: ...

    async def delete_fact_by_fragment(
        self, clinic_id: UUID, scope: MemoryEditScope, fragment: str
    ) -> MemoryEditResult: ...


class ThreadStore(Protocol):
    async def record_thread_activity(
        self,
        clinic_id: UUID,
        *,
        account_id: str,
        thread_id: str,
        thread_type: int,
        display_name: str,
        sender_name: str,
    ) -> None: ...

    async def is_bot_enabled(self, clinic_id: UUID, account_id: str, thread_id: str) -> bool: ...

    async def set_bot_enabled(
        self, clinic_id: UUID, account_id: str, thread_id: str, enabled: bool
    ) -> bool: ...

    async def get_thread_summary(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadSummary: ...

    async def set_thread_summary(
        self, clinic_id: UUID, account_id: str, thread_id: str, summary: str, covers_to: int
    ) -> None: ...

    async def get_thread_context_epoch(self, clinic_id: UUID, account_id: str, thread_id: str) -> int:
        """Part of the router session key; bumped on every context wipe to open a fresh cache session."""
        ...

    async def list_threads(
        self,
        clinic_id: UUID,
        *,
        account_id: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[ThreadRow]: ...

    async def wipe_thread_context(self, clinic_id: UUID, account_id: str, thread_id: str) -> None:
        """``wipe-thread-context.ts``: history, summary and media of the thread; bumps context_epoch."""
        ...


class UsageStore(Protocol):
    async def open_agent_turn(
        self, clinic_id: UUID, account_id: str, thread_id: str, source: TurnSource = TurnSource.MESSAGE
    ) -> int:
        """Opens the row BEFORE the turn runs so a failed turn keeps an id and its trace."""
        ...

    async def finish_agent_turn(self, clinic_id: UUID, turn_id: int, usage: TokenUsage) -> None: ...

    async def append_step(self, clinic_id: UUID, turn_id: int, step: StepTrace) -> None: ...

    async def save_turn_trace(self, clinic_id: UUID, turn_id: int, steps: list[StepTrace]) -> None:
        """``saveTurnTrace``: INSERT of the whole trace of a turn, at most once per turn. Calling it twice
        would duplicate rows (and a second ``finish_agent_turn`` with fake zero usage would overwrite the real
        tokens), so callers keep a flag, exactly like the original processor."""
        ...

    async def get_thread_usage_totals(
        self, clinic_id: UUID, account_id: str, thread_id: str
    ) -> ThreadUsageTotals: ...

    async def get_account_stats(
        self, clinic_id: UUID, account_id: str, start_of_today_utc: str
    ) -> AccountStats:
        """ "Today" starts at ``start_of_today_utc`` (``start_of_day_utc(bot_time_zone())``)."""
        ...

    async def get_daily_usage(
        self, clinic_id: UUID, account_id: str, since_utc_iso: str, time_zone: str
    ) -> list[DailyUsage]:
        """Grouped by day IN ``time_zone`` (newest first), not by UTC day."""
        ...


class ContactStore(Protocol):
    async def record_contact_activity(
        self, clinic_id: UUID, account_id: str, user_id: str, display_name: str
    ) -> None: ...

    async def list_contacts(
        self,
        clinic_id: UUID,
        *,
        account_id: str | None = None,
        query: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[ContactRow]: ...

    async def delete_contact(self, clinic_id: UUID, account_id: str, user_id: str) -> bool: ...


class ImageDescriptionStore(Protocol):
    async def get_image_description(self, clinic_id: UUID, rel_path: str) -> str | None: ...

    async def save_image_description(
        self, clinic_id: UUID, rel_path: str, description: str, model: str
    ) -> None: ...


class ConversationStore(
    HistoryStore, MemoryStore, ThreadStore, UsageStore, ContactStore, ImageDescriptionStore, Protocol
):
    """Everything package D2 provides, as one object to inject. Fakes may implement a subset by
    implementing the sub-protocol a consumer actually needs."""

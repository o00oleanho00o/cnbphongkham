# ported from: none (test double of the engine's conversation store; ``appendMessage`` of history-store.ts)
"""``FakeConversation``: dict-based stand-in for the slice of ``ConversationStore`` the engine reads
(``agent_loop.EngineConversation``) plus the image-description cache. Import in tests only. Package D2 owns
the real stores; this keeps the D1 tests independent of them."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

from pema_contracts.agent_turn import TurnSource
from pema_contracts.common import now_vn
from pema_contracts.conversation import MemoryContextItem, StoredMessage, ThreadSummary


@dataclass
class FakeConversation:
    messages: dict[tuple[str, str], list[StoredMessage]] = field(
        default_factory=dict[tuple[str, str], list[StoredMessage]]
    )
    memories: list[MemoryContextItem] = field(default_factory=list[MemoryContextItem])
    summaries: dict[tuple[str, str], str] = field(default_factory=dict[tuple[str, str], str])
    epochs: dict[tuple[str, str], int] = field(default_factory=dict[tuple[str, str], int])
    opened_turns: list[tuple[str, str, TurnSource]] = field(default_factory=list[tuple[str, str, TurnSource]])
    descriptions: dict[str, str] = field(default_factory=dict[str, str])
    _next_id: int = 1

    def add_message(
        self,
        account_id: str,
        thread_id: str,
        *,
        role: Literal["user", "assistant"] = "user",
        content: str,
        sender_name: str | None = None,
        sender_id: str | None = None,
        images: list[str] | None = None,
    ) -> int:
        """The test-side ``appendMessage``: returns the new row id."""
        row = StoredMessage(
            id=self._next_id,
            role=role,
            content=content,
            sender_name=sender_name,
            sender_id=sender_id,
            images=images or [],
            created_at=now_vn(),
        )
        self._next_id += 1
        self.messages.setdefault((account_id, thread_id), []).append(row)
        return row.id or 0

    async def get_recent_messages(
        self, clinic_id: UUID, account_id: str, thread_id: str, limit: int | None = None
    ) -> list[StoredMessage]:
        rows = self.messages.get((account_id, thread_id), [])
        return list(rows if limit is None else rows[-limit:])

    async def get_memories_for_context(
        self, clinic_id: UUID, *, account_id: str, thread_id: str, sender_id: str, is_group: bool
    ) -> list[MemoryContextItem]:
        return list(self.memories)

    async def get_thread_summary(self, clinic_id: UUID, account_id: str, thread_id: str) -> ThreadSummary:
        return ThreadSummary(summary=self.summaries.get((account_id, thread_id), ""))

    async def get_thread_context_epoch(self, clinic_id: UUID, account_id: str, thread_id: str) -> int:
        return self.epochs.get((account_id, thread_id), 0)

    async def open_agent_turn(
        self,
        clinic_id: UUID,
        account_id: str,
        thread_id: str,
        source: TurnSource = TurnSource.MESSAGE,
    ) -> int:
        self.opened_turns.append((account_id, thread_id, source))
        return len(self.opened_turns)

    async def get_image_description(self, clinic_id: UUID, rel_path: str) -> str | None:
        return self.descriptions.get(rel_path)

    async def save_image_description(
        self, clinic_id: UUID, rel_path: str, description: str, model: str
    ) -> None:
        self.descriptions[rel_path] = description

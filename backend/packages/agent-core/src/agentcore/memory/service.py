"""Notes the agent keeps across sessions: its own (``agent``) and about the person it talks to (``user``).

Notes are short entries kept as one Markdown text per key, separated by a line holding only ``§`` (the format
of Hermes' MEMORY.md / USER.md), so a backend stores plain text and an export is a readable file. Each target
has a character cap; when it is full the agent has to merge or remove notes. Writes use a version check, so
two sessions writing at once never lose a note.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Literal, Protocol

MemoryTarget = Literal["agent", "user"]

ENTRY_SEPARATOR: Final = "\n§\n"
AGENT_NOTES_CHARS: Final = 2_200
USER_NOTES_CHARS: Final = 1_375
SAVE_ATTEMPTS: Final = 3
MATCHES_SHOWN: Final = 3


class MemoryEditError(ValueError):
    """A change the agent asked for cannot be made; the message tells it what to do instead."""


@dataclass(frozen=True, slots=True)
class MemoryKey:
    tenant_id: str
    agent: str
    target: MemoryTarget
    user_id: str = ""
    """Empty for the ``agent`` target."""


@dataclass(frozen=True, slots=True)
class StoredNotes:
    text: str = ""
    version: int = 0
    """0 when nothing was ever saved under the key."""


class MemoryBackend(Protocol):
    async def load(self, key: MemoryKey) -> StoredNotes: ...

    async def save(self, key: MemoryKey, text: str, expected_version: int) -> bool:
        """Store ``text`` as version ``expected_version + 1`` if the stored version is still
        ``expected_version``; False when another writer came first."""
        ...


class InMemoryMemoryBackend:
    def __init__(self) -> None:
        self._notes: dict[MemoryKey, StoredNotes] = {}

    async def load(self, key: MemoryKey) -> StoredNotes:
        return self._notes.get(key, StoredNotes())

    async def save(self, key: MemoryKey, text: str, expected_version: int) -> bool:
        if self._notes.get(key, StoredNotes()).version != expected_version:
            return False
        self._notes[key] = StoredNotes(text=text, version=expected_version + 1)
        return True


@dataclass(frozen=True, slots=True)
class MemoryLimits:
    agent_chars: int = AGENT_NOTES_CHARS
    user_chars: int = USER_NOTES_CHARS

    def __post_init__(self) -> None:
        if self.agent_chars < 1 or self.user_chars < 1:
            raise ValueError("memory limits must be positive")

    def of(self, target: MemoryTarget) -> int:
        return self.agent_chars if target == "agent" else self.user_chars


@dataclass(frozen=True, slots=True)
class MemoryChange:
    entries: tuple[str, ...]
    used: int
    limit: int
    changed: bool = True


@dataclass(frozen=True, slots=True)
class MemorySnapshot:
    agent_notes: tuple[str, ...]
    user_notes: tuple[str, ...]
    limits: MemoryLimits
    has_user: bool


class MemoryService:
    def __init__(self, backend: MemoryBackend, limits: MemoryLimits | None = None) -> None:
        self._backend = backend
        self.limits = limits or MemoryLimits()

    async def notes(self, key: MemoryKey) -> list[str]:
        return parse_entries((await self._backend.load(key)).text)

    async def snapshot(self, tenant_id: str, agent: str, user_id: str | None) -> MemorySnapshot:
        agent_notes = await self.notes(MemoryKey(tenant_id, agent, "agent"))
        user_notes = await self.notes(MemoryKey(tenant_id, agent, "user", user_id)) if user_id else []
        return MemorySnapshot(tuple(agent_notes), tuple(user_notes), self.limits, has_user=bool(user_id))

    async def add(self, key: MemoryKey, content: str) -> MemoryChange:
        note = _clean(content)

        def change(entries: list[str]) -> list[str] | None:
            return None if note in entries else [*entries, note]

        return await self._edit(key, change)

    async def replace(self, key: MemoryKey, old_text: str, content: str) -> MemoryChange:
        note = _clean(content)

        def change(entries: list[str]) -> list[str] | None:
            index = _only_match(entries, old_text)
            return [*entries[:index], note, *entries[index + 1 :]]

        return await self._edit(key, change)

    async def remove(self, key: MemoryKey, old_text: str) -> MemoryChange:
        def change(entries: list[str]) -> list[str] | None:
            index = _only_match(entries, old_text)
            return [*entries[:index], *entries[index + 1 :]]

        return await self._edit(key, change)

    async def _edit(self, key: MemoryKey, change: Callable[[list[str]], list[str] | None]) -> MemoryChange:
        """``change`` returns the new entries, or None when nothing changes."""
        limit = self.limits.of(key.target)
        for _ in range(SAVE_ATTEMPTS):
            stored = await self._backend.load(key)
            entries = parse_entries(stored.text)
            updated = change(entries)
            if updated is None:
                return MemoryChange(tuple(entries), _size(entries), limit, changed=False)
            used = _size(updated)
            if used > limit:
                raise MemoryEditError(
                    f"The {key.target} memory would use {used}/{limit} chars. Replace or remove older notes "
                    "first, or save something shorter."
                )
            if await self._backend.save(key, ENTRY_SEPARATOR.join(updated), stored.version):
                return MemoryChange(tuple(updated), used, limit)
        raise MemoryEditError("The memory is being changed by another conversation right now; try again.")


def parse_entries(text: str) -> list[str]:
    return [entry.strip() for entry in text.split(ENTRY_SEPARATOR) if entry.strip()]


def _size(entries: list[str]) -> int:
    return len(ENTRY_SEPARATOR.join(entries))


def _clean(content: str) -> str:
    note = content.strip()
    if not note:
        raise MemoryEditError("The note is empty.")
    if "§" in note:
        raise MemoryEditError("A note may not contain the character '§'.")
    return note


def _only_match(entries: list[str], old_text: str) -> int:
    needle = old_text.strip()
    if not needle:
        raise MemoryEditError("old_text is empty: give a part of the note to change.")
    matches = [i for i, entry in enumerate(entries) if needle in entry]
    if not matches:
        raise MemoryEditError(f"No note contains {needle!r}.")
    if len(matches) > 1:
        shown = "; ".join(repr(entries[i][:60]) for i in matches[:MATCHES_SHOWN])
        raise MemoryEditError(
            f"{len(matches)} notes contain {needle!r} ({shown}). Use a longer, unique part."
        )
    return matches[0]

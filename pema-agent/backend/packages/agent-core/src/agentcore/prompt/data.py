"""What session sections may read besides the agent's configuration: notes and the skills index.

Loaded once when the system prompt is built and frozen with it, so a note or skill saved during a session
shows up in the prompt of the next session (or after a compaction), never mid-session.
"""

from __future__ import annotations

from dataclasses import dataclass

from agentcore.memory.service import MemoryService
from agentcore.skills.library import SkillLibrary


@dataclass(frozen=True, slots=True)
class SkillEntry:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class SessionData:
    agent_notes: tuple[str, ...] = ()
    user_notes: tuple[str, ...] = ()
    agent_notes_limit: int = 0
    user_notes_limit: int = 0
    has_user: bool = False
    skills: tuple[SkillEntry, ...] = ()


async def load_session_data(
    *,
    memory: MemoryService | None,
    skills: SkillLibrary | None,
    tenant_id: str,
    agent: str,
    user_id: str | None,
) -> SessionData:
    agent_notes: tuple[str, ...] = ()
    user_notes: tuple[str, ...] = ()
    agent_limit = user_limit = 0
    if memory is not None:
        snapshot = await memory.snapshot(tenant_id, agent, user_id)
        agent_notes, user_notes = snapshot.agent_notes, snapshot.user_notes
        agent_limit, user_limit = snapshot.limits.agent_chars, snapshot.limits.user_chars
    entries: tuple[SkillEntry, ...] = ()
    if skills is not None:
        entries = tuple(SkillEntry(s.name, s.description) for s in await skills.list(tenant_id, agent))
    return SessionData(
        agent_notes=agent_notes,
        user_notes=user_notes,
        agent_notes_limit=agent_limit,
        user_notes_limit=user_limit,
        has_user=bool(user_id),
        skills=entries,
    )

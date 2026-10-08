"""A session store in process memory, for tests and the CLI. Lost when the process ends."""

from __future__ import annotations

from agentcore.messages import Message


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], list[Message]] = {}

    async def load(self, tenant_id: str, session_id: str) -> list[Message]:
        # Copies, so a caller that edits what it loaded cannot change the stored history.
        return [m.model_copy(deep=True) for m in self._sessions.get((tenant_id, session_id), [])]

    async def append(self, tenant_id: str, session_id: str, message: Message) -> None:
        self._sessions.setdefault((tenant_id, session_id), []).append(message.model_copy(deep=True))

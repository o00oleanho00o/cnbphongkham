"""A session store in process memory, for tests and the CLI. Lost when the process ends."""

from __future__ import annotations

from agentcore.harness.store.base import StoredPrompt
from agentcore.messages import Message


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[tuple[str, str], list[Message]] = {}
        self._prompts: dict[tuple[str, str], StoredPrompt] = {}

    async def load(self, tenant_id: str, session_id: str) -> list[Message]:
        # Copies, so a caller that edits what it loaded cannot change the stored history.
        return [m.model_copy(deep=True) for m in self._sessions.get((tenant_id, session_id), [])]

    async def append(self, tenant_id: str, session_id: str, message: Message) -> None:
        self._sessions.setdefault((tenant_id, session_id), []).append(message.model_copy(deep=True))

    async def load_prompt(self, tenant_id: str, session_id: str) -> StoredPrompt | None:
        saved = self._prompts.get((tenant_id, session_id))
        return saved.model_copy() if saved is not None else None

    async def save_prompt(self, tenant_id: str, session_id: str, prompt: StoredPrompt) -> None:
        self._prompts[(tenant_id, session_id)] = prompt.model_copy()

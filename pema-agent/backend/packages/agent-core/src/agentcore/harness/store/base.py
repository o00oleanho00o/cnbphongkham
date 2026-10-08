"""The port every session store implements."""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel

from agentcore.messages import Message


class StoredPrompt(BaseModel):
    """A session's frozen system prompt and the fingerprint of the configuration that produced it."""

    text: str
    fingerprint: str


class SessionStore(Protocol):
    async def load(self, tenant_id: str, session_id: str) -> list[Message]: ...

    async def append(self, tenant_id: str, session_id: str, message: Message) -> None: ...

    async def load_prompt(self, tenant_id: str, session_id: str) -> StoredPrompt | None: ...

    async def save_prompt(self, tenant_id: str, session_id: str, prompt: StoredPrompt) -> None: ...

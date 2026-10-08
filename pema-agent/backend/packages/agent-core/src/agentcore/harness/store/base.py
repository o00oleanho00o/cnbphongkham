"""The port every session store implements."""

from __future__ import annotations

from typing import Protocol

from agentcore.messages import Message


class SessionStore(Protocol):
    async def load(self, tenant_id: str, session_id: str) -> list[Message]: ...

    async def append(self, tenant_id: str, session_id: str, message: Message) -> None: ...

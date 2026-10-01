"""The narrow slice of Redis the middleware uses, as a Protocol, plus the adapter over ``redis.asyncio``.

New module (no TypeScript source): zalo-agent had no Redis. Keeping the surface this small has two reasons:
``redis-py`` has loosely typed async/sync union signatures that do not survive pyright strict, and a Protocol
lets a test substitute another implementation. Everything atomic is a Lua script run through ``eval`` (no
``WATCH`` loops), see ``redis_backends``.

The client must be created with ``decode_responses=True`` (``AsyncRedisOps.from_url`` does that).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, cast


class RedisOps(Protocol):
    async def eval(self, script: str, keys: Sequence[str], args: Sequence[str | int | float]) -> object: ...

    async def blmove(self, source: str, destination: str, timeout_seconds: float) -> str | None:
        """``BLMOVE source destination LEFT RIGHT timeout``."""
        ...

    async def get(self, key: str) -> str | None: ...

    async def hget(self, key: str, field: str) -> str | None: ...

    async def aclose(self) -> None: ...


class AsyncRedisOps:
    def __init__(self, client: Any) -> None:
        self._client = client
        self._scripts: dict[str, Any] = {}

    @classmethod
    def from_url(cls, url: str) -> AsyncRedisOps:
        from redis.asyncio import Redis  # local import: only the processes that use Redis load it

        return cls(Redis.from_url(url, decode_responses=True))  # pyright: ignore[reportUnknownMemberType]

    async def eval(self, script: str, keys: Sequence[str], args: Sequence[str | int | float]) -> object:
        registered = self._scripts.get(script)
        if registered is None:
            registered = self._client.register_script(script)
            self._scripts[script] = registered
        return cast(object, await registered(keys=list(keys), args=list(args)))

    async def blmove(self, source: str, destination: str, timeout_seconds: float) -> str | None:
        result = await self._client.blmove(source, destination, timeout_seconds, "LEFT", "RIGHT")
        return None if result is None else str(result)

    async def get(self, key: str) -> str | None:
        value = await self._client.get(key)
        return None if value is None else str(value)

    async def hget(self, key: str, field: str) -> str | None:
        value = await self._client.hget(key, field)
        return None if value is None else str(value)

    async def aclose(self) -> None:
        await self._client.aclose()

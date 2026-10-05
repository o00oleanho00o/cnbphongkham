"""The narrow slice of Redis the middleware uses, as a Protocol, plus the adapter over ``redis.asyncio``.

New module (no TypeScript source): zalo-agent had no Redis. Keeping the surface this small has two reasons:
``redis-py`` has loosely typed async/sync union signatures that do not survive pyright strict, and a Protocol
lets a test substitute another implementation. Everything atomic is a Lua script run through ``eval`` (no
``WATCH`` loops), see ``redis_backends``.

The client must be created with ``decode_responses=True`` (``AsyncRedisOps.from_url`` does that) and with a
read timeout LONGER than the longest blocking call: ``redis-py`` 8 defaults ``socket_timeout`` to 5 seconds,
which made a ``BLMOVE`` of 5 seconds (the idle poll of the turn worker) fail with ``TimeoutError`` every time
the queue was empty. ``make_redis_client`` is the one place that builds the client.
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


SOCKET_TIMEOUT_S = 60.0
"""Read timeout of the client: well above the blocking poll of the turn queue (5 s)."""


def make_redis_client(url: str) -> Any:
    from redis.asyncio import Redis  # local import: only the processes that use Redis load it

    return Redis.from_url(  # pyright: ignore[reportUnknownMemberType]
        url, decode_responses=True, socket_timeout=SOCKET_TIMEOUT_S, health_check_interval=30
    )


class AsyncRedisOps:
    def __init__(self, client: Any) -> None:
        self._client = client
        self._scripts: dict[str, Any] = {}

    @classmethod
    def from_url(cls, url: str) -> AsyncRedisOps:
        return cls(make_redis_client(url))

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

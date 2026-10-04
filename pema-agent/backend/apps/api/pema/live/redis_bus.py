"""Redis adapter of ``LiveEventBus``: one pub/sub channel per installation (ST-R).

New module (not a port). ``publish`` is a plain ``PUBLISH`` on the shared client; ``listen`` opens a pub/sub
connection of its own (one per process: the ``LiveHub`` fans out to the streams), subscribes, and
``get`` polls
it with a timeout so the hub can notice a shutdown. The client is created with ``decode_responses=True`` by
``make_redis_client``. Typed as ``Any`` for the same reason as ``redis_ops``: redis-py's async
signatures do not
survive pyright strict.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from pema.live.bus import BusListener, decode_event, encode_event
from pema_contracts.live import LiveEvent


class RedisLiveEventBus:
    def __init__(self, client: Any, channel: Callable[[], str]) -> None:
        self._client = client
        self._channel = channel
        """Resolved on every call: the clinic id is known only after start-up read the database."""

    async def publish(self, event: LiveEvent) -> None:
        await self._client.publish(self._channel(), encode_event(event))

    async def listen(self) -> BusListener:
        pubsub: Any = self._client.pubsub()
        try:
            await pubsub.subscribe(self._channel())
        except BaseException:
            await pubsub.aclose()
            raise
        return _RedisListener(pubsub)


class _RedisListener:
    def __init__(self, pubsub: Any) -> None:
        self._pubsub = pubsub

    async def get(self, wait_s: float) -> LiveEvent | None:
        """Frames that are not live events (and the subscribe confirmation, which redis-py reports as an
        empty read) are skipped without using up the wait."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait_s
        while (remaining := deadline - loop.time()) > 0:
            message: Any = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=remaining)
            if message is None:
                continue
            data: Any = message.get("data")
            event = decode_event(data) if isinstance(data, str) else None
            if event is not None:
                return event
        return None

    async def aclose(self) -> None:
        try:
            await self._pubsub.aclose()
        except Exception:  # closing a connection that is already gone
            return

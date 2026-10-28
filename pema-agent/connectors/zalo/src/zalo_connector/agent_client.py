"""This service as the agent sees it (docs/CONNECTOR-PROTOCOL.md, section 3): channel registration, and the
OUTBOX every message heard on Zalo goes through.

Nothing is lost because the agent is down or restarting: a message (or an observed event) is written to the
store FIRST, then pushed; a push that does not end in 200 is tried again, doubling the pause from 2 s up to
60 s; the entry is deleted only after the 200. The outbox survives a restart. Entries of one conversation go
out in the order they came (a failing head holds back the rest of that conversation, not the other chats).

* 404: the agent does not know the channel (its record was lost): register again, then retry.
* 401: the connector key is wrong or revoked: logged loudly on every attempt, the message is kept and retried
  at the slowest pace.
* ``typing`` is not kept: a "typing" that arrives a minute late is worth nothing, so it is sent once.

Registration is kept as wanted state (``set_channel`` / ``remove_channel``) and applied by the same loop, so
a channel registered while the agent is down is registered when it comes back.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Callable
from typing import Any, Final

import httpx

from .auth import sign
from .channels import InboundMessage, ObservedMessage
from .store import Store

PROTOCOL: Final = 1
OUTBOX: Final = "outbox:"
FIRST_RETRY_S: Final = 2.0
LAST_RETRY_S: Final = 60.0
IDLE_S: Final = 5.0
"""How long the loop sleeps when nothing woke it (a retry that comes due ends it earlier)."""
REQUEST_TIMEOUT_S: Final = 15.0
TYPING_TIMEOUT_S: Final = 5.0

logger = logging.getLogger(__name__)


def _retry_delay(attempts: int) -> float:
    return min(FIRST_RETRY_S * 2 ** max(attempts - 1, 0), LAST_RETRY_S)


class AgentClient:
    def __init__(
        self,
        store: Store,
        *,
        agent_url: str,
        callback_url: str,
        connector: str,
        key: str,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._base = f"{agent_url.rstrip('/')}/v1/hooks/connectors"
        self._callback_url = callback_url
        self._connector = connector
        self._key = key
        self._http = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S, transport=transport)
        self._clock = clock
        self._seq = 0
        self._wake = asyncio.Event()
        self._tasks: set[asyncio.Task[None]] = set()
        self._wanted: dict[str, dict[str, Any] | None] = {}
        """Channel name to the registration body it should have; None: it should not be registered."""
        self._applied: dict[str, dict[str, Any]] = {}
        self._register_failures = 0
        self._register_at = 0.0
        self._sleep_s = IDLE_S

    # --- registration ---

    def set_channel(
        self, name: str, *, rules: str = "", disabled_tools: list[str] | None = None, markdown: bool = False
    ) -> None:
        """The channel should be registered (or updated) with these settings."""
        body = {
            "protocol": PROTOCOL,
            "callback_url": self._callback_url,
            "max_text_chars": None,
            "markdown": markdown,
            "rules": rules,
            "disabled_tools": sorted(disabled_tools or []),
        }
        if self._wanted.get(name) != body:
            self._wanted[name] = body
            self._wake.set()

    def remove_channel(self, name: str) -> None:
        """The channel should not be registered (the account stopped or was deleted)."""
        if name in self._wanted or name in self._applied:
            self._wanted[name] = None
            self._wake.set()

    async def forget_channel(self, name: str) -> None:
        """The account is gone for good: its messages still in the outbox are dropped."""
        self.remove_channel(name)
        for key, entry in await self._store.list(OUTBOX):
            if entry.get("channel") == name:
                await self._store.delete(key)

    async def _register_all(self) -> None:
        if self._clock() < self._register_at:
            return
        failed = False
        for name, body in list(self._wanted.items()):
            if body is not None and self._applied.get(name) == body:
                continue
            if body is None and name not in self._applied:
                self._wanted.pop(name, None)
                continue
            try:
                response = await self._request(
                    "DELETE" if body is None else "PUT", f"/channels/{name}", b"" if body is None else _encode(body)
                )
            except httpx.HTTPError as err:
                logger.warning("channel %s not registered, the agent is unreachable (%s)", name, type(err).__name__)
                failed = True
                continue
            if response.status_code == 200 or (body is None and response.status_code == 404):
                if body is None:
                    self._applied.pop(name, None)
                    self._wanted.pop(name, None)
                else:
                    self._applied[name] = body
                    logger.info("channel %s registered with the agent", name)
                continue
            self._log_refusal(f"registering channel {name}", response)
            failed = True
        self._register_failures = self._register_failures + 1 if failed else 0
        if failed:
            self._register_at = self._clock() + _retry_delay(self._register_failures)

    # --- what the channels hand over ---

    async def inbound(self, message: InboundMessage) -> None:
        """A message to answer: kept first, pushed after."""
        if not message.message_id or not message.conversation_id or not message.user_id:
            logger.warning("channel %s handed over a message without ids; dropped", message.channel)
            return
        if not message.text.strip():
            return
        await self._enqueue(
            message.channel,
            message.conversation_id,
            "inbound",
            {
                "conversation_id": message.conversation_id,
                "user_id": message.user_id,
                "message_id": message.message_id,
                "text": message.text,
                "metadata": dict(message.metadata),
            },
        )

    async def observed(self, message: ObservedMessage) -> None:
        """A message the agent only watches: kept first, pushed after."""
        await self._enqueue(
            message.channel,
            message.conversation_id,
            "observed",
            {
                "conversation_id": message.conversation_id,
                "sender_id": message.sender_id,
                "message_id": message.message_id,
                "text": message.text,
                "origin": message.origin,
                "is_group": message.is_group,
                "sender_name": message.sender_name,
                "user_id": message.user_id,
                "answered": message.answered,
                "at": message.at.isoformat(),
                "metadata": dict(message.metadata),
            },
        )

    def typing(self, channel: str, conversation_id: str) -> None:
        """A person is typing: told once, in the background, never kept."""
        if not self._key:
            return
        task = asyncio.get_running_loop().create_task(self._typing(channel, conversation_id), name="typing")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _typing(self, channel: str, conversation_id: str) -> None:
        try:
            await self._request(
                "POST",
                f"/channels/{channel}/typing",
                _encode({"conversation_id": conversation_id}),
                timeout=TYPING_TIMEOUT_S,
            )
        except httpx.HTTPError as err:
            logger.debug("typing of %s not told (%s)", channel, type(err).__name__)

    async def _enqueue(self, channel: str, conversation_id: str, kind: str, body: dict[str, Any]) -> None:
        self._seq = max(self._seq + 1, time.time_ns())
        await self._store.put(
            f"{OUTBOX}{self._seq:020d}",
            {
                "kind": kind,
                "channel": channel,
                "conversation_id": conversation_id,
                "path": f"/channels/{channel}/{kind}",
                "body": body,
                "attempts": 0,
                "next_at": 0.0,
            },
        )
        self._wake.set()

    async def pending(self) -> int:
        return len(await self._store.list(OUTBOX))

    # --- the pusher ---

    async def run(self) -> None:
        """The loop of the service: register what is wanted, push what is kept, sleep until woken or due."""
        try:
            while True:
                try:
                    await self.step()
                except Exception as err:  # the next round tries again; nothing here may kill the loop
                    logger.error("the outbox round failed (%s)", type(err).__name__)
                await self._sleep()
        finally:
            await self._http.aclose()

    async def step(self) -> None:
        """One round: registrations, then every entry of the outbox that is due, oldest first."""
        if not self._key:
            return
        await self._register_all()
        blocked: set[tuple[str, str]] = set()
        soonest = IDLE_S + self._clock()
        for key, entry in await self._store.list(OUTBOX):
            conversation = (entry["channel"], entry["conversation_id"])
            if conversation in blocked:
                continue
            if entry["next_at"] > self._clock() or not await self._push(key, entry):
                blocked.add(conversation)
                soonest = min(soonest, entry["next_at"])
        self._sleep_s = max(0.05, soonest - self._clock())

    async def _push(self, key: str, entry: dict[str, Any]) -> bool:
        """True when the agent took the entry (and it is deleted)."""
        body = _encode(entry["body"])
        try:
            response = await self._request("POST", entry["path"], body)
            if response.status_code == 404 and entry["channel"] in self._wanted:
                # The agent lost the channel: register again, then this entry once more.
                self._applied.pop(entry["channel"], None)
                self._register_at = 0.0
                await self._register_all()
                response = await self._request("POST", entry["path"], body)
        except httpx.HTTPError as err:
            return await self._failed(key, entry, f"the agent is unreachable ({type(err).__name__})", warn=False)
        if response.status_code == 200:
            await self._store.delete(key)
            return True
        self._log_refusal(f"pushing {entry['kind']} of {entry['channel']}", response)
        return await self._failed(key, entry, f"HTTP {response.status_code}", warn=True)

    async def _failed(self, key: str, entry: dict[str, Any], why: str, *, warn: bool) -> bool:
        entry["attempts"] += 1
        pause = _retry_delay(entry["attempts"])
        entry["next_at"] = self._clock() + pause
        await self._store.put(key, entry)
        if warn or entry["attempts"] in (1, 5) or entry["attempts"] % 30 == 0:
            logger.warning(
                "%s of %s kept, %s; attempt %d, trying again in %.0f s",
                entry["kind"],
                entry["channel"],
                why,
                entry["attempts"],
                pause,
            )
        return False

    def _log_refusal(self, what: str, response: httpx.Response) -> None:
        if response.status_code == 401:
            logger.error(
                "THE AGENT REFUSES THE CONNECTOR KEY while %s (401): CONNECTOR_KEY is wrong or was revoked; "
                "nothing is lost, messages wait in the outbox",
                what,
            )

    async def _sleep(self) -> None:
        self._wake.clear()
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=self._sleep_s)
        except TimeoutError:
            return

    async def _request(
        self, method: str, suffix: str, body: bytes, *, timeout: float = REQUEST_TIMEOUT_S
    ) -> httpx.Response:
        url = f"{self._base}{suffix}"
        headers = sign(self._key, self._connector, method, httpx.URL(url).path, body, now=self._clock)
        if body:
            headers["Content-Type"] = "application/json"
        return await self._http.request(method, url, content=body or None, headers=headers, timeout=timeout)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self._http.aclose()


def _encode(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")

"""What the agent calls (docs/CONNECTOR-PROTOCOL.md, section 4): ``POST /send``, ``POST /typing``,
``GET /health``. Every call is signed with the connector key; a missing or wrong signature is a 401 that says
nothing more.

``/send`` gets the WHOLE reply and answers as soon as the reply is ACCEPTED, not sent: the channel's
``prepare`` runs at once (markdown stripped when the channel cannot show it; a reply that leaks the system
prompt is refused with 422), then the reply is ``split_reply``-ed at the platform's limit and written to the
store as one send job, and ``/send`` answers 200. The job's parts go out in the background, a random pause
(``PART_PAUSE_MIN_S``..``MAX_S``) between two parts, one conversation in order, retried with growing pauses
when the platform fails. So the pacing never runs into the agent's wait for ``/send``, however long a reply.
The same ``delivery_id`` twice is accepted once (the record is kept for a day).
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from typing import Any, Final

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .auth import verify
from .channels import ChannelSendError, OutboundMessage, split_reply
from .config import Config
from .service import ZaloService
from .store import Store

DELIVERY: Final = "delivery:"
"""``delivery:<delivery_id>``: the reply was accepted (dedupe), kept a day."""
JOB: Final = "sendjob:"
"""``sendjob:<seq>``: the parts of an accepted reply still to send, oldest first."""
KEEP_DELIVERY_S: Final = 24 * 3600.0
RETRY_S: Final = (2.0, 10.0, 60.0, 300.0)
MAX_ATTEMPTS: Final = 8
"""A part the platform keeps failing is given up after this many tries (about half an hour); logged."""
NOT_RUNNING_RETRY_S: Final = 30.0
IDLE_S: Final = 5.0

logger = logging.getLogger(__name__)


class SendBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    delivery_id: str = Field(min_length=1, max_length=200)
    channel: str = Field(min_length=1, max_length=64)
    conversation_id: str = Field(min_length=1, max_length=200)
    user_id: str | None = None
    reply_to: str | None = None
    text: str
    metadata: dict[str, str] = Field(default_factory=dict[str, str])


class TypingBody(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channel: str = Field(min_length=1, max_length=64)
    conversation_id: str = Field(min_length=1, max_length=200)
    metadata: dict[str, str] = Field(default_factory=dict[str, str])


def failure(status_code: int, message: str, *, retryable: bool, retry_after_s: float | None = None) -> JSONResponse:
    """The error body of ``/send``."""
    return JSONResponse(
        {"error": message, "retryable": retryable, "retry_after_s": retry_after_s}, status_code=status_code
    )


class Sender:
    def __init__(
        self,
        config: Config,
        service: ZaloService,
        store: Store,
        *,
        sleep: Callable[[float], Any] = asyncio.sleep,
        rand: Callable[[float, float], float] = random.uniform,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._config = config
        self._service = service
        self._store = store
        self._sleep = sleep
        self._rand = rand
        self._clock = clock
        self._locks: dict[str, asyncio.Lock] = {}
        self._seq = 0
        self._wake = asyncio.Event()
        self._sleep_s = IDLE_S

    async def send(self, body: SendBody) -> JSONResponse:
        exists, channel = self._service.channel_state(body.channel)
        if not exists:
            return failure(422, "no such account", retryable=False)
        if channel is None:
            return failure(503, "the channel is not running", retryable=True)
        lock = self._locks.setdefault(body.delivery_id, asyncio.Lock())
        try:
            async with lock:
                record = await self._store.get(DELIVERY + body.delivery_id)
                if record is not None:
                    return JSONResponse({"sent": record["parts"]})
                prepared = channel.prepare(body.text)
                if prepared is None:
                    return failure(422, "the channel refused the reply", retryable=False)
                parts = split_reply(prepared, channel.capabilities.max_text_chars)
                self._seq = max(self._seq + 1, time.time_ns())
                job = {
                    "delivery_id": body.delivery_id,
                    "channel": body.channel,
                    "conversation_id": body.conversation_id,
                    "user_id": body.user_id,
                    "reply_to": body.reply_to,
                    "metadata": body.metadata,
                    "parts": parts,
                    "sent": 0,
                    "attempts": 0,
                    "next_at": 0.0,
                }
                accepted: list[tuple[str, Any]] = [
                    (DELIVERY + body.delivery_id, {"at": self._clock(), "parts": len(parts)})
                ]
                if parts:
                    accepted.append((f"{JOB}{self._seq:020d}", job))
                await self._store.put_many(accepted)
        finally:
            if not lock.locked():
                self._locks.pop(body.delivery_id, None)
        self._wake.set()
        return JSONResponse({"sent": len(parts)})

    async def run(self) -> None:
        """The background sender: every round, the due part of each conversation's oldest job."""
        while True:
            self._wake.clear()
            try:
                await self.step()
            except Exception as err:  # the next round tries again; nothing here may kill the loop
                logger.error("the send round failed (%s)", type(err).__name__)
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=self._sleep_s)
            except TimeoutError:
                pass

    async def step(self) -> None:
        now = self._clock()
        soonest = now + IDLE_S
        busy: set[tuple[str, str]] = set()
        for key, job in await self._store.list(JOB):
            conversation = (job["channel"], job["conversation_id"])
            if conversation in busy:
                continue
            busy.add(conversation)  # later replies of this conversation wait for this one
            if job["next_at"] <= now:
                await self._send_part(key, job)
            soonest = min(soonest, job["next_at"]) if job["next_at"] > now else soonest
        self._sleep_s = max(0.05, soonest - self._clock())

    async def _send_part(self, key: str, job: dict[str, Any]) -> None:
        exists, channel = self._service.channel_state(job["channel"])
        if not exists:
            logger.warning("reply %s dropped: the account %s is gone", job["delivery_id"], job["channel"])
            await self._store.delete(key)
            return
        if channel is None:
            job["next_at"] = self._clock() + NOT_RUNNING_RETRY_S
            await self._store.put(key, job)
            return
        index, parts = job["sent"], job["parts"]
        message = OutboundMessage(
            conversation_id=job["conversation_id"],
            text=parts[index],
            user_id=job["user_id"],
            reply_to=job["reply_to"],
            part=index + 1,
            parts=len(parts),
            metadata=job["metadata"],
        )
        try:
            await channel.send(message)
        except ChannelSendError as err:
            if not err.retryable:
                logger.warning("reply %s part %d refused for good: %s", job["delivery_id"], index + 1, err)
                await self._store.delete(key)
                return
            await self._retry(key, job, str(err), err.retry_after_s)
            return
        except Exception as err:  # a channel bug is retried like a network error
            await self._retry(key, job, type(err).__name__, None)
            return
        job["sent"], job["attempts"] = index + 1, 0
        if job["sent"] >= len(parts):
            await self._store.delete(key)
            self._wake.set()  # the next reply of this conversation may go now
            return
        low, high = self._config.part_pause_s
        job["next_at"] = self._clock() + self._rand(low, high)
        await self._store.put(key, job)

    async def _retry(self, key: str, job: dict[str, Any], why: str, after_s: float | None) -> None:
        job["attempts"] += 1
        if job["attempts"] >= MAX_ATTEMPTS:
            logger.error(
                "reply %s given up at part %d after %d tries: %s",
                job["delivery_id"],
                job["sent"] + 1,
                job["attempts"],
                why,
            )
            await self._store.delete(key)
            return
        pause = after_s if after_s is not None else RETRY_S[min(job["attempts"], len(RETRY_S)) - 1]
        logger.warning("reply %s part %d not sent (%s); again in %.0f s", job["delivery_id"], job["sent"] + 1, why, pause)
        job["next_at"] = self._clock() + pause
        await self._store.put(key, job)

    async def typing(self, body: TypingBody) -> None:
        """Lets the person see the account typing; a failure is the agent's to ignore, so it is ours too."""
        _, channel = self._service.channel_state(body.channel)
        if channel is None:
            return
        try:
            await channel.typing(body.conversation_id, body.metadata)
        except Exception as err:
            logger.debug("typing on %s failed (%s)", body.channel, type(err).__name__)

    async def prune(self) -> int:
        """Forgets the deliveries older than a day; how many went."""
        gone = 0
        cutoff = self._clock() - KEEP_DELIVERY_S
        for key, record in await self._store.list(DELIVERY):
            if isinstance(record, dict) and record.get("at", 0) < cutoff:
                gone += await self._store.delete(key)
        return gone


def callback_router(config: Config, sender: Sender) -> APIRouter:
    router = APIRouter()

    async def signed(request: Request) -> bytes:
        body = await request.body()
        if not verify(
            config.connector_key, config.connector_name, request.headers, request.method, request.url.path, body
        ):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unauthorized")
        return body

    @router.get("/health")
    async def health(_: bytes = Depends(signed)) -> dict[str, Any]:
        return {}

    @router.post("/send")
    async def send(body: bytes = Depends(signed)) -> Response:
        try:
            parsed = SendBody.model_validate_json(body)
        except ValidationError:
            return failure(422, "the body is not a send request", retryable=False)
        return await sender.send(parsed)

    @router.post("/typing")
    async def typing(body: bytes = Depends(signed)) -> dict[str, Any]:
        try:
            await sender.typing(TypingBody.model_validate_json(body))
        except ValidationError:
            pass
        return {}

    return router


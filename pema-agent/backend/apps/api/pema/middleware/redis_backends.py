"""Redis implementations of the cross-process seams of the inbound path (CONTRACTS section 4).

New module (no TypeScript source). zalo-agent ran the batcher, the thread lock and the turn in ONE process, so
it needed none of this; Pema runs the batcher in the API process and the turn in the worker (CONTRACTS
decision 6), and the two meet only through Redis:

* ``RedisPendingBatchStore``  the messages waiting in the batcher (``PendingBatchStore``), also read by the
  worker through ``StorePendingInbox`` (``PendingInbox``);
* ``RedisThreadRunChain``     the thread lock (``ThreadLock`` through ``ClinicThreadLock``) and the "is this
  thread busy / since when" view the batcher and the busy-wait notice use (``ThreadBusy``);
* ``RedisTurnQueue``          ``TurnQueue``: a reliable list queue (``BLMOVE`` to a processing list,
  visibility timeout, ``reclaim_expired``). A thread counts as busy from ``enqueue`` until ``ack``/final
  ``nack``, so a batch that follows a just-enqueued job parks instead of becoming a second turn.

Atomicity is Lua (``eval``), never read-then-write. Every key carries a TTL so a crashed process cannot keep a
thread busy or a batch alive forever. Message bodies are JSON of ``InboundMessage``: they are patient text, so
Redis must not be exposed outside the clinic network (infra concern, package F).
"""

from __future__ import annotations

import asyncio
import contextlib
import random
import time
import uuid
from typing import cast
from uuid import UUID

from pema.middleware.message_batcher import AppendOutcome, PendingBatch
from pema.middleware.redis_ops import RedisOps
from pema.middleware.thread_run_chain import FreeHook, ThreadRef
from pema.shared.logger import create_logger
from pema_contracts.agent_turn import ThreadLockHandle, TurnJob
from pema_contracts.channel import InboundMessage

_log = create_logger("redis-backends")

NAMESPACE = "pema"
KEY_TTL_MS = 60 * 60 * 1000
"""Every state key expires after an hour without a write: orphans of a crashed process vanish."""
LOCK_TTL_MS = 60_000
"""A held thread lock expires after one minute without a heartbeat (a heartbeat runs every third of it)."""
LOCK_POLL_MS = 50

# ---------------------------------------------------------------------------------------------- batch store

_APPEND = """
-- KEYS: msgs, meta, thread set, all set
-- ARGV: cap, message json, deadline, thread_key, sender, member, now, ttl
local n = redis.call('LLEN', KEYS[1])
if n > 0 and n >= tonumber(ARGV[1]) then
  return {0, redis.call('HINCRBY', KEYS[2], 'dropped', 1)}
end
redis.call('RPUSH', KEYS[1], ARGV[2])
redis.call('HSET', KEYS[2], 'thread_key', ARGV[4], 'sender', ARGV[5], 'deadline', ARGV[3])
redis.call('HSETNX', KEYS[2], 'dropped', 0)
redis.call('ZADD', KEYS[3], 'NX', ARGV[7], ARGV[6])
redis.call('ZADD', KEYS[4], 'NX', ARGV[7], ARGV[6])
redis.call('PEXPIRE', KEYS[1], ARGV[8])
redis.call('PEXPIRE', KEYS[2], ARGV[8])
return {1, tonumber(redis.call('HGET', KEYS[2], 'dropped'))}
"""

_READ = """
-- KEYS: msgs, meta, thread set, all set; ARGV: member, remove (1/0), only_if_parked (1/0)
local msgs = redis.call('LRANGE', KEYS[1], 0, -1)
if #msgs == 0 then return false end
if ARGV[3] == '1' then
  local d = redis.call('HGET', KEYS[2], 'deadline')
  if d and d ~= '' then return false end
end
local meta = redis.call('HGETALL', KEYS[2])
if ARGV[2] == '1' then
  redis.call('DEL', KEYS[1], KEYS[2])
  redis.call('ZREM', KEYS[3], ARGV[1])
  redis.call('ZREM', KEYS[4], ARGV[1])
end
return {msgs, meta}
"""

_PARK = """
-- KEYS: msgs, meta
if redis.call('EXISTS', KEYS[1]) == 1 then redis.call('HSET', KEYS[2], 'deadline', '') end
return 1
"""

_LIST = """
-- KEYS: zset of members; ARGV: msgs prefix, meta prefix, remove (1/0), thread set prefix, all set
local out = {}
for _, member in ipairs(redis.call('ZRANGE', KEYS[1], 0, -1)) do
  local msgs = redis.call('LRANGE', ARGV[1] .. member, 0, -1)
  if #msgs > 0 then
    local meta = redis.call('HGETALL', ARGV[2] .. member)
    table.insert(out, {msgs, meta})
    if ARGV[3] == '1' then
      redis.call('DEL', ARGV[1] .. member, ARGV[2] .. member)
      redis.call('ZREM', ARGV[5], member)
      redis.call('ZREM', KEYS[1], member)
    end
  else
    redis.call('ZREM', KEYS[1], member)
  end
end
return out
"""

_CLEAR = """
-- KEYS: all set; ARGV: msgs prefix, meta prefix, thread set prefix
for _, member in ipairs(redis.call('ZRANGE', KEYS[1], 0, -1)) do
  local tk = redis.call('HGET', ARGV[2] .. member, 'thread_key')
  redis.call('DEL', ARGV[1] .. member, ARGV[2] .. member)
  if tk then redis.call('ZREM', ARGV[3] .. tk, member) end
end
redis.call('DEL', KEYS[1])
return 1
"""


def _as_list(value: object) -> list[object]:
    return cast(list[object], value) if isinstance(value, list) else []


def _parse_batches(raw: object) -> list[PendingBatch]:
    batches: list[PendingBatch] = []
    for item in _as_list(raw):
        pair = _as_list(item)
        if len(pair) != 2:
            continue
        messages = [InboundMessage.model_validate_json(str(m)) for m in _as_list(pair[0])]
        flat = [str(x) for x in _as_list(pair[1])]
        meta = dict(zip(flat[0::2], flat[1::2], strict=False))
        deadline = meta.get("deadline", "")
        batches.append(
            PendingBatch(
                thread_key=meta.get("thread_key", ""),
                sender_id=meta.get("sender", ""),
                messages=messages,
                deadline_ms=float(deadline) if deadline else None,
                dropped=int(meta.get("dropped", "0")),
            )
        )
    return batches


class RedisPendingBatchStore:
    def __init__(self, ops: RedisOps, *, namespace: str = NAMESPACE) -> None:
        self._ops = ops
        self._p = f"{namespace}:pb:"

    @staticmethod
    def _member(thread_key: str, sender_id: str) -> str:
        return f"{thread_key}#{sender_id}"

    def _keys(self, thread_key: str, sender_id: str) -> list[str]:
        member = self._member(thread_key, sender_id)
        return [
            f"{self._p}msgs:{member}",
            f"{self._p}meta:{member}",
            f"{self._p}thr:{thread_key}",
            f"{self._p}all",
        ]

    async def append(
        self, thread_key: str, sender_id: str, message: InboundMessage, deadline_ms: float, cap: int
    ) -> AppendOutcome:
        raw = await self._ops.eval(
            _APPEND,
            self._keys(thread_key, sender_id),
            [
                cap,
                message.model_dump_json(),
                repr(deadline_ms),
                thread_key,
                sender_id,
                self._member(thread_key, sender_id),
                repr(time.time() * 1000),
                KEY_TTL_MS,
            ],
        )
        result = _as_list(raw)
        return AppendOutcome(accepted=int(cast(int, result[0])) == 1, dropped=int(cast(int, result[1])))

    async def _read(
        self, thread_key: str, sender_id: str, *, remove: bool, only_if_parked: bool
    ) -> PendingBatch | None:
        raw = await self._ops.eval(
            _READ,
            self._keys(thread_key, sender_id),
            [self._member(thread_key, sender_id), "1" if remove else "0", "1" if only_if_parked else "0"],
        )
        if not raw:
            return None
        parsed = _parse_batches([raw])
        return parsed[0] if parsed else None

    async def get(self, thread_key: str, sender_id: str) -> PendingBatch | None:
        return await self._read(thread_key, sender_id, remove=False, only_if_parked=False)

    async def mark_parked(self, thread_key: str, sender_id: str) -> None:
        keys = self._keys(thread_key, sender_id)
        await self._ops.eval(_PARK, keys[:2], [])

    async def pop(
        self, thread_key: str, sender_id: str, *, only_if_parked: bool = False
    ) -> PendingBatch | None:
        return await self._read(thread_key, sender_id, remove=True, only_if_parked=only_if_parked)

    async def list_for_thread(self, thread_key: str) -> list[PendingBatch]:
        raw = await self._ops.eval(
            _LIST, [f"{self._p}thr:{thread_key}"], [f"{self._p}msgs:", f"{self._p}meta:", "0", "", ""]
        )
        return _parse_batches(raw)

    async def remove_thread(self, thread_key: str) -> list[PendingBatch]:
        raw = await self._ops.eval(
            _LIST,
            [f"{self._p}thr:{thread_key}"],
            [f"{self._p}msgs:", f"{self._p}meta:", "1", "", f"{self._p}all"],
        )
        return _parse_batches(raw)

    async def list_all(self) -> list[PendingBatch]:
        raw = await self._ops.eval(
            _LIST, [f"{self._p}all"], [f"{self._p}msgs:", f"{self._p}meta:", "0", "", ""]
        )
        return _parse_batches(raw)

    async def list_parked_thread_keys(self) -> list[str]:
        return sorted({b.thread_key for b in await self.list_all() if b.deadline_ms is None})

    async def count(self) -> int:
        return len(await self.list_all())

    async def clear(self) -> None:
        await self._ops.eval(
            _CLEAR, [f"{self._p}all"], [f"{self._p}msgs:", f"{self._p}meta:", f"{self._p}thr:"]
        )


# ------------------------------------------------------------------------------------------ thread lock/busy

_ACQUIRE = """
-- KEYS: lock, since; ARGV: token, ttl, now, since ttl
if redis.call('SET', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2]) then
  redis.call('SET', KEYS[2], ARGV[3], 'NX', 'PX', ARGV[4])
  return 1
end
return 0
"""

_EXTEND = """
-- KEYS: lock, since; ARGV: token, ttl, since ttl
if redis.call('GET', KEYS[1]) == ARGV[1] then
  redis.call('PEXPIRE', KEYS[1], ARGV[2])
  redis.call('PEXPIRE', KEYS[2], ARGV[3])
  return 1
end
return 0
"""

_RELEASE = """
-- KEYS: lock, since, jobs; ARGV: token
if redis.call('GET', KEYS[1]) == ARGV[1] then redis.call('DEL', KEYS[1]) end
local jobs = tonumber(redis.call('GET', KEYS[3]) or '0')
if redis.call('EXISTS', KEYS[1]) == 0 and jobs <= 0 then
  redis.call('DEL', KEYS[2])
  return 1
end
return 0
"""

_IS_BUSY = """
-- KEYS: lock, jobs
if redis.call('EXISTS', KEYS[1]) == 1 then return 1 end
if tonumber(redis.call('GET', KEYS[2]) or '0') > 0 then return 1 end
return 0
"""


class RedisThreadRunChain:
    """The thread lock and the busy view over Redis (``ThreadBusy`` + ``HoldsThreadKey``).

    A thread is busy while its lock is held OR turn jobs are queued/in flight for it (``RedisTurnQueue`` keeps
    the job counter). ``busy_for_ms`` measures from when it first became busy, like the original (same known
    limit, see ``thread_run_chain``). Cross-process "became free" events are not pushed: the batcher polls
    (``PARKED_RECHECK_MS``); hooks fire only for releases made by THIS process."""

    def __init__(
        self,
        ops: RedisOps,
        *,
        namespace: str = NAMESPACE,
        lock_ttl_ms: int = LOCK_TTL_MS,
        poll_ms: int = LOCK_POLL_MS,
    ) -> None:
        self._ops = ops
        self._p = f"{namespace}:th:"
        self.lock_ttl_ms = lock_ttl_ms
        self.poll_ms = poll_ms
        self._free_hooks: list[FreeHook] = []
        self.local_holds = 0

    def lock_key(self, thread_key: str) -> str:
        return f"{self._p}lock:{thread_key}"

    def since_key(self, thread_key: str) -> str:
        return f"{self._p}since:{thread_key}"

    def jobs_key(self, thread_key: str) -> str:
        return f"{self._p}jobs:{thread_key}"

    # ThreadBusy -----------------------------------------------------------------------------------
    def on_thread_free(self, fn: FreeHook) -> None:
        self._free_hooks.append(fn)

    async def is_busy(self, thread_key: str) -> bool:
        raw = await self._ops.eval(_IS_BUSY, [self.lock_key(thread_key), self.jobs_key(thread_key)], [])
        return int(cast(int, raw)) == 1

    async def busy_for_ms(self, thread_key: str) -> int | None:
        if not await self.is_busy(thread_key):
            return None
        since = await self._ops.get(self.since_key(thread_key))
        return None if since is None else max(0, int(time.time() * 1000 - float(since)))

    def active_count(self) -> int:
        return self.local_holds

    def fire_free(self, thread_key: str) -> None:
        for hook in list(self._free_hooks):
            try:
                hook(thread_key)
            except Exception as exc:
                _log.error("Hook thread rảnh ném lỗi", err=exc)

    # lock -----------------------------------------------------------------------------------------
    def hold_key(self, thread_key: str) -> ThreadLockHandle:
        return _RedisHold(self, thread_key)

    async def try_acquire(self, thread_key: str, token: str) -> bool:
        raw = await self._ops.eval(
            _ACQUIRE,
            [self.lock_key(thread_key), self.since_key(thread_key)],
            [token, self.lock_ttl_ms, repr(time.time() * 1000), KEY_TTL_MS],
        )
        return int(cast(int, raw)) == 1

    async def extend(self, thread_key: str, token: str) -> bool:
        raw = await self._ops.eval(
            _EXTEND,
            [self.lock_key(thread_key), self.since_key(thread_key)],
            [token, self.lock_ttl_ms, KEY_TTL_MS],
        )
        return int(cast(int, raw)) == 1

    async def release(self, thread_key: str, token: str) -> bool:
        raw = await self._ops.eval(
            _RELEASE,
            [self.lock_key(thread_key), self.since_key(thread_key), self.jobs_key(thread_key)],
            [token],
        )
        return int(cast(int, raw)) == 1


class _RedisHold:
    def __init__(self, chain: RedisThreadRunChain, thread_key: str) -> None:
        self._chain = chain
        self._key = thread_key
        self._token = uuid.uuid4().hex
        self._heartbeat: asyncio.Task[None] | None = None

    async def __aenter__(self) -> None:
        chain = self._chain
        # Wait for the previous holder (turns of one thread are serial). A small random jitter keeps several
        # waiters from polling in step.
        while not await chain.try_acquire(self._key, self._token):  # noqa: ASYNC110
            await asyncio.sleep((chain.poll_ms + random.randint(0, chain.poll_ms)) / 1000)  # noqa: S311
        chain.local_holds += 1
        self._heartbeat = asyncio.ensure_future(self._beat())

    async def _beat(self) -> None:
        interval = self._chain.lock_ttl_ms / 3000
        try:
            while True:
                await asyncio.sleep(interval)
                if not await self._chain.extend(self._key, self._token):
                    _log.error("Mất khóa thread giữa chừng (hết hạn hoặc bị lấy)")
                    return
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            _log.error("Gia hạn khóa thread thất bại", err=exc)

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self._heartbeat is not None:
            self._heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._heartbeat
            self._heartbeat = None
        self._chain.local_holds -= 1
        await self._chain.release(self._key, self._token)
        # Fire for every release, free or not (see thread_run_chain: one extra fire beats a missed one).
        self._chain.fire_free(self._key)


# --------------------------------------------------------------------------------------------- turn queue

_ENQUEUE = """
-- KEYS: pending, jobs, since; ARGV: job json, now, ttl
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('INCR', KEYS[2])
redis.call('PEXPIRE', KEYS[2], ARGV[3])
redis.call('SET', KEYS[3], ARGV[2], 'NX', 'PX', ARGV[3])
return 1
"""

_CLAIMED = """
-- KEYS: inflight, inflight thread keys, claimed zset, jobs; ARGV: job id, raw, thread_key, now_ms, ttl
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
redis.call('HSET', KEYS[2], ARGV[1], ARGV[3])
redis.call('ZADD', KEYS[3], ARGV[4], ARGV[1])
redis.call('PEXPIRE', KEYS[4], ARGV[5])
return 1
"""

_FINISH = """
-- KEYS: processing, inflight, inflight thread keys, claimed zset, pending; ARGV: job id, jobs prefix,
-- since prefix, lock prefix, mode (done|retry), retry json
local raw = redis.call('HGET', KEYS[2], ARGV[1])
if not raw then return {0, ''} end
local tk = redis.call('HGET', KEYS[3], ARGV[1])
redis.call('LREM', KEYS[1], 1, raw)
redis.call('HDEL', KEYS[2], ARGV[1])
redis.call('HDEL', KEYS[3], ARGV[1])
redis.call('ZREM', KEYS[4], ARGV[1])
if ARGV[5] == 'retry' then
  redis.call('RPUSH', KEYS[5], ARGV[6])
  return {1, tk or ''}
end
if not tk then return {1, ''} end
local jobs_key = ARGV[2] .. tk
local jobs = redis.call('DECR', jobs_key)
if jobs <= 0 then
  redis.call('DEL', jobs_key)
  if redis.call('EXISTS', ARGV[4] .. tk) == 0 then redis.call('DEL', ARGV[3] .. tk) end
  return {2, tk}
end
return {1, tk}
"""

_RECLAIM = """
-- KEYS: processing, inflight, inflight thread keys, claimed zset, pending; ARGV: cutoff ms
local ids = redis.call('ZRANGEBYSCORE', KEYS[4], '-inf', ARGV[1])
local n = 0
for _, id in ipairs(ids) do
  local raw = redis.call('HGET', KEYS[2], id)
  if raw then
    redis.call('LREM', KEYS[1], 1, raw)
    redis.call('RPUSH', KEYS[5], raw)
    n = n + 1
  end
  redis.call('HDEL', KEYS[2], id)
  redis.call('HDEL', KEYS[3], id)
  redis.call('ZREM', KEYS[4], id)
end
return n
"""


class RedisTurnQueue:
    """``pema_contracts.agent_turn.TurnQueue`` over Redis lists. At-least-once: a worker that dies after
    ``claim`` leaves the job in the processing list; ``reclaim_expired`` (run it from the worker loop) puts
    jobs older than the visibility timeout back. A worker must therefore be idempotent per ``job_id``."""

    def __init__(
        self,
        ops: RedisOps,
        chain: RedisThreadRunChain,
        *,
        namespace: str = NAMESPACE,
        visibility_timeout_ms: int = 20 * 60 * 1000,
    ) -> None:
        self._ops = ops
        self._chain = chain
        p = f"{namespace}:tq:"
        self._pending = f"{p}pending"
        self._processing = f"{p}processing"
        self._inflight = f"{p}inflight"
        self._inflight_threads = f"{p}inflight-thread"
        self._claimed = f"{p}claimed"
        self._visibility_timeout_ms = visibility_timeout_ms

    @staticmethod
    def _thread_key(job: TurnJob) -> str:
        return ThreadRef(job.clinic_id, job.account_id, job.thread_id).key

    async def enqueue(self, job: TurnJob) -> None:
        await self._ops.eval(
            _ENQUEUE,
            [
                self._pending,
                self._chain.jobs_key(self._thread_key(job)),
                self._chain.since_key(self._thread_key(job)),
            ],
            [job.model_dump_json(), repr(time.time() * 1000), KEY_TTL_MS],
        )

    async def claim(self, block_seconds: float) -> TurnJob | None:
        raw = await self._ops.blmove(self._pending, self._processing, max(block_seconds, 0.01))
        if raw is None:
            return None
        job = TurnJob.model_validate_json(raw)
        thread_key = self._thread_key(job)
        await self._ops.eval(
            _CLAIMED,
            [self._inflight, self._inflight_threads, self._claimed, self._chain.jobs_key(thread_key)],
            [str(job.job_id), raw, thread_key, int(time.time() * 1000), KEY_TTL_MS],
        )
        return job

    async def _finish(self, job_id: UUID, *, retry_json: str | None) -> None:
        raw = await self._ops.eval(
            _FINISH,
            [self._processing, self._inflight, self._inflight_threads, self._claimed, self._pending],
            [
                str(job_id),
                self._chain.jobs_key(""),
                self._chain.since_key(""),
                self._chain.lock_key(""),
                "retry" if retry_json is not None else "done",
                retry_json or "",
            ],
        )
        result = _as_list(raw)
        if len(result) == 2 and int(cast(int, result[0])) == 2:
            self._chain.fire_free(str(result[1]))

    async def ack(self, job_id: UUID) -> None:
        await self._finish(job_id, retry_json=None)

    async def nack(self, job_id: UUID, *, retry: bool) -> None:
        if not retry:
            await self._finish(job_id, retry_json=None)
            return
        raw = await self._ops.hget(self._inflight, str(job_id))
        if raw is None:
            return
        job = TurnJob.model_validate_json(raw)
        again = job.model_copy(update={"attempt": job.attempt + 1})
        await self._finish(job_id, retry_json=again.model_dump_json())

    async def reclaim_expired(self) -> int:
        """Put jobs claimed longer ago than the visibility timeout back on the queue. Returns how many."""
        cutoff = int(time.time() * 1000) - self._visibility_timeout_ms
        raw = await self._ops.eval(
            _RECLAIM,
            [self._processing, self._inflight, self._inflight_threads, self._claimed, self._pending],
            [cutoff],
        )
        return int(cast(int, raw))

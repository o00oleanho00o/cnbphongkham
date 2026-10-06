"""200 threads, 5 operators, one identity, over a real Postgres. New module, no zalo-agent original.

Needs a THROWAWAY database (``evals.care.db_setup.seeded_database`` drops and re-creates every Pema schema), so
``run_eval`` reports this part as "not run" without ``PEMA_EVAL_OPS_DATABASE_URL`` (or ``PEMA_TEST_DATABASE_URL``).

What runs is the real code of package O: ``assignment.claim`` and ``assignment.takeover`` (row lock ``FOR UPDATE``,
history row, outbox rows, version bump in one transaction) and ``conversations.send_message`` (send lock, then
``deliver_queued_message`` with its second lock check and the identity resolution), through a fake
``OutboundDelivery`` that records what reached the "channel". The five operators race on the SAME list of
threads in the same order, so every thread is contested by up to five claims: one wins, the others get 409
``thread_locked``. Every tenth thread is taken over by another operator after the first reply, who then writes
the second one. Times are wall milliseconds on this machine (real database, no network).

After the run the SQL invariants of ``evals.ops.invariants`` are checked over every thread of the run.
"""

from __future__ import annotations

import asyncio
import time
from collections import Counter
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Engine

from evals.care.stats import Latency
from evals.ops.db_support import (
    DEFAULT_IDENTITY,
    OPERATOR_KEYS,
    ensure_operators,
    insert_account,
    new_threads,
    staff_context,
)
from evals.ops.invariants import Violation, all_invariants
from pema.clinic.actions import FakeOutboundDelivery, assignment, conversations
from pema.clinic.actions.seed_demo import SeedResult
from pema.core.db import ClinicDatabase
from pema_contracts.conversations import MessageCreate
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.ops import TakeoverRequest


@dataclass(frozen=True)
class ClaimsParameters:
    threads: int = 200
    takeover_every: int = 10


@dataclass
class _Samples:
    claim_won_ns: list[int] = field(default_factory=list[int])
    claim_locked_ns: list[int] = field(default_factory=list[int])
    send_ns: list[int] = field(default_factory=list[int])
    takeover_ns: list[int] = field(default_factory=list[int])
    other_errors: Counter[str] = field(default_factory=Counter[str])


@dataclass(frozen=True)
class ClaimsReport:
    parameters: ClaimsParameters
    operators: int
    claim_attempts: int
    claims_won: int
    claims_locked: int
    other_errors: dict[str, int]
    takeovers: int
    sends: int
    delivered_to_channel: int
    wall_s: float
    claim_won: Latency
    claim_locked: Latency
    send: Latency
    takeover: Latency
    threads_with_one_holder: int
    outbox_group_rows: int
    outbox_user_rows: int
    violations: tuple[Violation, ...]


async def _operator(
    db: ClinicDatabase,
    world: SeedResult,
    key: str,
    order: list[UUID],
    takeover_by: dict[UUID, str],
    delivery: FakeOutboundDelivery,
    samples: _Samples,
) -> tuple[int, int, int, int]:
    """One operator walks the whole list: claim, reply on a win; returns (attempts, won, locked, sends)."""
    ctx = staff_context(world, key)
    attempts = won = locked = sends = 0
    for thread_id in order:
        attempts += 1
        started = time.perf_counter_ns()
        try:
            await assignment.claim(db, ctx, thread_id)
        except DomainError as exc:
            if exc.code is ErrorCode.THREAD_LOCKED:
                locked += 1
                samples.claim_locked_ns.append(time.perf_counter_ns() - started)
            else:
                samples.other_errors[exc.code.value] += 1
            continue
        won += 1
        samples.claim_won_ns.append(time.perf_counter_ns() - started)
        started = time.perf_counter_ns()
        await conversations.send_message(
            db, ctx, thread_id, MessageCreate(text="Dạ em chào chị, em hỗ trợ chị ạ."), delivery=delivery
        )
        samples.send_ns.append(time.perf_counter_ns() - started)
        sends += 1
        if thread_id in takeover_by and takeover_by[thread_id] != key:
            successor = staff_context(world, takeover_by[thread_id])
            started = time.perf_counter_ns()
            await assignment.takeover(
                db, successor, thread_id, TakeoverRequest(reason="Chị hẹn gọi lại (mẫu)")
            )
            samples.takeover_ns.append(time.perf_counter_ns() - started)
            started = time.perf_counter_ns()
            await conversations.send_message(
                db, successor, thread_id, MessageCreate(text="Em tiếp nhận ạ."), delivery=delivery
            )
            samples.send_ns.append(time.perf_counter_ns() - started)
            sends += 1
    return attempts, won, locked, sends


async def measure_claims(
    db: ClinicDatabase, admin: Engine, world: SeedResult, params: ClaimsParameters | None = None
) -> ClaimsReport:
    use = params or ClaimsParameters()
    ensure_operators(admin, world)
    insert_account(admin, world, DEFAULT_IDENTITY)
    threads = await new_threads(db, admin, world, use.threads)
    delivery = FakeOutboundDelivery(requires_identity=True)
    takeover_by = {
        thread_id: OPERATOR_KEYS[(index + 1) % len(OPERATOR_KEYS)]
        for index, thread_id in enumerate(threads)
        if index % use.takeover_every == 0
    }
    samples = _Samples()
    started = time.perf_counter()
    totals = await asyncio.gather(
        *(_operator(db, world, key, threads, takeover_by, delivery, samples) for key in OPERATOR_KEYS)
    )
    wall = time.perf_counter() - started

    with admin.connect() as conn:
        holders = conn.execute(
            text(
                "SELECT count(*) FROM clinic.conversation WHERE id = ANY(:ids) AND assigned_user_id IS NOT NULL"
            ),
            {"ids": threads},
        ).scalar_one()
        grouped = conn.execute(
            text(
                "SELECT recipient_kind, count(*) FROM clinic.notification_outbox "
                "WHERE conversation_id = ANY(:ids) GROUP BY recipient_kind"
            ),
            {"ids": threads},
        ).all()
    rows = {str(kind): int(count) for kind, count in grouped}
    return ClaimsReport(
        parameters=use,
        operators=len(OPERATOR_KEYS),
        claim_attempts=sum(t[0] for t in totals),
        claims_won=sum(t[1] for t in totals),
        claims_locked=sum(t[2] for t in totals),
        other_errors=dict(samples.other_errors),
        takeovers=len(samples.takeover_ns),
        sends=sum(t[3] for t in totals),
        delivered_to_channel=len(delivery.requests),
        wall_s=wall,
        claim_won=Latency.from_ns(samples.claim_won_ns),
        claim_locked=Latency.from_ns(samples.claim_locked_ns),
        send=Latency.from_ns(samples.send_ns),
        takeover=Latency.from_ns(samples.takeover_ns),
        threads_with_one_holder=int(holders),
        outbox_group_rows=int(rows.get("team_group", 0)),
        outbox_user_rows=int(rows.get("user", 0)),
        violations=tuple(all_invariants(admin, threads)),
    )

"""Run the ops eval and write ``report.md``. New module, no zalo-agent original.

From ``pema-agent/backend``::

    PYTHONPATH=.. uv run python -m evals.ops.run_eval                       # queue, chain, escalation (no database)
    PYTHONPATH=.. PEMA_EVAL_OPS_DATABASE_URL=postgresql+psycopg://... uv run python -m evals.ops.run_eval

The claims part (200 threads, 5 operators over a real Postgres) needs a THROWAWAY database: it is dropped and
re-created. Without ``PEMA_EVAL_OPS_DATABASE_URL`` (or ``PEMA_TEST_DATABASE_URL``) that part is written to the
report as "not run". ``--tests-note FILE`` includes a file (the real output of the pytest run) as section 5.

Exit code 1 when an invariant fails: a gap under the minimum, a bell rung for an acknowledged notice, a text with
personal data, an escalation that did not reach the 24/7 contact, a model call, a thread with two holders or a
violated SQL invariant.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy.engine import make_url

from evals.care.db_setup import seeded_database
from evals.ops.measure_claims import ClaimsReport, measure_claims
from evals.ops.measure_escalation import measure_escalation
from evals.ops.measure_notify import measure_notify
from evals.ops.measure_queue import measure_queue
from evals.ops.report import OpsResults, render
from pema.core.event_loop import ensure_selector_event_loop_policy

DEFAULT_OUT = Path(__file__).with_name("report.md")
ENV_URLS = ("PEMA_EVAL_OPS_DATABASE_URL", "PEMA_TEST_DATABASE_URL")
COMMAND = (
    "cd pema-agent/backend\n"
    "PYTHONPATH=.. PEMA_EVAL_OPS_DATABASE_URL=<throwaway postgres> uv run python -m evals.ops.run_eval"
)


def database_url() -> str | None:
    for name in ENV_URLS:
        value = os.environ.get(name)
        if value:
            return value
    return None


def safety_failures(results: OpsResults) -> list[str]:
    failures: list[str] = []
    if results.queue.violations:
        failures.append("a message left less than the minimum gap after the previous one")
    notify = results.notify
    if notify.bell_rung_after_ack:
        failures.append("the bell rang for an acknowledged notice")
    if notify.texts_with_pii:
        failures.append("a notification text carried personal data")
    nobody = [r for r in results.escalation if not r.case.first_accepts]
    if any(not r.reached_on_call for r in nobody):
        failures.append("a handoff nobody took did not reach the 24/7 contact")
    if any(r.reached_on_call for r in results.escalation if r.case.first_accepts):
        failures.append("the 24/7 contact was told although a person accepted")
    if any(r.model_calls for r in results.escalation):
        failures.append("a model was called during escalation")
    claims = results.claims
    if claims is not None:
        if claims.violations:
            failures.append("an invariant of the shared inbox failed in SQL")
        if claims.threads_with_one_holder != claims.parameters.threads:
            failures.append("a thread was left without a holder or with the wrong count")
        if claims.claims_won != claims.parameters.threads:
            failures.append("a thread was claimed more than once or not at all")
    return failures


async def gather(url: str | None) -> OpsResults:
    queue = await measure_queue()
    notify = await measure_notify()
    escalation = await measure_escalation()
    claims: ClaimsReport | None = None
    reason = "No throwaway database was given (set PEMA_EVAL_OPS_DATABASE_URL)."
    if url is not None:
        from sqlalchemy import create_engine

        engine = create_engine(url)
        try:
            async with seeded_database(url) as (db, world):
                claims = await measure_claims(db, engine, world)
        finally:
            engine.dispose()
        reason = ""
    return OpsResults(queue, notify, escalation, claims, reason, "", COMMAND)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate the shared inbox (package O, step O7).")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--tests-note", type=Path, default=None, help="text of the real pytest run, for section 5"
    )
    parser.add_argument("--no-db", action="store_true", help="skip the database part even if a URL is set")
    args = parser.parse_args(argv)
    ensure_selector_event_loop_policy()
    url = None if args.no_db else database_url()
    if url is not None:
        make_url(url)  # a malformed URL fails here, before anything is dropped
    results = asyncio.run(gather(url))
    if args.tests_note is not None:
        results = OpsResults(
            results.queue,
            results.notify,
            results.escalation,
            results.claims,
            results.claims_reason,
            args.tests_note.read_text(encoding="utf-8"),
            results.command,
        )
    args.out.write_text(render(results), encoding="utf-8")
    failures = safety_failures(results)
    for failure in failures:
        sys.stderr.write(f"FAILED: {failure}\n")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

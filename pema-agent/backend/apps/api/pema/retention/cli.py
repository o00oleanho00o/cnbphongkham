"""Command line of the retention job: ``python -m pema.retention.cli``.

Options: ``[--dry-run]``.

New module (no TS source; was ``pema.workers.retention`` before the agent layer and its worker were removed on
branch feat/agent-v2). It runs ONE pass of scope ``clinic`` over the clinic of the installation as ``be_app``
(``PEMA_DATABASE_URL``) and exits; the periodic run is started by the API process.

``--dry-run`` counts what would be deleted and changes nothing (no row, no audit row). There is no clinic
option: one installation is one clinic. The periods are the ``PEMA_RETENTION_*`` settings; ``0`` keeps a group
forever. Exit code 1 when a group failed or the arguments are wrong, else 0.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import TextIO

from pema.config.env import Settings, get_settings
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.core.db import ClinicDatabase
from pema.core.event_loop import ensure_selector_event_loop_policy
from pema.retention.policy import Scope, policy_from_settings
from pema.retention.runner import RetentionRunner, RunStatus, ScopeReport
from pema.shared.logger import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pema.retention.cli",
        description="Delete clinic data older than its retention period (PEMA_RETENTION_*; 0 keeps a group).",
    )
    parser.add_argument("--dry-run", action="store_true", help="count what would be deleted; delete nothing")
    return parser


def format_report(report: ScopeReport) -> str:
    verb = "would delete" if report.dry_run else "deleted"
    lines = [f"scope={report.scope.value} status={report.status.value}"]
    if report.status is RunStatus.SKIPPED_LOCKED:
        lines.append("  skipped: another runner holds the lock for this scope")
        return "\n".join(lines)
    lines.extend(f"  {verb} {group}: {n}" for group, n in sorted(report.counts.items()))
    if report.disabled:
        lines.append("  kept (0 days): " + ", ".join(report.disabled))
    if report.capped:
        lines.append("  more left (batch cap reached, the next run continues): " + ", ".join(report.capped))
    if report.failed:
        lines.append("  FAILED: " + ", ".join(report.failed))
    return "\n".join(lines)


async def run_cli(
    argv: Sequence[str] | None = None, *, settings: Settings | None = None, out: TextIO | None = None
) -> int:
    args = build_parser().parse_args(argv)
    config = settings or get_settings()
    stream = out or sys.stdout
    db = ClinicDatabase(config.database_url, pool_size=3)
    try:
        runner = RetentionRunner(
            db, lambda: policy_from_settings(config, get_tuning_int), scopes=(Scope.CLINIC,)
        )
        reports = await runner.run_all(dry_run=bool(args.dry_run))
    finally:
        await db.dispose()
    for report in reports:
        stream.write(format_report(report) + "\n")
    return 1 if any(r.failed for r in reports) else 0


def main_cli() -> None:
    ensure_selector_event_loop_policy()
    config = get_settings()
    configure_logging(
        config.log_level,
        file_enabled=config.log_file_enabled,
        log_dir=config.log_dir,
        keep_days=config.log_file_keep_days,
    )
    sys.exit(asyncio.run(run_cli(settings=config)))


if __name__ == "__main__":
    main_cli()

"""Command line of the retention job: ``python -m pema.workers.retention``.

Options: ``[--dry-run] [--clinic <id>] [--scope all|agent|clinic]``.

New module (no TS source). It runs ONE pass over the clinics and exits; the periodic run is started by the
worker (scope ``agent``) and the API process (scope ``clinic``), both from ``pema.retention``.

Which database role the pass uses follows the scope, so the command never asks for more than it needs:

* ``--scope agent`` connects as ``agent_worker`` (``PEMA_WORKER_DATABASE_URL``): run it in the worker
  container. It covers the ``agent.*`` groups and the media files of the local volume;
* ``--scope clinic`` and the default ``--scope all`` connect as ``be_app`` (``PEMA_DATABASE_URL``): run
  them in the API container. ``be_app`` already holds DML on ``clinic.*`` and ``agent.*``.

``--dry-run`` counts what would be deleted and changes nothing (no row, no file, no audit row). Without
``--clinic`` every ACTIVE clinic is visited; ``--clinic <uuid>`` names one (also an inactive one: the
lookup of active clinics only lists the active ones). The periods are the ``PEMA_RETENTION_*`` settings;
``0`` keeps a group forever. Exit code 1 when a group failed or the arguments are wrong, else 0.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import TextIO
from uuid import UUID

from pema.config.env import Settings, get_settings
from pema.config.runtime_tuning_settings import get_tuning_int
from pema.conversation.media_store import MediaStore
from pema.core.db import ClinicDatabase
from pema.core.event_loop import ensure_selector_event_loop_policy
from pema.retention.policy import Scope, policy_from_settings
from pema.retention.runner import RetentionRunner, RunStatus, ScopeReport
from pema.shared.logger import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m pema.workers.retention",
        description="Delete data older than its retention period (PEMA_RETENTION_*; 0 keeps a group).",
    )
    parser.add_argument("--dry-run", action="store_true", help="count what would be deleted; delete nothing")
    parser.add_argument(
        "--clinic", type=UUID, default=None, help="only this clinic id (default: every active one)"
    )
    parser.add_argument(
        "--scope",
        choices=("all", "agent", "clinic"),
        default="all",
        help="agent = agent.* + media files (role agent_worker); clinic = clinic.* (role be_app); "
        "all = both (be_app)",
    )
    return parser


def format_report(report: ScopeReport) -> str:
    verb = "would delete" if report.dry_run else "deleted"
    lines = [f"clinic {report.clinic_id} scope={report.scope.value} status={report.status.value}"]
    if report.status is RunStatus.SKIPPED_LOCKED:
        lines.append("  skipped: another runner holds the lock for this clinic and scope")
        return "\n".join(lines)
    lines.extend(f"  {verb} {group}: {n}" for group, n in sorted(report.counts.items()))
    if report.disabled:
        lines.append("  kept (0 days or no volume): " + ", ".join(report.disabled))
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
    scope_arg: str = args.scope
    scopes = tuple(Scope) if scope_arg == "all" else (Scope(scope_arg),)
    url = config.worker_database_url if scopes == (Scope.AGENT,) else config.database_url
    db = ClinicDatabase(url, pool_size=3)
    try:
        runner = RetentionRunner(
            db,
            lambda: policy_from_settings(config, get_tuning_int),
            media=MediaStore(),
            scopes=scopes,
        )
        clinic_id: UUID | None = args.clinic
        clinic_ids = [clinic_id] if clinic_id is not None else await db.list_active_clinic_ids()
        reports = await runner.run_clinics(clinic_ids, dry_run=bool(args.dry_run))
    finally:
        await db.dispose()
    for report in reports:
        stream.write(format_report(report) + "\n")
    if not reports:
        stream.write("no active clinic\n")
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

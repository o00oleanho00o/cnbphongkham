"""The ``pema`` command line (package U, step U5). New module, not a port.

``pema catalog import <json>`` loads the clinic's product catalog (``prototype/shared/product-catalog.json``,
the file ``prototype/import-product-catalog.py`` wrote from the Excel price list) into ``clinic.product``.
It reads the file once, here; the application never reads the prototype folder at runtime. The import is
idempotent (see ``pema.clinic.actions.catalog``) and prints one JSON line: row counts, the SHA-256 of the
canonical rows and whether anything changed. It connects as ``PEMA_DATABASE_URL`` (role ``be_app``) and acts
as the system.

``--source-sha256`` records the SHA-256 of the Excel file the JSON came from (docs/20_CATALOG_ORDERS.md lists
it); ``--source-name`` overrides the file name stored with the import.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pema.clinic.actions import catalog
from pema.clinic.domain.orders import CatalogRow, parse_catalog_rows
from pema.config.env import get_settings
from pema.core.db import ClinicDatabase, get_installation_clinic_id
from pema.core.event_loop import ensure_selector_event_loop_policy
from pema_contracts.actions import ActionContext, ActionSource
from pema_contracts.errors import DomainError
from pema_contracts.roles import ActorType

_SHA256_LENGTH = 64


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pema", description="Pema operations.")
    sub = parser.add_subparsers(dest="group", required=True)
    group = sub.add_parser("catalog", help="the product catalog")
    actions = group.add_subparsers(dest="action", required=True)
    load = actions.add_parser("import", help="load product-catalog.json into clinic.product (idempotent)")
    load.add_argument("source", type=Path, help="path of product-catalog.json")
    load.add_argument("--source-name", default=None, help="name stored with the import (default: file name)")
    load.add_argument("--source-sha256", default=None, help="SHA-256 of the Excel file the JSON came from")
    return parser


async def _import(rows: list[CatalogRow], source_name: str, source_sha256: str | None) -> int:
    digest = source_sha256.lower() if source_sha256 else None
    if digest is not None and len(digest) != _SHA256_LENGTH:
        sys.stderr.write("--source-sha256 must be 64 hex characters.\n")
        return 2
    db = ClinicDatabase(get_settings().database_url)
    try:
        ctx = ActionContext(
            clinic_id=await get_installation_clinic_id(db),
            actor_type=ActorType.SYSTEM,
            source=ActionSource.SYSTEM,
            request_id="catalog-import",
        )
        result = await catalog.import_catalog(db, ctx, rows, source_name=source_name, source_sha256=digest)
    finally:
        await db.dispose()
    sys.stdout.write(json.dumps(result.model_dump(), ensure_ascii=False) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(sys.argv[1:] if argv is None else argv)
    ensure_selector_event_loop_policy()
    try:
        source: Path = args.source
        rows = parse_catalog_rows(json.loads(source.read_text(encoding="utf-8")))
        return asyncio.run(_import(rows, args.source_name or source.name, args.source_sha256))
    except (DomainError, OSError, ValueError) as exc:
        sys.stderr.write(f"Catalog import failed: {exc}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

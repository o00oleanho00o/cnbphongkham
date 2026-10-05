# ported from: prototype/shared/product-catalog-runtime.js (get, find, summary, counts) and
# prototype/import-product-catalog.py (the catalog is data, loaded by an import, never read at runtime)
"""The product catalog the quick order draws from: list and search for the order dialog, the counts line, and
the import that loads ``product-catalog.json`` (the clinic's own price list, 115 rows) into
``clinic.product``.

Forced deviations from the JavaScript:

* the browser kept the 115 rows in a generated ``product-catalog.js``; here they are rows of
  ``clinic.product`` loaded ONCE by ``import_catalog`` (CLI ``pema catalog import <json>``). Nothing reads
  the prototype folder at runtime;
* the product id is the Excel code (the prototype's ``PRD-<code>`` is only the code with a prefix);
* the import is idempotent: the SHA-256 of the canonical rows is the provenance (``clinic.catalog_import``).
  The same rows again change nothing and write no audit row; a changed catalog updates the rows whose content
  changed and switches off the codes that left the file (orders keep their own snapshot of name and price).

The catalog is the clinic's real data, not synthetic: tests read the real file, fixtures never invent prices.

Permissions: reading is for everybody who works with orders (``order.read`` or ``order.write``); the import
needs ``admin.rules`` (owner, manager) or the system actor (the CLI).
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from pema.clinic import audit
from pema.clinic.domain.orders import (
    CONSULTATION,
    PRESCRIPTION,
    UNRESOLVED,
    CatalogRow,
    catalog_hash,
    find_products,
)
from pema.clinic.models import CatalogImport, Product
from pema.clinic.rbac import require, require_any
from pema.core.db import ClinicDatabase
from pema_contracts.actions import ActionContext
from pema_contracts.common import Page
from pema_contracts.orders import CatalogImportOut, CatalogSummaryOut, OrderRoute, ProductOut
from pema_contracts.roles import Permission

READ_PERMISSIONS = (Permission.ORDER_READ, Permission.ORDER_WRITE)


def product_out(row: Product) -> ProductOut:
    return ProductOut(
        code=row.code,
        name=row.name,
        unit=row.unit,
        source_type=row.source_type,
        route=OrderRoute(row.route),
        price_vnd=row.price_vnd,
        vat=float(row.vat),
        row_number=row.row_number,
        active=row.active,
    )


async def load_products(
    session: AsyncSession, ctx: ActionContext, *, active_only: bool = True
) -> list[Product]:
    query = (
        select(Product).where(Product.clinic_id == ctx.clinic_id).order_by(Product.row_number, Product.code)
    )
    if active_only:
        query = query.where(Product.active.is_(True))
    return list((await session.scalars(query)).all())


async def list_products(
    db: ClinicDatabase, ctx: ActionContext, *, q: str = "", limit: int = 20, offset: int = 0
) -> Page[ProductOut]:
    """Products whose code, name or type contain ``q`` (accents and case ignored); an exact code first."""
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        found = find_products([product_out(r) for r in await load_products(session, ctx)], q)
    return Page[ProductOut](
        items=found[offset : offset + limit], total=len(found), limit=limit, offset=offset
    )


async def get_product(session: AsyncSession, ctx: ActionContext, code: str) -> Product | None:
    return await session.scalar(
        select(Product).where(Product.clinic_id == ctx.clinic_id, Product.code == code.strip().upper())
    )


async def catalog_summary(db: ClinicDatabase, ctx: ActionContext) -> CatalogSummaryOut:
    """``summary()``: the counts of the active products and where the catalog came from."""
    require_any(ctx, READ_PERMISSIONS)
    async with db.session() as session:
        counted = await session.execute(
            select(Product.route, func.count())
            .where(Product.clinic_id == ctx.clinic_id, Product.active.is_(True))
            .group_by(Product.route)
        )
        counts = {str(row[0]): int(row[1]) for row in counted}
        latest = await session.scalar(
            select(CatalogImport)
            .where(CatalogImport.clinic_id == ctx.clinic_id)
            .order_by(CatalogImport.imported_at.desc(), CatalogImport.id)
            .limit(1)
        )
    return CatalogSummaryOut(
        total=sum(counts.values()),
        prescription=counts.get(PRESCRIPTION, 0),
        consultation=counts.get(CONSULTATION, 0),
        unresolved=counts.get(UNRESOLVED, 0),
        source_name=latest.source_name if latest else None,
        sha256=latest.sha256 if latest else None,
        imported_at=latest.imported_at if latest else None,
    )


_FIELDS = (
    "name",
    "unit",
    "source_type",
    "route",
    "price_vnd",
    "vat",
    "price_before_tax",
    "row_number",
    "batch",
    "serial",
)


def _differs(row: Product, new: CatalogRow) -> bool:
    return (
        any(
            (float(getattr(row, f)) != float(getattr(new, f)))
            if f in {"vat", "price_before_tax"}
            else getattr(row, f) != getattr(new, f)
            for f in _FIELDS
        )
        or not row.active
    )


async def import_catalog(
    db: ClinicDatabase,
    ctx: ActionContext,
    rows: list[CatalogRow],
    *,
    source_name: str,
    source_sha256: str | None = None,
) -> CatalogImportOut:
    """Load parsed catalog rows. Idempotent: rows whose canonical hash was the last import change nothing."""
    require(ctx, Permission.ADMIN_RULES)
    digest = catalog_hash(rows)
    async with db.session() as session:
        last = await session.scalar(
            select(CatalogImport)
            .where(CatalogImport.clinic_id == ctx.clinic_id)
            .order_by(CatalogImport.imported_at.desc(), CatalogImport.id)
            .limit(1)
        )
        existing = {p.code: p for p in await load_products(session, ctx, active_only=False)}
        if (
            last is not None
            and last.sha256 == digest
            and set(existing) == {r.code for r in rows}
            and not any(_differs(existing[r.code], r) for r in rows)
        ):
            return CatalogImportOut(
                total=len(rows),
                created=0,
                updated=0,
                unchanged=len(rows),
                deactivated=0,
                sha256=digest,
                unchanged_run=True,
            )
        created = updated = unchanged = 0
        for new in rows:
            row = existing.get(new.code)
            if row is None:
                session.add(
                    Product(
                        clinic_id=ctx.clinic_id,
                        code=new.code,
                        name=new.name,
                        unit=new.unit,
                        source_type=new.source_type,
                        route=new.route,
                        price_vnd=new.price_vnd,
                        vat=new.vat,
                        price_before_tax=new.price_before_tax,
                        row_number=new.row_number,
                        batch=new.batch,
                        serial=new.serial,
                        active=True,
                        catalog_hash=digest,
                    )
                )
                created += 1
            elif _differs(row, new):
                for f in _FIELDS:
                    setattr(row, f, getattr(new, f))
                row.active = True
                row.catalog_hash = digest
                updated += 1
            else:
                unchanged += 1
        wanted = {r.code for r in rows}
        deactivated = 0
        for code, row in existing.items():
            if code not in wanted and row.active:
                row.active = False
                deactivated += 1
        session.add(
            CatalogImport(
                clinic_id=ctx.clinic_id,
                source_name=source_name,
                sha256=digest,
                source_sha256=source_sha256,
                total_rows=len(rows),
                prescription_rows=sum(1 for r in rows if r.route == PRESCRIPTION),
            )
        )
        await session.flush()
        await audit.record(
            session,
            ctx,
            "catalog.import",
            "catalog",
            None,
            {
                "sha256": digest,
                "total": len(rows),
                "created": created,
                "updated": updated,
                "deactivated": deactivated,
            },
        )
    return CatalogImportOut(
        total=len(rows),
        created=created,
        updated=updated,
        unchanged=unchanged,
        deactivated=deactivated,
        sha256=digest,
        unchanged_run=False,
    )

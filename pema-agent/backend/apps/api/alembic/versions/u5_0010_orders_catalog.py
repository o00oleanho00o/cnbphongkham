"""product catalog and quick orders (package U, step U5).

Source: ``prototype/shared/order-data.js`` (``saveOrder``, ``approveOrder``, ``orderPrintData``),
``prototype/shared/product-catalog.json`` and ``prototype/import-product-catalog.py`` (the clinic's own
price list, 115 rows, product id = the Excel code), ``docs/20_CATALOG_ORDERS.md``. Single tenant
(``st_0009_single_tenant``): no row level security; every table keeps ``clinic_id`` (the installation id).

* ``clinic.catalog_import``: one row per import run (file name, SHA-256 of the canonical rows, row count,
  prescription count). The catalog the orders read is the product table; this row is its provenance.
* ``clinic.product``: one row per Excel code, loaded by the CLI ``pema catalog import <json>`` (never at
  runtime from the prototype folder). ``route`` is the prototype's ``outputType`` (PRESCRIPTION when the
  Excel type is "Thuốc", CONSULTATION for any other type, UNRESOLVED when the type is empty). ``price_vnd``
  is the price after tax, an integer (a price of 0 stays 0).
* ``clinic.order`` / ``clinic.order_item``: a quick order of one patient. ``status`` is ``draft`` or
  ``approved``; an approved order is immutable (a trigger refuses UPDATE of its columns other than the
  payment mirror and DELETE of its lines). The lines keep a snapshot of name, unit, route and price, so a
  later catalog import changes nothing in an order. ``received_vnd`` / ``paid`` mirror what the invoice of
  step U6 has collected (U6 sets them; until then they stay 0/false): a draft with money received cannot
  be edited. ``invoice_id`` is the link U6 fills; it has no foreign key yet.

Only ``be_app`` gets privileges (the worker reads none of this).

Revision ID: u5_0010_orders_catalog
Revises: u4_0010_services_resources
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u5_0010_orders_catalog"
down_revision = "u4_0010_services_resources"
branch_labels = None
depends_on = None

ROUTES = "'PRESCRIPTION', 'CONSULTATION', 'NONE', 'UNRESOLVED'"


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("""
        CREATE TABLE clinic.catalog_import (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            source_name text NOT NULL CHECK (length(source_name) BETWEEN 1 AND 200),
            sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            source_sha256 text CHECK (source_sha256 IS NULL OR source_sha256 ~ '^[0-9a-f]{64}$'),
            total_rows integer NOT NULL CHECK (total_rows >= 1),
            prescription_rows integer NOT NULL CHECK (prescription_rows >= 0),
            imported_at timestamptz NOT NULL DEFAULT now()
        )""")
    _sql("CREATE INDEX catalog_import_at_idx ON clinic.catalog_import (clinic_id, imported_at DESC)")

    _sql(f"""
        CREATE TABLE clinic.product (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            code text NOT NULL CHECK (code ~ '^[A-Z0-9][A-Z0-9._-]{{0,39}}$'),
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 400),
            unit text NOT NULL DEFAULT '' CHECK (length(unit) <= 40),
            source_type text NOT NULL DEFAULT '' CHECK (length(source_type) <= 60),
            route text NOT NULL CHECK (route IN ({ROUTES})),
            price_vnd bigint NOT NULL CHECK (price_vnd >= 0),
            vat numeric(6, 4) NOT NULL DEFAULT 0 CHECK (vat >= 0),
            price_before_tax numeric(18, 4) NOT NULL DEFAULT 0 CHECK (price_before_tax >= 0),
            row_number integer NOT NULL DEFAULT 0 CHECK (row_number >= 0),
            batch text NOT NULL DEFAULT '',
            serial text NOT NULL DEFAULT '',
            active boolean NOT NULL DEFAULT true,
            catalog_hash text NOT NULL CHECK (catalog_hash ~ '^[0-9a-f]{{64}}$'),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (clinic_id, code)
        )""")

    _sql("""
        CREATE TABLE clinic."order" (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            doctor_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved')),
            order_date date NOT NULL,
            diagnosis text NOT NULL DEFAULT '' CHECK (length(diagnosis) <= 2000),
            note text NOT NULL DEFAULT '' CHECK (length(note) <= 2000),
            total_vnd bigint NOT NULL DEFAULT 0 CHECK (total_vnd >= 0),
            catalog_hash text CHECK (catalog_hash IS NULL OR catalog_hash ~ '^[0-9a-f]{64}$'),
            reviewed_by uuid,
            reviewed_at timestamptz,
            invoice_id uuid,
            received_vnd bigint NOT NULL DEFAULT 0 CHECK (received_vnd >= 0),
            paid boolean NOT NULL DEFAULT false,
            created_by uuid,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (status = 'draft' OR (reviewed_by IS NOT NULL AND reviewed_at IS NOT NULL)),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql('CREATE INDEX order_patient_idx ON clinic."order" (clinic_id, patient_id, created_at DESC)')
    _sql('CREATE INDEX order_status_idx ON clinic."order" (clinic_id, status, created_at DESC)')

    _sql(f"""
        CREATE TABLE clinic.order_item (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            order_id uuid NOT NULL,
            line_no integer NOT NULL CHECK (line_no >= 1),
            product_code text NOT NULL,
            name text NOT NULL CHECK (length(name) BETWEEN 1 AND 400),
            source_type text NOT NULL DEFAULT '',
            unit text NOT NULL DEFAULT '',
            row_number integer NOT NULL DEFAULT 0,
            catalog_route text NOT NULL CHECK (catalog_route IN ({ROUTES})),
            route text NOT NULL CHECK (route IN ({ROUTES})),
            route_reason text NOT NULL DEFAULT '' CHECK (length(route_reason) <= 500),
            quantity integer NOT NULL CHECK (quantity BETWEEN 1 AND 9999),
            unit_price_vnd bigint NOT NULL CHECK (unit_price_vnd >= 0),
            usage text NOT NULL DEFAULT '' CHECK (length(usage) <= 2000),
            note text NOT NULL DEFAULT '' CHECK (length(note) <= 1000),
            UNIQUE (order_id, line_no),
            FOREIGN KEY (clinic_id, order_id) REFERENCES clinic."order" (clinic_id, id) ON DELETE CASCADE
        )""")

    # An approved order keeps its lines and its content: only the payment mirror may still change.
    _sql("""
        CREATE FUNCTION clinic.order_approved_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        BEGIN
            IF TG_TABLE_NAME = 'order' THEN
                IF OLD.status = 'approved' AND (
                    NEW.status IS DISTINCT FROM OLD.status OR NEW.patient_id IS DISTINCT FROM OLD.patient_id
                    OR NEW.doctor_id IS DISTINCT FROM OLD.doctor_id OR NEW.diagnosis IS DISTINCT FROM OLD.diagnosis
                    OR NEW.note IS DISTINCT FROM OLD.note OR NEW.total_vnd IS DISTINCT FROM OLD.total_vnd
                    OR NEW.reviewed_by IS DISTINCT FROM OLD.reviewed_by
                    OR NEW.reviewed_at IS DISTINCT FROM OLD.reviewed_at
                    OR NEW.order_date IS DISTINCT FROM OLD.order_date
                ) THEN
                    RAISE EXCEPTION 'an approved order is immutable';
                END IF;
                RETURN NEW;
            END IF;
            IF EXISTS (
                SELECT 1 FROM clinic."order" o
                 WHERE o.clinic_id = COALESCE(NEW.clinic_id, OLD.clinic_id)
                   AND o.id = COALESCE(NEW.order_id, OLD.order_id) AND o.status = 'approved'
            ) THEN
                RAISE EXCEPTION 'the lines of an approved order are immutable';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $fn$""")
    _sql(
        'CREATE TRIGGER order_approved_immutable BEFORE UPDATE ON clinic."order" '
        "FOR EACH ROW EXECUTE FUNCTION clinic.order_approved_immutable()"
    )
    _sql(
        "CREATE TRIGGER order_item_approved_immutable BEFORE UPDATE OR DELETE ON clinic.order_item "
        "FOR EACH ROW EXECUTE FUNCTION clinic.order_approved_immutable()"
    )

    for table in ("product", '"order"'):
        bare = table.strip('"')
        _sql(
            f"CREATE TRIGGER {bare}_touch BEFORE UPDATE ON clinic.{table} "
            "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
        )
    for table in ("product", '"order"', "order_item"):
        _sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.{table} TO be_app")
    _sql("GRANT SELECT, INSERT ON clinic.catalog_import TO be_app")


def downgrade() -> None:
    for table in ("order_item", '"order"', "product", "catalog_import"):
        _sql(f"DROP TABLE IF EXISTS clinic.{table}")
    _sql("DROP FUNCTION IF EXISTS clinic.order_approved_immutable()")

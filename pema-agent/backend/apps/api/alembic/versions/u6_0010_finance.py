"""finance PB02: invoices, payments, performed procedures, monthly periods, owner notifications (package U, step U6).

Source: ``prototype/finance_server.py`` (the JSON document of its SQLite ``state`` table: ``invoices``,
``payments``, ``entries``, ``periods``, ``notifications``), ``docs/24_FINANCE_AND_PROCEDURE_FEES.md`` and
``docs/SPEC-PB02.md``. Single tenant (``st_0009_single_tenant``): no row level security; every table keeps
``clinic_id`` (the installation id). Money is an integer number of VND, a rate or a share an integer number of
basis points (10000 = 100 %), as in the prototype.

* ``clinic.invoice``: a receivable of one patient. ``source`` is ``order`` (the invoice of a U5 quick order,
  ``order_id`` unique) or ``finance`` (the invoice a performed procedure creates for itself). ``received_vnd``
  never exceeds ``amount_vnd`` (CHECK), so an overpayment is refused by the database as well as by the action.
* ``clinic.payment``: one receipt. ``idempotency_key`` is unique per clinic: the retry of a receipt finds the
  first one instead of collecting twice.
* ``clinic.procedure_entry`` + ``clinic.procedure_entry_person``: a performed procedure and who performed it. The
  entry keeps the service terms it was made under (``terms_version``, ``basis``); each person row keeps the
  revenue share and the commission rate that applied (``share_bp``, ``rate_bp``), so a later change of the
  service terms never moves an old entry. The performer is chosen by the accountant: nothing here defaults to the
  doctor in charge of the patient.
* ``clinic.finance_period``: a month that was closed (status ``closed``) and later paid out (``paid``). A month
  without a row is open. ``snapshot`` is the frozen commission table of the month. While a row exists the database
  refuses INSERT, UPDATE and DELETE of the month's entries and people (``finance_closed_period_guard``), and the
  snapshot, month and closing columns of the period never change (``finance_period_frozen``).
* ``clinic.finance_notification``: one notification of the owner per receipt (``payment_id`` unique).

Only ``be_app`` gets privileges (the worker reads none of this).

Revision ID: u6_0010_finance
Revises: u5_0010_orders_catalog
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u6_0010_finance"
down_revision = "u5_0010_orders_catalog"
branch_labels = None
depends_on = None


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("""
        CREATE TABLE clinic.invoice (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            number text NOT NULL CHECK (length(number) BETWEEN 3 AND 40),
            patient_id uuid NOT NULL,
            source text NOT NULL CHECK (source IN ('finance', 'order')),
            order_id uuid,
            amount_vnd bigint NOT NULL CHECK (amount_vnd >= 0),
            received_vnd bigint NOT NULL DEFAULT 0 CHECK (received_vnd >= 0),
            invoice_date date NOT NULL,
            created_by uuid,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (received_vnd <= amount_vnd),
            CHECK ((source = 'order') = (order_id IS NOT NULL)),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, number),
            UNIQUE (order_id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, order_id) REFERENCES clinic."order" (clinic_id, id),
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX invoice_patient_idx ON clinic.invoice (clinic_id, patient_id, invoice_date DESC)")
    _sql(
        "CREATE INDEX invoice_due_idx ON clinic.invoice (clinic_id, invoice_date DESC) "
        "WHERE received_vnd < amount_vnd"
    )

    _sql("""
        CREATE TABLE clinic.payment (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 3 AND 160),
            invoice_id uuid NOT NULL,
            patient_id uuid NOT NULL,
            amount_vnd bigint NOT NULL CHECK (amount_vnd >= 1),
            method text NOT NULL CHECK (method IN ('cash', 'transfer')),
            paid_on date NOT NULL,
            received_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, idempotency_key),
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, received_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX payment_day_idx ON clinic.payment (clinic_id, paid_on DESC, created_at DESC)")
    _sql("CREATE INDEX payment_invoice_idx ON clinic.payment (clinic_id, invoice_id)")

    _sql("""
        CREATE TABLE clinic.procedure_entry (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            service_id uuid NOT NULL,
            service_name text NOT NULL CHECK (length(service_name) BETWEEN 1 AND 200),
            terms_version integer NOT NULL CHECK (terms_version >= 1),
            basis text NOT NULL CHECK (basis IN ('net', 'list', 'collected')),
            entry_date date NOT NULL,
            invoice_id uuid NOT NULL,
            owns_invoice boolean NOT NULL DEFAULT true,
            list_vnd bigint NOT NULL CHECK (list_vnd >= 1),
            discount_vnd bigint NOT NULL DEFAULT 0 CHECK (discount_vnd >= 0),
            net_vnd bigint NOT NULL CHECK (net_vnd >= 0),
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'void')),
            note text NOT NULL CHECK (length(note) BETWEEN 1 AND 500),
            void_reason text CHECK (void_reason IS NULL OR length(void_reason) BETWEEN 1 AND 500),
            created_by uuid,
            approved_by uuid,
            approved_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CHECK (discount_vnd <= list_vnd),
            CHECK (net_vnd = list_vnd - discount_vnd),
            CHECK ((status = 'void') = (void_reason IS NOT NULL)),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, service_id) REFERENCES clinic.service (clinic_id, id),
            FOREIGN KEY (service_id, terms_version) REFERENCES clinic.service_version (service_id, version_no),
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice (clinic_id, id),
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX procedure_entry_day_idx ON clinic.procedure_entry (clinic_id, entry_date, created_at)")
    _sql("CREATE INDEX procedure_entry_invoice_idx ON clinic.procedure_entry (clinic_id, invoice_id)")

    _sql("""
        CREATE TABLE clinic.procedure_entry_person (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            entry_id uuid NOT NULL,
            position integer NOT NULL CHECK (position BETWEEN 1 AND 4),
            doctor_id uuid NOT NULL,
            share_bp integer NOT NULL CHECK (share_bp BETWEEN 1 AND 10000),
            rate_bp integer NOT NULL CHECK (rate_bp BETWEEN 0 AND 10000),
            UNIQUE (entry_id, position),
            UNIQUE (entry_id, doctor_id),
            FOREIGN KEY (clinic_id, entry_id) REFERENCES clinic.procedure_entry (clinic_id, id),
            FOREIGN KEY (clinic_id, doctor_id) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql(
        "CREATE INDEX procedure_entry_person_doctor_idx ON clinic.procedure_entry_person (clinic_id, doctor_id)"
    )

    _sql("""
        CREATE TABLE clinic.finance_period (
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            month text NOT NULL CHECK (month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'),
            status text NOT NULL DEFAULT 'closed' CHECK (status IN ('closed', 'paid')),
            closed_at timestamptz NOT NULL DEFAULT now(),
            closed_by uuid,
            paid_at timestamptz,
            paid_by uuid,
            reference text CHECK (reference IS NULL OR length(reference) BETWEEN 1 AND 120),
            snapshot jsonb NOT NULL,
            PRIMARY KEY (clinic_id, month),
            CHECK ((status = 'paid') = (reference IS NOT NULL AND paid_at IS NOT NULL)),
            FOREIGN KEY (clinic_id, closed_by) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, paid_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")

    _sql("""
        CREATE TABLE clinic.finance_notification (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            payment_id uuid NOT NULL,
            title text NOT NULL CHECK (length(title) BETWEEN 1 AND 200),
            body text NOT NULL CHECK (length(body) BETWEEN 1 AND 500),
            amount_vnd bigint NOT NULL CHECK (amount_vnd >= 1),
            invoice_id uuid NOT NULL,
            is_read boolean NOT NULL DEFAULT false,
            read_at timestamptz,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (payment_id),
            FOREIGN KEY (clinic_id, payment_id) REFERENCES clinic.payment (clinic_id, id),
            FOREIGN KEY (clinic_id, invoice_id) REFERENCES clinic.invoice (clinic_id, id)
        )""")
    _sql("CREATE INDEX finance_notification_idx ON clinic.finance_notification (clinic_id, created_at DESC)")

    # A closed month is immutable: its entries and people cannot be inserted, changed or deleted.
    _sql("""
        CREATE FUNCTION clinic.finance_closed_period_guard() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        DECLARE
            target_clinic uuid;
            target_day date;
            old_day date;
        BEGIN
            IF TG_TABLE_NAME = 'procedure_entry' THEN
                IF TG_OP <> 'INSERT' THEN old_day := OLD.entry_date; END IF;
                IF TG_OP <> 'DELETE' THEN target_day := NEW.entry_date; END IF;
                target_clinic := COALESCE(NEW.clinic_id, OLD.clinic_id);
            ELSE
                SELECT e.entry_date INTO target_day FROM clinic.procedure_entry e
                 WHERE e.clinic_id = COALESCE(NEW.clinic_id, OLD.clinic_id)
                   AND e.id = COALESCE(NEW.entry_id, OLD.entry_id);
                old_day := target_day;
                target_clinic := COALESCE(NEW.clinic_id, OLD.clinic_id);
            END IF;
            IF EXISTS (
                SELECT 1 FROM clinic.finance_period p
                 WHERE p.clinic_id = target_clinic
                   AND p.month IN (to_char(target_day, 'YYYY-MM'), to_char(old_day, 'YYYY-MM'))
            ) THEN
                RAISE EXCEPTION 'the finance period is closed';
            END IF;
            RETURN COALESCE(NEW, OLD);
        END
        $fn$""")
    _sql(
        "CREATE TRIGGER procedure_entry_closed_guard BEFORE INSERT OR UPDATE OR DELETE ON clinic.procedure_entry "
        "FOR EACH ROW EXECUTE FUNCTION clinic.finance_closed_period_guard()"
    )
    _sql(
        "CREATE TRIGGER procedure_entry_person_closed_guard "
        "BEFORE INSERT OR UPDATE OR DELETE ON clinic.procedure_entry_person "
        "FOR EACH ROW EXECUTE FUNCTION clinic.finance_closed_period_guard()"
    )

    # A closed period keeps its month, its snapshot and its closing; only closed -> paid (with a reference) moves.
    _sql("""
        CREATE FUNCTION clinic.finance_period_frozen() RETURNS trigger
        LANGUAGE plpgsql AS $fn$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'a finance period is never deleted';
            END IF;
            IF NEW.month IS DISTINCT FROM OLD.month OR NEW.snapshot IS DISTINCT FROM OLD.snapshot
               OR NEW.closed_at IS DISTINCT FROM OLD.closed_at OR NEW.closed_by IS DISTINCT FROM OLD.closed_by
               OR (OLD.status = 'paid' AND NEW IS DISTINCT FROM OLD)
               OR (OLD.status = 'closed' AND NEW.status NOT IN ('closed', 'paid')) THEN
                RAISE EXCEPTION 'a closed finance period is immutable';
            END IF;
            RETURN NEW;
        END
        $fn$""")
    _sql(
        "CREATE TRIGGER finance_period_frozen BEFORE UPDATE OR DELETE ON clinic.finance_period "
        "FOR EACH ROW EXECUTE FUNCTION clinic.finance_period_frozen()"
    )

    for table in ("invoice", "procedure_entry"):
        _sql(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON clinic.{table} "
            "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
        )
    for table in ("invoice", "procedure_entry"):
        _sql(f"GRANT SELECT, INSERT, UPDATE ON clinic.{table} TO be_app")
    _sql("GRANT SELECT, INSERT, UPDATE ON clinic.procedure_entry_person TO be_app")
    _sql("GRANT SELECT, INSERT ON clinic.payment TO be_app")
    _sql("GRANT SELECT, INSERT, UPDATE ON clinic.finance_period TO be_app")
    _sql("GRANT SELECT, INSERT, UPDATE ON clinic.finance_notification TO be_app")


def downgrade() -> None:
    for table in (
        "finance_notification",
        "finance_period",
        "procedure_entry_person",
        "procedure_entry",
        "payment",
        "invoice",
    ):
        _sql(f"DROP TABLE IF EXISTS clinic.{table}")
    _sql("DROP FUNCTION IF EXISTS clinic.finance_period_frozen()")
    _sql("DROP FUNCTION IF EXISTS clinic.finance_closed_period_guard()")

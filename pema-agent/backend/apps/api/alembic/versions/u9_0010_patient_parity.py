"""Patient 360 parity fixes (package U, step U9): warnings, history and diagnosis, patient app notes, briefs,
and the price fixed on a plan.

Source: ``prototype/shared/clinic.js`` (``p.alerts``, ``p.aftercare``, ``p.approvedBrief``),
``crm-automation.js`` (``p.clinical``), ``care-finance.js`` (``servicePlans``: ``listPrice``, ``discount``,
``agreedPrice``). Single tenant: no row level security, ``clinic_id`` is the installation id.

* ``clinic.patient.alerts``: the lines of "Thông tin cần nhớ" (text array, empty by default).
* ``clinic.treatment_plan``: ``unit_price_vnd``, ``discount_vnd``, ``agreed_price_vnd``, ``service_terms_version``.
  Filled only by "Thêm dịch vụ vào liệu trình": the price of the catalog snapshot at that moment, never
  re-read afterwards ("Giá đã chốt được lưu trên hồ sơ"). All four are null or all four are set (CHECK).
* ``clinic.patient_clinical_note``: "Tiền sử & chẩn đoán", one row per patient, written only by a clinician.
* ``clinic.patient_app_event``: a note on the patient app timeline ("Nhắn tin", "Chăm sóc tại nhà").
* ``clinic.patient_brief``: a templated brief a doctor edited and approved, with the records it came from.

``be_app`` gets DML like the other ``clinic.*`` tables; ``agent_worker`` gets nothing (it reaches the clinic
through ``clinic_agent``, whose views name their columns, so the new ``alerts`` column is not exposed).

Revision ID: u9_0010_patient_parity
Revises: u10_0010_appointment_room
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u9_0010_patient_parity"
down_revision = "u10_0010_appointment_room"
branch_labels = None
depends_on = None

NEW_TABLES = ("patient_clinical_note", "patient_app_event", "patient_brief")
PLAN_PRICE_COLUMNS = ("unit_price_vnd", "discount_vnd", "agreed_price_vnd", "service_terms_version")


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("ALTER TABLE clinic.patient ADD COLUMN alerts text[] NOT NULL DEFAULT '{}'")
    _sql(
        "ALTER TABLE clinic.patient ADD CONSTRAINT patient_alerts_size "
        "CHECK (coalesce(cardinality(alerts), 0) <= 20)"
    )

    _sql("ALTER TABLE clinic.treatment_plan ADD COLUMN unit_price_vnd bigint CHECK (unit_price_vnd >= 0)")
    _sql("ALTER TABLE clinic.treatment_plan ADD COLUMN discount_vnd bigint CHECK (discount_vnd >= 0)")
    _sql("ALTER TABLE clinic.treatment_plan ADD COLUMN agreed_price_vnd bigint CHECK (agreed_price_vnd >= 0)")
    _sql("ALTER TABLE clinic.treatment_plan ADD COLUMN service_terms_version integer")
    _sql(
        "ALTER TABLE clinic.treatment_plan ADD CONSTRAINT treatment_plan_price_together CHECK ("
        "(unit_price_vnd IS NULL) = (discount_vnd IS NULL) "
        "AND (unit_price_vnd IS NULL) = (agreed_price_vnd IS NULL) "
        "AND (unit_price_vnd IS NULL) = (service_terms_version IS NULL))"
    )

    _sql("""
        CREATE TABLE clinic.patient_clinical_note (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            history text NOT NULL CHECK (length(history) BETWEEN 1 AND 4000),
            diagnosis text NOT NULL CHECK (length(diagnosis) BETWEEN 1 AND 4000),
            reviewed_by uuid,
            reviewed_at timestamptz NOT NULL DEFAULT now(),
            version integer NOT NULL DEFAULT 1,
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, patient_id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")

    _sql("""
        CREATE TABLE clinic.patient_app_event (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('message', 'aftercare')),
            body text NOT NULL CHECK (length(body) BETWEEN 1 AND 2000),
            created_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql(
        "CREATE INDEX patient_app_event_idx ON clinic.patient_app_event "
        "(clinic_id, patient_id, created_at DESC)"
    )

    _sql("""
        CREATE TABLE clinic.patient_brief (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            body text NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
            source_ids text[] NOT NULL DEFAULT '{}',
            approved_by uuid,
            approved_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX patient_brief_idx ON clinic.patient_brief (clinic_id, patient_id, approved_at DESC)")

    for table in NEW_TABLES:
        _sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.{table} TO be_app")


def downgrade() -> None:
    for table in NEW_TABLES[::-1]:
        _sql(f"DROP TABLE IF EXISTS clinic.{table}")
    _sql("ALTER TABLE clinic.treatment_plan DROP CONSTRAINT IF EXISTS treatment_plan_price_together")
    for column in PLAN_PRICE_COLUMNS:
        _sql(f"ALTER TABLE clinic.treatment_plan DROP COLUMN IF EXISTS {column}")
    _sql("ALTER TABLE clinic.patient DROP CONSTRAINT IF EXISTS patient_alerts_size")
    _sql("ALTER TABLE clinic.patient DROP COLUMN IF EXISTS alerts")

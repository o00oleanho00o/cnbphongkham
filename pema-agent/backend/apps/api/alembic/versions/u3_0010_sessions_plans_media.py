"""Patient 360 tabs (package U, step U3): sessions with their record, plans with a goal, consult notes, media.

``clinic.treatment_plan`` and ``clinic.treatment_session`` already exist (0001); this revision widens them with
what the old Clinic Web saved when a doctor recorded a session (``session-*`` inputs of ``prototype/shared/
clinic.js``): the type of the session, the region and the angle of the photo, the date the doctor wants to see
the patient again, the aftercare text, the consent the photos rest on, and the review stamp. Two tables are new:

* ``clinic.consult_note``: the consultation note of the Tư vấn tab. ``draft`` until a clinician approves it
  (one open draft per patient), then ``approved`` and part of the timeline;
* ``clinic.media``: one row per clinical photo. The bytes live in the storage behind ``MediaStorage`` (a local
  volume today); the row holds the key, the MIME type, the size, the SHA-256 and the consent the upload rests
  on. ``status``: ``pending`` (upload intent issued) -> ``uploaded`` (bytes stored and checked) ->
  ``confirmed`` (staff confirmed). Nothing here analyses the content of an image.

Single tenant: no row level security, ``clinic_id`` is the installation id. ``be_app`` gets DML like the other
``clinic.*`` tables; ``agent_worker`` gets nothing (it reaches the clinic only through ``clinic_agent``).

Revision ID: u3_0010_sessions_plans_media
Revises: m_0002_paused_reminders
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "u3_0010_sessions_plans_media"
down_revision = "m_0002_paused_reminders"
branch_labels = None
depends_on = None

NEW_TABLES = ("consult_note", "media")


def _sql(statement: str) -> None:
    op.execute(sa.text(statement))


def upgrade() -> None:
    _sql("ALTER TABLE clinic.treatment_plan ADD COLUMN goal text")

    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN session_type text")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN region text")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN view text")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN next_visit_on date")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN aftercare text")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN consent_id uuid")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN reviewed boolean NOT NULL DEFAULT false")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN reviewed_by uuid")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN reviewed_at timestamptz")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN created_by uuid")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN version integer NOT NULL DEFAULT 1")
    _sql("ALTER TABLE clinic.treatment_session ADD COLUMN updated_at timestamptz NOT NULL DEFAULT now()")
    _sql(
        "ALTER TABLE clinic.treatment_session ADD CONSTRAINT treatment_session_consent_fk "
        "FOREIGN KEY (clinic_id, consent_id) REFERENCES clinic.consent (clinic_id, id)"
    )
    _sql(
        "ALTER TABLE clinic.treatment_session ADD CONSTRAINT treatment_session_reviewed_by_fk "
        "FOREIGN KEY (clinic_id, reviewed_by) REFERENCES clinic.user_account (clinic_id, id)"
    )
    _sql(
        "ALTER TABLE clinic.treatment_session ADD CONSTRAINT treatment_session_created_by_fk "
        "FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id)"
    )
    _sql(
        "CREATE TRIGGER treatment_session_touch BEFORE UPDATE ON clinic.treatment_session "
        "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
    )

    _sql("""
        CREATE TABLE clinic.consult_note (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved')),
            source_text text NOT NULL DEFAULT '',
            body text NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
            created_by uuid,
            approved_by uuid,
            approved_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, created_by) REFERENCES clinic.user_account (clinic_id, id),
            FOREIGN KEY (clinic_id, approved_by) REFERENCES clinic.user_account (clinic_id, id),
            CHECK (status <> 'approved' OR approved_at IS NOT NULL)
        )""")
    _sql(
        "CREATE INDEX consult_note_patient_idx ON clinic.consult_note (clinic_id, patient_id, created_at DESC)"
    )
    _sql(
        "CREATE UNIQUE INDEX consult_note_one_draft_idx ON clinic.consult_note (clinic_id, patient_id) "
        "WHERE status = 'draft'"
    )

    _sql("""
        CREATE TABLE clinic.media (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            clinic_id uuid NOT NULL REFERENCES clinic.clinic (id),
            patient_id uuid NOT NULL,
            session_id uuid,
            stage text NOT NULL CHECK (stage IN ('before', 'after')),
            region text,
            view text,
            storage_key text NOT NULL,
            mime text NOT NULL CHECK (mime IN ('image/jpeg', 'image/png', 'image/webp')),
            size_bytes bigint NOT NULL CHECK (size_bytes > 0),
            sha256 text,
            consent_id uuid NOT NULL,
            status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'uploaded', 'confirmed')),
            uploaded_by uuid,
            created_at timestamptz NOT NULL DEFAULT now(),
            uploaded_at timestamptz,
            confirmed_at timestamptz,
            version integer NOT NULL DEFAULT 1,
            updated_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (clinic_id, id),
            UNIQUE (clinic_id, storage_key),
            FOREIGN KEY (clinic_id, patient_id) REFERENCES clinic.patient (clinic_id, id),
            FOREIGN KEY (clinic_id, session_id) REFERENCES clinic.treatment_session (clinic_id, id),
            FOREIGN KEY (clinic_id, consent_id) REFERENCES clinic.consent (clinic_id, id),
            FOREIGN KEY (clinic_id, uploaded_by) REFERENCES clinic.user_account (clinic_id, id)
        )""")
    _sql("CREATE INDEX media_patient_idx ON clinic.media (clinic_id, patient_id, created_at DESC)")
    _sql("CREATE INDEX media_session_idx ON clinic.media (clinic_id, session_id)")

    for table in NEW_TABLES:
        _sql(
            f"CREATE TRIGGER {table}_touch BEFORE UPDATE ON clinic.{table} "
            "FOR EACH ROW EXECUTE FUNCTION clinic.touch_updated_at()"
        )
        _sql(f"GRANT SELECT, INSERT, UPDATE, DELETE ON clinic.{table} TO be_app")


def downgrade() -> None:
    for table in NEW_TABLES[::-1]:
        _sql(f"DROP TABLE IF EXISTS clinic.{table}")
    _sql("DROP TRIGGER IF EXISTS treatment_session_touch ON clinic.treatment_session")
    for constraint in (
        "treatment_session_created_by_fk",
        "treatment_session_reviewed_by_fk",
        "treatment_session_consent_fk",
    ):
        _sql(f"ALTER TABLE clinic.treatment_session DROP CONSTRAINT IF EXISTS {constraint}")
    for column in (
        "updated_at",
        "version",
        "created_by",
        "reviewed_at",
        "reviewed_by",
        "reviewed",
        "consent_id",
        "aftercare",
        "next_visit_on",
        "view",
        "region",
        "session_type",
    ):
        _sql(f"ALTER TABLE clinic.treatment_session DROP COLUMN IF EXISTS {column}")
    _sql("ALTER TABLE clinic.treatment_plan DROP COLUMN IF EXISTS goal")

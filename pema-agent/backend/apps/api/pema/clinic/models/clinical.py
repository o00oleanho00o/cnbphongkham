"""``clinic.consult_note`` and ``clinic.media`` (migration u3_0010; package U, step U3), and the three
tables of step U9 (migration u9_0010): ``patient_clinical_note``, ``patient_app_event``, ``patient_brief``."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from pema.clinic.models.base import Base


class ConsultNote(Base):
    """The note of the Tư vấn tab: one open ``draft`` per patient, ``approved`` once a clinician signs it."""

    __tablename__ = "consult_note"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(Text, default="draft")
    source_text: Mapped[str] = mapped_column(Text, default="")
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    approved_by: Mapped[UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class Media(Base):
    """One clinical photo. The bytes are in the ``MediaStorage`` under ``storage_key``; this row is the record
    of who uploaded it, on which consent, and how far the upload got (``pending``, ``uploaded``,
    ``confirmed``)."""

    __tablename__ = "media"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    session_id: Mapped[UUID | None] = mapped_column(default=None)
    stage: Mapped[str] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text, default=None)
    view: Mapped[str | None] = mapped_column(Text, default=None)
    storage_key: Mapped[str] = mapped_column(Text)
    mime: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(Text, default=None)
    consent_id: Mapped[UUID]
    status: Mapped[str] = mapped_column(Text, default="pending")
    uploaded_by: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class PatientClinicalNote(Base):
    """'Tiền sử & chẩn đoán': what the doctor recorded. One row per patient (old ``p.clinical``); the doctor
    who saved it and when are on the row. Nothing writes here except a clinician's own save."""

    __tablename__ = "patient_clinical_note"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    history: Mapped[str] = mapped_column(Text)
    diagnosis: Mapped[str] = mapped_column(Text)
    reviewed_by: Mapped[UUID | None] = mapped_column(default=None)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    version: Mapped[int] = mapped_column(Integer, default=1)

    __mapper_args__ = {"version_id_col": version}  # noqa: RUF012


class PatientAppEvent(Base):
    """A note on the patient app timeline: 'Nhắn tin' (``message``) or 'Chăm sóc tại nhà' (``aftercare``).
    The patient app reads it; no channel (Zalo, SMS) is involved."""

    __tablename__ = "patient_app_event"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    kind: Mapped[str] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    created_by: Mapped[UUID | None] = mapped_column(default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientBrief(Base):
    """A brief a doctor edited and approved ('Duyệt & lưu brief'), with the records it was built from."""

    __tablename__ = "patient_brief"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    clinic_id: Mapped[UUID]
    patient_id: Mapped[UUID]
    body: Mapped[str] = mapped_column(Text)
    source_ids: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    approved_by: Mapped[UUID | None] = mapped_column(default=None)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

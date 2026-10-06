"""ORM mapping of the clinic.* tables. Owner: B1. The agent side must never import this (import-linter)."""

from pema.clinic.models.audit import AuditLog
from pema.clinic.models.base import CLINIC_SCHEMA, Base
from pema.clinic.models.care import Consent, Episode, Patient, TreatmentPlan, TreatmentSession
from pema.clinic.models.catalog import Protocol, Room, RoomBlock, Service, ServiceVersion
from pema.clinic.models.clinical import (
    ConsultNote,
    Media,
    PatientAppEvent,
    PatientBrief,
    PatientClinicalNote,
)
from pema.clinic.models.crm import CrmActivity, CrmRule, CrmTask, MessageTemplate
from pema.clinic.models.finance import (
    FinanceNotification,
    FinancePeriod,
    Invoice,
    Payment,
    ProcedureEntry,
    ProcedureEntryPerson,
)
from pema.clinic.models.inbox import ChannelIdentity, Conversation, Message, ReviewItem
from pema.clinic.models.ops import AccountRoster
from pema.clinic.models.orders import CatalogImport, Order, OrderItem, Product
from pema.clinic.models.scheduling import Appointment
from pema.clinic.models.tenant import AuthSession, Clinic, UserAccount

__all__ = [
    "CLINIC_SCHEMA",
    "AccountRoster",
    "Appointment",
    "AuditLog",
    "AuthSession",
    "Base",
    "CatalogImport",
    "ChannelIdentity",
    "Clinic",
    "Consent",
    "ConsultNote",
    "Conversation",
    "CrmActivity",
    "CrmRule",
    "CrmTask",
    "Episode",
    "FinanceNotification",
    "FinancePeriod",
    "Invoice",
    "Media",
    "Message",
    "MessageTemplate",
    "Order",
    "OrderItem",
    "Patient",
    "PatientAppEvent",
    "PatientBrief",
    "PatientClinicalNote",
    "Payment",
    "ProcedureEntry",
    "ProcedureEntryPerson",
    "Product",
    "Protocol",
    "ReviewItem",
    "Room",
    "RoomBlock",
    "Service",
    "ServiceVersion",
    "TreatmentPlan",
    "TreatmentSession",
    "UserAccount",
]

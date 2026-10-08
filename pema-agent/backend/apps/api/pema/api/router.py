"""Aggregates the routers. Order here is the order of tags in the OpenAPI document.

Every router module has ONE owning package (docs/CONTRACTS-AI01.md, section 3). The owner replaces the
``not_implemented()`` bodies in its own files and nothing else; adding a route is a contract change
that goes through package G (``make openapi`` + ``make types``).
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.routing import APIRoute

from pema.api.deps import API_PREFIX
from pema.api.routers import (
    admin_audit,
    admin_crm_rules,
    admin_kb,
    admin_templates,
    admin_users,
    appointments,
    assignment,
    auth,
    conversations,
    crm,
    dashboard,
    finance,
    guide,
    live,
    orders,
    patient_care,
    patient_profile,
    patients,
    resources,
    review_items,
    services,
    staff,
    system,
)

TAGS_METADATA: list[dict[str, str]] = [
    {"name": "auth", "description": "Session, current user, permissions. (B1)"},
    {"name": "patients", "description": "Patients, Patient 360, consent. (B1)"},
    {
        "name": "patient-care",
        "description": "Plans, sessions, consult notes and clinical photos of a patient. (U3)",
    },
    {
        "name": "patient-profile",
        "description": "Patient 360 dialogs: warnings, history and diagnosis, expected return, "
        "patient app notes, templated brief, service added to a course. (U9)",
    },
    {"name": "appointments", "description": "Scheduling and reception transitions. (B1)"},
    {"name": "dashboard", "description": "Clinic KPIs for the owner and the desk. (U2)"},
    {"name": "services", "description": "Service catalog with versioned price and rate terms. (U4)"},
    {"name": "protocols", "description": "Follow-up protocols: milestone days the CRM rules read. (U4)"},
    {
        "name": "finance",
        "description": "Finance PB02: procedure fees, invoices, receipts, monthly periods. (U6)",
    },
    {"name": "orders", "description": "Quick orders: draft, doctor approval, A5 sheets. (U5)"},
    {"name": "catalog", "description": "Product catalog (the clinic's price list) for orders. (U5)"},
    {"name": "resources", "description": "Doctors, rooms and room blocks. (U4)"},
    {"name": "studio", "description": "Before/after photo studio of one patient. (U4)"},
    {"name": "crm", "description": "CSKH tasks and contact log. (B1)"},
    {"name": "guide", "description": "Staff guide and Hoi Pema, backed by the knowledge base. (U7)"},
    {"name": "conversations", "description": "Inbox and messages. (B1)"},
    {"name": "review-items", "description": "Doctor follow-up queue (Theo dõi): alerts from CRM tasks. (B1)"},
    {"name": "live", "description": "Live updates (server-sent events) and presence. (ST-R)"},
    {"name": "staff", "description": "Pickers for every signed-in member: who can be assigned work. (ST-S)"},
    {"name": "assignment", "description": "Who holds a conversation: claim, takeover, release. (O2)"},
    {"name": "admin-crm", "description": "CRM automation rules. (B2)"},
    {"name": "admin-audit", "description": "Audit log reader. (B1)"},
    {"name": "admin-users", "description": "Staff accounts: owner resets a password. (B1)"},
    {"name": "admin-templates", "description": "Doctor-approved message templates. (B1)"},
    {"name": "admin-kb", "description": "Knowledge base. (D3)"},
    {"name": "system", "description": "Health."},
]


def unique_operation_id(route: APIRoute) -> str:
    """``<tag>_<function>`` so generated TypeScript clients get stable, readable names."""
    tag = route.tags[0] if route.tags else "api"
    return f"{str(tag).replace('-', '_')}_{route.name}"


def build_api_router() -> APIRouter:
    api = APIRouter(prefix=API_PREFIX)
    for router in (
        auth.router,
        patients.router,
        patient_care.router,
        patient_profile.router,
        appointments.router,
        dashboard.router,
        services.router,
        services.protocols_router,
        orders.router,
        orders.catalog_router,
        finance.router,
        resources.router,
        resources.studio_router,
        crm.router,
        guide.router,
        conversations.router,
        assignment.router,
        review_items.router,
        live.router,
        staff.router,
        admin_crm_rules.router,
        admin_audit.router,
        admin_users.router,
        admin_templates.router,
        admin_kb.router,
    ):
        api.include_router(router)
    return api


def build_system_router() -> APIRouter:
    return system.router

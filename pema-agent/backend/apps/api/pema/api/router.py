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
    admin_accounts,
    admin_agents,
    admin_audit,
    admin_bot_accounts,
    admin_channels,
    admin_crm_rules,
    admin_friends,
    admin_kb,
    admin_mcp,
    admin_model,
    admin_policy,
    admin_schedules,
    admin_templates,
    admin_threads,
    admin_tools,
    admin_usage,
    admin_users,
    appointments,
    auth,
    care,
    conversations,
    crm,
    live,
    patient_care,
    patients,
    review_items,
    staff,
    system,
    webhooks_zalo_bot,
    webhooks_zalo_bridge,
)

TAGS_METADATA: list[dict[str, str]] = [
    {"name": "auth", "description": "Session, current user, permissions. (B1)"},
    {"name": "patients", "description": "Patients, Patient 360, consent. (B1)"},
    {
        "name": "patient-care",
        "description": "Plans, sessions, consult notes and clinical photos of a patient. (U3)",
    },
    {"name": "appointments", "description": "Scheduling and reception transitions. (B1)"},
    {"name": "crm", "description": "CSKH tasks and contact log. (B1)"},
    {"name": "conversations", "description": "Inbox and messages. (B1)"},
    {"name": "review-items", "description": "Human review queue for agent output. (B1)"},
    {"name": "live", "description": "Live updates (server-sent events) and presence. (ST-R)"},
    {"name": "care", "description": "Supervision of the per-patient care agent and its administration. (M5)"},
    {"name": "staff", "description": "Pickers for every signed-in member: who can be assigned work. (ST-S)"},
    {"name": "webhooks", "description": "Channel webhooks, not for the FE. (C1 Bot API, C2 bridge)"},
    {"name": "admin-crm", "description": "CRM automation rules. (B2)"},
    {"name": "admin-channels", "description": "Channel switchboard and kill switch. (C2)"},
    {"name": "admin-audit", "description": "Audit log reader. (B1)"},
    {"name": "admin-users", "description": "Staff accounts: owner resets a password. (B1)"},
    {"name": "admin-templates", "description": "Doctor-approved message templates. (B1)"},
    {"name": "admin-accounts", "description": "Zalo accounts, QR login, bot token, friends. (C2, C1)"},
    {"name": "admin-bot-accounts", "description": "Bot API token. (C1)"},
    {"name": "admin-agents", "description": "Agents and persona. (D2)"},
    {"name": "admin-threads", "description": "Threads, contacts, memories. (D2)"},
    {"name": "admin-model", "description": "LLM provider, vision, image generation, tuning. (D1)"},
    {"name": "admin-tools", "description": "Tool catalogue and source chains. (D4)"},
    {"name": "admin-kb", "description": "Knowledge base. (D3)"},
    {"name": "admin-schedules", "description": "Scheduled jobs. (S)"},
    {"name": "admin-mcp", "description": "MCP servers and bindings. (D5)"},
    {"name": "admin-usage", "description": "Overview, usage, traces, logs. (D1)"},
    {"name": "admin-policy", "description": "Policy profiles, identity links. (P)"},
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
        appointments.router,
        crm.router,
        conversations.router,
        review_items.router,
        live.router,
        care.router,
        staff.router,
        webhooks_zalo_bot.router,
        webhooks_zalo_bridge.router,
        admin_crm_rules.router,
        admin_channels.router,
        admin_audit.router,
        admin_users.router,
        admin_templates.router,
        admin_accounts.router,
        admin_bot_accounts.router,
        admin_friends.router,
        admin_agents.router,
        admin_threads.router,
        admin_threads.contacts_router,
        admin_threads.memories_router,
        admin_model.router,
        admin_tools.router,
        admin_kb.router,
        admin_schedules.router,
        admin_mcp.router,
        admin_usage.router,
        admin_usage.traces_router,
        admin_usage.logs_router,
        admin_policy.router,
    ):
        api.include_router(router)
    return api


def build_system_router() -> APIRouter:
    return system.router

"""Roles, actor types and permission codes.

The six roles are fixed (docs/CONTRACTS-AI01.md). Authorization is deny-by-default and is enforced in
``pema.clinic.actions`` only; FE and AI never decide access. The role-to-permission matrix is implemented by
the BE core package (B1) from ARCH-PB01; the permission *codes* below are the stable vocabulary.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    DOCTOR = "doctor"
    CS_STAFF = "cs_staff"
    RECEPTION = "reception"
    PATIENT = "patient"


STAFF_ROLES: frozenset[Role] = frozenset(
    {Role.OWNER, Role.MANAGER, Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION}
)
"""Roles that sign in to the staff dashboard (everything except the patient)."""


class ActorType(StrEnum):
    """Who performs an action. The agent worker is an ``agent`` actor, never a sixth role."""

    USER = "user"
    AGENT = "agent"
    SCHEDULER = "scheduler"
    SYSTEM = "system"


class Permission(StrEnum):
    PATIENT_READ = "patient.read"
    PATIENT_WRITE = "patient.write"
    PATIENT_READ_360 = "patient.read_360"
    CONSENT_READ = "consent.read"
    CONSENT_WRITE = "consent.write"
    APPOINTMENT_READ = "appointment.read"
    APPOINTMENT_WRITE = "appointment.write"
    APPOINTMENT_CHECK_IN = "appointment.check_in"
    SESSION_WRITE = "session.write"
    CRM_TASK_READ = "crm.task.read"
    CRM_TASK_RESOLVE = "crm.task.resolve"
    CRM_ACTIVITY_WRITE = "crm.activity.write"
    CONVERSATION_READ = "conversation.read"
    CONVERSATION_REPLY = "conversation.reply"
    REVIEW_READ = "review.read"
    REVIEW_DECIDE = "review.decide"
    REVIEW_DECIDE_CLINICAL = "review.decide_clinical"
    KB_READ = "kb.read"
    KB_MANAGE = "kb.manage"
    ADMIN_RULES = "admin.rules"
    ADMIN_CHANNELS = "admin.channels"
    ADMIN_KILL_SWITCH = "admin.kill_switch"
    ADMIN_LOGS = "admin.logs"
    ADMIN_ACCOUNTS = "admin.accounts"
    """Zalo accounts, QR login, bot token, friends."""
    ADMIN_USERS = "admin.users"
    """Staff accounts of the clinic (reset another user's password). Owner only: a manager manages Zalo
    accounts but must not be able to take over an owner's login."""
    ADMIN_AGENTS = "admin.agents"
    """Agents, persona, per-agent model and tools, threads, memories."""
    ADMIN_MODEL = "admin.model"
    """LLM provider, vision/image settings, tuning parameters."""
    ADMIN_TOOLS = "admin.tools"
    ADMIN_SCHEDULES = "admin.schedules"
    ADMIN_MCP = "admin.mcp"
    ADMIN_USAGE = "admin.usage"
    """Token usage and agent traces (may contain message text: staff-only)."""
    ADMIN_POLICY = "admin.policy"
    """Assign policy profiles, confirm zalo_uid identity links."""
    AGENT_SUBMIT = "agent.submit"
    """Held by the agent worker's actor only: create review items, read minimal context."""

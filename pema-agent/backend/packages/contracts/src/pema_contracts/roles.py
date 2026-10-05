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
    SESSION_READ = "session.read"
    """Read the clinical text of sessions and consult notes (doctor, owner; care staff only for the patients
    they look after: narrowed by the action)."""
    MEDIA_READ = "media.read"
    """See clinical photos of a patient (doctor, owner; care staff only for their patients, and only while the
    patient's media consent is granted)."""
    MEDIA_WRITE = "media.write"
    """Upload clinical photos. Needs the patient's media consent (the action refuses without it)."""
    ORDER_READ = "order.read"
    """Read quick orders (prescriptions and consultation sheets) and the product catalog (a doctor is narrowed
    to own patients by the action; reception and manager see the clinic)."""
    ORDER_WRITE = "order.write"
    """Create and edit DRAFT orders (cashier work: reception, manager, doctor, owner). A draft is not shown on
    the patient app and cannot be printed."""
    ORDER_APPROVE = "order.approve"
    """Approve an order so it can be printed and shown: the responsible doctor (the owner may approve for any
    doctor). Never reception or a manager: the order carries a clinical text."""
    FINANCE_READ = "finance.read"
    """Read the clinic-wide finance projection (PB02): revenue performed, cash collected, debt, the commission
    table of every doctor, invoices and receipts. Owner and the accountant (the manager role)."""
    FINANCE_READ_OWN = "finance.read_own"
    """Read the personal finance projection: only the rows of the caller as a performer, never invoices,
    receipts, debt or the clinic totals. Doctor (and the owner, who is the clinic's doctor)."""
    FINANCE_WRITE = "finance.write"
    """Record performed procedures, approve or void them, close a month and confirm its payout. Owner and the
    accountant. The commission rates and bases live on the service terms (``admin.rules``)."""
    FINANCE_COLLECT = "finance.collect"
    """Raise the invoice of an order and record a receipt on an invoice (cashier work: reception, accountant,
    owner). Holds no read access to the finance projection."""
    FINANCE_NOTIFICATIONS = "finance.notifications"
    """Read the owner's payment notifications and mark them read. Owner only: the accountant does not read the
    owner's inbox."""
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
    ADMIN_USERS_READ = "admin.users.read"
    """List the staff accounts of the clinic (owner and manager). Read only: never a password hash."""
    ADMIN_USERS = "admin.users"
    """Change staff accounts of the clinic: create, rename, change role, lock or unlock, reset another user's
    password. Owner only: a manager manages Zalo accounts but must not be able to take over an owner's
    login."""
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
    CARE_READ = "care.read"
    """See the care agent of a patient (timeline) and the handoffs waiting for the caller."""
    CARE_ACT = "care.act"
    """Accept or decline a handoff, return a conversation to the agent, tell the agent something."""
    CARE_ADMIN = "care.admin"
    """Staff skills and shifts, the 24/7 on-call contact, SLA and the alerts of the care agents."""
    CARE_MATRIX = "care.matrix"
    """Read and edit the depth and autonomy matrix (the thresholds the doctor decides)."""
    CARE_APPROVE = "care.approve"
    """Clear the ``pending_doctor_approval`` badge of the matrix and the timing: doctor, manager, owner."""
    AGENT_SUBMIT = "agent.submit"
    """Held by the agent worker's actor only: create review items, read minimal context."""

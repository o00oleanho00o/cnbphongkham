"""Role to permission matrix. New module: implements the authorization matrix of ``docs/ARCH-PB01.md`` for
the six roles of ``pema_contracts.roles`` (deny by default).

How the columns of the ARCH-PB01 table map to the roles of this system:

=================  ==============================================================================
ARCH-PB01 column   role
=================  ==============================================================================
Le tan             ``reception``
Bac si             ``doctor``
Cham soc           ``cs_staff``
Thu ngan           none: billing is PB02 (finance), not part of the clinic CRM API
Nguoi benh         ``patient`` (the patient app is not a staff session; see ``PATIENT_PERMISSIONS``)
Quan ly            ``manager`` ("Quan tri catalog/role": quan ly)
Chu phong kham     ``owner`` (the prototype's ``staff-context.js`` gives the owner the capabilities
                   clinical, crm, booking, config: owner is a doctor in the demo)
=================  ==============================================================================

Rules that cannot be expressed as a flat permission set (doctor sees only records they own or are
scheduled for; a doctor edits only their own appointments; a CS handles clinical items never) are enforced
in ``pema.clinic.actions`` through ``pema.clinic.rbac.authorize`` and the scope helpers there. The flat set
is the CEILING: an action checks it first, then narrows.
"""

from __future__ import annotations

from collections.abc import Mapping

from pema_contracts.roles import STAFF_ROLES, ActorType, Permission, Role

P = Permission

_STAFF_COMMON: frozenset[Permission] = frozenset({P.KB_READ})

OWNER_PERMISSIONS: frozenset[Permission] = frozenset(set(Permission) - {P.AGENT_SUBMIT})
"""The owner holds every human permission. ``agent.submit`` belongs to the agent actor only."""

MANAGER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        P.PATIENT_READ,
        P.PATIENT_WRITE,
        P.PATIENT_READ_360,
        P.CONSENT_READ,
        P.CONSENT_WRITE,
        P.APPOINTMENT_READ,
        P.APPOINTMENT_WRITE,
        P.APPOINTMENT_CHECK_IN,
        P.ORDER_READ,
        P.ORDER_WRITE,  # not ORDER_APPROVE: the doctor of the order signs it, a manager is not a clinician
        P.FINANCE_READ,  # PB02 "Ke toan": no accountant role exists, the manager holds it (open item)
        P.FINANCE_WRITE,
        P.FINANCE_COLLECT,  # not FINANCE_NOTIFICATIONS: the owner's inbox is the owner's
        P.CRM_TASK_READ,
        P.CRM_TASK_RESOLVE,
        P.CRM_ACTIVITY_WRITE,
        P.CONVERSATION_READ,
        P.CONVERSATION_REPLY,
        P.REVIEW_READ,
        P.REVIEW_DECIDE,
        # not REVIEW_DECIDE_CLINICAL and not SESSION_WRITE: a manager is not a clinician
        P.KB_READ,
        P.KB_MANAGE,
        P.ADMIN_RULES,
        P.ADMIN_CHANNELS,
        P.ADMIN_KILL_SWITCH,
        P.ADMIN_LOGS,
        P.ADMIN_ACCOUNTS,
        P.ADMIN_USERS_READ,  # may LIST staff, never change them (that is ADMIN_USERS, owner only)
        P.ADMIN_AGENTS,
        P.ADMIN_MODEL,
        P.ADMIN_TOOLS,
        P.ADMIN_SCHEDULES,
        P.ADMIN_MCP,
        P.ADMIN_USAGE,
        P.ADMIN_POLICY,
        P.CARE_READ,
        P.CARE_ACT,
        P.CARE_ADMIN,
        P.CARE_MATRIX,
        P.CARE_APPROVE,
    }
)

DOCTOR_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        P.PATIENT_READ,  # narrowed to own / scheduled patients by the action
        P.PATIENT_READ_360,
        P.CONSENT_READ,
        P.CONSENT_WRITE,
        P.APPOINTMENT_READ,  # "xem lich": all
        P.APPOINTMENT_WRITE,  # "gioi han": own appointments only (action)
        P.APPOINTMENT_CHECK_IN,  # "gioi han": own appointments only (action)
        P.SESSION_WRITE,
        P.SESSION_READ,
        P.MEDIA_READ,  # narrowed to own / scheduled patients by the action
        P.MEDIA_WRITE,
        P.ORDER_READ,  # narrowed to own / scheduled patients by the action
        P.ORDER_WRITE,
        P.ORDER_APPROVE,  # only the orders of which the caller is the responsible doctor (action)
        P.FINANCE_READ_OWN,  # PB02: the rows where the caller is a performer, nothing clinic-wide
        P.CRM_TASK_READ,  # D+7 review of own patients only (action)
        P.CRM_TASK_RESOLVE,  # idem
        P.CRM_ACTIVITY_WRITE,  # own patients only (action)
        P.CONVERSATION_READ,  # follow-up replies
        P.CONVERSATION_REPLY,
        P.REVIEW_READ,
        P.REVIEW_DECIDE,
        P.REVIEW_DECIDE_CLINICAL,  # "Duyet prescription/AI draft": doctor only (with the owner)
        P.KB_READ,
        P.KB_MANAGE,  # doctor sign-off on KB documents (approved_by_clinical_owner)
        P.CARE_READ,  # narrowed to own patients by the service (like the inbox)
        P.CARE_ACT,
        P.CARE_MATRIX,  # the thresholds are the doctor's decision (PLAN-AI01-M section 15.1)
        P.CARE_APPROVE,
    }
)

CS_STAFF_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        P.PATIENT_READ,
        P.PATIENT_WRITE,
        P.PATIENT_READ_360,
        P.CONSENT_READ,
        P.CONSENT_WRITE,
        P.APPOINTMENT_READ,
        # no APPOINTMENT_WRITE / CHECK_IN: "Sua lich/check-in: cham soc X". Booking from a CRM task goes
        # through CRM_TASK_RESOLVE (the prototype gives the care role the 'booking' capability only there).
        # "Ghi session: cham soc theo phan cong": care staff read (and upload photos for) the patients they
        # look after only; they never write a session or a note (SESSION_WRITE stays clinical)
        P.SESSION_READ,
        P.MEDIA_READ,
        P.MEDIA_WRITE,
        P.CRM_TASK_READ,
        P.CRM_TASK_RESOLVE,
        P.CRM_ACTIVITY_WRITE,
        P.CONVERSATION_READ,
        P.CONVERSATION_REPLY,
        P.REVIEW_READ,
        P.REVIEW_DECIDE,  # non-clinical items only; never REVIEW_DECIDE_CLINICAL
        P.KB_READ,
        P.CARE_READ,  # supervises the agent of the patients they look after; no matrix, no admin
        P.CARE_ACT,
    }
)

RECEPTION_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        P.PATIENT_READ,  # identity and schedule only: no Patient 360, no conversations
        P.PATIENT_WRITE,
        P.CONSENT_READ,
        P.CONSENT_WRITE,
        P.APPOINTMENT_READ,
        P.APPOINTMENT_WRITE,
        P.APPOINTMENT_CHECK_IN,
        P.ORDER_READ,  # "Thu ngân lên đơn": the cashier work of the clinic has no role of its own (open item)
        P.ORDER_WRITE,
        P.FINANCE_COLLECT,  # the cashier records receipts; it reads no finance totals
        P.KB_READ,
    }
)

PATIENT_PERMISSIONS: frozenset[Permission] = frozenset()
"""Deny by default. "Nguoi benh: cua minh" needs a link from a patient session to a ``clinic.patient`` row
(there is no such column yet): open item for the patient-app package. Until then the patient role holds no
staff permission and every staff route answers 403."""

ROLE_PERMISSIONS: Mapping[Role, frozenset[Permission]] = {
    Role.OWNER: OWNER_PERMISSIONS,
    Role.MANAGER: MANAGER_PERMISSIONS,
    Role.DOCTOR: DOCTOR_PERMISSIONS,
    Role.CS_STAFF: CS_STAFF_PERMISSIONS,
    Role.RECEPTION: RECEPTION_PERMISSIONS,
    Role.PATIENT: PATIENT_PERMISSIONS,
}

AGENT_PERMISSIONS: frozenset[Permission] = frozenset({P.AGENT_SUBMIT})
"""The agent worker may create review items and read a minimal care context, nothing else."""

SCHEDULER_PERMISSIONS: frozenset[Permission] = frozenset(
    {
        P.PATIENT_READ,
        P.CONSENT_READ,
        P.APPOINTMENT_READ,
        P.CRM_TASK_READ,
        P.REVIEW_READ,
        P.AGENT_SUBMIT,
    }
)
"""Scheduler and CRM rule engine: read context, raise review items. They create tasks through their own
package, not through the REST actions."""

CLINICAL_ROLES: frozenset[Role] = frozenset({Role.OWNER, Role.DOCTOR})
"""Roles allowed to see and decide clinical review items (``requires_doctor``)."""


ASSIGNABLE_ROLES: frozenset[Role] = frozenset(
    role for role in STAFF_ROLES if ROLE_PERMISSIONS[role] & {P.CONVERSATION_REPLY, P.CRM_TASK_RESOLVE}
)
"""Roles a task, a conversation or a patient's "Phụ trách" can be handed to (ST-S): staff who can
actually work the item, that is who hold ``conversation.reply`` or ``crm_task.resolve``. Derived from the
matrix above, not a second list, so a role that gains or loses those permissions follows. Today: owner,
manager, doctor, cs_staff. Reception is excluded (no conversations, no CRM queue: an item handed to them
would sit unseen) and so is ``patient`` (not a staff role). Whether a role may be assigned is separate
from who may assign: that is the permission of the action (``conversation.reply``,
``crm_task.resolve``, ``patient.write``)."""


def permissions_for(actor_type: ActorType, role: Role | None) -> frozenset[Permission]:
    """Permission ceiling of an actor. ``system`` (seeding, migrations of data) may do everything."""
    if actor_type is ActorType.USER:
        return ROLE_PERMISSIONS.get(role, frozenset()) if role is not None else frozenset()
    if actor_type is ActorType.AGENT:
        return AGENT_PERMISSIONS
    if actor_type is ActorType.SCHEDULER:
        return SCHEDULER_PERMISSIONS
    return frozenset(Permission)

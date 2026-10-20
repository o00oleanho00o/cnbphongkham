"""The role to permission matrix of ARCH-PB01, deny by default. Pure: no database."""

from __future__ import annotations

from uuid import uuid4

import pytest

from pema.clinic.rbac import (
    AGENT_PERMISSIONS,
    ROLE_PERMISSIONS,
    SCHEDULER_PERMISSIONS,
    has_permission,
    is_clinical,
    permissions_for,
    require,
    require_any,
)
from pema_contracts.actions import ActionContext
from pema_contracts.errors import DomainError, ErrorCode
from pema_contracts.roles import ActorType, Permission, Role

P = Permission


def _ctx(role: Role | None, actor: ActorType = ActorType.USER) -> ActionContext:
    return ActionContext(clinic_id=uuid4(), actor_type=actor, actor_user_id=uuid4(), actor_role=role)


def test_every_role_of_the_system_has_an_entry_and_the_patient_has_none() -> None:
    assert set(ROLE_PERMISSIONS) == set(Role)
    assert ROLE_PERMISSIONS[Role.PATIENT] == frozenset()


AGENT_GATEWAY = {
    P.AGENT_SLOTS_READ,
    P.AGENT_CONTACT_WRITE,
    P.AGENT_BOOKING_WRITE,
    P.AGENT_APPOINTMENT_READ,
    P.AGENT_APPOINTMENT_CHANGE,
    P.AGENT_REMINDERS_READ,
}


def test_owner_holds_every_staff_permission_and_the_agent_only_the_gateway() -> None:
    """T7 (L2, L4): the agent holds the six gateway permissions and nothing else; no role holds any of them"""
    assert ROLE_PERMISSIONS[Role.OWNER] == frozenset(Permission) - AGENT_GATEWAY
    assert AGENT_PERMISSIONS == AGENT_GATEWAY
    assert {p for p in Permission if p.value.startswith("agent.")} == AGENT_GATEWAY
    for role, permissions in ROLE_PERMISSIONS.items():
        assert not permissions & AGENT_GATEWAY, role


def test_every_permission_code_is_granted_to_someone() -> None:
    granted: set[Permission] = set()
    for permissions in (*ROLE_PERMISSIONS.values(), AGENT_PERMISSIONS):
        granted |= permissions
    assert set(Permission) - granted == set()


@pytest.mark.parametrize(
    ("permission", "allowed", "denied"),
    [
        # ARCH-PB01: "Xem identity/lich": reception, doctor, care
        (P.APPOINTMENT_READ, {Role.RECEPTION, Role.DOCTOR, Role.CS_STAFF}, {Role.PATIENT}),
        # "Sua lich/check-in": reception yes, doctor limited (own only: enforced in the action), care no
        (P.APPOINTMENT_WRITE, {Role.RECEPTION, Role.DOCTOR}, {Role.CS_STAFF, Role.PATIENT}),
        (P.APPOINTMENT_CHECK_IN, {Role.RECEPTION, Role.DOCTOR}, {Role.CS_STAFF, Role.PATIENT}),
        # "Ghi session": doctor; reception no
        (P.SESSION_WRITE, {Role.DOCTOR}, {Role.RECEPTION, Role.CS_STAFF, Role.MANAGER, Role.PATIENT}),
        # package U3: clinical text of sessions and notes, and clinical photos. Care staff read and upload for their
        # own patients (the action narrows it), never write a session; reception and manager see none of it.
        (
            P.SESSION_READ,
            {Role.DOCTOR, Role.CS_STAFF, Role.OWNER},
            {Role.RECEPTION, Role.MANAGER, Role.PATIENT},
        ),
        (
            P.MEDIA_READ,
            {Role.DOCTOR, Role.CS_STAFF, Role.OWNER},
            {Role.RECEPTION, Role.MANAGER, Role.PATIENT},
        ),
        (
            P.MEDIA_WRITE,
            {Role.DOCTOR, Role.CS_STAFF, Role.OWNER},
            {Role.RECEPTION, Role.MANAGER, Role.PATIENT},
        ),
        # reception sees identity and schedule, not the 360
        (P.PATIENT_READ, {Role.RECEPTION, Role.DOCTOR, Role.CS_STAFF, Role.MANAGER}, {Role.PATIENT}),
        (P.PATIENT_READ_360, {Role.DOCTOR, Role.CS_STAFF, Role.MANAGER}, {Role.RECEPTION, Role.PATIENT}),
        (P.CRM_TASK_READ, {Role.CS_STAFF, Role.DOCTOR, Role.MANAGER}, {Role.RECEPTION, Role.PATIENT}),
        # "Quan tri catalog/role": manager; nobody else but the owner
        (
            P.ADMIN_RULES,
            {Role.MANAGER, Role.OWNER},
            {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT},
        ),
        (
            P.ADMIN_LOGS,
            {Role.MANAGER, Role.OWNER},
            {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT},
        ),
        (P.ADMIN_ACCOUNTS, {Role.MANAGER, Role.OWNER}, {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION}),
        (P.ADMIN_USAGE, {Role.MANAGER, Role.OWNER}, {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION}),
        # resetting another staff member's password (SEC-24): the owner alone, a manager cannot take over a login
        (
            P.ADMIN_USERS,
            {Role.OWNER},
            {Role.MANAGER, Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT},
        ),
        # listing staff (H4): owner and manager read, nobody else; changing them stays the owner's alone
        (
            P.ADMIN_USERS_READ,
            {Role.OWNER, Role.MANAGER},
            {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT},
        ),
        (P.KB_MANAGE, {Role.MANAGER, Role.OWNER, Role.DOCTOR}, {Role.CS_STAFF, Role.RECEPTION, Role.PATIENT}),
        # package U, steps U6 and U11 (PB02 finance): the accountant is a role of its own (U11) and the manager
        # keeps the same finance rights. The clinic projection and every write are theirs and the owner's; a
        # doctor reads only the personal one; reception only collects; the owner's payment notifications are the
        # owner's alone.
        (
            P.FINANCE_READ,
            {Role.OWNER, Role.MANAGER, Role.ACCOUNTANT},
            {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT},
        ),
        (
            P.FINANCE_READ_OWN,
            {Role.OWNER, Role.DOCTOR},
            {Role.MANAGER, Role.CS_STAFF, Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT},
        ),
        (
            P.FINANCE_WRITE,
            {Role.OWNER, Role.MANAGER, Role.ACCOUNTANT},
            {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT},
        ),
        (
            P.FINANCE_PERIOD_CLOSE,
            {Role.OWNER, Role.MANAGER, Role.ACCOUNTANT},
            {Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.PATIENT},
        ),
        (
            P.FINANCE_COLLECT,
            {Role.OWNER, Role.MANAGER, Role.RECEPTION, Role.ACCOUNTANT},
            {Role.DOCTOR, Role.CS_STAFF, Role.PATIENT},
        ),
        (
            P.FINANCE_NOTIFICATIONS,
            {Role.OWNER},
            {Role.MANAGER, Role.DOCTOR, Role.CS_STAFF, Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT},
        ),
    ],
)
def test_matrix_row(permission: Permission, allowed: set[Role], denied: set[Role]) -> None:
    for role in allowed:
        assert permission in ROLE_PERMISSIONS[role], f"{role.value} must hold {permission.value}"
    for role in denied:
        assert permission not in ROLE_PERMISSIONS[role], f"{role.value} must NOT hold {permission.value}"


def test_a_user_without_a_role_has_no_permission() -> None:
    assert permissions_for(ActorType.USER, None) == frozenset()


def test_system_may_do_everything_agent_and_scheduler_only_their_sets() -> None:
    assert permissions_for(ActorType.SYSTEM, None) == frozenset(Permission)
    assert permissions_for(ActorType.AGENT, None) == AGENT_PERMISSIONS
    assert permissions_for(ActorType.SCHEDULER, None) == SCHEDULER_PERMISSIONS


def test_require_raises_forbidden_with_the_missing_permission() -> None:
    with pytest.raises(DomainError) as caught:
        require(_ctx(Role.RECEPTION), P.SESSION_WRITE)
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert caught.value.http_status == 403
    assert caught.value.details == {"permission": "session.write"}
    require(_ctx(Role.DOCTOR), P.SESSION_WRITE)


def test_require_any_needs_one_of_them() -> None:
    require_any(_ctx(Role.CS_STAFF), (P.APPOINTMENT_WRITE, P.CRM_TASK_RESOLVE))
    with pytest.raises(DomainError):
        require_any(_ctx(Role.RECEPTION), (P.CRM_TASK_RESOLVE, P.SESSION_WRITE))


def test_an_agent_actor_holds_no_staff_permission() -> None:
    agent = _ctx(None, ActorType.AGENT)
    assert {p for p in Permission if has_permission(agent, p)} == AGENT_GATEWAY


def test_only_owner_and_doctor_are_clinical() -> None:
    assert is_clinical(_ctx(Role.DOCTOR))
    assert is_clinical(_ctx(Role.OWNER))
    for role in (Role.MANAGER, Role.CS_STAFF, Role.RECEPTION, Role.ACCOUNTANT, Role.PATIENT):
        assert not is_clinical(_ctx(role))

// Who a task or a conversation can be handed to, as the backend decides it (backend
// pema/clinic/actions/assignees.py): ACTIVE staff whose role can work conversations and CRM tasks. Reception cannot
// (no Inbox, no CRM queue) and `patient` is not staff. One list for `GET /api/v1/staff/assignable` and for the
// checks of the routes that accept an assignee, so the mock cannot drift from itself.
import { USERS, type MockUser } from "./auth";
import { fail, type Role } from "./core";

export const ASSIGNABLE_ROLES: readonly Role[] = ["owner", "manager", "doctor", "cs_staff"];

/** The one answer for an unknown, locked or non-assignable target (it must not tell which accounts exist). */
export const INVALID_ASSIGNEE = "Người được giao không hợp lệ.";

function byName(a: MockUser, b: MockUser): number {
  const order = a.display_name.toLowerCase().localeCompare(b.display_name.toLowerCase());
  return order !== 0 ? order : a.id.localeCompare(b.id);
}

/** Active users with an assignable role, A to Z by name (ties by id). */
export function assignableUsers(): MockUser[] {
  return USERS.filter((u) => u.active && ASSIGNABLE_ROLES.includes(u.role)).toSorted(byName);
}

/** 422 `validation_failed` unless `userId` is an active user with an assignable role. */
export function assertAssignable(userId: string, message: string = INVALID_ASSIGNEE): void {
  if (!assignableUsers().some((u) => u.id === userId)) fail(422, "validation_failed", message);
}

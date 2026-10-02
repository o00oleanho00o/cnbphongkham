// Options of a "Phụ trách" box (a CRM task in "Việc hôm nay", a conversation in the Inbox). They always start with
// "Tôi" and, when somebody else already owns the item, "Giữ nguyên: <name>"; after those come the other staff
// from `GET /api/v1/staff/assignable`. The person already shown is never listed twice. The BE decides whether the
// hand-over is allowed; this only builds the choices and turns the chosen value into a user id.
import type { SelectOption } from "@/components/admin/shared/select-menu";
import type { AssignableStaff } from "@/lib/live/live-types";
import { ROLE_LABEL } from "@/lib/session/session-context";

export const OWNER_ME = "me";
export const OWNER_KEEP = "keep";

const UNKNOWN_OWNER = "người phụ trách hiện tại";

export type OwnerOptionsInput = {
  me: { id: string; display_name: string };
  /** Who owns the item now (null: nobody). */
  currentId: string | null | undefined;
  /** Name the item already carries, when it has one; otherwise it is looked up in `staff`. */
  currentName?: string | null;
  staff: readonly AssignableStaff[];
  /** Offer "Giữ nguyên" also when nobody owns the item (the Inbox shows it as the selected value). */
  keepWhenUnassigned?: boolean;
};

function currentNameOf({ currentId, currentName, staff }: OwnerOptionsInput): string {
  if (currentName) return currentName;
  return staff.find((s) => s.id === currentId)?.name ?? UNKNOWN_OWNER;
}

function keepOption(input: OwnerOptionsInput): SelectOption[] {
  const { currentId, me, keepWhenUnassigned } = input;
  if (!currentId) {
    return keepWhenUnassigned ? [{ value: OWNER_KEEP, label: "Giữ nguyên: chưa giao" }] : [];
  }
  if (currentId === me.id) return [];
  return [{ value: OWNER_KEEP, label: `Giữ nguyên: ${currentNameOf(input)}` }];
}

export function ownerOptions(input: OwnerOptionsInput): SelectOption[] {
  const { me, currentId, staff } = input;
  const others = staff
    .filter((s) => s.id !== me.id && s.id !== currentId)
    .map((s) => ({ value: s.id, label: `${s.name} (${ROLE_LABEL[s.role]})` }));
  return [{ value: OWNER_ME, label: `Tôi (${me.display_name})` }, ...keepOption(input), ...others];
}

/** The option that is selected when the box opens. */
export function initialOwnerValue(input: OwnerOptionsInput): string {
  if (input.currentId && input.currentId === input.me.id) return OWNER_ME;
  return input.currentId || input.keepWhenUnassigned ? OWNER_KEEP : OWNER_ME;
}

/** User id the chosen value stands for; null when the value means "leave it as it is" with nobody owning it. */
export function ownerIdFor(
  value: string,
  me: { id: string },
  currentId: string | null | undefined,
): string | null {
  if (value === OWNER_ME) return me.id;
  if (value === OWNER_KEEP) return currentId ?? null;
  return value;
}

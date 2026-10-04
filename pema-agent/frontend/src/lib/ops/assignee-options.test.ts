import { describe, expect, it } from "vitest";

import type { AssignableStaff } from "@/lib/staff/assignable-staff";
import {
  OWNER_KEEP,
  OWNER_ME,
  OWNER_NONE,
  initialOwnerValue,
  ownerIdFor,
  ownerOptions,
} from "@/lib/ops/assignee-options";

const me = { id: "u-me", display_name: "Mai Anh" };
const STAFF: AssignableStaff[] = [
  { id: "u-me", name: "Mai Anh", role: "cs_staff" },
  { id: "u-lan", name: "Bùi Ngọc Lan", role: "manager" },
  { id: "u-tam", name: "BS. Lê Minh Tâm", role: "doctor" },
];

function values(options: { value: string }[]): string[] {
  return options.map((o) => o.value);
}

describe("ownerOptions", () => {
  it("starts with Tôi and lists the other staff with their role", () => {
    const options = ownerOptions({ me, currentId: null, staff: STAFF });
    expect(values(options)).toEqual([OWNER_ME, "u-lan", "u-tam"]);
    expect(options[0]?.label).toBe("Tôi (Mai Anh)");
    expect(options[1]?.label).toBe("Bùi Ngọc Lan (Quản lý)");
  });

  it("offers Giữ nguyên with the current owner's name and does not list that person twice", () => {
    const options = ownerOptions({
      me,
      currentId: "u-lan",
      currentName: "Bùi Ngọc Lan",
      staff: STAFF,
    });
    expect(values(options)).toEqual([OWNER_ME, OWNER_KEEP, "u-tam"]);
    expect(options[1]?.label).toBe("Giữ nguyên: Bùi Ngọc Lan");
  });

  it("finds the current owner's name in the staff list when the item carries none", () => {
    const options = ownerOptions({ me, currentId: "u-tam", staff: STAFF });
    expect(options[1]?.label).toBe("Giữ nguyên: BS. Lê Minh Tâm");
  });

  it("still offers Tôi and Giữ nguyên while the staff list is not loaded", () => {
    const options = ownerOptions({ me, currentId: "u-lan", staff: [] });
    expect(values(options)).toEqual([OWNER_ME, OWNER_KEEP]);
    expect(options[1]?.label).toBe("Giữ nguyên: người phụ trách hiện tại");
  });

  it("offers Chưa giao after Giữ nguyên only when asked and only while somebody owns the item", () => {
    const owned = ownerOptions({ me, currentId: "u-lan", staff: STAFF, allowUnassign: true });
    expect(values(owned)).toEqual([OWNER_ME, OWNER_KEEP, OWNER_NONE, "u-tam"]);
    expect(owned[2]?.label).toBe("Chưa giao");
    const mine = ownerOptions({ me, currentId: "u-me", staff: STAFF, allowUnassign: true });
    expect(values(mine)).toEqual([OWNER_ME, OWNER_NONE, "u-lan", "u-tam"]);
    const nobody = ownerOptions({ me, currentId: null, staff: [], allowUnassign: true });
    expect(values(nobody)).toEqual([OWNER_ME]);
    const notAsked = ownerOptions({ me, currentId: "u-lan", staff: STAFF });
    expect(values(notAsked)).not.toContain(OWNER_NONE);
  });

  it("has no Giữ nguyên when the item is mine, or when nobody owns it (unless asked)", () => {
    expect(values(ownerOptions({ me, currentId: "u-me", staff: STAFF }))).toEqual([
      OWNER_ME,
      "u-lan",
      "u-tam",
    ]);
    expect(values(ownerOptions({ me, currentId: null, staff: [] }))).toEqual([OWNER_ME]);
    const unassigned = ownerOptions({ me, currentId: null, staff: [], keepWhenUnassigned: true });
    expect(values(unassigned)).toEqual([OWNER_ME, OWNER_KEEP]);
  });
});

describe("initialOwnerValue", () => {
  it("is Tôi when the item is mine or unowned, Giữ nguyên when somebody else owns it", () => {
    expect(initialOwnerValue({ me, currentId: "u-me", staff: [] })).toBe(OWNER_ME);
    expect(initialOwnerValue({ me, currentId: null, staff: [] })).toBe(OWNER_ME);
    expect(initialOwnerValue({ me, currentId: "u-lan", staff: [] })).toBe(OWNER_KEEP);
  });

  it("is Giữ nguyên for an unowned item when the box shows it (the Inbox)", () => {
    expect(initialOwnerValue({ me, currentId: null, staff: [], keepWhenUnassigned: true })).toBe(
      OWNER_KEEP,
    );
  });
});

describe("ownerIdFor", () => {
  it("maps Tôi to me, Giữ nguyên to the current owner and a staff id to itself", () => {
    expect(ownerIdFor(OWNER_ME, me, "u-lan")).toBe("u-me");
    expect(ownerIdFor(OWNER_KEEP, me, "u-lan")).toBe("u-lan");
    expect(ownerIdFor(OWNER_KEEP, me, null)).toBeNull();
    expect(ownerIdFor("u-tam", me, "u-lan")).toBe("u-tam");
    expect(ownerIdFor(OWNER_NONE, me, "u-lan")).toBeNull();
  });
});

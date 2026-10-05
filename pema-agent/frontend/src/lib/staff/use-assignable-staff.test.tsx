// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AssignableStaff } from "@/lib/staff/assignable-staff";
import { useAssignableStaff } from "@/lib/staff/use-assignable-staff";

const api = vi.hoisted(() => ({ fetch: vi.fn(), invalidate: vi.fn() }));

vi.mock("@/lib/staff/assignable-staff", () => ({
  fetchAssignableStaff: (...args: unknown[]) => api.fetch(...args),
  invalidateAssignableStaff: () => api.invalidate(),
}));

const STAFF: AssignableStaff[] = [{ id: "u-1", name: "Mai Anh", role: "cs_staff" }];

beforeEach(() => {
  api.fetch.mockReset().mockResolvedValue(STAFF);
  api.invalidate.mockReset();
});

afterEach(() => cleanup());

describe("useAssignableStaff", () => {
  it("starts loading with an empty list, then returns the staff", async () => {
    const { result } = renderHook(() => useAssignableStaff());
    expect(result.current.loading).toBe(true);
    expect(result.current.staff).toEqual([]);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.staff).toEqual(STAFF);
    expect(result.current.error).toBe("");
  });

  it("keeps an empty list and exposes the message when the list cannot be read", async () => {
    api.fetch.mockReset().mockRejectedValue(new Error("Quá nhiều lần"));
    const { result } = renderHook(() => useAssignableStaff());

    await waitFor(() => expect(result.current.error).toBe("Quá nhiều lần"));
    expect(result.current.staff).toEqual([]);
    expect(result.current.loading).toBe(false);
  });

  it("reload drops the shared answer and reads again", async () => {
    api.fetch.mockReset().mockRejectedValueOnce(new Error("Lỗi 500"));
    api.fetch.mockResolvedValue(STAFF);
    const { result } = renderHook(() => useAssignableStaff());
    await waitFor(() => expect(result.current.error).toBe("Lỗi 500"));

    act(() => result.current.reload());

    await waitFor(() => expect(result.current.staff).toEqual(STAFF));
    expect(api.invalidate).toHaveBeenCalledTimes(1);
    expect(result.current.error).toBe("");
  });

  it("keeps the same list object while nothing changed, so pickers do not rebuild their options", () => {
    api.fetch.mockReset().mockReturnValue(new Promise(() => undefined));
    const { result, rerender } = renderHook(() => useAssignableStaff());
    const first = result.current.staff;
    rerender();
    expect(result.current.staff).toBe(first);
  });
});

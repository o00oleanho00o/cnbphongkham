import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "@/lib/api/client";
import {
  ASSIGNABLE_STAFF_TTL_MS,
  fetchAssignableStaff,
  invalidateAssignableStaff,
  type AssignableStaff,
} from "@/lib/staff/assignable-staff";

const api = vi.hoisted(() => ({ get: vi.fn() }));

vi.mock("@/lib/api/client", async (importActual) => {
  const actual = await importActual<typeof import("@/lib/api/client")>();
  return { ...actual, http: { GET: (...args: unknown[]) => api.get(...args) } };
});

const STAFF: AssignableStaff[] = [
  { id: "u-1", name: "Mai Anh", role: "cs_staff" },
  { id: "u-2", name: "BS. Lê Minh Tâm", role: "doctor" },
];

function answer(data: unknown, status = 200) {
  return Promise.resolve({
    data: status === 200 ? data : undefined,
    error:
      status === 200 ? undefined : { error: { code: "rate_limited", message: "Quá nhiều lần" } },
    response: new Response(null, { status }),
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  invalidateAssignableStaff();
  api.get.mockReset().mockImplementation(() => answer(STAFF));
});

afterEach(() => vi.useRealTimers());

describe("fetchAssignableStaff", () => {
  it("calls GET /api/v1/staff/assignable of the typed client and returns the rows as they are", async () => {
    const rows = await fetchAssignableStaff();
    expect(rows).toEqual(STAFF);
    expect(api.get).toHaveBeenCalledTimes(1);
    expect(api.get.mock.calls[0]?.[0]).toBe("/api/v1/staff/assignable");
  });

  it("shares one answer between callers for a minute, so switching conversations does not call again", async () => {
    await fetchAssignableStaff();
    await fetchAssignableStaff();
    expect(api.get).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(ASSIGNABLE_STAFF_TTL_MS + 1);
    await fetchAssignableStaff();
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it("joins a call that is still on its way instead of starting a second one", async () => {
    const [a, b] = await Promise.all([fetchAssignableStaff(), fetchAssignableStaff()]);
    expect(a).toEqual(b);
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it("never keeps a failed answer: the next call asks again, and the error is the BE's message", async () => {
    api.get.mockImplementationOnce(() => answer(undefined, 429));
    await expect(fetchAssignableStaff()).rejects.toMatchObject({
      status: 429,
      message: "Quá nhiều lần",
    });
    await expect(fetchAssignableStaff()).resolves.toEqual(STAFF);
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it("invalidate forces the next call to ask again", async () => {
    await fetchAssignableStaff();
    invalidateAssignableStaff();
    await fetchAssignableStaff();
    expect(api.get).toHaveBeenCalledTimes(2);
  });

  it("lets one caller give up without cancelling the call another caller waits for", async () => {
    let finish: (value: unknown) => void = () => undefined;
    api.get.mockImplementationOnce(() => new Promise((resolve) => (finish = resolve)));
    const quitter = new AbortController();
    const abandoned = fetchAssignableStaff(quitter.signal);
    const patient = fetchAssignableStaff();

    quitter.abort();
    await expect(abandoned).rejects.toMatchObject({ name: "AbortError" });
    finish({ data: STAFF, response: new Response(null, { status: 200 }) });

    await expect(patient).resolves.toEqual(STAFF);
    expect(api.get).toHaveBeenCalledTimes(1);
  });

  it("is already cancelled when the caller's signal is", async () => {
    const quitter = new AbortController();
    quitter.abort();
    await expect(fetchAssignableStaff(quitter.signal)).rejects.toMatchObject({
      name: "AbortError",
    });
  });

  it("an error from the BE is an ApiError", async () => {
    api.get.mockImplementationOnce(() => answer(undefined, 403));
    await expect(fetchAssignableStaff()).rejects.toBeInstanceOf(ApiError);
  });
});

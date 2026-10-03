// The schedule and dashboard routes of the mock behave like backend `pema/clinic/actions/appointments.py` and
// `dashboard.py`: the board lists a day or seven days (a doctor only their own), a transition needs the right
// permission and the right starting status, the hours and double-booking rules answer in the BE's sentences, and
// the KPIs are counted from the rows, with no money in them.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { DOCTOR_AN, DOCTOR_TAM, clinicToday, patientRef } from "./data/clinic";
import { startMockServer } from "./server";

let server: Server;
let base: string;

beforeAll(async () => {
  server = await startMockServer(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
});

afterAll(() => {
  server.close();
});

async function signIn(email: string): Promise<string> {
  const res = await fetch(`${base}/api/v1/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password: "demo1234" }),
  });
  expect(res.status).toBe(200);
  return res.headers.get("set-cookie")?.split(";")[0] ?? "";
}

function call(cookie: string, method: string, path: string, body?: unknown): Promise<Response> {
  return fetch(`${base}${path}`, {
    method,
    headers: { "content-type": "application/json", ...(cookie ? { cookie } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

type Item = {
  id: string;
  status: string;
  version: number;
  doctor_id: string | null;
  patient_name: string | null;
  starts_at: string;
};
type Board = {
  view: string;
  from_day: string;
  to_day: string;
  items: Item[];
  doctors: { id: string; name: string }[];
};

const board = async (cookie: string, query: string): Promise<Board> =>
  (await (await call(cookie, "GET", `/api/v1/appointments/schedule?${query}`)).json()) as Board;

describe("schedule board (mock)", () => {
  it("lists_the_day_in_time_order_with_names_for_a_role_that_reads_patients", async () => {
    const reception = await signIn("reception@pema.test");
    const day = await board(reception, `day=${clinicToday()}`);

    expect(day.view).toBe("day");
    expect(day.from_day).toBe(day.to_day);
    expect(day.items.length).toBeGreaterThanOrEqual(8);
    expect(day.items.every((i) => i.patient_name !== null)).toBe(true);
    expect(day.items.map((i) => i.starts_at)).toEqual(day.items.map((i) => i.starts_at).toSorted());
  });

  it("has_every_reception_status_on_the_demo_day", async () => {
    const reception = await signIn("reception@pema.test");
    const statuses = new Set(
      (await board(reception, `day=${clinicToday()}`)).items.map((i) => i.status),
    );

    ["booked", "confirmed", "arrived", "in_progress", "completed", "missed", "cancelled"].forEach(
      (s) => expect(statuses.has(s)).toBe(true),
    );
  });

  it("spans_seven_days_in_the_week_view", async () => {
    const owner = await signIn("owner@pema.test");
    const week = await board(owner, `day=${clinicToday()}&view=week`);

    expect(week.view).toBe("week");
    expect(week.to_day > week.from_day).toBe(true);
    expect(week.items.length).toBeGreaterThan(
      (await board(owner, `day=${clinicToday()}`)).items.length,
    );
  });

  it("filters_by_doctor_for_the_desk_and_forces_the_own_board_for_a_doctor", async () => {
    const reception = await signIn("reception@pema.test");
    const own = await board(reception, `day=${clinicToday()}&doctor_id=${DOCTOR_AN}`);
    expect(own.items.every((i) => i.doctor_id === DOCTOR_AN)).toBe(true);

    const tam = await signIn("doctor@pema.test");
    const asked = await board(tam, `day=${clinicToday()}&doctor_id=${DOCTOR_AN}`);
    expect(asked.items.every((i) => i.doctor_id === DOCTOR_TAM)).toBe(true);
    expect(asked.doctors.map((d) => d.id)).toEqual([DOCTOR_TAM]);
  });

  it("refuses_a_missing_or_malformed_day", async () => {
    const reception = await signIn("reception@pema.test");

    expect((await call(reception, "GET", "/api/v1/appointments/schedule")).status).toBe(422);
    expect(
      (await call(reception, "GET", "/api/v1/appointments/schedule?day=20-09-2026")).status,
    ).toBe(422);
  });
});

describe("reception transitions (mock)", () => {
  async function bookedToday(cookie: string): Promise<Item> {
    const day = await board(cookie, `day=${clinicToday()}`);
    const found = day.items.find((i) => i.status === "booked");
    if (!found) throw new Error("no booked visit in the mock day");
    return found;
  }

  it("confirm_moves_a_booked_visit_once_and_a_second_try_is_an_invalid_state", async () => {
    const reception = await signIn("reception@pema.test");
    const visit = await bookedToday(reception);
    const first = await call(reception, "POST", `/api/v1/appointments/${visit.id}/confirm`, {
      version: visit.version,
    });
    const again = await call(reception, "POST", `/api/v1/appointments/${visit.id}/confirm`, {
      version: visit.version + 1,
    });

    expect(((await first.json()) as Item).status).toBe("confirmed");
    expect(again.status).toBe(409);
  });

  it("a_stale_version_is_a_conflict", async () => {
    const reception = await signIn("reception@pema.test");
    const day = await board(reception, `day=${clinicToday()}`);
    const visit = day.items.find((i) => i.status === "confirmed");
    if (!visit) throw new Error("no confirmed visit in the mock day");

    const res = await call(reception, "POST", `/api/v1/appointments/${visit.id}/check-in`, {
      version: visit.version + 7,
    });

    expect(res.status).toBe(409);
  });

  it("start_and_complete_need_the_reception_permission_not_the_session_one", async () => {
    const cs = await signIn("cs@pema.test");

    expect((await call(cs, "POST", "/api/v1/appointments/x/start", { version: 1 })).status).toBe(
      403,
    );
    expect((await call(cs, "POST", "/api/v1/appointments/x/complete", { version: 1 })).status).toBe(
      403,
    );
  });

  it("confirm_is_not_for_the_care_role", async () => {
    const cs = await signIn("cs@pema.test");

    expect((await call(cs, "POST", "/api/v1/appointments/x/confirm", { version: 1 })).status).toBe(
      403,
    );
  });
});

describe("booking rules (mock)", () => {
  const patient = patientRef(4).id;

  it("refuses_a_start_outside_the_shift_and_inside_the_lunch_break", async () => {
    const reception = await signIn("reception@pema.test");
    const day = clinicToday(30);
    const early = await call(reception, "POST", "/api/v1/appointments", {
      patient_id: patient,
      doctor_id: DOCTOR_AN,
      starts_at: `${day}T07:30:00+07:00`,
      duration_min: 30,
    });
    const lunch = await call(reception, "POST", "/api/v1/appointments", {
      patient_id: patient,
      doctor_id: DOCTOR_AN,
      starts_at: `${day}T11:45:00+07:00`,
      duration_min: 30,
    });

    expect(early.status).toBe(422);
    expect(lunch.status).toBe(422);
  });

  it("refuses_a_second_booking_of_the_same_doctor_on_an_overlapping_slot", async () => {
    const reception = await signIn("reception@pema.test");
    const day = clinicToday(31);
    const body = {
      patient_id: patient,
      doctor_id: DOCTOR_TAM,
      starts_at: `${day}T09:00:00+07:00`,
      duration_min: 30,
    };
    const first = await call(reception, "POST", "/api/v1/appointments", body);
    const clash = await call(reception, "POST", "/api/v1/appointments", {
      ...body,
      patient_id: patientRef(5).id,
      starts_at: `${day}T09:15:00+07:00`,
    });

    expect(first.status).toBe(201);
    expect(clash.status).toBe(409);
  });

  it("a_visit_that_has_started_cannot_be_moved", async () => {
    const reception = await signIn("reception@pema.test");
    const day = await board(reception, `day=${clinicToday()}`);
    const started = day.items.find((i) => i.status === "in_progress");
    if (!started) throw new Error("no in-progress visit in the mock day");

    const res = await call(reception, "PATCH", `/api/v1/appointments/${started.id}`, {
      version: started.version,
      note: "x",
    });

    expect(res.status).toBe(409);
  });

  it("the_free_slot_is_the_first_start_the_rules_accept_and_not_before_eight", async () => {
    const reception = await signIn("reception@pema.test");
    const day = clinicToday(40);
    const res = await call(
      reception,
      "GET",
      `/api/v1/appointments/free-slot?patient_id=${patient}&doctor_id=${DOCTOR_AN}&day=${day}&duration_min=30`,
    );

    expect(((await res.json()) as { starts_at: string }).starts_at).toBe(`${day}T08:00:00+07:00`);
  });

  it("the_free_slot_is_null_when_no_start_fits_the_duration", async () => {
    const reception = await signIn("reception@pema.test");
    const day = clinicToday(41);
    const res = await call(
      reception,
      "GET",
      `/api/v1/appointments/free-slot?patient_id=${patient}&day=${day}&duration_min=360`,
    );

    expect(await res.json()).toEqual({ starts_at: null });
  });
});

describe("dashboard KPIs (mock)", () => {
  type Kpis = {
    scope: string;
    starts_on: string;
    ends_on: string;
    appointments: { total: number; visits: number; missed: number } | null;
    patients: { seen: number } | null;
    care: { tasks_due: number } | null;
  } & Record<string, unknown>;

  const kpis = async (cookie: string, range: string): Promise<Kpis> =>
    (await (await call(cookie, "GET", `/api/v1/dashboard/kpis?range=${range}`)).json()) as Kpis;

  it("counts_today_from_the_rows_and_has_no_money", async () => {
    const owner = await signIn("owner@pema.test");
    const today = await kpis(owner, "today");
    const rows = await board(owner, `day=${clinicToday()}`);

    expect(today.scope).toBe("clinic");
    expect(today.starts_on).toBe(clinicToday());
    expect(today.appointments?.total).toBe(rows.items.length);
    expect(Object.keys(today)).not.toContain("revenue");
  });

  it("the_week_holds_at_least_the_day", async () => {
    const owner = await signIn("owner@pema.test");

    expect((await kpis(owner, "week")).appointments?.total).toBeGreaterThanOrEqual(
      (await kpis(owner, "today")).appointments?.total ?? 0,
    );
  });

  it("scopes_a_doctor_to_their_own_visits", async () => {
    const doctor = await signIn("doctor@pema.test");

    expect((await kpis(doctor, "today")).scope).toBe("doctor");
  });

  it("refuses_an_unknown_range", async () => {
    const owner = await signIn("owner@pema.test");

    expect((await call(owner, "GET", "/api/v1/dashboard/kpis?range=year")).status).toBe(422);
  });
});

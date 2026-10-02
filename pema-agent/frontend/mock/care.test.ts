// The care routes of the mock behave like the contract of backend `pema/api/routers/care.py`: the role gate is the
// route permission (CSKH has no matrix, only doctor, manager and owner approve), a request is taken by one person,
// a release only lowers the level, a stale version is a 409, and the live events name the patient but carry no text.
import type { Server } from "node:http";
import type { AddressInfo } from "node:net";

import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { patientRef } from "./data/clinic";
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

const PATIENT_ROUND = patientRef(2).id; // asked of Mai Anh (cs)
const PATIENT_STAFF = patientRef(7).id; // held by Mai Anh, base level L2

describe("care routes (mock)", () => {
  it("refuses an anonymous caller and a role without care.read", async () => {
    expect((await call("", "GET", "/api/v1/care/handoffs")).status).toBe(401);
    const reception = await signIn("reception@pema.test");
    expect((await call(reception, "GET", "/api/v1/care/handoffs")).status).toBe(403);
  });

  it("lists what is waiting for the caller, urgent first, and tells what they may do", async () => {
    const cs = await signIn("cs@pema.test");
    const res = await call(cs, "GET", "/api/v1/care/handoffs?scope=mine");
    const body = (await res.json()) as {
      items: { patient_id: string; mine: boolean; can_accept: boolean; can_decline: boolean }[];
    };
    expect(body.items.map((i) => i.patient_id)).toContain(PATIENT_ROUND);
    expect(body.items.every((i) => i.mine)).toBe(true);
    expect(body.items.every((i) => i.can_accept && i.can_decline)).toBe(true);
  });

  it("gives the matrix to doctor, manager and owner but not to CSKH", async () => {
    expect(
      (await call(await signIn("cs@pema.test"), "GET", "/api/v1/care/admin/matrix")).status,
    ).toBe(403);
    expect(
      (await call(await signIn("doctor@pema.test"), "GET", "/api/v1/care/admin/matrix")).status,
    ).toBe(200);
    expect(
      (await call(await signIn("cs@pema.test"), "GET", "/api/v1/care/admin/staff")).status,
    ).toBe(403);
  });

  it("lets a doctor approve, puts the badge back on edit, and refuses a stale version", async () => {
    const doctor = await signIn("doctor@pema.test");
    const read = async () =>
      (await (await call(doctor, "GET", "/api/v1/care/admin/matrix")).json()) as {
        pending_doctor_approval: boolean;
        can_approve: boolean;
        version: number;
        handoff: unknown;
        autonomy: unknown;
      };
    const first = await read();
    expect(first.can_approve).toBe(true);

    const approved = await call(doctor, "POST", "/api/v1/care/admin/matrix/approval", {
      approved: true,
      version: first.version,
    });
    expect(approved.status).toBe(200);
    expect(
      ((await approved.json()) as { pending_doctor_approval: boolean }).pending_doctor_approval,
    ).toBe(false);

    const stale = await call(doctor, "POST", "/api/v1/care/admin/matrix/approval", {
      approved: true,
      version: first.version,
    });
    expect(stale.status).toBe(409);

    const current = await read();
    const saved = await call(doctor, "PUT", "/api/v1/care/admin/matrix", {
      version: current.version,
      handoff: current.handoff,
      autonomy: current.autonomy,
    });
    expect(
      ((await saved.json()) as { pending_doctor_approval: boolean }).pending_doctor_approval,
    ).toBe(true);
  });

  it("refuses the approval route to CSKH", async () => {
    const cs = await signIn("cs@pema.test");
    const res = await call(cs, "POST", "/api/v1/care/admin/matrix/approval", {
      approved: true,
      version: 1,
    });
    expect(res.status).toBe(403);
  });

  it("declining needs a reason and moves the round on", async () => {
    const cs = await signIn("cs@pema.test");
    const none = await call(cs, "POST", `/api/v1/care/handoffs/${PATIENT_ROUND}/decline`, {
      reason: " ",
    });
    expect(none.status).toBe(422);
    const ok = await call(cs, "POST", `/api/v1/care/handoffs/${PATIENT_ROUND}/decline`, {
      reason: "Đang bận ca khác",
      suggest_user_id: null,
    });
    expect(ok.status).toBe(200);
    const after = (await (await call(cs, "GET", "/api/v1/care/handoffs?scope=mine")).json()) as {
      items: { patient_id: string }[];
    };
    expect(after.items.map((i) => i.patient_id)).not.toContain(PATIENT_ROUND);
  });

  it("a release only lowers the level and needs the days", async () => {
    const cs = await signIn("cs@pema.test");
    const timeline = (await (
      await call(cs, "GET", `/api/v1/care/patients/${PATIENT_STAFF}/timeline`)
    ).json()) as { can_release: boolean; release_levels: string[]; control: { state: string } };
    expect(timeline.control.state).toBe("STAFF");
    expect(timeline.can_release).toBe(true);
    expect(timeline.release_levels).toEqual(["L0", "L1", "L2"]);

    const noDays = await call(
      cs,
      "POST",
      `/api/v1/care/patients/${PATIENT_STAFF}/release/preview`,
      {
        note: "",
        level: "L0",
      },
    );
    expect(((await noDays.json()) as { allowed: boolean }).allowed).toBe(false);

    const lowered = await call(cs, "POST", `/api/v1/care/patients/${PATIENT_STAFF}/release`, {
      note: "Khách ổn, tiếp tục",
      level: "L0",
      days: 7,
    });
    expect(lowered.status).toBe(200);
    const body = (await lowered.json()) as { state: string; override_level: string };
    expect(body).toMatchObject({ state: "AUTO", override_level: "L0" });

    const again = await call(cs, "POST", `/api/v1/care/patients/${PATIENT_STAFF}/release`, {
      note: "",
    });
    expect(again.status).toBe(409);
  });

  it("refuses a level above the agent's own", async () => {
    const cs = await signIn("cs@pema.test");
    // patient 8 is held by the doctor and the agent's own level is L1
    const timeline = (await (
      await call(
        await signIn("doctor@pema.test"),
        "GET",
        `/api/v1/care/patients/${patientRef(8).id}/timeline`,
      )
    ).json()) as { release_levels: string[] };
    expect(timeline.release_levels).toEqual(["L0", "L1"]);
    const res = await call(
      cs,
      "POST",
      `/api/v1/care/patients/${patientRef(8).id}/release/preview`,
      {
        note: "",
        level: "L2",
        days: 3,
      },
    );
    expect(((await res.json()) as { allowed: boolean }).allowed).toBe(false);
  });

  it("saves what staff tell the agent as memory of source staff", async () => {
    const cs = await signIn("cs@pema.test");
    const patient = patientRef(1).id;
    const saved = await call(cs, "POST", `/api/v1/care/patients/${patient}/tell-agent`, {
      instruction: "Nhắn sau 18 giờ",
    });
    expect(saved.status).toBe(200);
    const timeline = (await (
      await call(cs, "GET", `/api/v1/care/patients/${patient}/timeline`)
    ).json()) as {
      memory: { fact: string; source: string }[];
    };
    expect(timeline.memory[0]).toMatchObject({ fact: "Nhắn sau 18 giờ", source: "staff" });
  });
});

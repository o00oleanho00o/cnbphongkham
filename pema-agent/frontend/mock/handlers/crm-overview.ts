// Mock of the CRM groups (`/crm/segments`) and the read-only rule list (`/crm/rules`). The lifecycle numbers of each
// fictional patient are fixed here (the real backend computes them from visits, plans and appointments with
// `compute_profile`); the marketing opt-out and the version come from the shared patient list, so the switch
// on the screen (`PATCH /patients/{id}`) shows in the next read.
import { patients, rules } from "../data/clinic";
import { DAY, fail, isoFromNow, paginate, type Reply, type Router, type Schemas } from "../core";

type S = Schemas;

type Profile = {
  stage: Exclude<S["CrmSegmentKey"], "at_risk">;
  lastVisitDaysAgo: number | null;
  /** days from today to the expected next visit (negative: overdue) */
  expectedInDays: number | null;
  remaining: number;
  risk: "normal" | "high";
};

/** By patient number (P001..P010 of the mock patient list). */
const PROFILES: Record<number, Profile> = {
  1: { stage: "treating", lastVisitDaysAgo: 8, expectedInDays: 20, remaining: 2, risk: "normal" },
  2: { stage: "returning", lastVisitDaysAgo: 40, expectedInDays: -12, remaining: 0, risk: "high" },
  3: { stage: "new", lastVisitDaysAgo: null, expectedInDays: null, remaining: 0, risk: "normal" },
  4: {
    stage: "dormant",
    lastVisitDaysAgo: 130,
    expectedInDays: null,
    remaining: 0,
    risk: "normal",
  },
  5: { stage: "treating", lastVisitDaysAgo: 62, expectedInDays: -17, remaining: 3, risk: "high" },
  6: {
    stage: "reactivated",
    lastVisitDaysAgo: 15,
    expectedInDays: 30,
    remaining: 0,
    risk: "normal",
  },
  7: { stage: "returning", lastVisitDaysAgo: 25, expectedInDays: 5, remaining: 0, risk: "normal" },
  8: {
    stage: "dormant",
    lastVisitDaysAgo: 200,
    expectedInDays: null,
    remaining: 0,
    risk: "normal",
  },
  9: {
    stage: "returning",
    lastVisitDaysAgo: 55,
    expectedInDays: null,
    remaining: 0,
    risk: "normal",
  },
  10: { stage: "new", lastVisitDaysAgo: null, expectedInDays: null, remaining: 0, risk: "normal" },
};

const STAGES: Exclude<S["CrmSegmentKey"], "at_risk">[] = [
  "new",
  "returning",
  "treating",
  "dormant",
  "reactivated",
];

const SEGMENT_KEYS: readonly S["CrmSegmentKey"][] = [...STAGES, "at_risk"];

const dateAt = (days: number | null): string | null =>
  days === null ? null : isoFromNow(days * DAY).slice(0, 10);

function rows(): S["CrmSegmentPatientOut"][] {
  return patients.flatMap((p, index) => {
    const profile = PROFILES[index + 1];
    if (!profile) return [];
    const overdue =
      profile.expectedInDays !== null && profile.expectedInDays < 0 ? -profile.expectedInDays : 0;
    return [
      {
        patient_id: p.id,
        patient_code: p.code,
        full_name: p.full_name,
        version: p.version,
        lifecycle_stage: profile.stage,
        last_visit_at: dateAt(profile.lastVisitDaysAgo === null ? null : -profile.lastVisitDaysAgo),
        expected_next_visit_at: dateAt(profile.expectedInDays),
        overdue_days: overdue,
        remaining_sessions: profile.remaining,
        risk_level: profile.risk,
        marketing_opt_out: p.marketing_opt_out ?? false,
        cs_owner_name: p.cs_owner_name ?? null,
      },
    ];
  });
}

const inSegment = (row: S["CrmSegmentPatientOut"], key: S["CrmSegmentKey"]): boolean =>
  key === "at_risk" ? row.risk_level === "high" : row.lifecycle_stage === key;

export function register(r: Router): void {
  r.get("/api/v1/crm/segments", "crm.task.read", (): Reply => {
    const all = rows();
    return {
      body: {
        total_patients: all.length,
        segments: SEGMENT_KEYS.map((key) => ({
          key,
          count: all.filter((row) => inSegment(row, key)).length,
        })),
        marketing_opt_out: all.filter((row) => row.marketing_opt_out).length,
      } satisfies S["CrmSegmentsOut"],
    };
  });

  r.get("/api/v1/crm/segments/{segment}/patients", "crm.task.read", (ctx): Reply => {
    const key = SEGMENT_KEYS.find((candidate) => candidate === ctx.params.segment);
    if (key === undefined) fail(422, "validation_failed", "Nhóm khách không hợp lệ.");
    const members = rows()
      .filter((row) => inSegment(row, key))
      .toSorted(
        (a, b) => b.overdue_days - a.overdue_days || a.patient_code.localeCompare(b.patient_code),
      );
    return { body: paginate(members, ctx.query) };
  });

  r.get("/api/v1/crm/rules", "crm.task.read", (): Reply => ({ body: rules }));
}

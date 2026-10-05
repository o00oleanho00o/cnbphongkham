// Mock of the care-agent supervision routes (backend pema/api/routers/care.py, package M step M5):
//   GET  /api/v1/care/handoffs, POST .../{patient_id}/accept and /decline
//   GET  /api/v1/care/patients/{patient_id}/timeline, POST .../release/preview, /release, /tell-agent
//   GET/PUT /api/v1/care/admin/staff, /on-call, /matrix (+ POST /matrix/approval), /timing, GET /alerts
// The role gate is the route permission (mock/core.ts). The few rules here (who may accept, the levels a release
// may use, the badge that only an approver clears) simulate the real service so the screens can be exercised;
// the screens themselves hold none of them.
import { USERS } from "../auth";
import {
  BASE_LEVEL,
  KNOWN_SKILLS,
  MAX_OVERRIDE_DAYS,
  alerts,
  controls,
  entries,
  matrix,
  memory,
  onCall,
  overrides,
  pausedReminders,
  pendingDrafts,
  rounds,
  staffProfiles,
  timing,
  userName,
  type MockRound,
} from "../data/care";
import { patientById } from "../data/clinic";
import {
  HttpError,
  bodyOf,
  fail,
  isoFromNow,
  uid,
  uuid,
  DAY,
  MIN,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
  type Session,
} from "../core";

type S = Schemas;

const LEVELS: S["CareLevel"][] = ["L0", "L1", "L2"];
const VERSION_CONFLICT = "Bản ghi vừa được người khác cập nhật. Tải lại rồi thử lại.";
const MANAGERIAL = ["owner", "manager"];

function session(ctx: Ctx): Session {
  if (!ctx.session) throw new HttpError(401, "unauthenticated", "Bạn chưa đăng nhập.");
  return ctx.session;
}

function patientName(id: string): string {
  const patient = patientById(id);
  if (!patient) fail(404, "not_found", "Không tìm thấy bệnh nhân.");
  return patient.full_name;
}

function checkVersion(current: number, sent: number): void {
  if (current !== sent) fail(409, "version_conflict", VERSION_CONFLICT);
}

function currentCandidate(round: MockRound): string | null {
  return round.chain[round.idx] ?? null;
}

function roundOf(patientId: string): MockRound | undefined {
  return rounds.find((r) => r.patientId === patientId);
}

function waiting(round: MockRound, s: Session): S["HandoffWaitingOut"] {
  const candidate = currentCandidate(round);
  const mine = candidate !== null && candidate === s.userId;
  const managerial = MANAGERIAL.includes(s.role);
  return {
    patient_id: round.patientId,
    patient_name: patientName(round.patientId),
    reason: round.reason,
    summary: round.summary,
    depth: round.depth,
    urgency: round.urgency,
    confidence: round.confidence,
    required_skill: round.requiredSkill,
    opened_at: round.openedAt,
    sla_due_at: round.slaDueAt,
    position: round.idx + 1,
    chain_length: round.chain.length,
    on_call_step: candidate === null,
    suggested_by_name: round.suggestedBy,
    mine,
    can_accept: mine || managerial || (candidate === null && s.role === "doctor"),
    can_decline: mine,
  };
}

function resultOf(patientId: string): S["HandoffResultOut"] {
  const control = controls.get(patientId);
  return {
    patient_id: patientId,
    state: control?.state ?? "AUTO",
    outcome: control?.state === "STAFF" ? "accepted" : null,
  };
}

function baseLevel(patientId: string): S["CareLevel"] {
  return BASE_LEVEL[patientId] ?? "L0";
}

function activeOverride(patientId: string) {
  const o = overrides.get(patientId) ?? null;
  return o && new Date(o.until).getTime() > Date.now() ? o : null;
}

function effectiveLevel(patientId: string): S["CareLevel"] {
  const base = baseLevel(patientId);
  const o = activeOverride(patientId);
  if (!o) return base;
  return LEVELS.indexOf(o.level) < LEVELS.indexOf(base) ? o.level : base;
}

const LEVEL_MEANING: Record<S["CareLevel"], string> = {
  L0: "mọi tin chỉ là nháp chờ người duyệt",
  L1: "chỉ gửi tin mẫu đã được bác sĩ duyệt",
  L2: "trả lời câu hỏi thường gặp có nguồn trích dẫn",
};

function releaseLevels(patientId: string): S["CareLevel"][] {
  const rank = LEVELS.indexOf(baseLevel(patientId));
  return LEVELS.filter((_, i) => i <= rank);
}

function canRelease(patientId: string, s: Session): boolean {
  const control = controls.get(patientId);
  if (control?.state !== "STAFF") return false;
  return control.ownerId === s.userId || MANAGERIAL.includes(s.role);
}

function timelineOf(patientId: string, s: Session): S["PatientCareTimelineOut"] {
  const control = controls.get(patientId);
  const round = roundOf(patientId);
  const o = activeOverride(patientId);
  return {
    patient_id: patientId,
    patient_name: patientName(patientId),
    control: {
      state: control?.state ?? (round ? "HANDOFF_ROUTING" : "AUTO"),
      since: control?.since ?? round?.openedAt ?? isoFromNow(-30 * DAY),
      staff_owner_id: control?.ownerId ?? null,
      staff_owner_name: userName(control?.ownerId ?? null),
      release_note: control?.note ?? null,
    },
    autonomy: {
      effective_level: effectiveLevel(patientId),
      base_level: baseLevel(patientId),
      override_level: o?.level ?? null,
      override_until: o?.until ?? null,
      paused: false,
    },
    open_handoff: round
      ? {
          reason: round.reason,
          summary: round.summary,
          depth: round.depth,
          urgency: round.urgency,
          confidence: round.confidence,
          required_skill: round.requiredSkill,
          opened_at: round.openedAt,
          current_candidate_name: userName(currentCandidate(round)),
          sla_due_at: round.slaDueAt,
        }
      : null,
    pending_drafts: pendingDrafts.get(patientId) ?? [],
    paused_reminders: pausedReminders.get(patientId) ?? [],
    entries: (entries.get(patientId) ?? []).toSorted((a, b) => b.at.localeCompare(a.at)),
    memory: memory.get(patientId) ?? [],
    can_release: canRelease(patientId, s),
    can_tell_agent: true,
    release_levels: releaseLevels(patientId),
    max_override_days: MAX_OVERRIDE_DAYS,
  };
}

function preview(patientId: string, body: S["ReleaseIn"]): S["ReleasePreviewOut"] {
  const base = baseLevel(patientId);
  if (!body.level) {
    return {
      allowed: true,
      consequence: `Agent tiếp tục ở mức ${base} (${LEVEL_MEANING[base]}). Nhắc lịch đã tạm dừng được rà soát, chỉ gửi lại khi còn phù hợp.`,
    };
  }
  if (!releaseLevels(patientId).includes(body.level)) {
    return {
      allowed: false,
      consequence: "Khi trả lại chỉ được giữ nguyên hoặc hạ mức, không được nâng mức tự chủ.",
    };
  }
  if (!body.days) {
    return { allowed: false, consequence: "Hãy chọn số ngày áp dụng mức đã hạ." };
  }
  return {
    allowed: true,
    consequence: `Trong ${body.days} ngày agent chỉ làm ở mức ${body.level} (${LEVEL_MEANING[body.level]}), sau đó tự về mức ${base}.`,
  };
}

function addEntry(patientId: string, e: S["TimelineEntryOut"]): void {
  entries.set(patientId, [e, ...(entries.get(patientId) ?? [])]);
}

function staffOut(profile: (typeof staffProfiles)[number]): S["StaffCareProfileOut"] {
  const user = USERS.find((u) => u.id === profile.userId);
  const load = [...controls.values()].filter(
    (c) => c.state === "STAFF" && c.ownerId === profile.userId,
  ).length;
  return {
    user_id: profile.userId,
    name: user?.display_name ?? "Nhân viên",
    role: user?.role ?? "cs_staff",
    skills: profile.skills,
    shift: profile.shift,
    capacity: profile.capacity,
    languages: profile.languages,
    load,
    version: profile.version,
  };
}

function matrixOut(s: Session): S["CareMatrixOut"] {
  return {
    pending_doctor_approval: matrix.pending,
    can_edit: s.permissions.includes("care.matrix"),
    can_approve: s.permissions.includes("care.approve"),
    handoff: matrix.handoff,
    autonomy: matrix.autonomy,
    version: matrix.version,
  };
}

function timingOut(s: Session): S["CareTimingOut"] {
  return {
    ...timing,
    send_window_start: "08:00",
    send_window_end: "20:00",
    time_zone: "Asia/Ho_Chi_Minh",
    pending_doctor_approval: matrix.pending,
    can_edit: s.permissions.includes("care.admin"),
  };
}

export function register(r: Router): void {
  // ------------------------------------------------------------------------------- staff side
  r.get("/api/v1/care/handoffs", "care.read", (ctx): Reply => {
    const s = session(ctx);
    const scope = ctx.query.get("scope") === "all" ? "all" : "mine";
    const items = rounds
      .map((round) => waiting(round, s))
      .filter((w) => scope === "all" || w.mine || (w.on_call_step && w.can_accept))
      .toSorted(
        (a, b) =>
          Number(b.urgency === "urgent") - Number(a.urgency === "urgent") ||
          a.opened_at.localeCompare(b.opened_at),
      );
    return { body: { items } satisfies S["HandoffListOut"] };
  });

  r.post("/api/v1/care/handoffs/{patient_id}/accept", "care.act", (ctx): Reply => {
    const s = session(ctx);
    const patientId = ctx.params.patient_id ?? "";
    const round = roundOf(patientId);
    if (!round) fail(409, "invalid_state", "Yêu cầu này đã có người nhận hoặc đã đóng.");
    if (!waiting(round, s).can_accept)
      fail(403, "forbidden", "Bạn không phải người đang được hỏi.");
    rounds.splice(rounds.indexOf(round), 1);
    controls.set(patientId, {
      state: "STAFF",
      since: isoFromNow(0),
      ownerId: s.userId,
      note: null,
    });
    addEntry(patientId, {
      id: uid("e"),
      at: isoFromNow(0),
      kind: "control",
      code: "control:handoff_routing_to_staff:staff",
      actor_name: userName(s.userId),
    });
    return { body: resultOf(patientId) };
  });

  r.post("/api/v1/care/handoffs/{patient_id}/decline", "care.act", (ctx): Reply => {
    const s = session(ctx);
    const patientId = ctx.params.patient_id ?? "";
    const body = bodyOf<S["HandoffDeclineIn"]>(ctx);
    if (!body.reason || body.reason.trim() === "")
      fail(422, "validation_failed", "Hãy ghi lý do từ chối.");
    const round = roundOf(patientId);
    if (!round) fail(409, "invalid_state", "Yêu cầu này đã có người nhận hoặc đã đóng.");
    if (!waiting(round, s).can_decline)
      fail(403, "forbidden", "Bạn không phải người đang được hỏi.");
    if (body.suggest_user_id) {
      round.chain.splice(round.idx + 1, 0, body.suggest_user_id);
      round.suggestedBy = userName(s.userId);
    }
    round.idx = Math.min(round.idx + 1, round.chain.length - 1);
    round.slaDueAt = isoFromNow((round.urgency === "urgent" ? 5 : 30) * MIN);
    addEntry(patientId, {
      id: uid("e"),
      at: isoFromNow(0),
      kind: "paused",
      code: "control:handoff_routing_declined:staff",
      actor_name: userName(s.userId),
    });
    return { body: resultOf(patientId) };
  });

  r.get("/api/v1/care/patients/{patient_id}/timeline", "care.read", (ctx): Reply => {
    const s = session(ctx);
    return { body: timelineOf(ctx.params.patient_id ?? "", s) };
  });

  r.post("/api/v1/care/patients/{patient_id}/release/preview", "care.act", (ctx): Reply => {
    session(ctx);
    const patientId = ctx.params.patient_id ?? "";
    patientName(patientId);
    return { body: preview(patientId, bodyOf<S["ReleaseIn"]>(ctx)) };
  });

  r.post("/api/v1/care/patients/{patient_id}/release", "care.act", (ctx): Reply => {
    const s = session(ctx);
    const patientId = ctx.params.patient_id ?? "";
    const body = bodyOf<S["ReleaseIn"]>(ctx);
    const control = controls.get(patientId);
    if (control?.state !== "STAFF")
      fail(409, "invalid_state", "Cuộc trò chuyện này đang do agent phụ trách.");
    if (!canRelease(patientId, s))
      fail(403, "forbidden", "Chỉ người đang phụ trách mới trả lại được.");
    const check = preview(patientId, body);
    if (!check.allowed) fail(422, "validation_failed", check.consequence);
    const note = (body.note ?? "").trim();
    controls.set(patientId, {
      state: "AUTO",
      since: isoFromNow(0),
      ownerId: null,
      note: note || null,
    });
    if (note) {
      memory.set(patientId, [
        {
          id: uid("m") as string,
          fact: note,
          source: "staff",
          created_at: isoFromNow(0),
          valid_until: null,
        },
        ...(memory.get(patientId) ?? []),
      ]);
    }
    let until: string | null = null;
    if (body.level && body.days) {
      until = isoFromNow(body.days * DAY);
      overrides.set(patientId, { level: body.level, until });
    }
    pausedReminders.delete(patientId);
    addEntry(patientId, {
      id: uid("e"),
      at: isoFromNow(0),
      kind: "control",
      code: "control:staff_to_auto:staff",
      actor_name: userName(s.userId),
    });
    return {
      body: {
        patient_id: patientId,
        state: "AUTO",
        override_level: body.level ?? null,
        override_until: until,
      } satisfies S["ReleaseResultOut"],
    };
  });

  r.post("/api/v1/care/patients/{patient_id}/tell-agent", "care.act", (ctx): Reply => {
    session(ctx);
    const patientId = ctx.params.patient_id ?? "";
    patientName(patientId);
    const { instruction } = bodyOf<S["TellAgentIn"]>(ctx);
    if (!instruction || instruction.trim() === "")
      fail(422, "validation_failed", "Hãy nhập nội dung cần nói với agent.");
    const memoryId = uuid(Math.floor(Math.random() * 1_000_000) + 1000, 5);
    memory.set(patientId, [
      {
        id: memoryId,
        fact: instruction.trim(),
        source: "staff",
        created_at: isoFromNow(0),
        valid_until: null,
      },
      ...(memory.get(patientId) ?? []),
    ]);
    return { body: { memory_id: memoryId, source: "staff" } satisfies S["TellAgentOut"] };
  });

  // ------------------------------------------------------------------------------- admin side
  r.get("/api/v1/care/admin/staff", "care.admin", (): Reply => ({
    body: {
      items: staffProfiles.map(staffOut),
      known_skills: KNOWN_SKILLS,
    } satisfies S["StaffCareProfileListOut"],
  }));

  r.put("/api/v1/care/admin/staff/{user_id}", "care.admin", (ctx): Reply => {
    const profile = staffProfiles.find((x) => x.userId === ctx.params.user_id);
    if (!profile) fail(404, "not_found", "Không tìm thấy nhân viên.");
    const body = bodyOf<S["StaffCareProfileIn"]>(ctx);
    checkVersion(profile.version, body.version);
    profile.skills = body.skills;
    profile.shift = body.shift;
    profile.capacity = body.capacity;
    profile.languages = body.languages;
    profile.version += 1;
    return { body: staffOut(profile) };
  });

  r.get("/api/v1/care/admin/on-call", "care.admin", (): Reply => ({
    body: {
      items: onCall,
      chain_ends_with_on_call: onCall.some((c) => c.active),
    } satisfies S["OnCallListOut"],
  }));

  r.post("/api/v1/care/admin/on-call", "care.admin", (ctx): Reply => {
    const body = bodyOf<S["OnCallContactIn"]>(ctx);
    const created: S["OnCallContactOut"] = {
      id: uuid(Math.floor(Math.random() * 1_000_000) + 1000, 6),
      zalo_number: body.zalo_number,
      owner: body.owner,
      valid_from: body.valid_from ?? isoFromNow(0),
      valid_to: body.valid_to ?? null,
      active: body.active ?? true,
      is_fixture: false,
      version: 1,
    };
    onCall.push(created);
    return { status: 201, body: created };
  });

  r.put("/api/v1/care/admin/on-call/{contact_id}", "care.admin", (ctx): Reply => {
    const contact = onCall.find((c) => c.id === ctx.params.contact_id);
    if (!contact) fail(404, "not_found", "Không tìm thấy số trực.");
    const body = bodyOf<S["OnCallContactIn"]>(ctx);
    if (body.version !== undefined && body.version !== null)
      checkVersion(contact.version, body.version);
    const wasActive = contact.active;
    if (wasActive && body.active === false && onCall.filter((c) => c.active).length === 1)
      fail(409, "invalid_state", "Phải còn ít nhất một số trực 24/24 đang bật.");
    contact.zalo_number = body.zalo_number;
    contact.owner = body.owner;
    contact.valid_from = body.valid_from ?? contact.valid_from;
    contact.valid_to = body.valid_to ?? null;
    contact.active = body.active ?? true;
    contact.is_fixture = false;
    contact.version += 1;
    return { body: contact };
  });

  r.get("/api/v1/care/admin/matrix", "care.matrix", (ctx): Reply => ({
    body: matrixOut(session(ctx)),
  }));

  r.put("/api/v1/care/admin/matrix", "care.matrix", (ctx): Reply => {
    const s = session(ctx);
    const body = bodyOf<S["CareMatrixIn"]>(ctx);
    checkVersion(matrix.version, body.version);
    matrix.handoff = body.handoff;
    matrix.autonomy = {
      ...body.autonomy,
      rules: body.autonomy.rules.map((rule) => {
        const stored = matrix.autonomy.rules.find((x) => x.action_type === rule.action_type);
        return stored?.hard_human ? stored : rule;
      }),
    };
    matrix.pending = true;
    matrix.version += 1;
    return { body: matrixOut(s) };
  });

  r.post("/api/v1/care/admin/matrix/approval", "care.approve", (ctx): Reply => {
    const s = session(ctx);
    const body = bodyOf<S["CareApprovalIn"]>(ctx);
    checkVersion(matrix.version, body.version);
    matrix.pending = !body.approved;
    matrix.version += 1;
    return { body: matrixOut(s) };
  });

  r.get("/api/v1/care/admin/timing", "care.admin", (ctx): Reply => ({
    body: timingOut(session(ctx)),
  }));

  r.put("/api/v1/care/admin/timing", "care.admin", (ctx): Reply => {
    const s = session(ctx);
    const body = bodyOf<S["CareTimingIn"]>(ctx);
    checkVersion(timing.version, body.version);
    timing.sla_urgent_minutes = body.sla_urgent_minutes;
    timing.sla_normal_minutes = body.sla_normal_minutes;
    timing.max_candidates = body.max_candidates;
    timing.oncall_direct_from_depth = body.oncall_direct_from_depth;
    timing.version += 1;
    matrix.pending = true;
    return { body: timingOut(s) };
  });

  r.get("/api/v1/care/admin/alerts", "care.admin", (): Reply => ({
    body: {
      items: alerts.toSorted((a, b) => b.at.localeCompare(a.at)),
    } satisfies S["CareAlertListOut"],
  }));
}

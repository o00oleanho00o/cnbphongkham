// Mock of the configuration screens: the service catalog with versioned price and rate terms
// (`/services`), follow-up protocols (`/protocols`), doctors, rooms and room blocks (`/resources`, `/rooms`,
// `/room-blocks`) and the before/after studio (`/studio/{patient_id}`). The rules are the backend's
// (`pema.clinic.actions.services|protocols|resources|studio`); here only what the screens need to be tried:
// a change of price, rate, basis, duration or buffer adds a snapshot, the commission terms are hidden from
// people who cannot manage the catalog, a block stays inside 08:00-18:00 with a reason, the studio has no photo
// yet (the photo store is the Patient 360 step).
import { USERS } from "../auth";
import {
  DEFAULT_SHIFT,
  blocks,
  protocols,
  rooms,
  services,
  type ServiceRecord,
} from "../data/catalog";
import { appointments, consents, patientById } from "../data/clinic";
import {
  bodyOf,
  fail,
  isoFromNow,
  uid,
  type Ctx,
  type Permission,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

const VERSION_CONFLICT = "Bản ghi đã được người khác thay đổi. Hãy tải lại rồi thử lại.";
const STUDIO_VIEWS = ["Chính diện", "Má trái", "Má phải"];

function has(ctx: Ctx, permission: Permission): boolean {
  return ctx.session?.permissions.includes(permission) ?? false;
}

function needAny(ctx: Ctx, ...permissions: Permission[]): void {
  if (!permissions.some((p) => has(ctx, p))) {
    fail(403, "forbidden", "Bạn không có quyền thực hiện thao tác này.");
  }
}

// ------------------------------------------------------------------------------------------------ services
function currentTerms(s: ServiceRecord) {
  const terms = s.history.find((h) => h.version_no === s.terms_version);
  if (!terms) fail(404, "not_found", "Không tìm thấy điều khoản dịch vụ.");
  return terms;
}

function serviceOut(s: ServiceRecord, payroll: boolean): S["ServiceOut"] {
  const t = currentTerms(s);
  return {
    id: s.id,
    code: s.code,
    name: s.name,
    active: s.active,
    protocol_code: s.protocol_code,
    room_ids: s.room_ids,
    price_vnd: t.price_vnd,
    rate_bp: payroll ? t.rate_bp : null,
    basis: payroll ? t.basis : null,
    duration_min: t.duration_min,
    buffer_min: t.buffer_min,
    terms_version: s.terms_version,
    version: s.version,
  };
}

function serviceOr404(ctx: Ctx): ServiceRecord {
  const found = services.find((s) => s.id === ctx.params.service_id);
  if (!found) fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (dịch vụ)");
  return found;
}

function checkLinks(protocolCode: string | null | undefined, roomIds: string[] | null | undefined) {
  if (protocolCode && !protocols.some((p) => p.code === protocolCode)) {
    fail(422, "validation_failed", "Giao thức theo dõi không tồn tại.");
  }
  if (roomIds?.some((id) => !rooms.some((r) => r.id === id))) {
    fail(422, "validation_failed", "Có phòng không tồn tại trong danh sách phòng.");
  }
}

function registerServices(r: Router): void {
  r.get("/api/v1/services", "appointment.read", (ctx): Reply => {
    const active = ctx.query.get("active");
    const payroll = has(ctx, "admin.rules");
    const rows = services
      .filter((s) => active === null || String(s.active) === active)
      .toSorted((a, b) => a.name.localeCompare(b.name, "vi"));
    return { body: rows.map((s) => serviceOut(s, payroll)) };
  });

  r.post("/api/v1/services", "admin.rules", (ctx): Reply => {
    const input = bodyOf<S["ServiceCreate"]>(ctx);
    if (services.some((s) => s.code === input.code)) {
      fail(422, "validation_failed", "Mã dịch vụ đã tồn tại.");
    }
    checkLinks(input.protocol_code, input.room_ids);
    const record: ServiceRecord = {
      id: uid("svc"),
      code: input.code,
      name: input.name,
      active: input.active ?? true,
      protocol_code: input.protocol_code ?? null,
      room_ids: input.room_ids ?? [],
      terms_version: 1,
      version: 1,
      history: [
        {
          version_no: 1,
          price_vnd: input.price_vnd,
          rate_bp: input.rate_bp ?? 0,
          basis: input.basis ?? "net",
          duration_min: input.duration_min,
          buffer_min: input.buffer_min ?? 0,
          changed_by: ctx.session?.userId ?? null,
          created_at: isoFromNow(0),
        },
      ],
    };
    services.push(record);
    return { status: 201, body: serviceOut(record, true) };
  });

  r.get("/api/v1/services/{service_id}", "appointment.read", (ctx): Reply => {
    const service = serviceOr404(ctx);
    const payroll = has(ctx, "admin.rules");
    const history: S["ServiceTermsOut"][] = service.history
      .toSorted((a, b) => b.version_no - a.version_no)
      .map((h) => ({
        version_no: h.version_no,
        price_vnd: h.price_vnd,
        rate_bp: payroll ? h.rate_bp : null,
        basis: payroll ? h.basis : null,
        duration_min: h.duration_min,
        buffer_min: h.buffer_min,
        changed_by: h.changed_by,
        created_at: h.created_at,
      }));
    return { body: { ...serviceOut(service, payroll), history } };
  });

  r.patch("/api/v1/services/{service_id}", "admin.rules", (ctx): Reply => {
    const service = serviceOr404(ctx);
    const input = bodyOf<S["ServiceUpdate"]>(ctx);
    if (input.version !== service.version) fail(409, "version_conflict", VERSION_CONFLICT);
    checkLinks(input.protocol_code, input.room_ids);
    const sent = (key: keyof S["ServiceUpdate"]) => Object.hasOwn(input, key);
    const before = currentTerms(service);
    const next = {
      price_vnd: input.price_vnd ?? before.price_vnd,
      rate_bp: input.rate_bp ?? before.rate_bp,
      basis: input.basis ?? before.basis,
      duration_min: input.duration_min ?? before.duration_min,
      buffer_min: input.buffer_min ?? before.buffer_min,
    };
    const termsChanged =
      next.price_vnd !== before.price_vnd ||
      next.rate_bp !== before.rate_bp ||
      next.basis !== before.basis ||
      next.duration_min !== before.duration_min ||
      next.buffer_min !== before.buffer_min;
    const rowChanged =
      (input.name != null && input.name !== service.name) ||
      (input.active != null && input.active !== service.active) ||
      (sent("protocol_code") && (input.protocol_code ?? null) !== service.protocol_code) ||
      (input.room_ids != null &&
        input.room_ids.toSorted().join() !== service.room_ids.toSorted().join());
    if (!termsChanged && !rowChanged) return { body: serviceOut(service, true) };
    if (input.name != null) service.name = input.name;
    if (input.active != null) service.active = input.active;
    if (sent("protocol_code")) service.protocol_code = input.protocol_code ?? null;
    if (input.room_ids != null) service.room_ids = input.room_ids;
    if (termsChanged) {
      service.terms_version += 1;
      service.history.push({
        version_no: service.terms_version,
        ...next,
        changed_by: ctx.session?.userId ?? null,
        created_at: isoFromNow(0),
      });
    }
    service.version += 1;
    return { body: serviceOut(service, true) };
  });
}

// ----------------------------------------------------------------------------------------------- protocols
function protocolOr404(ctx: Ctx): S["ProtocolOut"] {
  const found = protocols.find((p) => p.id === ctx.params.protocol_id);
  if (!found) fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (giao thức)");
  return found;
}

function checkMilestones(milestones: S["ProtocolMilestone"][], windowDays: number): void {
  const keys = milestones.map((m) => m.rule_key);
  if (keys.some((k) => !["d1", "d3", "d7"].includes(k))) {
    fail(422, "validation_failed", "Mốc theo dõi chỉ gồm D+1, D+3 và D+7.");
  }
  if (new Set(keys).size !== keys.length) {
    fail(422, "validation_failed", "Mỗi mốc theo dõi chỉ khai báo một lần.");
  }
  const late = milestones.find((m) => m.day > windowDays);
  if (late) {
    fail(
      422,
      "validation_failed",
      `Mốc ngày ${late.day} vượt quá cửa sổ áp dụng ${windowDays} ngày.`,
    );
  }
}

function registerProtocols(r: Router): void {
  r.get("/api/v1/protocols", null, (ctx): Reply => {
    needAny(ctx, "admin.rules", "session.write");
    return { body: protocols };
  });

  r.post("/api/v1/protocols", "admin.rules", (ctx): Reply => {
    const input = bodyOf<S["ProtocolCreate"]>(ctx);
    if (protocols.some((p) => p.code === input.code)) {
      fail(422, "validation_failed", "Mã giao thức đã tồn tại.");
    }
    checkMilestones(input.milestones ?? [], input.window_days ?? 45);
    const created: S["ProtocolOut"] = {
      id: uid("proto"),
      code: input.code,
      name: input.name,
      milestones: input.milestones ?? [],
      followup_days: input.followup_days ?? null,
      window_days: input.window_days ?? 45,
      active: input.active ?? true,
      version: 1,
    };
    protocols.push(created);
    return { status: 201, body: created };
  });

  r.patch("/api/v1/protocols/{protocol_id}", "admin.rules", (ctx): Reply => {
    const protocol = protocolOr404(ctx);
    const input = bodyOf<S["ProtocolUpdate"]>(ctx);
    if (input.version !== protocol.version) fail(409, "version_conflict", VERSION_CONFLICT);
    const windowDays = input.window_days ?? protocol.window_days;
    checkMilestones(input.milestones ?? protocol.milestones, windowDays);
    if (input.name != null) protocol.name = input.name;
    if (input.milestones != null) protocol.milestones = input.milestones;
    if (Object.hasOwn(input, "followup_days")) protocol.followup_days = input.followup_days ?? null;
    protocol.window_days = windowDays;
    if (input.active != null) protocol.active = input.active;
    protocol.version += 1;
    return { body: protocol };
  });
}

// ------------------------------------------------------------------------------------ doctors and rooms
const WEEKDAYS = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"] as const;

function shiftMinutes(shift: S["ShiftIntervalOut"][]): number {
  const minutes = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3));
  return shift.reduce((sum, i) => sum + ((minutes(i.end) - minutes(i.start) + 1440) % 1440), 0);
}

function doctorCards(day: string): S["DoctorResourceOut"][] {
  const weekday = WEEKDAYS[new Date(`${day}T12:00:00+07:00`).getUTCDay()];
  const shift = weekday === "sun" ? [] : DEFAULT_SHIFT;
  return USERS.filter((u) => u.role === "doctor").map((u, index) => {
    const mine = appointments.filter(
      (a) =>
        a.doctor_id === u.id &&
        a.starts_at.slice(0, 10) === day &&
        !["cancelled", "missed"].includes(a.status),
    );
    const hasShift = index !== 2;
    const intervals = hasShift ? shift : [];
    return {
      user_id: u.id,
      name: u.display_name,
      active: u.active,
      has_shift: hasShift,
      shift: intervals,
      shift_minutes: shiftMinutes(intervals),
      booked_count: mine.length,
      booked_minutes: mine.reduce((sum, a) => sum + a.duration_min, 0),
    };
  });
}

function roomOr404(id: string): S["RoomOut"] {
  const found = rooms.find((room) => room.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (phòng)");
  return found;
}

function registerResources(r: Router): void {
  r.get("/api/v1/resources", "appointment.read", (ctx): Reply => {
    const day = ctx.query.get("day") ?? isoFromNow(0).slice(0, 10);
    const out: S["ResourcesOut"] = {
      day,
      doctors: doctorCards(day),
      rooms: rooms.toSorted((a, b) => a.name.localeCompare(b.name, "vi")),
      blocks: blocks
        .filter((b) => b.day >= day)
        .toSorted((a, b) => `${a.day}${a.start}`.localeCompare(`${b.day}${b.start}`)),
    };
    return { body: out };
  });

  r.post("/api/v1/rooms", "admin.rules", (ctx): Reply => {
    const input = bodyOf<S["RoomCreate"]>(ctx);
    if (rooms.some((room) => room.name === input.name)) {
      fail(422, "validation_failed", "Tên phòng đã tồn tại.");
    }
    const created: S["RoomOut"] = {
      id: uid("room"),
      name: input.name,
      capacity: input.capacity ?? 1,
      active: true,
      version: 1,
    };
    rooms.push(created);
    return { status: 201, body: created };
  });

  r.patch("/api/v1/rooms/{room_id}", "admin.rules", (ctx): Reply => {
    const room = roomOr404(ctx.params.room_id ?? "");
    const input = bodyOf<S["RoomUpdate"]>(ctx);
    if (input.version !== room.version) fail(409, "version_conflict", VERSION_CONFLICT);
    if (input.name != null && rooms.some((o) => o.id !== room.id && o.name === input.name)) {
      fail(422, "validation_failed", "Tên phòng đã tồn tại.");
    }
    if (input.name != null) room.name = input.name;
    if (input.capacity != null) room.capacity = input.capacity;
    if (input.active != null) room.active = input.active;
    room.version += 1;
    return { body: room };
  });

  r.post("/api/v1/room-blocks", "admin.rules", (ctx): Reply => {
    const input = bodyOf<S["RoomBlockCreate"]>(ctx);
    roomOr404(input.room_id);
    const inside = input.start >= "08:00" && input.end <= "18:00" && input.start < input.end;
    if (!inside || input.reason.trim() === "") {
      fail(422, "validation_failed", "Khoảng khóa phải hợp lệ trong 08:00–18:00 và có lý do.");
    }
    const created: S["RoomBlockOut"] = {
      id: uid("block"),
      room_id: input.room_id,
      day: input.day,
      start: input.start,
      end: input.end,
      reason: input.reason.trim(),
      created_by: ctx.session?.userId ?? null,
    };
    blocks.push(created);
    return { status: 201, body: created };
  });

  r.delete("/api/v1/room-blocks/{block_id}", "admin.rules", (ctx): Reply => {
    const index = blocks.findIndex((b) => b.id === ctx.params.block_id);
    if (index < 0)
      fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (khóa phòng)");
    blocks.splice(index, 1);
    return { status: 204 };
  });
}

// ---------------------------------------------------------------------------------------------------- studio
function registerStudio(r: Router): void {
  r.get("/api/v1/studio/{patient_id}", "patient.read_360", (ctx): Reply => {
    const patient = patientById(ctx.params.patient_id ?? "");
    if (!patient)
      fail(404, "not_found", "Không tìm thấy dữ liệu trong phòng khám này. (bệnh nhân)");
    const view = ctx.query.get("view") ?? STUDIO_VIEWS[0] ?? "";
    if (!STUDIO_VIEWS.includes(view)) fail(422, "validation_failed", "Góc ảnh không hợp lệ.");
    const media = (consents[patient.id] ?? []).find((c) => c.kind === "media");
    const out: S["StudioOut"] = {
      patient_id: patient.id,
      patient_code: patient.code,
      patient_name: patient.full_name,
      concern: "Nám · tăng sắc tố",
      view,
      views: STUDIO_VIEWS,
      media_consent: media?.granted === true,
      photos: [],
    };
    return { body: out };
  });
}

export function register(r: Router): void {
  registerServices(r);
  registerProtocols(r);
  registerResources(r);
  registerStudio(r);
}

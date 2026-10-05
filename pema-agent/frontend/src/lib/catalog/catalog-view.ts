// Pure rules of the three configuration screens (`/services`, `/resources`, `/studio`; package U, step U4).
// The backend owns every rule (who may change the catalog, the versioned price and rate snapshots, the 08:00-18:00
// block window, the audit); this file only words things for the screen and checks a form BEFORE it is sent with the
// same bounds the old web used (`operations-data.js` `updateService`, `block`), so a mistake is told in place and
// the BE answer stays the last word. Money is whole VND, a commission rate is basis points (10000 = 100 %).
import type { Schemas } from "@/lib/api";
import { ApiError } from "@/lib/api/client";

export type ServiceRow = Schemas["ServiceOut"];
export type ServiceDetail = Schemas["ServiceDetailOut"];
export type ServiceBasis = Schemas["ServiceBasis"];
export type ProtocolRow = Schemas["ProtocolOut"];
export type RoomRow = Schemas["RoomOut"];
export type DoctorRow = Schemas["DoctorResourceOut"];
export type BlockRow = Schemas["RoomBlockOut"];
export type ShiftInterval = Schemas["ShiftIntervalOut"];

// ---------------------------------------------------------------------------------------------------- money
export const BASES: readonly ServiceBasis[] = ["net", "list", "collected"];

/** Labels of the finance prototype (`finance.js`). */
export const BASIS_LABEL: Record<ServiceBasis, string> = {
  net: "Giá sau giảm",
  list: "Giá niêm yết",
  collected: "Theo thực thu",
};

/** The basis a `<select>` value stands for; the value always comes from `BASES`, `net` is only the fallback. */
export function asBasis(value: string): ServiceBasis {
  return BASES.find((basis) => basis === value) ?? "net";
}

const VND = new Intl.NumberFormat("vi-VN");

/** "2.500.000 ₫". */
export function formatVnd(amount: number): string {
  return `${VND.format(amount)} ₫`;
}

/** Basis points as the percentage people type: 2000 -> "20", 1250 -> "12,5". */
export function bpToPercentText(bp: number): string {
  return String(bp / 100).replace(".", ",");
}

/** "20%" / "12,5%". */
export function formatRate(bp: number): string {
  return `${bpToPercentText(bp)}%`;
}

/** What was typed in the rate box ("12,5" or "12.5") as basis points, or `null` when it is not 0-100 with at most two decimals. */
export function percentTextToBp(text: string): number | null {
  const clean = text.trim().replace(",", ".");
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(clean)) return null;
  const percent = Number(clean);
  if (percent < 0 || percent > 100) return null;
  return Math.round(percent * 100);
}

// -------------------------------------------------------------------------------------------------- services
export const SERVICE_BOUNDS = {
  durationMin: { min: 15, max: 180 },
  bufferMin: { min: 0, max: 60 },
} as const;

const CODE_PATTERN = /^[a-z0-9][a-z0-9-]{1,39}$/;
export const SERVICE_CODE_HINT =
  "Chữ thường, số và dấu gạch ngang, 2-40 ký tự. Không đổi được sau khi tạo.";
export const SERVICE_FORM_PROBLEM =
  "Kiểm tra tên, thời lượng 15–180 phút, đệm 0–60 phút và giá không âm.";
export const RATE_FORM_PROBLEM = "Tỷ lệ tiền thủ thuật từ 0 đến 100%, tối đa hai chữ số thập phân.";
export const CODE_FORM_PROBLEM = `Mã dịch vụ không hợp lệ. ${SERVICE_CODE_HINT}`;

/** Text of the service form, as typed. */
export type ServiceForm = {
  code: string;
  name: string;
  price: string;
  rate: string;
  basis: ServiceBasis;
  duration: string;
  buffer: string;
  protocolCode: string;
  roomIds: readonly string[];
  active: boolean;
};

export function emptyServiceForm(): ServiceForm {
  return {
    code: "",
    name: "",
    price: "",
    rate: "0",
    basis: "net",
    duration: "45",
    buffer: "15",
    protocolCode: "",
    roomIds: [],
    active: true,
  };
}

export function formFromService(s: ServiceRow): ServiceForm {
  return {
    code: s.code,
    name: s.name,
    price: String(s.price_vnd),
    rate: s.rate_bp == null ? "" : bpToPercentText(s.rate_bp),
    basis: s.basis ?? "net",
    duration: String(s.duration_min),
    buffer: String(s.buffer_min),
    protocolCode: s.protocol_code ?? "",
    roomIds: s.room_ids,
    active: s.active,
  };
}

type Parsed = {
  name: string;
  price: number;
  rateBp: number;
  basis: ServiceBasis;
  duration: number;
  buffer: number;
  protocolCode: string | null;
  roomIds: string[];
  active: boolean;
};

function wholeNumber(text: string): number | null {
  return /^\d{1,10}$/.test(text.trim()) ? Number(text.trim()) : null;
}

/** The numbers of the form, or the sentence that says what is wrong. `withRate`: the caller may see and set the commission terms. */
export function parseServiceForm(
  form: ServiceForm,
  options: { create: boolean; withRate: boolean },
): { ok: true; value: Parsed } | { ok: false; problem: string } {
  if (options.create && !CODE_PATTERN.test(form.code.trim())) {
    return { ok: false, problem: CODE_FORM_PROBLEM };
  }
  const duration = wholeNumber(form.duration);
  const buffer = wholeNumber(form.buffer);
  const price = wholeNumber(form.price);
  const { durationMin, bufferMin } = SERVICE_BOUNDS;
  if (
    form.name.trim() === "" ||
    duration === null ||
    duration < durationMin.min ||
    duration > durationMin.max ||
    buffer === null ||
    buffer < bufferMin.min ||
    buffer > bufferMin.max ||
    price === null
  ) {
    return { ok: false, problem: SERVICE_FORM_PROBLEM };
  }
  let rateBp = 0;
  if (options.withRate) {
    const parsed = percentTextToBp(form.rate);
    if (parsed === null) return { ok: false, problem: RATE_FORM_PROBLEM };
    rateBp = parsed;
  }
  return {
    ok: true,
    value: {
      name: form.name.trim(),
      price,
      rateBp,
      basis: form.basis,
      duration,
      buffer,
      protocolCode: form.protocolCode === "" ? null : form.protocolCode,
      roomIds: [...form.roomIds],
      active: form.active,
    },
  };
}

export function buildServiceCreate(value: Parsed, code: string): Schemas["ServiceCreate"] {
  return {
    code: code.trim(),
    name: value.name,
    price_vnd: value.price,
    rate_bp: value.rateBp,
    basis: value.basis,
    duration_min: value.duration,
    buffer_min: value.buffer,
    protocol_code: value.protocolCode,
    room_ids: value.roomIds,
    active: value.active,
  };
}

type ServiceChanges = Omit<Schemas["ServiceUpdate"], "version">;

const when = <T extends object>(condition: boolean, fields: T): T | Record<string, never> =>
  condition ? fields : {};

/** Only what changed, with the version that was read. `null` when nothing changed (no request, no new version). */
export function buildServiceUpdate(
  service: ServiceRow,
  value: Parsed,
  withRate: boolean,
): Schemas["ServiceUpdate"] | null {
  const changes: ServiceChanges = {
    ...when(value.name !== service.name, { name: value.name }),
    ...when(value.active !== service.active, { active: value.active }),
    ...when(value.protocolCode !== (service.protocol_code ?? null), {
      protocol_code: value.protocolCode,
    }),
    ...when(!sameSet(value.roomIds, service.room_ids), { room_ids: value.roomIds }),
    ...when(value.price !== service.price_vnd, { price_vnd: value.price }),
    ...when(value.duration !== service.duration_min, { duration_min: value.duration }),
    ...when(value.buffer !== service.buffer_min, { buffer_min: value.buffer }),
    ...when(withRate && value.rateBp !== (service.rate_bp ?? null), { rate_bp: value.rateBp }),
    ...when(withRate && value.basis !== (service.basis ?? null), { basis: value.basis }),
  };
  return Object.keys(changes).length === 0 ? null : { version: service.version, ...changes };
}

function sameSet(a: readonly string[], b: readonly string[]): boolean {
  return a.length === b.length && a.every((x) => b.includes(x));
}

/** True when saving these changes starts a new price/rate snapshot (the form says so before it is sent). */
export function startsNewVersion(body: Schemas["ServiceUpdate"]): boolean {
  return (
    body.price_vnd !== undefined ||
    body.rate_bp !== undefined ||
    body.basis !== undefined ||
    body.duration_min !== undefined ||
    body.buffer_min !== undefined
  );
}

/** "45 phút điều trị" and, when there is one, "15 phút chuẩn bị phòng". */
export function serviceDetails(s: Pick<ServiceRow, "duration_min" | "buffer_min">): string[] {
  const lines = [`${s.duration_min} phút điều trị`];
  if (s.buffer_min > 0) lines.push(`${s.buffer_min} phút chuẩn bị phòng`);
  return lines;
}

// ------------------------------------------------------------------------------------------------- protocols
export const MILESTONE_KEYS = ["d1", "d3", "d7"] as const;
export type MilestoneKey = (typeof MILESTONE_KEYS)[number];

export type ProtocolForm = {
  code: string;
  name: string;
  /** day of each milestone as typed; "" = the protocol has no such milestone */
  milestones: Record<MilestoneKey, string>;
  followup: string;
  window: string;
  active: boolean;
};

export function emptyProtocolForm(): ProtocolForm {
  return {
    code: "",
    name: "",
    milestones: { d1: "1", d3: "3", d7: "7" },
    followup: "30",
    window: "45",
    active: true,
  };
}

export function formFromProtocol(p: ProtocolRow): ProtocolForm {
  const day = (key: MilestoneKey) => p.milestones.find((m) => m.rule_key === key)?.day;
  const text = (key: MilestoneKey) => (day(key) === undefined ? "" : String(day(key)));
  return {
    code: p.code,
    name: p.name,
    milestones: { d1: text("d1"), d3: text("d3"), d7: text("d7") },
    followup: p.followup_days === null ? "" : String(p.followup_days),
    window: String(p.window_days),
    active: p.active,
  };
}

/** "D+1, D+3, D+7" in the order of the days; "Không có mốc" for none. */
export function milestonesLabel(p: Pick<ProtocolRow, "milestones">): string {
  if (p.milestones.length === 0) return "Không có mốc";
  return p.milestones
    .toSorted((a, b) => a.day - b.day)
    .map((m) => `D+${m.day}`)
    .join(", ");
}

export const PROTOCOL_FORM_PROBLEM =
  "Mỗi mốc là số ngày từ 0 đến 365 và không vượt cửa sổ áp dụng; ngày đánh giá lại từ 1 đến 365.";

type ProtocolParsed = {
  name: string;
  milestones: Schemas["ProtocolMilestone"][];
  followupDays: number | null;
  windowDays: number;
  active: boolean;
};

function isDay(day: number | null, max: number): day is number {
  return day !== null && day <= max;
}

export function parseProtocolForm(
  form: ProtocolForm,
  options: { create: boolean },
): { ok: true; value: ProtocolParsed } | { ok: false; problem: string } {
  const refuse = { ok: false, problem: PROTOCOL_FORM_PROBLEM } as const;
  if (options.create && !CODE_PATTERN.test(form.code.trim())) {
    return { ok: false, problem: CODE_FORM_PROBLEM };
  }
  const windowDays = wholeNumber(form.window);
  if (form.name.trim() === "" || windowDays === null || windowDays < 1 || windowDays > 365) {
    return refuse;
  }
  const typed = MILESTONE_KEYS.map((key) => ({ key, raw: form.milestones[key].trim() })).filter(
    (m) => m.raw !== "",
  );
  const days = typed.map((m) => wholeNumber(m.raw));
  if (!days.every((day) => isDay(day, Math.min(365, windowDays)))) return refuse;
  const milestones = typed.map((m, i) => ({ rule_key: m.key, day: days[i] ?? 0 }));
  const followup = wholeNumber(form.followup);
  const followupTyped = form.followup.trim() !== "";
  if (followupTyped && (followup === null || followup < 1 || followup > 365)) return refuse;
  return {
    ok: true,
    value: {
      name: form.name.trim(),
      milestones,
      followupDays: followupTyped ? followup : null,
      windowDays,
      active: form.active,
    },
  };
}

// --------------------------------------------------------------------------------------------- doctors, rooms
export const BLOCK_WINDOW = { from: "08:00", to: "18:00" } as const;
export const BLOCK_FORM_PROBLEM = "Khoảng khóa phải hợp lệ trong 08:00–18:00 và có lý do.";

export type BlockForm = { roomId: string; day: string; start: string; end: string; reason: string };

export function validateBlockForm(form: BlockForm): string {
  const valid =
    form.roomId !== "" &&
    /^\d{4}-\d{2}-\d{2}$/.test(form.day) &&
    form.reason.trim() !== "" &&
    form.start >= BLOCK_WINDOW.from &&
    form.end <= BLOCK_WINDOW.to &&
    form.start < form.end;
  return valid ? "" : BLOCK_FORM_PROBLEM;
}

/** "08:00–12:00 · 13:00–18:00"; "Chưa có ca" when the day has no interval. */
export function shiftLabel(shift: readonly ShiftInterval[]): string {
  if (shift.length === 0) return "Chưa có ca";
  return shift.map((i) => `${i.start}–${i.end}`).join(" · ");
}

/** "Nghỉ 12:00–13:00": the gap between two intervals of the day, if there is one. */
export function breakLabel(shift: readonly ShiftInterval[]): string | null {
  const ordered = shift.toSorted((a, b) => a.start.localeCompare(b.start));
  const gap = ordered
    .slice(1)
    .map((after, i) => ({ from: ordered[i]?.end ?? "", to: after.start }))
    .find((g) => g.from < g.to);
  return gap ? `Nghỉ ${gap.from}–${gap.to}` : null;
}

/** Width of the load bar: booked minutes over the shift, never above 100. */
export function loadPercent(bookedMinutes: number, shiftMinutes: number): number {
  if (shiftMinutes <= 0) return 0;
  return Math.min(100, Math.round((bookedMinutes / shiftMinutes) * 100));
}

/** "6 lịch · 270 phút điều trị / 540 phút ca". */
export function loadLine(
  d: Pick<DoctorRow, "booked_count" | "booked_minutes" | "shift_minutes">,
): string {
  return `${d.booked_count} lịch · ${d.booked_minutes} phút điều trị / ${d.shift_minutes} phút ca`;
}

// ------------------------------------------------------------------------------------------------------ studio
export const STUDIO_ALIGNMENT_NOTICE =
  "Chưa kiểm định căn chỉnh ảnh; bác sĩ kiểm tra điều kiện chụp trước khi so sánh.";

/** Said under the metadata: the images are illustrations, so no medical effect may be read from them. */
export const STUDIO_NO_MEDICAL_READING = "Không suy ra hiệu quả y khoa từ ảnh minh họa.";

/** The metadata line under the comparison ("vùng Mặt; góc Chính diện; ... đồng ý chăm sóc: có ghi nhận"). */
export function studioMetadata(view: string, consent: boolean, hasPhotos: boolean): string {
  return `Metadata: vùng Mặt; góc ${view}; mốc buổi ${hasPhotos ? "gần nhất" : "minh họa"}; đồng ý chăm sóc: ${consent ? "có ghi nhận" : "chưa xác nhận"}.`;
}

// ------------------------------------------------------------------------------------------------------ errors
const FIXED: Record<number, string> = {
  401: "Phiên đăng nhập đã hết. Hãy đăng nhập lại.",
  403: "Bạn không có quyền thay đổi mục này. Chỉ chủ phòng khám và quản lý được sửa danh mục.",
  404: "Mục này không còn nữa. Danh sách đã được tải lại.",
};
const CONFLICT_MESSAGE =
  "Mục này vừa được người khác thay đổi. Danh sách đã được tải lại, hãy thử lại.";

/** The sentence the screen shows for a failed catalog call (the BE's own 409 and 422 sentences are Vietnamese). */
export function catalogErrorMessage(error: unknown): string {
  if (!(error instanceof ApiError)) return "Có lỗi xảy ra. Hãy thử lại.";
  if (error.code === "version_conflict") return CONFLICT_MESSAGE;
  const fixed = FIXED[error.status];
  if (fixed) return fixed;
  if (error.status === 409 || error.status === 422 || error.status === 0) return error.message;
  return "Có lỗi xảy ra. Hãy thử lại.";
}

/** After these answers the list on screen is stale. */
export function catalogStale(error: unknown): boolean {
  return error instanceof ApiError && (error.code === "version_conflict" || error.status === 404);
}

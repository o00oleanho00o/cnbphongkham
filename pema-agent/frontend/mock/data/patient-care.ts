// Fictional plans, sessions, consult notes and photos for Patient 360 (package U, step U3). Everything is
// synthetic: the "photos" are small generated colour blocks (valid PNGs), never a picture of a person.
import { deflateSync } from "node:zlib";

import { DAY, isoFromNow, uuid, type Schemas } from "../core";
import { patientRef } from "./clinic";

type S = Schemas;

export type StoredMedia = S["MediaOut"] & { bytes: Buffer | null; declaredSize: number };

export const plans: Array<S["TreatmentPlanOut"] & { patient_id: string }> = [];
export const sessions: S["SessionDetailOut"][] = [];
export const notes: S["ConsultNoteOut"][] = [];
export const media: StoredMedia[] = [];

// ------------------------------------------------------------ tiny PNG (colour block with a soft gradient)

const CRC_TABLE: number[] = Array.from({ length: 256 }, (_unused, n) =>
  Array.from({ length: 8 }).reduce<number>((c) => (c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1), n),
);

function crc32(data: Buffer): number {
  return (
    (data.reduce((crc, byte) => CRC_TABLE[(crc ^ byte) & 0xff]! ^ (crc >>> 8), 0xffffffff) ^
      0xffffffff) >>>
    0
  );
}

function chunk(type: string, data: Buffer): Buffer {
  const body = Buffer.concat([Buffer.from(type, "ascii"), data]);
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(body));
  return Buffer.concat([length, body, crc]);
}

/** A 48x60 PNG: a vertical gradient between two tints. Valid for any browser, carries no content. */
export function placeholderPng(
  top: [number, number, number],
  bottom: [number, number, number],
): Buffer {
  const width = 48;
  const height = 60;
  const rows = Array.from({ length: height }, (_unused, y) => {
    const mix = y / (height - 1);
    const pixel = top.map((t, i) => Math.round(t + (bottom[i]! - t) * mix));
    return Buffer.concat([
      Buffer.from([0]),
      ...Array.from({ length: width }, () => Buffer.from(pixel)),
    ]);
  });
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header.set([8, 2, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(Buffer.concat(rows))),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

// ------------------------------------------------------------------------------------------------ seeds

const doctorOf = (n: number): { id: string | null; name: string | null } => {
  const p = patientRef(n);
  return { id: p.doctor_id ?? null, name: p.doctor_name ?? null };
};

function seedSession(
  n: number,
  planId: string,
  index: number,
  daysAgo: number,
  total: number,
): S["SessionDetailOut"] {
  const doctor = doctorOf(n);
  return {
    id: uuid(n * 100 + index, 14),
    patient_id: patientRef(n).id,
    plan_id: planId,
    performed_at: isoFromNow(-daysAgo * DAY),
    doctor_id: doctor.id,
    doctor_name: doctor.name,
    protocol_id: "laser-co2",
    title: `Buổi ${index}/${total} · Laser CO2`,
    status: "completed",
    session_type: "Laser CO2",
    region: "Mặt",
    view: "Chính diện",
    next_visit_on: null,
    note:
      index === 1 ? "Da nhạy cảm, đỏ nhẹ sau buổi đầu (mẫu)." : "Đỏ giảm, da hồi phục tốt (mẫu).",
    aftercare: "Dưỡng ẩm dịu nhẹ, chống nắng SPF 50+ mỗi sáng (mẫu).",
    reviewed: true,
    reviewed_by: doctor.id,
    reviewed_at: isoFromNow(-daysAgo * DAY),
    consent_id: null,
    version: 2,
  };
}

function seedPlan(n: number, title: string, completed: number, total: number): void {
  const patient = patientRef(n);
  const planId = uuid(n * 10 + 3, 13);
  plans.push({
    id: planId,
    patient_id: patient.id,
    episode_id: n === 1 || n === 7 ? uuid(1, 12) : null,
    service_code: "laser-co2",
    title,
    goal: "Giảm biểu hiện tăng sắc tố, theo dõi đáp ứng qua từng mốc ảnh (mẫu).",
    total_sessions: total,
    completed_sessions: completed,
    status: completed >= total ? "completed" : "active",
    doctor_id: patient.doctor_id ?? null,
    version: 1 + completed,
  });
  Array.from({ length: completed }, (_unused, i) =>
    seedSession(n, planId, i + 1, (completed - i) * 14, total),
  ).forEach((s) => sessions.unshift(s));
}

function seedPhoto(
  n: number,
  index: number,
  stage: S["MediaStage"],
  daysAgo: number,
  tint: [[number, number, number], [number, number, number]],
): void {
  const patient = patientRef(n);
  const bytes = placeholderPng(tint[0], tint[1]);
  media.push({
    id: uuid(n * 100 + index, 15),
    patient_id: patient.id,
    session_id: null,
    stage,
    region: "Mặt",
    view: "Chính diện",
    mime: "image/png",
    size_bytes: bytes.length,
    status: "confirmed",
    consent_id: uuid(300, 6),
    consent_active: true,
    uploaded_by: patient.doctor_id ?? null,
    uploaded_by_name: patient.doctor_name ?? null,
    created_at: isoFromNow(-daysAgo * DAY),
    confirmed_at: isoFromNow(-daysAgo * DAY),
    content_path: `/api/v1/media/${uuid(n * 100 + index, 15)}/content`,
    version: 3,
    bytes,
    declaredSize: bytes.length,
  });
}

seedPlan(1, "Laser CO2 phục hồi da (4 buổi)", 2, 4);
seedPlan(7, "Laser CO2 vùng má (3 buổi)", 1, 3);
seedPhoto(1, 1, "before", 60, [
  [226, 196, 178],
  [205, 164, 144],
]);
seedPhoto(1, 2, "after", 6, [
  [236, 212, 196],
  [220, 186, 168],
]);
notes.push({
  id: uuid(1, 16),
  patient_id: patientRef(1).id,
  status: "approved",
  source_text: "Da ổn hơn",
  body: "Ghi chú tư vấn (mẫu): da ổn hơn, đỏ giảm sau 2 ngày. Tiếp tục chăm sóc tại nhà theo hướng dẫn.",
  created_by: doctorOf(1).id,
  created_by_name: doctorOf(1).name,
  approved_by: doctorOf(1).id,
  approved_by_name: doctorOf(1).name,
  approved_at: isoFromNow(-6 * DAY),
  created_at: isoFromNow(-6 * DAY),
  version: 2,
});

// ----------------------------------------------------------------------------------------------- views

export const plansOf = (patientId: string): S["TreatmentPlanOut"][] =>
  plans.filter((p) => p.patient_id === patientId).map(({ patient_id: _patient, ...plan }) => plan);

export const sessionsOf = (patientId: string): S["SessionDetailOut"][] =>
  sessions
    .filter((s) => s.patient_id === patientId)
    .toSorted((a, b) => b.performed_at.localeCompare(a.performed_at));

/** The light session of the 360 list: no clinical text. */
export function lightSession(s: S["SessionDetailOut"]): S["TreatmentSessionOut"] {
  return {
    id: s.id,
    plan_id: s.plan_id ?? null,
    performed_at: s.performed_at,
    doctor_id: s.doctor_id ?? null,
    protocol_id: s.protocol_id ?? null,
    title: s.title,
    status: s.status,
    session_type: s.session_type ?? null,
    region: s.region ?? null,
    view: s.view ?? null,
    next_visit_on: s.next_visit_on ?? null,
    reviewed: s.reviewed ?? false,
    version: s.version ?? 1,
  };
}

export const publicMedia = ({
  bytes: _bytes,
  declaredSize: _size,
  ...rest
}: StoredMedia): S["MediaOut"] => rest;

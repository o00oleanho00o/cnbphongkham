/** Words and small functions the pages share (no screen code here). */
import type { Audience, Lifecycle, Processing, Progress, WarningLevel } from "./types";

/** The approval step ("Duyệt") is hidden for now (user, 2026-10-12): every source is used as soon as it is ready.
 * Set it back to true to show the column, filter, buttons and settings again; the data model keeps `approved`. */
export const APPROVAL_STEP = false;

/** One shared store for every channel (user, 2026-10-12): no patient/staff split while the agent's answers from the
 * documents are being tested. Hides "Đối tượng" everywhere; set it back to true to bring the split back. */
export const AUDIENCE_SPLIT = false;

export type Tone = "neutral" | "info" | "success" | "warning" | "danger";

export const AUDIENCE_LABEL: Record<Audience, string> = {
  patient: "Bệnh nhân",
  staff: "Nội bộ",
};

export const AUDIENCE_HINT: Record<Audience, string> = {
  patient: "Agent được trả lời bệnh nhân từ nguồn này",
  staff: "Chỉ nhân viên thấy; kênh bệnh nhân không dùng",
};

export const LIFECYCLE_LABEL: Record<Lifecycle, string> = {
  active: "Đang dùng",
  draft: "Nháp",
  superseded: "Đã thay thế",
  expired: "Hết hạn",
  adversarial: "Tấn công thử",
};

export const LIFECYCLE_TONE: Record<Lifecycle, Tone> = {
  active: "success",
  draft: "neutral",
  superseded: "neutral",
  expired: "warning",
  adversarial: "danger",
};

export const PROCESSING_LABEL: Record<Processing, string> = {
  queued: "Chờ",
  processing: "Đang xử lý",
  ready: "Sẵn sàng",
  error: "Lỗi",
};

export const PROCESSING_TONE: Record<Processing, Tone> = {
  queued: "neutral",
  processing: "info",
  ready: "success",
  error: "danger",
};

export const WARNING_TONE: Record<WarningLevel, Tone> = {
  info: "info",
  warn: "warning",
  error: "danger",
};

/** Formats accepted when adding files. */
export const FILE_EXTENSIONS = [".md", ".txt", ".docx", ".xlsx", ".pdf"] as const;
export const MAX_FILE_BYTES = 25 * 1024 * 1024;
export const MAX_TEXT_CHARS = 100_000;

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** `2026-10-12` or an ISO time as `12/10/2026`; empty when there is none. */
export function formatDate(value: string | null): string {
  if (!value) return "";
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}

/** "đã chia 42 đoạn · nhãn 18/42 · vector 0/42", the line under the bar of a source being processed. */
export function progressText(progress: Progress): string {
  return `đã chia ${progress.chunks} đoạn · nhãn ${progress.labelled}/${progress.chunks} · vector ${progress.embedded}/${progress.chunks}`;
}

/** 0-100: how far a source is, the three stages counting equally. */
export function progressPercent(progress: Progress): number {
  if (progress.chunks === 0) return 0;
  const done = progress.labelled + progress.embedded + progress.chunks;
  return Math.round((done / (progress.chunks * 3)) * 100);
}

/** A period as "từ 01/10/2026" / "đến 30/09/2026" / "01/10/2026 - 30/09/2027"; "không hạn" when open. */
export function periodText(from: string | null, to: string | null): string {
  if (from && to) return `${formatDate(from)} - ${formatDate(to)}`;
  if (from) return `từ ${formatDate(from)}`;
  if (to) return `đến ${formatDate(to)}`;
  return "không hạn";
}

export function todayIso(now: Date = new Date()): string {
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${now.getFullYear()}-${month}-${day}`;
}

export function hasExtension(name: string): boolean {
  const lower = name.toLowerCase();
  return FILE_EXTENSIONS.some((extension) => lower.endsWith(extension));
}

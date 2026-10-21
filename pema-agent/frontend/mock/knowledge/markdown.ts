// Pure helpers of the fake knowledge store: read headings out of Markdown, cut it into chunks, make a believable
// text for a source that has none, take sections out of a text. Used by `detail.ts`.
import type { OutlineNode } from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";

export interface Section {
  level: number;
  title: string;
  /** The text under the heading up to the next heading, trimmed. */
  body: string;
  /** Line range [start, end) of the heading and its text. */
  start: number;
  end: number;
}

export interface ChunkDraft {
  id: string;
  ordinal: number;
  path: string;
  text: string;
  chars: number;
}

const HEADING = /^(#{1,6})\s+(.+?)\s*$/;
/** Sections at these levels carry a chunk of their own (when they have text). */
const CHUNK_LEVELS = [2, 3];

export function sectionsOf(markdown: string): Section[] {
  const lines = markdown.split("\n");
  const heads = lines.flatMap((line, index) => {
    const found = HEADING.exec(line);
    return found ? [{ level: found[1]?.length ?? 1, title: found[2] ?? "", index }] : [];
  });
  return heads.map((head, position) => {
    const end = heads[position + 1]?.index ?? lines.length;
    return {
      level: head.level,
      title: head.title,
      start: head.index,
      end,
      body: lines
        .slice(head.index + 1, end)
        .join("\n")
        .trim(),
    };
  });
}

function carriesChunk(section: Section): boolean {
  return CHUNK_LEVELS.includes(section.level) && section.body.length > 0;
}

export function outlineOf(markdown: string): OutlineNode[] {
  return sectionsOf(markdown).map((section) => ({
    level: section.level,
    title: section.title,
    chunks: carriesChunk(section) ? 1 : 0,
    chars: section.body.length,
  }));
}

/** "Tiêu đề > Mục > Mục con": the headings above a section, itself included. */
function pathsOf(sections: readonly Section[]): string[] {
  return sections.reduce<{ stack: { level: number; title: string }[]; paths: string[] }>(
    (acc, section) => {
      const stack = [...acc.stack.filter((above) => above.level < section.level), section];
      return { stack, paths: [...acc.paths, stack.map((above) => above.title).join(" > ")] };
    },
    { stack: [], paths: [] },
  ).paths;
}

export function chunksOf(sourceId: string, markdown: string): ChunkDraft[] {
  const sections = sectionsOf(markdown);
  const paths = pathsOf(sections);
  return sections
    .flatMap((section, index) =>
      carriesChunk(section) ? [{ section, path: paths[index] ?? section.title }] : [],
    )
    .map(({ section, path }, ordinal) => ({
      id: `${sourceId}-c${ordinal + 1}`,
      ordinal,
      path,
      text: section.body,
      chars: section.body.length,
    }));
}

/** The line range [start, end) of the section at `position` with everything nested under it. */
function spanOf(sections: readonly Section[], position: number): [number, number] {
  const head = sections[position];
  if (!head) return [0, 0];
  const after = sections.slice(position + 1);
  const next = after.findIndex((section) => section.level <= head.level);
  const nested = next === -1 ? after.length : next;
  const last = after[nested - 1] ?? head;
  return [head.start, last.end];
}

/** Takes the sections at these outline positions (with what is nested under them) out of the text. */
export function takeSections(
  markdown: string,
  positions: readonly number[],
): { kept: string; moved: string } {
  const lines = markdown.split("\n");
  const sections = sectionsOf(markdown);
  const taken = new Set(
    positions.flatMap((position) => {
      const [start, end] = spanOf(sections, position);
      return lines.map((_, index) => index).filter((index) => index >= start && index < end);
    }),
  );
  const pick = (wanted: boolean) =>
    lines
      .filter((_, index) => taken.has(index) === wanted)
      .join("\n")
      .trim();
  return { kept: pick(false), moved: pick(true) };
}

function money(value: number): string {
  return `${String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ".")}đ`;
}

/** A believable text of 4-6 sections about a title, for sources the mock has no text for. */
export function generateMarkdown(title: string): string {
  const rows = Array.from({ length: 26 }, (_, index) => {
    const sessions = index + 1;
    return `| Liệu trình ${sessions} buổi | ${money(sessions * 1_200_000 - (sessions > 5 ? 300_000 : 0))} | Bảo hành ${sessions > 5 ? 6 : 3} tháng |`;
  });
  return [
    `# ${title}`,
    "",
    `Tài liệu mẫu (dữ liệu giả lập) về "${title}" của Pema Clinic & Spa.`,
    "",
    "## Tổng quan",
    `${title} do bác sĩ da liễu của phòng khám thực hiện sau khi tư vấn và soi da. Hiệu quả phụ thuộc vào cơ địa, mức độ tổn thương và việc chăm sóc tại nhà; bác sĩ sẽ nói rõ kết quả dự kiến trước khi bắt đầu.`,
    "",
    "## Quy trình thực hiện",
    "Khách được khám, chụp ảnh da và ký đồng ý trước khi làm. Mỗi buổi kéo dài từ 30 đến 60 phút.",
    "",
    "### Trước khi làm",
    "Không dùng thuốc bôi có acid trong 3 ngày trước buổi hẹn. Báo cho bác sĩ nếu đang mang thai, cho con bú hoặc có tiền sử dị ứng.",
    "",
    "### Sau khi làm",
    "Dùng kem chống nắng mỗi ngày, tránh nắng gắt và không tự ý bóc vảy. Tái khám theo lịch hẹn để bác sĩ điều chỉnh liệu trình.",
    "",
    "## Bảng giá tham khảo",
    "| Gói | Giá | Bảo hành |",
    "| --- | --- | --- |",
    ...rows,
    "",
    "## Lưu ý và chính sách",
    "Giá có thể thay đổi theo chương trình từng thời kỳ. Phòng khám không hoàn tiền sau khi đã thực hiện, trừ khi có sai sót chuyên môn được xác nhận.",
    "",
    "## Liên hệ",
    "Hotline 0900 000 000 (số giả lập). Giờ làm việc 8:00 - 20:00 mỗi ngày.",
  ].join("\n");
}

/** "2.0" -> "2.1"; a source with no version starts at "1.1". */
export function bumpVersion(version: string | null): string {
  const found = /^(\d+)\.(\d+)$/.exec(version ?? "1.0");
  return found ? `${found[1]}.${Number(found[2]) + 1}` : `${version ?? "1.0"}.1`;
}

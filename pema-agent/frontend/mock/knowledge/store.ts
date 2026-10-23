// The fake knowledge store behind `bun run dev:mock`: sources, services, settings and gaps held in memory, with
// FICTIONAL data (the Pema demo clinic). The route files of this folder read and change this one object; the real
// plugin is built later (docs/PLAN-knowledge-plugin.md).
import type {
  Gap,
  KnowledgeSettings,
  Service,
  Source,
  SourceEvent,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";

export interface Store {
  sources: Source[];
  /** Source id -> the Markdown the reader built; sources without an entry show a short generated text. */
  markdown: Map<string, string>;
  events: Map<string, SourceEvent[]>;
  services: Service[];
  gaps: Gap[];
  settings: KnowledgeSettings;
  /** Previews waiting for a confirm: preview id -> the parsed items, whatever the add route stored. */
  previews: Map<string, unknown>;
}

const NOW = "2026-10-12T08:30:00+07:00";

function source(partial: Partial<Source> & Pick<Source, "id" | "title">): Source {
  return {
    doc_code: null,
    kind: "file",
    format: "md",
    size: 8_400,
    services: [],
    audience: "patient",
    processing: "ready",
    progress: { chunks: 12, labelled: 12, embedded: 12 },
    error: null,
    lifecycle: "active",
    version: "2.0",
    effective_from: "2026-10-01",
    effective_to: null,
    approved: true,
    approved_by: "Quản trị",
    approved_at: NOW,
    chunk_count: 12,
    note: "",
    created_by: "Quản trị",
    created_at: NOW,
    updated_at: NOW,
    ...partial,
  };
}

function seedSources(): Source[] {
  return [
    source({
      id: "src-seed-1",
      title: "Pema Clinic & Spa (demo): bảng giá hiện hành",
      doc_code: "DEMO-PEMA-D07",
      services: ["NAM", "HORI", "TANNHANG", "MUN"],
      chunk_count: 13,
      progress: { chunks: 13, labelled: 13, embedded: 0 },
    }),
    source({
      id: "src-seed-2",
      title: "Bảng giá cũ (đến 30/09/2026)",
      doc_code: "DEMO-PEMA-D07-V1",
      services: ["NAM", "HORI"],
      version: "1.0",
      effective_from: "2026-01-01",
      effective_to: "2026-09-30",
      lifecycle: "superseded",
      chunk_count: 11,
      progress: { chunks: 11, labelled: 11, embedded: 0 },
    }),
    source({
      id: "src-seed-3",
      title: "Quy trình tư vấn nội bộ",
      doc_code: "DEMO-PEMA-D19",
      audience: "staff",
      chunk_count: 8,
      progress: { chunks: 8, labelled: 8, embedded: 0 },
    }),
    source({
      id: "src-seed-4",
      title: "Cẩm nang nám - bớt Hori (bản PDF)",
      kind: "file",
      format: "pdf",
      size: 2_400_000,
      processing: "processing",
      chunk_count: 42,
      progress: { chunks: 42, labelled: 18, embedded: 0 },
    }),
    source({
      id: "src-seed-5",
      title: "Phiếu khảo sát khách (bản scan)",
      format: "pdf",
      size: 5_100_000,
      processing: "error",
      error: "PDF là ảnh scan, chưa đọc được chữ. Bật Docling trong Cài đặt hoặc dán nội dung vào.",
      chunk_count: 0,
      progress: { chunks: 0, labelled: 0, embedded: 0 },
    }),
    source({
      id: "src-seed-6",
      title: "Giờ mở cửa dịp lễ",
      kind: "text",
      format: "text",
      size: 640,
      services: [],
      version: null,
      effective_from: null,
      chunk_count: 2,
      progress: { chunks: 2, labelled: 2, embedded: 0 },
    }),
  ];
}

function seedServices(): Service[] {
  const base = { branches: [] as string[], enabled: true, description: "" };
  return [
    {
      ...base,
      id: "svc-nam",
      code: "NAM",
      name: "Điều trị nám",
      aliases: ["nám", "trị nám", "nám má"],
      description: "Laser và liệu trình trị nám",
      chunk_count: 38,
      branches: ["Hà Nội", "HCM"],
    },
    {
      ...base,
      id: "svc-hori",
      code: "HORI",
      name: "Bớt Hori",
      aliases: ["hori", "bớt hori", "nám hori"],
      description: "Điều trị bớt Hori",
      chunk_count: 27,
      branches: ["Hà Nội"],
    },
    {
      ...base,
      id: "svc-tannhang",
      code: "TANNHANG",
      name: "Tàn nhang",
      aliases: ["tàn nhang", "đồi mồi"],
      chunk_count: 9,
      branches: ["Hà Nội"],
    },
    {
      ...base,
      id: "svc-mun",
      code: "MUN",
      name: "Điều trị mụn",
      aliases: ["mụn", "trị mụn", "mụn viêm"],
      chunk_count: 14,
      branches: ["Hà Nội", "HCM"],
    },
    {
      ...base,
      id: "svc-peel",
      code: "PEEL",
      name: "Peel da",
      aliases: ["peel", "lột da"],
      chunk_count: 5,
      branches: ["Hà Nội", "HCM"],
    },
    {
      ...base,
      id: "svc-facial",
      code: "FACIAL",
      name: "Chăm sóc da",
      aliases: ["facial", "chăm sóc da mặt"],
      chunk_count: 6,
      branches: ["Hà Nội", "HCM"],
    },
    {
      ...base,
      id: "svc-consult",
      code: "CONSULT",
      name: "Tư vấn",
      aliases: ["tư vấn", "khám tư vấn"],
      chunk_count: 4,
      enabled: true,
    },
  ];
}

function seedGaps(): Gap[] {
  const gap = (
    id: string,
    question: string,
    count: number,
    channel: string,
    last: string,
  ): Gap => ({
    id,
    question,
    count,
    channel,
    last_asked_at: last,
    state: "open",
  });
  return [
    gap("gap-1", "có làm laser trị sẹo rỗ không", 7, "zalo-cskh-mau", "2026-10-11T16:20:00+07:00"),
    gap(
      "gap-2",
      "phòng khám có bãi gửi xe ô tô không",
      4,
      "zalo-cskh-mau",
      "2026-10-10T10:05:00+07:00",
    ),
    gap(
      "gap-3",
      "thanh toán bằng thẻ tín dụng có phụ phí không",
      3,
      "zalo-bot",
      "2026-10-12T07:40:00+07:00",
    ),
    gap(
      "gap-4",
      "trẻ dưới 16 tuổi có điều trị được không",
      2,
      "zalo-cskh-mau",
      "2026-10-09T14:12:00+07:00",
    ),
  ];
}

function seedSettings(): KnowledgeSettings {
  return {
    embedding: {
      base_url: "",
      model: "qwen/qwen3-embedding-8b",
      dimensions: 1024,
      query_prefix: "",
      document_prefix: "",
      has_key: false,
      origin: "profile",
      chunks_without_vector: 76,
    },
    parser: { kind: "simple", docling_url: "", origin: "profile" },
    labelling: { enabled: true, model_entry: null },
    judging: { enabled: false, level: "medium" },
    search: {
      results: 8,
      min_score: 0.2,
      char_budget: 6000,
      patient_channel_prefix: "zalo-",
      // The approval step is hidden for now (user, 2026-10-12): every source is used once it is ready.
      patient_only_approved: false,
    },
    benchmark_mode: false,
  };
}

function seed(): Store {
  return {
    sources: seedSources(),
    markdown: new Map(),
    events: new Map(),
    services: seedServices(),
    gaps: seedGaps(),
    settings: seedSettings(),
    previews: new Map(),
  };
}

export const store: Store = seed();

let counter = 0;
export function nextId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter}`;
}

export function nowIso(): string {
  return new Date().toISOString();
}

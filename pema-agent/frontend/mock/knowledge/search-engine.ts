// The fake search behind "Thử tìm": believable stages built from the store's sources and services. Pure functions of
// (store, question, channel, date); the real engine is built later (docs/PLAN-knowledge-plugin.md).
import type {
  Candidate,
  SearchDebug,
  SearchDebugQuery,
  SearchStage,
  Service,
  Source,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import type { Store } from "./store";

type Kind = "price" | "policy" | "procedure" | "info";

interface Chunk {
  id: string;
  source: Source;
  kind: Kind;
  path: string;
  excerpt: string;
}

interface Ranked {
  chunk: Chunk;
  score: number;
}

const STOPWORDS = new Set([
  "co",
  "khong",
  "la",
  "va",
  "cua",
  "cho",
  "toi",
  "minh",
  "em",
  "anh",
  "chi",
  "ban",
  "bao",
  "nhieu",
  "the",
  "nao",
  "gi",
  "duoc",
  "o",
  "de",
  "voi",
  "ve",
  "mot",
  "cac",
  "thi",
  "nay",
  "hay",
  "xin",
  "a",
  "ah",
]);

const KIND_WORDS: Record<Exclude<Kind, "info">, readonly string[]> = {
  price: ["gia", "bao nhieu", "chi phi", "phi", "tien"],
  policy: ["huy", "doi lich", "chinh sach", "dat lich", "bao hanh", "hoan"],
  procedure: ["quy trinh", "lam sao", "the nao", "bao lau", "buoi", "cham soc"],
};

const KIND_ORDER = ["price", "policy", "procedure"] as const;
const KIND_TITLE: Record<Kind, string> = {
  price: "Giá",
  policy: "Chính sách",
  procedure: "Quy trình",
  info: "Thông tin",
};

/** Removes Vietnamese diacritics (`đ` too) and lowercases. */
export function fold(text: string): string {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();
}

/** A stable number in [0, 1) for a string, so the same question gives the same fake scores. */
function unit(text: string): number {
  const hash = Array.from(text).reduce(
    (sum, char) => (Math.imul(sum, 31) + char.charCodeAt(0)) >>> 0,
    7,
  );
  return (hash % 10_000) / 10_000;
}

const round = (value: number, digits = 2): number => Number(value.toFixed(digits));

function hasWord(folded: string, phrase: string): boolean {
  const escaped = phrase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^a-z0-9])${escaped}($|[^a-z0-9])`).test(folded);
}

function tokensOf(folded: string): string[] {
  return folded.split(/[^a-z0-9]+/).filter((token) => token.length >= 2 && !STOPWORDS.has(token));
}

export function recogniseServices(folded: string, services: readonly Service[]): Service[] {
  return services.filter(
    (service) =>
      service.enabled &&
      [service.name, ...service.aliases].some((name) => hasWord(folded, fold(name))),
  );
}

function wantedKind(folded: string): Kind {
  const found = KIND_ORDER.find((kind) => KIND_WORDS[kind].some((word) => folded.includes(word)));
  return found ?? "info";
}

function canned(kind: Kind, name: string): string {
  const sentences: Record<Kind, string> = {
    price: `Giá tham khảo ${name}: từ 1.200.000đ mỗi buổi, đã gồm tư vấn và chăm sóc sau điều trị.`,
    policy: `Khách đặt lịch ${name} trước ít nhất 24 giờ; hủy hoặc đổi lịch trước 12 giờ không mất phí.`,
    procedure: `Quy trình ${name}: soi da, làm sạch, thực hiện liệu trình, bôi phục hồi và dặn chăm sóc tại nhà.`,
    info: `Thông tin chung về ${name}: liên hệ lễ tân để được tư vấn chi tiết theo tình trạng da.`,
  };
  return sentences[kind];
}

interface Section {
  path: string;
  lines: string[];
}

/** Sections of a source's Markdown with their heading paths; shown as plain text. */
function sectionsOf(markdown: string): { path: string; text: string }[] {
  const { items } = markdown.split("\n").reduce<{ stack: string[]; items: Section[] }>(
    (state, line) => {
      const heading = /^(#{1,6})\s+(.*)$/.exec(line);
      const current = state.items.at(-1);
      if (!heading) {
        const grown = current
          ? [...state.items.slice(0, -1), { ...current, lines: [...current.lines, line] }]
          : state.items;
        return { ...state, items: grown };
      }
      const stack = [...state.stack.slice(0, (heading[1] ?? "#").length - 1), heading[2] ?? ""];
      return { stack, items: [...state.items, { path: stack.join(" > "), lines: [] }] };
    },
    { stack: [], items: [] },
  );
  return items
    .map((item) => ({ path: item.path, text: item.lines.join(" ").replace(/\s+/g, " ").trim() }))
    .filter((item) => item.text.length > 0);
}

function chunksOf(
  source: Source,
  services: readonly Service[],
  markdown: string | undefined,
): Chunk[] {
  if (markdown) {
    return sectionsOf(markdown)
      .slice(0, source.chunk_count)
      .map((section, index) => ({
        id: `${source.id}-c${index + 1}`,
        source,
        kind: wantedKind(fold(section.path)),
        path: `${source.title} > ${section.path}`,
        excerpt: section.text.slice(0, 220),
      }));
  }
  const own = services.filter((service) => source.services.includes(service.code)).slice(0, 3);
  const named = own.length === 0 ? [{ name: source.title }] : own;
  const kinds: readonly Kind[] = own.length === 0 ? ["info"] : KIND_ORDER;
  return named
    .flatMap((service, serviceIndex) =>
      kinds.map((kind, kindIndex) => ({
        n: serviceIndex * kinds.length + kindIndex + 1,
        service,
        kind,
      })),
    )
    .filter(({ n }) => n <= source.chunk_count)
    .map(({ n, service, kind }) => ({
      id: `${source.id}-c${n}`,
      source,
      kind,
      path: `${source.title} > ${service.name} > ${KIND_TITLE[kind]}`,
      excerpt: canned(kind, service.name),
    }));
}

type Reason = "staff" | "outdated";

const REASONS: readonly Reason[] = ["staff", "outdated"];
const REASON_TEXT: Record<Reason, string> = {
  staff: "đoạn nội bộ",
  outdated: "đoạn hết hiệu lực hoặc ngoài ngày hỏi",
};

/** Why a question may not see a source, or null when it may. Every channel shares one store for now (user,
 * 2026-10-12), so internal sources are not hidden; pass `split` to bring the patient/staff split back. */
export function hiddenReason(source: Source, asOf: string, split = false): Reason | null {
  if (split && source.audience === "staff") return "staff";
  const outside =
    source.lifecycle !== "active" ||
    (source.effective_from !== null && source.effective_from > asOf) ||
    (source.effective_to !== null && source.effective_to < asOf);
  return outside ? "outdated" : null;
}

const toCandidate = ({ chunk, score }: Ranked): Candidate => ({
  chunk_id: chunk.id,
  doc_code: chunk.source.doc_code,
  source_title: chunk.source.title,
  path: chunk.path,
  excerpt: chunk.excerpt,
  score,
});

const stage = (
  id: string,
  title: string,
  ms: number,
  note: string,
  items: readonly Ranked[],
  skipped = false,
): SearchStage => ({ id, title, ms, note, skipped, candidates: items.map(toCandidate) });

const sentence = (...parts: string[]): string => parts.filter(Boolean).join(". ");

export function runSearch(store: Store, query: SearchDebugQuery): SearchDebug {
  const folded = fold(query.question).replace(/\s+/g, " ").trim();
  const recognised = recogniseServices(folded, store.services);
  const codes = recognised.map((service) => service.code);
  const tokens = tokensOf(folded);
  const kind = wantedKind(folded);
  const { settings } = store;
  const patient = query.channel === "patient";
  const channelName = patient ? "bệnh nhân" : "nhân viên";

  const relevance = (source: Source): number => {
    const haystack = fold(
      `${source.title} ${source.doc_code ?? ""} ${store.markdown.get(source.id) ?? ""}`,
    );
    const byService = source.services.some((code) => codes.includes(code)) ? 3 : 0;
    return byService + tokens.filter((token) => haystack.includes(token)).length * 0.4;
  };
  const relevant = store.sources.filter(
    (source) => source.processing === "ready" && source.chunk_count > 0 && relevance(source) > 0,
  );
  const reasonOf = (source: Source): Reason | null => hiddenReason(source, query.as_of);
  const filterText = REASONS.map((reason) => ({
    reason,
    count: relevant
      .filter((source) => reasonOf(source) === reason)
      .reduce((sum, source) => sum + source.chunk_count, 0),
  }))
    .filter(({ count }) => count > 0)
    .map(({ reason, count }) => `${count} ${REASON_TEXT[reason]} bị lọc`)
    .join("; ");

  const chunks = relevant
    .filter((source) => reasonOf(source) === null)
    .flatMap((source) => chunksOf(source, store.services, store.markdown.get(source.id)));
  const hits = (chunk: Chunk): number => {
    const text = fold(`${chunk.path} ${chunk.excerpt}`);
    return tokens.filter((token) => text.includes(token)).length;
  };
  const jitter = (chunk: Chunk): number => unit(`${chunk.id}|${folded}`);
  const byScoreDesc = (a: Ranked, b: Ranked): number => b.score - a.score;

  const keyword = chunks
    .filter((chunk) => hits(chunk) > 0 || chunk.kind === kind)
    .map((chunk) => ({
      chunk,
      score: round(2 + hits(chunk) * 1.3 + (chunk.kind === kind ? 1.6 : 0) + jitter(chunk) * 1.2),
    }))
    .toSorted(byScoreDesc)
    .slice(0, 12);

  const vectorOn = settings.embedding.has_key;
  const vector = vectorOn
    ? chunks
        .map((chunk) => ({
          chunk,
          score: round(
            0.62 - hits(chunk) * 0.05 - (chunk.kind === kind ? 0.12 : 0) + jitter(chunk) * 0.3,
            3,
          ),
        }))
        .toSorted((a, b) => a.score - b.score)
        .slice(0, 12)
    : [];

  const rrf = (ranked: readonly Ranked[], chunk: Chunk): number => {
    const at = ranked.findIndex((item) => item.chunk.id === chunk.id);
    return at < 0 ? 0 : 1 / (60 + at + 1);
  };
  const fused = chunks
    .map((chunk) => ({ chunk, score: round(rrf(keyword, chunk) + rrf(vector, chunk), 4) }))
    .filter(({ score }) => score > 0)
    .toSorted(byScoreDesc)
    .slice(0, 10);

  // The mock has no Jev judge: the judged stage is skipped, as it is on the server while plugin jev is off.
  const reranked: Ranked[] = [];
  const pool = fused;
  const final = pool
    .slice(0, settings.search.results)
    .reduce<{ items: Ranked[]; used: number }>(
      (state, item) =>
        state.used + item.chunk.excerpt.length > settings.search.char_budget
          ? state
          : { items: [...state.items, item], used: state.used + item.chunk.excerpt.length },
      { items: [], used: 0 },
    ).items;

  const base = Math.round(unit(folded) * 6);
  const stages: SearchStage[] = [
    stage(
      "understand",
      "Hiểu câu hỏi",
      3 + base,
      sentence(
        "Bỏ dấu và chuẩn hóa",
        recognised.length
          ? `nhận ra ${recognised.length} dịch vụ (${codes.join(", ")})`
          : "không nhận ra dịch vụ nào, tìm theo từ khóa",
        `Kênh ${channelName}, ngày hỏi ${query.as_of}`,
      ),
      [],
    ),
    stage(
      "keyword",
      "Ứng viên từ khóa (điểm)",
      9 + base,
      sentence(`${keyword.length} đoạn khớp từ khóa (điểm BM25 giả lập)`, filterText),
      keyword,
    ),
    stage(
      "vector",
      "Ứng viên vector (khoảng cách)",
      vectorOn ? 150 + base * 9 : 0,
      vectorOn
        ? `${vector.length} đoạn gần nghĩa nhất (khoảng cách cosine, càng nhỏ càng gần)`
        : "Embedding chưa kết nối: bỏ qua nhánh vector",
      vector,
      !vectorOn,
    ),
    stage(
      "fused",
      "Sau gộp RRF",
      1,
      vectorOn
        ? "Gộp hai danh sách bằng RRF (k = 60)"
        : "Chỉ có nhánh từ khóa nên RRF giữ nguyên thứ tự",
      fused,
    ),
    stage(
      "reranked",
      "Sau xếp lại",
      0,
      "Bộ chấm Jev không có trong bản mô phỏng: bước này bỏ qua",
      reranked,
      true,
    ),
    stage(
      "final",
      "Gói cuối đúng như agent thấy",
      2,
      final.length
        ? sentence(
            `${final.length} đoạn gửi cho agent (tối đa ${settings.search.results}, ngân sách ${settings.search.char_budget} ký tự)`,
            filterText,
          )
        : sentence(
            `Không có đoạn nào phù hợp với câu hỏi này ở kênh ${channelName}: agent sẽ nói chưa có thông tin`,
            filterText,
          ),
      final,
    ),
  ];
  return {
    question: query.question,
    folded,
    services: codes,
    stages,
    total_ms: stages.reduce((sum, item) => sum + item.ms, 0),
  };
}

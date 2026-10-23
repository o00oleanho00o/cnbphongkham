/** What the knowledge store's admin routes (`/v1/plugins/knowledge`) send and take. See docs/PLAN-knowledge-ui.md. */

/** Who may be answered from a source: the patient channel or staff only. */
export type Audience = "patient" | "staff";
/** The lifecycle of the content (not the processing state). */
export type Lifecycle = "active" | "draft" | "superseded" | "expired" | "adversarial";
export type Processing = "queued" | "processing" | "ready" | "error";
export type SourceFormat = "md" | "txt" | "docx" | "xlsx" | "pdf" | "text";

export interface Progress {
  chunks: number;
  labelled: number;
  embedded: number;
}

export interface Source {
  id: string;
  title: string;
  /** The code the answers cite (`doc_id` of the YAML head); unique in the clinic. */
  doc_code: string | null;
  kind: "file" | "text";
  format: SourceFormat;
  size: number;
  services: string[];
  audience: Audience;
  processing: Processing;
  progress: Progress;
  /** A sentence a person can read, when `processing` is `error`. */
  error: string | null;
  lifecycle: Lifecycle;
  version: string | null;
  effective_from: string | null;
  effective_to: string | null;
  approved: boolean;
  approved_by: string | null;
  approved_at: string | null;
  chunk_count: number;
  note: string;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface SourceSummary {
  ready: number;
  chunks: number;
  /** 0-100: chunks that have a vector. */
  embedded_percent: number;
  errors: number;
  unapproved: number;
  processing: number;
}

export interface SourceList {
  items: Source[];
  total: number;
  page: number;
  page_size: number;
  summary: SourceSummary;
  /** Sentences for the strip above the table, like "Embedding chưa kết nối: đang tìm bằng từ khóa". */
  warnings: string[];
}

export interface SourceQuery {
  q?: string;
  processing?: Processing;
  audience?: Audience;
  service?: string;
  lifecycle?: Lifecycle;
  /** `false`: only the sources not approved yet. */
  approved?: boolean;
  page?: number;
}

/** A change of many sources at once. */
export type BulkAction =
  | { action: "approve" }
  | { action: "unapprove" }
  | { action: "audience"; audience: Audience }
  | { action: "reindex" }
  | { action: "delete" };

export interface BulkResult {
  done: number;
  failed: { id: string; message: string }[];
}

export interface SourcePatch {
  title?: string;
  audience?: Audience;
  services?: string[];
  effective_from?: string | null;
  effective_to?: string | null;
  note?: string;
}

// -- adding sources: preview, then confirm ------------------------------------------------------------------

/** One file or one pasted text to look at before it is added. Text files carry `text`; the others `base64`. */
export interface PreviewInput {
  key: string;
  name: string;
  kind: "file" | "text";
  size: number;
  text?: string;
  base64?: string;
}

export interface PreviewMeta {
  doc_code: string | null;
  title: string | null;
  tenant_id: string | null;
  version: string | null;
  lifecycle: Lifecycle | null;
  effective_from: string | null;
  effective_to: string | null;
  audience: Audience | null;
  ingest_role: "kb" | "challenge" | null;
}

export interface OutlineNode {
  level: number;
  title: string;
  /** Chunks under this heading (its own text, not its children's). */
  chunks: number;
  chars: number;
}

export type WarningLevel = "info" | "warn" | "error";

export interface PreviewWarning {
  /** `no_headings`, `scan_pdf`, `personal_data`, `internal_script`, `same_content`, `same_title`, `tenant`, `challenge`... */
  code: string;
  level: WarningLevel;
  text: string;
  /** What a person can do about it, when there is something. */
  fix?: string;
}

export interface PreviewItem {
  key: string;
  name: string;
  format: SourceFormat;
  size: number;
  /** What the head of the file (YAML) said; empty fields when it has none. */
  meta: PreviewMeta;
  outline: OutlineNode[];
  chunk_count: number;
  avg_chars: number;
  tables_split: number;
  warnings: PreviewWarning[];
  /** A source with the same `doc_code` already in the store. */
  same_code_as: { id: string; title: string; version: string | null } | null;
  /** A source with exactly the same content. */
  same_content_as: { id: string; title: string } | null;
  /** The file could not be read at all: the sentence to show; the other items go on. */
  error: string | null;
}

export interface PreviewResult {
  preview_id: string;
  items: PreviewItem[];
  /** The benchmark mode of the plugin is on (files with `ingest_role: challenge` are accepted). */
  benchmark: boolean;
}

export interface ConfirmItem {
  key: string;
  title: string;
  doc_code: string | null;
  audience: Audience;
  approved: boolean;
  /** Service codes; empty means "recognise them". */
  services: string[];
  lifecycle: Lifecycle;
  version: string | null;
  effective_from: string | null;
  effective_to: string | null;
  /** Id of a source in use that this one replaces. */
  supersedes: string | null;
  note: string;
  /** What to do when the same `doc_code` exists: add as a new version, or leave this file out. */
  on_same_code: "version" | "skip";
}

export interface ConfirmResult {
  batch_id: string;
  created: Source[];
  skipped: { key: string; reason: string }[];
}

// -- one source: structure, chunks, history -----------------------------------------------------------------

export interface SourceStructure {
  /** The Markdown the reader built (headings, tables, lists). */
  markdown: string;
  outline: OutlineNode[];
}

export interface Chunk {
  id: string;
  ordinal: number;
  /** "Dịch vụ > Nám > Giá": the headings above it. */
  path: string;
  text: string;
  chars: number;
  services: string[];
  /** `price`, `policy`, `procedure`, `faq`, `internal_script`, `info`... */
  kind: string;
  embedded: boolean;
}

export interface ChunkList {
  items: Chunk[];
  total: number;
  page: number;
  page_size: number;
}

export interface SourceEvent {
  id: string;
  at: string;
  /** `uploaded`, `approved`, `unapproved`, `reindexed`, `edited`, `expired`, `error`, `replaced`, `restored`. */
  kind: string;
  by: string;
  note: string;
}

// -- services (the backbone of the labels) ------------------------------------------------------------------

export interface Service {
  id: string;
  code: string;
  name: string;
  aliases: string[];
  description: string;
  branches: string[];
  chunk_count: number;
  enabled: boolean;
}

export type ServiceBody = Omit<Service, "id" | "chunk_count">;

// -- trying a search ----------------------------------------------------------------------------------------

export interface SearchDebugQuery {
  question: string;
  /** Which door the question comes in by: it filters what may be seen. */
  channel: "patient" | "staff";
  /** ISO date the question is "asked on" (prices and rules in force that day). */
  as_of: string;
}

export interface Candidate {
  chunk_id: string;
  doc_code: string | null;
  source_title: string;
  path: string;
  excerpt: string;
  /** A rank-specific number: BM25 score, cosine similarity, the ranking score after both lists are put together, or the reranker's. */
  score: number;
}

export interface SearchStage {
  /** `understand`, `keyword`, `vector`, `fused`, `reranked`, `judge`, `judge_dropped`, `final`. */
  id: string;
  title: string;
  ms: number;
  /** A sentence about what this stage did ("Vector chưa bật: bỏ qua"). */
  note: string;
  skipped: boolean;
  candidates: Candidate[];
}

export interface SearchDebug {
  question: string;
  folded: string;
  services: string[];
  stages: SearchStage[];
  total_ms: number;
}

// -- questions with no document -----------------------------------------------------------------------------

export type GapState = "open" | "ignored" | "answered";

export interface Gap {
  id: string;
  question: string;
  count: number;
  channel: string;
  last_asked_at: string;
  state: GapState;
}

// -- settings -----------------------------------------------------------------------------------------------

/** Where a value comes from, as the model page says it. */
export type SettingOrigin = "saved" | "profile";

export interface EmbeddingSettings {
  base_url: string;
  model: string;
  dimensions: number;
  query_prefix: string;
  document_prefix: string;
  /** Whether a key is stored (never the key itself). */
  has_key: boolean;
  origin: SettingOrigin;
  /** Chunks with no vector under the current model. */
  chunks_without_vector: number;
}

/** How likely the best chunk must be to state the fact asked, for the Jev judge to hand anything over. */
export type JudgeLevel = "strict" | "medium" | "loose";

/** Whether plugin jev is on and has a key: what the judging section needs to say. */
export interface JevState {
  on: boolean;
  hasKey: boolean;
}

export interface KnowledgeSettings {
  embedding: EmbeddingSettings;
  parser: { kind: "simple" | "docling"; docling_url: string; origin: SettingOrigin };
  labelling: { enabled: boolean; model_entry: string | null };
  judging: { enabled: boolean; level: JudgeLevel };
  search: {
    results: number;
    min_score: number;
    char_budget: number;
    patient_channel_prefix: string;
    patient_only_approved: boolean;
  };
  benchmark_mode: boolean;
}

export type SettingsPatch = {
  embedding?: Partial<Omit<EmbeddingSettings, "has_key" | "origin" | "chunks_without_vector">> & {
    /** Replaces the stored key; an empty string removes it. */
    api_key?: string;
  };
  parser?: Partial<KnowledgeSettings["parser"]>;
  labelling?: Partial<KnowledgeSettings["labelling"]>;
  judging?: Partial<KnowledgeSettings["judging"]>;
  search?: Partial<KnowledgeSettings["search"]>;
  benchmark_mode?: boolean;
  /** Groups to put back to the profile's values ("Về mặc định"); the server clears their `origin`. */
  reset?: ("embedding" | "parser")[];
};

export interface EmbeddingTest {
  ok: boolean;
  dimensions: number | null;
  normalised: boolean | null;
  ms: number | null;
  /** A sentence a person can read when `ok` is false. */
  message: string;
}

export interface KnowledgeStatus {
  embedding_connected: boolean;
  embedding_model: string | null;
  queue: number;
  warnings: string[];
}

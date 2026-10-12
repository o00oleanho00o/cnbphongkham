/** Browser side of the preview: reads the picked files and sends them in groups. No screen code. */
import { knowledge } from "../client";
import type { PreviewInput, PreviewItem, PreviewMeta, PreviewResult } from "../types";
import { base64FromDataUrl, batchBySize, extensionOf, fileKey, readingText } from "./add-logic";
import { readFrontmatter } from "./frontmatter";

export interface Picked {
  key: string;
  file: File;
  /** Where the file sat inside a picked folder; empty for single files. */
  path: string;
}

/** What one input needs to go out: its weight (bytes) and a reader that fills `input` when it is its turn. */
export interface Reader {
  key: string;
  weight: number;
  read: () => Promise<{ input: PreviewInput; meta: PreviewMeta | null }>;
}

const TEXT_EXTENSIONS = [".md", ".txt"];

export function pickedFrom(file: File): Picked {
  const path = file.webkitRelativePath;
  return { key: fileKey(file.name, file.size, file.lastModified, path), file, path };
}

function dataUrlOf(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(typeof reader.result === "string" ? reader.result : "");
    reader.onerror = () => reject(reader.error ?? new Error("Không đọc được tệp."));
    reader.readAsDataURL(file);
  });
}

export function readerOfFile({ key, file }: Picked): Reader {
  const isText = TEXT_EXTENSIONS.includes(extensionOf(file.name));
  const base = { key, name: file.name, kind: "file" as const, size: file.size };
  return {
    key,
    weight: file.size,
    read: async () => {
      if (isText) {
        const text = await file.text();
        return { input: { ...base, text }, meta: readFrontmatter(text).meta };
      }
      return { input: { ...base, base64: base64FromDataUrl(await dataUrlOf(file)) }, meta: null };
    },
  };
}

export function readerOfText(title: string, text: string): Reader {
  const size = new TextEncoder().encode(text).length;
  return {
    key: "text",
    weight: size,
    read: async () => ({
      input: { key: "text", name: title.trim(), kind: "text", size, text },
      meta: readFrontmatter(text).meta,
    }),
  };
}

export interface PreviewRun {
  items: PreviewItem[];
  /** Item key -> the id of the call that read it (the one `confirm` needs). */
  previewIds: Record<string, string>;
  /** What this browser read from each YAML head, as a fallback for what the server says. */
  metas: Map<string, PreviewMeta>;
  benchmark: boolean;
}

/** Reads and sends the files group by group (one call each), telling `onProgress` how many files are done. */
export async function previewAll(readers: readonly Reader[], onProgress: (text: string) => void): Promise<PreviewRun> {
  const batches = batchBySize(readers, (reader) => reader.weight);
  const empty: PreviewRun = { items: [], previewIds: {}, metas: new Map(), benchmark: false };
  return batches.reduce<Promise<PreviewRun>>(async (previous, batch) => {
    const run = await previous;
    onProgress(readingText(run.items.length, readers.length));
    const loaded = await Promise.all(batch.map((reader) => reader.read()));
    const result: PreviewResult = await knowledge.preview(loaded.map(({ input }) => input));
    const metas = new Map([
      ...run.metas,
      ...loaded.flatMap(({ input, meta }) => (meta ? [[input.key, meta] as const] : [])),
    ]);
    return {
      items: [...run.items, ...result.items],
      previewIds: {
        ...run.previewIds,
        ...Object.fromEntries(result.items.map((item) => [item.key, result.preview_id])),
      },
      metas,
      benchmark: run.benchmark || result.benchmark,
    };
  }, Promise.resolve(empty));
}

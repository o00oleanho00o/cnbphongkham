/** Adding skill files straight in: the files a person chose or dropped are read, shown with what would happen to each
 * (new, or a new version of one that exists), and added together. */
import { useEffect, useMemo, useState } from "react";

import { messageOf, skills } from "../client";
import { KIND_LABEL, problems, scopesSummary, validScope } from "../logic";
import { Chip } from "../parts";
import { ui } from "../sdk";
import { ScopePicker } from "../scope/scope-picker";
import { type SkillFile, parseSkillFile } from "../skill-file";
import type { Choices, Item } from "../types";

const MAX_FILES = 20;
const MAX_BYTES = 200_000;
const ACCEPTED = /\.(md|markdown|txt)$/i;

export interface Entry {
  file: SkillFile;
  problems: string[];
}

type Outcome = { ok: true; text: string } | { ok: false; text: string };

/** Reads the files; one that is too big or not text becomes an entry with its problem. */
export async function readFiles(files: readonly File[]): Promise<Entry[]> {
  return Promise.all(
    files.slice(0, MAX_FILES).map(async (file) => {
      const empty = parseSkillFile(file.name, "");
      if (!ACCEPTED.test(file.name)) return { file: empty, problems: ["Chỉ nhận file .md, .markdown hoặc .txt."] };
      if (file.size > MAX_BYTES) return { file: empty, problems: ["File lớn quá (tối đa 200 KB)."] };
      const parsed = parseSkillFile(file.name, await file.text());
      const badScopes = parsed.scopes.filter((scope) => !validScope(scope));
      const scopeProblems = badScopes.map((scope) => `Nơi áp dụng "${scope}" không đúng. Dùng agent, plugin:<tên> hoặc channel:<tên>.`);
      return { file: parsed, problems: [...problems(parsed), ...scopeProblems] };
    }),
  );
}

function existing(items: readonly Item[], file: SkillFile): Item | undefined {
  return items.find((item) => item.kind === file.kind && item.name === file.name);
}

/** A file that names its places keeps them; the others go where the person chose above the list. */
function scopesOf(file: SkillFile, chosen: readonly string[]): string[] {
  return file.scopes.length > 0 ? file.scopes : [...chosen];
}

async function addOne(file: SkillFile, found: Item | undefined, chosen: readonly string[]): Promise<Outcome> {
  const { kind, name, description, body, status } = file;
  const scopes = scopesOf(file, chosen);
  try {
    if (found) {
      await skills.update(found.id, { description, body, scopes, status, reason: `thêm từ file ${file.fileName}` });
      return { ok: true, text: "Đã ghi bản mới" };
    }
    await skills.create({ kind, name, description, body, scopes, status });
    return { ok: true, text: "Đã thêm" };
  } catch (err) {
    return { ok: false, text: messageOf(err) };
  }
}

export function AddFiles({
  entries,
  choices,
  onClose,
  onAdded,
}: {
  entries: readonly Entry[];
  choices: Choices;
  onClose: () => void;
  onAdded: () => void;
}) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState<Map<string, Outcome>>(new Map());
  const [error, setError] = useState("");
  const [chosen, setChosen] = useState<string[]>([]);

  useEffect(() => {
    skills
      .items()
      .then((listing) => setItems(listing.items))
      .catch((err: unknown) => setError(messageOf(err)));
  }, []);

  const addable = useMemo(() => entries.filter((entry) => entry.problems.length === 0), [entries]);
  const done = results.size > 0;

  async function addAll() {
    if (items === null) return;
    setBusy(true);
    const outcomes = await addable.reduce<Promise<[string, Outcome][]>>(async (previous, entry) => {
      const before = await previous;
      return [...before, [entry.file.fileName, await addOne(entry.file, existing(items, entry.file), chosen)]];
    }, Promise.resolve([]));
    setResults(new Map(outcomes));
    setBusy(false);
    onAdded();
  }

  return (
    <ui.Card
      title="Thêm file vào kỹ năng"
      aside={
        <ui.Button variant="ghost" onClick={onClose}>
          {done ? "Xong" : "Hủy"}
        </ui.Button>
      }
    >
      <div className="space-y-3">
        {error && <ui.Notice tone="danger">{error}</ui.Notice>}
        {!done && (
          <div className="space-y-1">
            <p className="text-small font-bold text-heading">Áp dụng cho (các file không ghi sẵn nơi áp dụng)</p>
            <ScopePicker scopes={chosen} choices={choices} onChange={setChosen} />
          </div>
        )}
        <ul className="space-y-2">
          {entries.map((entry) => {
            const { file } = entry;
            const found = items ? existing(items, file) : undefined;
            const outcome = results.get(file.fileName);
            return (
              <li key={file.fileName} className="space-y-1 rounded-tile border border-line p-3">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="text-body font-bold break-all text-heading">{file.name || file.fileName}</span>
                  <ui.Badge>{KIND_LABEL[file.kind]}</ui.Badge>
                  <ui.Badge tone={found ? "warning" : "info"}>{found ? "Ghi bản mới" : "Mới"}</ui.Badge>
                  <span className="text-label text-ink-soft">{file.fileName}</span>
                </p>
                <p className="text-small text-ink">{file.description}</p>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="text-label text-ink-soft">Áp dụng:</span>
                  {(scopesOf(file, chosen).length === 0 ? ["agent"] : scopesOf(file, chosen)).map((scope) => (
                    <Chip key={scope}>{scopesSummary([scope])}</Chip>
                  ))}
                </div>
                {entry.problems.map((problem) => (
                  <p key={problem} className="text-small text-danger">
                    {problem}
                  </p>
                ))}
                {outcome && (
                  <p className={`text-small ${outcome.ok ? "text-success" : "text-danger"}`}>{outcome.text}</p>
                )}
              </li>
            );
          })}
        </ul>
        <p className="text-label text-ink-soft">
          Đầu file có thể có khối <code>---</code> với <code>name</code>, <code>description</code>, và nếu cần{" "}
          <code>kind</code> (skill, rules, persona), <code>scopes</code>, <code>status</code>. Không có thì lấy tên
          file làm tên.
        </p>
        {!done && (
          <div className="flex flex-wrap justify-end gap-2">
            <ui.Button variant="secondary" onClick={onClose}>
              Hủy
            </ui.Button>
            <ui.Button busy={busy} disabled={addable.length === 0 || items === null} onClick={() => void addAll()}>
              {`Thêm ${addable.length} file`}
            </ui.Button>
          </div>
        )}
      </div>
    </ui.Card>
  );
}

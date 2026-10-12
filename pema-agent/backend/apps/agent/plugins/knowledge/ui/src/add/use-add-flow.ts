/** The state and actions of the add-a-source flow (the three steps share it, so going back keeps what was typed). */
import { useEffect, useState } from "react";

import { knowledge, messageOf } from "../client";
import type { Audience, ConfirmResult, Service, Source } from "../types";
import {
  type Draft,
  type Entry,
  type Rejection,
  type Way,
  defaultDraft,
  draftProblems,
  hasProblems,
  ignoredText,
  mergeMeta,
  patientRisks,
  planFolder,
  refusalOf,
  splitByPreview,
  summarise,
  toConfirmItems,
  validateFile,
  validateText,
} from "./add-logic";
import { type Picked, type Reader, pickedFrom, previewAll, readerOfFile, readerOfText } from "./read-files";

export type Step = 1 | 2 | 3;
export type FileWay = Exclude<Way, "text">;

export interface Notes {
  rejected: Rejection[];
  ignored: string;
}

const NO_NOTES: Notes = { rejected: [], ignored: "" };

interface Lookups {
  services: Service[];
  active: Source[];
  failed: boolean;
}

/** The service catalogue and the sources in use (for "Thay thế nguồn cũ"), read once when the sheet opens. */
function useLookups(): Lookups {
  const [lookups, setLookups] = useState<Lookups>({ services: [], active: [], failed: false });
  useEffect(() => {
    const live = { on: true };
    const apply = (change: (now: Lookups) => Lookups) => {
      if (live.on) setLookups(change);
    };
    Promise.all([knowledge.services(), knowledge.sources({ lifecycle: "active" })])
      .then(([services, list]) => apply(() => ({ services, active: list.items, failed: false })))
      .catch(() => apply((now) => ({ ...now, failed: true })));
    return () => {
      live.on = false;
    };
  }, []);
  return lookups;
}

function appendPicked(now: readonly Picked[], more: readonly Picked[]): Picked[] {
  const known = new Set(now.map((item) => item.key));
  return [...now, ...more.filter((item) => !known.has(item.key))];
}

function notesOf(way: FileWay, files: readonly File[]): { accepted: File[]; notes: Notes } {
  if (way === "folder") {
    const plan = planFolder(files);
    return { accepted: plan.accepted, notes: { rejected: plan.rejected, ignored: ignoredText(plan) } };
  }
  const checked = files.map((file) => ({ file, reason: validateFile(file) }));
  return {
    accepted: checked.filter((item) => item.reason === null).map((item) => item.file),
    notes: {
      rejected: checked.flatMap((item) => (item.reason ? [{ name: item.file.name, reason: item.reason }] : [])),
      ignored: "",
    },
  };
}

export function useAddFlow(initial?: { title: string; text: string }) {
  const lookups = useLookups();
  const [step, setStep] = useState<Step>(1);
  const [way, setWay] = useState<Way>(initial ? "text" : "files");
  const [picked, setPicked] = useState<Record<FileWay, Picked[]>>({ files: [], folder: [] });
  const [notes, setNotes] = useState<Record<FileWay, Notes>>({ files: NO_NOTES, folder: NO_NOTES });
  const [title, setTitle] = useState(initial?.title ?? "");
  const [text, setText] = useState(initial?.text ?? "");
  const [entries, setEntries] = useState<Entry[]>([]);
  const [previewIds, setPreviewIds] = useState<Record<string, string>>({});
  const [benchmark, setBenchmark] = useState(false);
  const [readFor, setReadFor] = useState("");
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [showProblems, setShowProblems] = useState(false);
  const [result, setResult] = useState<ConfirmResult | null>(null);
  const [patientAsk, setPatientAsk] = useState<{ keys: string[]; risky: Entry[] } | null>(null);

  const signature = way === "text" ? `text\n${title}\n${text}` : [way, ...picked[way].map((item) => item.key)].join("|");
  const textProblem = validateText(title, text);
  const addable = entries.filter((entry) => refusalOf(entry.item, benchmark) === null);
  const summary = summarise(addable);
  const dirty = picked.files.length > 0 || picked.folder.length > 0 || entries.length > 0 || title !== (initial?.title ?? "") || text !== (initial?.text ?? "");

  const canLeaveChoose = way === "text" ? textProblem === null : picked[way].length > 0;
  const canLeaveInfo = addable.some((entry) => entry.draft.action === "add");

  function addFiles(target: FileWay, files: readonly File[]) {
    const { accepted, notes: next } = notesOf(target, files);
    setPicked((now) => ({ ...now, [target]: appendPicked(now[target], accepted.map(pickedFrom)) }));
    setNotes((now) => ({ ...now, [target]: next }));
  }

  function removePicked(target: FileWay, key: string) {
    setPicked((now) => ({ ...now, [target]: now[target].filter((item) => item.key !== key) }));
  }

  async function readAndPreview() {
    const readers: Reader[] = way === "text" ? [readerOfText(title, text)] : picked[way].map(readerOfFile);
    const run = await previewAll(readers, setProgress);
    const kept = new Map(entries.map((entry) => [entry.item.key, entry.draft]));
    const keepDrafts = way !== "text";
    const next = run.items.map((raw): Entry => {
      const item = { ...raw, meta: mergeMeta(raw.meta, run.metas.get(raw.key)) };
      return { item, draft: (keepDrafts ? kept.get(item.key) : undefined) ?? defaultDraft(item) };
    });
    setEntries(next);
    setPreviewIds(run.previewIds);
    setBenchmark(run.benchmark);
    setReadFor(signature);
  }

  /** Leaving step 1: the files are read once per change, so going back and forth does not read them again. */
  async function toInfo() {
    setError("");
    if (readFor === signature && entries.length > 0) {
      setStep(2);
      return;
    }
    try {
      await readAndPreview();
      setStep(2);
    } catch (err) {
      setError(messageOf(err));
    } finally {
      setProgress("");
    }
  }

  function toPreview() {
    setShowProblems(true);
    if (addable.some((entry) => entry.draft.action === "add" && hasProblems(entry.draft))) return;
    setStep(3);
  }

  function changeDraft(keys: readonly string[], patch: Partial<Draft>) {
    setEntries((now) =>
      now.map((entry) => (keys.includes(entry.item.key) ? { ...entry, draft: { ...entry.draft, ...patch } } : entry)),
    );
  }

  /** Sets the audience; "Bệnh nhân" for entries with internal sections or personal data waits for a yes. */
  function setAudience(keys: string[], audience: Audience) {
    const risky = audience === "patient" ? entries.filter((entry) => keys.includes(entry.item.key) && patientRisks(entry.item).length > 0) : [];
    if (risky.length === 0) {
      changeDraft(keys, { audience });
      return;
    }
    setPatientAsk({ keys, risky });
  }

  function answerPatient(yes: boolean) {
    if (yes && patientAsk) changeDraft(patientAsk.keys, { audience: "patient" });
    setPatientAsk(null);
  }

  async function confirm(): Promise<ConfirmResult> {
    setError("");
    setProgress("Đang nạp…");
    const groups = splitByPreview(toConfirmItems(addable), previewIds);
    const merged = await groups.reduce<Promise<ConfirmResult>>(
      async (previous, group) => {
        const soFar = await previous;
        try {
          const done = await knowledge.confirm(group.previewId, group.items);
          return { ...soFar, batch_id: done.batch_id, created: [...soFar.created, ...done.created], skipped: [...soFar.skipped, ...done.skipped] };
        } catch (err) {
          const failed = group.items.map((item) => ({ key: item.key, reason: messageOf(err) }));
          return { ...soFar, skipped: [...soFar.skipped, ...failed] };
        }
      },
      Promise.resolve({ batch_id: "", created: [], skipped: [] }),
    );
    setProgress("");
    setResult(merged);
    return merged;
  }

  return {
    lookups,
    step,
    setStep,
    way,
    setWay,
    picked,
    notes,
    title,
    setTitle,
    text,
    setText,
    entries,
    benchmark,
    progress,
    error,
    showProblems,
    result,
    textProblem,
    summary,
    dirty,
    canLeaveChoose,
    canLeaveInfo,
    addFiles,
    removePicked,
    toInfo,
    toPreview,
    changeDraft,
    patientAsk,
    setAudience,
    answerPatient,
    confirm,
    problemsOf: (draft: Draft) => (showProblems ? draftProblems(draft) : {}),
  };
}

export type AddFlow = ReturnType<typeof useAddFlow>;

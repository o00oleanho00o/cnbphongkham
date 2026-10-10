"use client";

// Model của agent: the list of models the agent keeps ready (several keys of the same provider side by side, grouped
// by provider), the one in use, and the form to add or change one. Using a model applies from the next reply; a key is
// stored encrypted and never shown back. The agent's own profile still answers when nothing was chosen.
import { useCallback, useEffect, useState } from "react";

import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { ModelEntryForm } from "@/components/agent/pages/model-entry-form";
import {
  Badge,
  Button,
  Card,
  Empty,
  type KitTone,
  Notice,
  PageHeader,
} from "@/components/agent/plugin-kit";
import { ApiError, agentApi as api } from "@/lib/agent/api";
import {
  brandCounts,
  ENTRIES_PATH,
  entryPath,
  groupByBrand,
  type ModelEntry,
} from "@/lib/agent/model-entries";

interface ModelShown {
  provider: string;
  model: string;
  base_url: string | null;
  api_key: string;
  api_key_broken: boolean;
  sources: Record<string, "db" | "profile" | "unset">;
  stored: boolean;
  entry_id: string | null;
}

interface TestOutcome {
  ok: boolean;
  model: string;
  latency_ms?: number;
  error_kind?: string;
}

type Message = { tone: KitTone; text: string };
/** `"new"` while adding, the model while changing it, null when no form is open. */
type Editing = "new" | ModelEntry | null;

const TEST_ERRORS: Record<string, string> = {
  auth: "Khóa API sai hoặc hết hạn",
  rate_limit: "Nhà cung cấp đang giới hạn số lần gọi",
  transient: "Nhà cung cấp tạm lỗi, thử lại sau",
  config: "Thiếu model hoặc khóa API",
  timeout: "Quá thời gian chờ",
};

function isOutcome(value: unknown): value is TestOutcome {
  return typeof value === "object" && value !== null && "ok" in value && "model" in value;
}

function inUseSource(shown: ModelShown, entries: readonly ModelEntry[]): string {
  const entry = entries.find((item) => item.id === shown.entry_id);
  if (entry) return `từ danh sách: ${entry.label}`;
  return shown.stored ? "chỉnh tay, không thuộc danh sách" : "theo cấu hình của profile";
}

function outcomeMessage(outcome: TestOutcome): Message {
  if (outcome.ok) {
    return {
      tone: "success",
      text: `${outcome.model} trả lời sau ${outcome.latency_ms ?? "?"} ms.`,
    };
  }
  return {
    tone: "danger",
    text: TEST_ERRORS[outcome.error_kind ?? ""] ?? `Lỗi: ${outcome.error_kind}`,
  };
}

/** A failed test call answers 502 with the outcome in the body. */
function outcomeOf(err: unknown): TestOutcome {
  if (err instanceof ApiError && isOutcome(err.payload)) return err.payload;
  throw err;
}

export function ModelPage() {
  const [shown, setShown] = useState<ModelShown | null>(null);
  const [entries, setEntries] = useState<ModelEntry[] | null>(null);
  const [editing, setEditing] = useState<Editing>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [busy, setBusy] = useState("");
  const { confirm, confirmDialog } = useConfirmDialog();

  const load = useCallback(async () => {
    const [current, listing] = await Promise.all([
      api.get<ModelShown>("/v1/admin/model"),
      api.get<{ entries: ModelEntry[] }>(ENTRIES_PATH),
    ]);
    setShown(current);
    setEntries(listing.entries);
  }, []);

  useEffect(() => {
    load().catch((err: unknown) =>
      setMessage({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" }),
    );
  }, [load]);

  async function run(label: string, work: () => Promise<Message | null>) {
    setBusy(label);
    setMessage(null);
    try {
      setMessage(await work());
    } catch (err) {
      setMessage({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" });
    } finally {
      setBusy("");
    }
  }

  const use = (entry: ModelEntry) =>
    run(`use-${entry.id}`, async () => {
      await api.post(entryPath(entry.id, "use"));
      await load();
      return {
        tone: "success",
        text: `Đang dùng ${entry.label} - áp dụng từ lượt trả lời tiếp theo.`,
      };
    });

  const testEntry = (entry: ModelEntry) =>
    run(`test-${entry.id}`, async () =>
      outcomeMessage(await api.post<TestOutcome>(entryPath(entry.id, "test")).catch(outcomeOf)),
    );

  const testInUse = () =>
    run("test", async () =>
      outcomeMessage(await api.post<TestOutcome>("/v1/admin/model/test").catch(outcomeOf)),
    );

  const backToProfile = () =>
    run("reset", async () => {
      await api.del("/v1/admin/model");
      await load();
      return { tone: "info", text: "Đã bỏ model đang dùng: agent dùng lại cấu hình của profile." };
    });

  async function remove(entry: ModelEntry) {
    const ok = await confirm({
      title: `Xóa ${entry.label}?`,
      message: entry.active
        ? "Model này đang được dùng: agent vẫn trả lời bằng nó cho tới khi bạn chọn model khác, nhưng nó không còn trong danh sách. Khóa API đã lưu cũng mất."
        : "Khóa API đã lưu của model này cũng mất. Không hoàn tác được.",
      confirmLabel: "Xóa model",
    });
    if (!ok) return;
    await run(`remove-${entry.id}`, async () => {
      await api.del(entryPath(entry.id));
      await load();
      return { tone: "info", text: `Đã xóa ${entry.label}.` };
    });
  }

  function saved(text: string) {
    setEditing(null);
    setMessage({ tone: "success", text });
    load().catch((err: unknown) =>
      setMessage({ tone: "danger", text: err instanceof Error ? err.message : "Lỗi" }),
    );
  }

  if (!shown || !entries) {
    return (
      <div>
        <PageHeader title="Model" />
        {message && <Notice tone={message.tone}>{message.text}</Notice>}
      </div>
    );
  }

  const groups = groupByBrand(entries);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Model"
        subtitle="Các model và khóa API agent có thể dùng để trả lời; chọn một cái để dùng"
        aside={editing ? null : <Button onClick={() => setEditing("new")}>+ Thêm model</Button>}
      />
      <Card title="Đang dùng" aside={inUseKey(shown)}>
        <p className="text-body text-ink">
          <b>{shown.model || "Chưa chọn model"}</b>{" "}
          <span className="text-ink-soft">({inUseSource(shown, entries)})</span>
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button variant="secondary" busy={busy === "test"} onClick={testInUse}>
            Gọi thử
          </Button>
          {shown.stored && (
            <Button variant="ghost" busy={busy === "reset"} onClick={backToProfile}>
              Về cấu hình profile
            </Button>
          )}
        </div>
      </Card>
      {message && <Notice tone={message.tone}>{message.text}</Notice>}
      {editing ? (
        <ModelEntryForm
          key={editing === "new" ? "new" : editing.id}
          editing={editing === "new" ? null : editing}
          entries={entries}
          onSaved={saved}
          onCancel={() => setEditing(null)}
        />
      ) : (
        <Card
          title="Danh sách model"
          aside={
            entries.length > 0 && (
              <span className="text-small text-ink-soft">{brandCounts(entries)}</span>
            )
          }
        >
          {entries.length === 0 ? (
            <Empty>Chưa có model nào trong danh sách. Bấm "+ Thêm model" để thêm.</Empty>
          ) : (
            <div className="space-y-5">
              {groups.map((group) => (
                <section key={group.brand} aria-label={`Model ${group.brand}`}>
                  <h3 className="mb-1 text-label font-semibold text-ink-soft">
                    {group.brand} ({group.entries.length})
                  </h3>
                  <ul className="divide-y divide-line">
                    {group.entries.map((entry) => (
                      <li key={entry.id}>
                        <EntryRow
                          entry={entry}
                          busy={busy}
                          onUse={() => use(entry)}
                          onTest={() => testEntry(entry)}
                          onEdit={() => setEditing(entry)}
                          onRemove={() => remove(entry)}
                        />
                      </li>
                    ))}
                  </ul>
                </section>
              ))}
            </div>
          )}
        </Card>
      )}
      {confirmDialog}
    </div>
  );
}

function inUseKey(shown: ModelShown) {
  if (shown.api_key_broken) return <Badge tone="danger">Khóa đã lưu không đọc được</Badge>;
  if (!shown.api_key) return <Badge tone="warning">Chưa có khóa</Badge>;
  return <Badge tone="success">Có khóa: {shown.api_key}</Badge>;
}

function keyBadge(entry: ModelEntry) {
  if (entry.api_key_broken) return <Badge tone="danger">Khóa không đọc được</Badge>;
  if (!entry.has_key) return <Badge tone="warning">Chưa có khóa</Badge>;
  return <Badge>{entry.api_key}</Badge>;
}

function EntryRow({
  entry,
  busy,
  onUse,
  onTest,
  onEdit,
  onRemove,
}: {
  entry: ModelEntry;
  busy: string;
  onUse: () => void;
  onTest: () => void;
  onEdit: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3 px-1 py-3">
      <div className="min-w-0 flex-1 basis-56">
        <p className="truncate font-semibold text-ink">{entry.label}</p>
        <p className="truncate text-small text-ink-soft">{entry.model}</p>
      </div>
      <div className="flex items-center gap-2">
        {keyBadge(entry)}
        {entry.active && <Badge tone="success">Đang dùng</Badge>}
      </div>
      <div className="flex flex-wrap gap-2">
        {!entry.active && (
          <Button
            variant="secondary"
            aria-label={`Dùng ${entry.label}`}
            busy={busy === `use-${entry.id}`}
            onClick={onUse}
          >
            Dùng
          </Button>
        )}
        <Button
          variant="ghost"
          aria-label={`Gọi thử ${entry.label}`}
          busy={busy === `test-${entry.id}`}
          onClick={onTest}
        >
          Gọi thử
        </Button>
        <Button variant="ghost" aria-label={`Sửa ${entry.label}`} onClick={onEdit}>
          Sửa
        </Button>
        <Button
          variant="ghost"
          aria-label={`Xóa ${entry.label}`}
          busy={busy === `remove-${entry.id}`}
          onClick={onRemove}
        >
          Xóa
        </Button>
      </div>
    </div>
  );
}

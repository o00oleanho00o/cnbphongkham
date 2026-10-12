/** The top of the source detail: name, states, facts and the actions. */
import { useState } from "react";

import { knowledge } from "../client";
import {
  AUDIENCE_HINT,
  AUDIENCE_LABEL,
  LIFECYCLE_LABEL,
  LIFECYCLE_TONE,
  PROCESSING_LABEL,
  PROCESSING_TONE,
  formatDate,
  periodText,
  progressPercent,
  progressText,
} from "../logic";
import { ProgressBar } from "../parts";
import { ui } from "../sdk";
import type { Audience, Source, SourcePatch } from "../types";
import { audienceChangeNeedsAsk, canExpire, internalSections } from "./detail-logic";
import { ExpireDialog, AudienceDialog, DeleteDialog } from "./header-dialogs";
import { MetaForm, ServiceChips } from "./meta-form";
import { useAction } from "./use-action";
import { isWorking } from "./use-source";

type Asking = null | "expire" | "delete" | { audience: Audience; sections: string[] };

const AUDIENCE_OPTIONS = (Object.keys(AUDIENCE_LABEL) as Audience[]).map((value) => ({
  value,
  label: AUDIENCE_LABEL[value],
}));

export function SourceHeader({
  source,
  onChanged,
  onBack,
  onDeleted,
}: {
  source: Source;
  onChanged: (source: Source) => void;
  onBack: () => void;
  onDeleted: () => void;
}) {
  const { busy, error, run } = useAction();
  const [renaming, setRenaming] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [asking, setAsking] = useState<Asking>(null);

  const change = (name: string, work: () => Promise<Source>) =>
    run(name, async () => onChanged(await work()));

  async function save(patch: SourcePatch, name: string): Promise<boolean> {
    const saved = await change(name, () => knowledge.updateSource(source.id, patch));
    return saved;
  }

  async function pickAudience(audience: Audience) {
    if (audience === source.audience) return;
    if (!audienceChangeNeedsAsk(source.audience, audience)) {
      await save({ audience }, "audience");
      return;
    }
    // The outline is only for the warning: when it cannot be read the question is still asked.
    const outline = await knowledge.structure(source.id).then(
      (found) => found.outline,
      () => [],
    );
    setAsking({ audience, sections: internalSections(outline) });
  }

  async function rename() {
    const title = (renaming ?? "").trim();
    if (title === "" || title === source.title) return setRenaming(null);
    if (await save({ title }, "rename")) setRenaming(null);
  }

  async function confirmAsking(done: () => Promise<boolean>) {
    if (await done()) setAsking(null);
  }

  return (
    <div className="mb-4 space-y-4">
      <ui.Button variant="secondary" onClick={onBack}>
        Về danh sách
      </ui.Button>
      <TitleRow
        title={source.title}
        renaming={renaming}
        busy={busy === "rename"}
        onStart={() => setRenaming(source.title)}
        onType={setRenaming}
        onSave={rename}
        onCancel={() => setRenaming(null)}
      />
      <div className="flex flex-wrap items-center gap-2">
        <ui.Badge tone={PROCESSING_TONE[source.processing]}>{PROCESSING_LABEL[source.processing]}</ui.Badge>
        <ui.Badge tone={LIFECYCLE_TONE[source.lifecycle]}>{LIFECYCLE_LABEL[source.lifecycle]}</ui.Badge>
        <ui.Badge tone={source.audience === "patient" ? "info" : "neutral"}>{AUDIENCE_LABEL[source.audience]}</ui.Badge>
        <ui.Badge tone={source.approved ? "success" : "warning"}>{source.approved ? "Đã duyệt" : "Chưa duyệt"}</ui.Badge>
      </div>
      {isWorking(source) && (
        <div className="max-w-md space-y-1">
          <ProgressBar percent={progressPercent(source.progress)} label="Tiến độ nạp" />
          <p className="text-label text-ink-soft">{progressText(source.progress)}</p>
        </div>
      )}
      {source.error && <ui.Notice tone="danger">{source.error}</ui.Notice>}
      {error && <ui.Notice tone="danger">{error}</ui.Notice>}
      <Facts source={source} />
      <div className="flex flex-wrap items-end gap-2">
        <ui.Button variant="secondary" busy={busy === "reindex"} onClick={() => change("reindex", () => knowledge.reindex(source.id))}>
          Nạp lại
        </ui.Button>
        {source.approved ? (
          <ui.Button variant="secondary" busy={busy === "approve"} onClick={() => change("approve", () => knowledge.unapprove(source.id))}>
            Bỏ duyệt
          </ui.Button>
        ) : (
          <ui.Button busy={busy === "approve"} onClick={() => change("approve", () => knowledge.approve(source.id))}>
            Duyệt
          </ui.Button>
        )}
        {canExpire(source) && (
          <ui.Button variant="secondary" onClick={() => setAsking("expire")}>
            Hết hiệu lực
          </ui.Button>
        )}
        <ui.Button variant="secondary" onClick={() => setEditing(!editing)}>
          Sửa dịch vụ và hiệu lực
        </ui.Button>
        <ui.Button variant="danger" onClick={() => setAsking("delete")}>
          Xóa
        </ui.Button>
        <div className="w-full sm:ml-auto sm:w-56">
          <ui.Field label="Đối tượng" hint={AUDIENCE_HINT[source.audience]}>
            <ui.Select
              value={source.audience}
              disabled={busy === "audience"}
              options={AUDIENCE_OPTIONS}
              onChange={(event) => pickAudience(event.target.value === "patient" ? "patient" : "staff")}
            />
          </ui.Field>
        </div>
      </div>
      {editing && (
        <MetaForm
          source={source}
          busy={busy === "meta"}
          onCancel={() => setEditing(false)}
          onSave={async (patch) => {
            if (await save(patch, "meta")) setEditing(false);
          }}
        />
      )}
      {asking === "expire" && (
        <ExpireDialog
          busy={busy === "expire"}
          onClose={() => setAsking(null)}
          onConfirm={() => confirmAsking(() => change("expire", () => knowledge.expire(source.id)))}
        />
      )}
      {asking === "delete" && (
        <DeleteDialog
          source={source}
          busy={busy === "delete"}
          onClose={() => setAsking(null)}
          onConfirm={() => confirmAsking(() => run("delete", () => knowledge.deleteSource(source.id).then(onDeleted)))}
        />
      )}
      {typeof asking === "object" && asking !== null && (
        <AudienceDialog
          sections={asking.sections}
          approved={source.approved}
          busy={busy === "audience"}
          onClose={() => setAsking(null)}
          onConfirm={() => confirmAsking(() => save({ audience: asking.audience }, "audience"))}
        />
      )}
    </div>
  );
}

function TitleRow({
  title,
  renaming,
  busy,
  onStart,
  onType,
  onSave,
  onCancel,
}: {
  title: string;
  renaming: string | null;
  busy: boolean;
  onStart: () => void;
  onType: (value: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  if (renaming === null) {
    return (
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="min-w-0 text-page font-bold break-words text-heading">{title}</h1>
        <ui.Button variant="ghost" onClick={onStart}>
          Đổi tên
        </ui.Button>
      </div>
    );
  }
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <div className="min-w-0 flex-1 basis-64">
        <ui.Field label="Tên nguồn">
          <ui.Input autoFocus value={renaming} onChange={(event) => onType(event.target.value)} />
        </ui.Field>
      </div>
      <ui.Button type="submit" busy={busy}>
        Lưu tên
      </ui.Button>
      <ui.Button variant="secondary" onClick={onCancel}>
        Hủy
      </ui.Button>
    </form>
  );
}

function Facts({ source }: { source: Source }) {
  const approvedBy = source.approved
    ? `${source.approved_by ?? "Quản trị"}${source.approved_at ? `, ${formatDate(source.approved_at)}` : ""}`
    : "Chưa duyệt";
  const rows: [string, string][] = [
    ["Mã tài liệu", source.doc_code ?? "Chưa có"],
    ["Phiên bản", source.version ?? "Chưa đặt"],
    ["Hiệu lực", periodText(source.effective_from, source.effective_to)],
    ["Duyệt", approvedBy],
    ["Số đoạn", String(source.chunk_count)],
  ];
  return (
    <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2 lg:grid-cols-3">
      {rows.map(([label, value]) => (
        <div key={label}>
          <dt className="text-label text-ink-soft">{label}</dt>
          <dd className="text-body break-words text-ink">{value}</dd>
        </div>
      ))}
      <div>
        <dt className="text-label text-ink-soft">Dịch vụ</dt>
        <dd>
          <ServiceChips codes={source.services} />
        </dd>
      </div>
    </dl>
  );
}

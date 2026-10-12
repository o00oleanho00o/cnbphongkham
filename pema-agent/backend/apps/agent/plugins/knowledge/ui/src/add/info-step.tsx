/** Step 2 "Thông tin": one editable block per file, and a bar that sets one thing for all of them. */
import { useState } from "react";

import { APPROVAL_STEP, AUDIENCE_HINT, AUDIENCE_LABEL, AUDIENCE_SPLIT } from "../logic";
import { ConfirmDialog, Section } from "../parts";
import { ui } from "../sdk";
import type { Audience, PreviewItem, Service, Source } from "../types";
import { type Draft, type Entry, approvedFromValue, audienceFromValue, patientRisks, refusalOf, replaceLabel } from "./add-logic";
import type { AddFlow } from "./use-add-flow";

const AUDIENCES: Audience[] = ["staff", "patient"];
const AUDIENCE_OPTIONS = AUDIENCES.map((value) => ({ value, label: AUDIENCE_LABEL[value] }));

function toggled(list: readonly string[], code: string): string[] {
  return list.includes(code) ? list.filter((item) => item !== code) : [...list, code];
}

function ServicePicker({ services, value, onChange }: { services: Service[]; value: string[]; onChange: (next: string[]) => void }) {
  return (
    <div role="group" aria-label="Dịch vụ" className="flex flex-wrap gap-1.5">
      <button
        type="button"
        aria-pressed={value.length === 0}
        onClick={() => onChange([])}
        className={`min-h-9 rounded-full border px-3 text-label ${value.length === 0 ? "border-link bg-surface-soft font-semibold text-link" : "border-line text-ink-soft"}`}
      >
        Tự nhận diện
      </button>
      {services.map((service) => (
        <button
          key={service.code}
          type="button"
          aria-pressed={value.includes(service.code)}
          onClick={() => onChange(toggled(value, service.code))}
          className={`min-h-9 rounded-full border px-3 text-label ${value.includes(service.code) ? "border-link bg-surface-soft font-semibold text-link" : "border-line text-ink-soft"}`}
        >
          {service.name}
        </button>
      ))}
    </div>
  );
}

function ApprovedBox({ checked, onChange }: { checked: boolean; onChange: (next: boolean) => void }) {
  return (
    <label className="flex min-h-11 items-center gap-2 text-small text-ink">
      <input type="checkbox" className="h-5 w-5" checked={checked} onChange={(event) => onChange(event.target.checked)} />
      Đã duyệt (bệnh nhân thấy được khi đối tượng là Bệnh nhân)
    </label>
  );
}

function DraftRow({ entry, flow }: { entry: Entry; flow: AddFlow }) {
  const { item, draft } = entry;
  const problems = flow.problemsOf(draft);
  const set = (patch: Partial<Draft>) => flow.changeDraft([item.key], patch);
  const skipped = draft.action === "skip";
  const replaceOptions = [
    { value: "", label: "Không thay nguồn nào" },
    ...flow.lookups.active.map((source: Source) => ({ value: source.id, label: replaceLabel(source.title, source.version) })),
  ];
  return (
    <div className={`space-y-3 rounded-tile border border-line p-4 ${skipped ? "opacity-70" : ""}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="min-w-0 text-small font-semibold break-words text-heading">{item.name}</p>
        {item.same_content_as && <ui.Badge tone="warning">Trùng hệt "{item.same_content_as.title}"</ui.Badge>}
      </div>
      {item.same_code_as && (
        <div className="space-y-2 rounded-tile bg-surface-soft p-3">
          <p className="text-small text-ink">
            Đã có nguồn cùng mã {draft.docCode}: "{item.same_code_as.title}"
            {item.same_code_as.version ? ` (v${item.same_code_as.version})` : ""}.
          </p>
          <div role="group" aria-label="Khi trùng mã" className="flex flex-wrap gap-2">
            <ui.Button variant={skipped ? "secondary" : "primary"} onClick={() => set({ action: "add" })}>
              Thêm phiên bản mới
            </ui.Button>
            <ui.Button variant={skipped ? "primary" : "secondary"} onClick={() => set({ action: "skip" })}>
              Bỏ qua tệp này
            </ui.Button>
          </div>
        </div>
      )}
      {!item.same_code_as && item.same_content_as && (
        <div role="group" aria-label="Khi trùng nội dung" className="flex flex-wrap gap-2">
          <ui.Button variant={skipped ? "primary" : "secondary"} onClick={() => set({ action: "skip" })}>
            Bỏ qua tệp này
          </ui.Button>
          <ui.Button variant={skipped ? "secondary" : "primary"} onClick={() => set({ action: "add" })}>
            Vẫn thêm
          </ui.Button>
        </div>
      )}
      <fieldset disabled={skipped} className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <ui.Field label="Tên hiển thị" error={problems.title}>
            <ui.Input value={draft.title} onChange={(event) => set({ title: event.target.value })} />
          </ui.Field>
          <ui.Field label="Mã tài liệu" hint="Mã dùng để trích dẫn, ví dụ DEMO-PEMA-D07">
            <ui.Input value={draft.docCode} onChange={(event) => set({ docCode: event.target.value })} />
          </ui.Field>
          {AUDIENCE_SPLIT && (
            <ui.Field label="Đối tượng" hint={AUDIENCE_HINT[draft.audience]}>
              <ui.Select
                value={draft.audience}
                options={AUDIENCE_OPTIONS}
                onChange={(event) => {
                  flow.setAudience([item.key], event.target.value === "patient" ? "patient" : "staff");
                }}
              />
            </ui.Field>
          )}
          <ui.Field label="Thay thế nguồn cũ" hint="Nguồn cũ chuyển sang Đã thay thế khi nguồn mới nạp xong">
            <ui.Select value={draft.supersedes} options={replaceOptions} onChange={(event) => set({ supersedes: event.target.value })} />
          </ui.Field>
          <ui.Field label="Hiệu lực từ">
            <ui.Input type="date" value={draft.from} onChange={(event) => set({ from: event.target.value })} />
          </ui.Field>
          <ui.Field label="Hiệu lực đến" hint="Để trống nếu không hạn" error={problems.to}>
            <ui.Input type="date" value={draft.to} onChange={(event) => set({ to: event.target.value })} />
          </ui.Field>
        </div>
        {APPROVAL_STEP && <ApprovedBox checked={draft.approved} onChange={(approved) => set({ approved })} />}
        <div className="space-y-1.5">
          <p className="text-label font-semibold text-ink-soft">Dịch vụ liên quan</p>
          <ServicePicker services={flow.lookups.services} value={draft.services} onChange={(services) => set({ services })} />
        </div>
        <ui.Field label="Ghi chú">
          <ui.Input value={draft.note} onChange={(event) => set({ note: event.target.value })} />
        </ui.Field>
      </fieldset>
    </div>
  );
}

interface Bulk {
  audience: "" | Audience;
  approved: "" | "yes" | "no";
  services: string[];
  from: string;
  to: string;
}

const NO_BULK: Bulk = { audience: "", approved: "", services: [], from: "", to: "" };

function patchOf(bulk: Bulk): Partial<Draft> {
  return {
    ...(bulk.approved === "" ? {} : { approved: bulk.approved === "yes" }),
    ...(bulk.services.length > 0 ? { services: bulk.services } : {}),
    ...(bulk.from === "" ? {} : { from: bulk.from }),
    ...(bulk.to === "" ? {} : { to: bulk.to }),
  };
}

function ApplyAll({ flow, keys }: { flow: AddFlow; keys: string[] }) {
  const [bulk, setBulk] = useState<Bulk>(NO_BULK);
  const patch = patchOf(bulk);
  const nothing = Object.keys(patch).length === 0 && bulk.audience === "";
  const apply = () => {
    flow.changeDraft(keys, patch);
    if (bulk.audience !== "") flow.setAudience(keys, bulk.audience);
    setBulk(NO_BULK);
  };
  return (
    <Section title="Áp dụng cho tất cả">
      <div className="grid gap-3 sm:grid-cols-2">
        {AUDIENCE_SPLIT && (
          <ui.Field label="Đối tượng">
            <ui.Select
              value={bulk.audience}
              options={[{ value: "", label: "Giữ nguyên" }, ...AUDIENCE_OPTIONS]}
              onChange={(event) => setBulk({ ...bulk, audience: audienceFromValue(event.target.value) })}
            />
          </ui.Field>
        )}
        {APPROVAL_STEP && (
        <ui.Field label="Đã duyệt">
          <ui.Select
            value={bulk.approved}
            options={[
              { value: "", label: "Giữ nguyên" },
              { value: "yes", label: "Đã duyệt" },
              { value: "no", label: "Chưa duyệt" },
            ]}
            onChange={(event) => setBulk({ ...bulk, approved: approvedFromValue(event.target.value) })}
          />
        </ui.Field>
        )}
        <ui.Field label="Hiệu lực từ">
          <ui.Input type="date" value={bulk.from} onChange={(event) => setBulk({ ...bulk, from: event.target.value })} />
        </ui.Field>
        <ui.Field label="Hiệu lực đến">
          <ui.Input type="date" value={bulk.to} onChange={(event) => setBulk({ ...bulk, to: event.target.value })} />
        </ui.Field>
      </div>
      <div className="space-y-1.5">
        <p className="text-label font-semibold text-ink-soft">Dịch vụ (chọn để gán cho tất cả)</p>
        <ServicePicker services={flow.lookups.services} value={bulk.services} onChange={(services) => setBulk({ ...bulk, services })} />
      </div>
      <ui.Button variant="secondary" disabled={nothing} onClick={apply}>
        Áp dụng cho {keys.length} tệp
      </ui.Button>
    </Section>
  );
}

function Refused({ items, benchmark }: { items: PreviewItem[]; benchmark: boolean }) {
  if (items.length === 0) return null;
  return (
    <Section title="Không nạp được">
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.key} className="text-small text-ink">
            <span className="font-semibold">{item.name}</span>: {refusalOf(item, benchmark)}
          </li>
        ))}
      </ul>
    </Section>
  );
}

/** Asks before anything that carries internal sections or personal data becomes "Bệnh nhân". */
function PatientDialog({ entries, onYes, onNo }: { entries: Entry[]; onYes: () => void; onNo: () => void }) {
  return (
    <ConfirmDialog
      title="Cho bệnh nhân thấy tài liệu này?"
      onClose={onNo}
      actions={
        <>
          <ui.Button variant="secondary" onClick={onNo}>
            Giữ Nội bộ
          </ui.Button>
          <ui.Button variant="danger" onClick={onYes}>
            Vẫn cho bệnh nhân thấy
          </ui.Button>
        </>
      }
    >
      <p className="mb-2">Agent sẽ được phép trả lời bệnh nhân từ nội dung dưới đây:</p>
      <ul className="space-y-2">
        {entries.map(({ item }) => (
          <li key={item.key}>
            <span className="font-semibold text-ink">{item.name}</span>
            <ul className="list-disc pl-5">
              {patientRisks(item).map((warning) => (
                <li key={warning.code}>{warning.text}</li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
    </ConfirmDialog>
  );
}

export function InfoStep({ flow }: { flow: AddFlow }) {
  const usable = flow.entries.filter((entry) => refusalOf(entry.item, flow.benchmark) === null);
  const refused = flow.entries.filter((entry) => refusalOf(entry.item, flow.benchmark) !== null);
  return (
    <div className="space-y-4">
      {flow.lookups.failed && <ui.Notice tone="warning">Không tải được danh sách dịch vụ hoặc nguồn đang dùng; các ô này tạm trống.</ui.Notice>}
      <ui.Notice tone="info">
        Tệp có phần đầu YAML được điền sẵn theo đó. Nạp xong là agent dùng ngay, trên mọi kênh.
      </ui.Notice>
      {usable.length > 1 && <ApplyAll flow={flow} keys={usable.map((entry) => entry.item.key)} />}
      {usable.map((entry) => (
        <DraftRow key={entry.item.key} entry={entry} flow={flow} />
      ))}
      <Refused items={refused.map((entry) => entry.item)} benchmark={flow.benchmark} />
      {flow.patientAsk && (
        <PatientDialog entries={flow.patientAsk.risky} onYes={() => flow.answerPatient(true)} onNo={() => flow.answerPatient(false)} />
      )}
    </div>
  );
}

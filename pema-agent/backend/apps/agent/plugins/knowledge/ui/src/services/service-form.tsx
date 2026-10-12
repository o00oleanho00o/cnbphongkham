/** Add or change one service in a sheet; changing the code asks first because the labels depend on it. */
import { type FormEvent, useState } from "react";

import { messageOf } from "../client";
import { ConfirmDialog, Sheet, Switch } from "../parts";
import { ui } from "../sdk";
import type { Service, ServiceBody } from "../types";
import {
  CODE_RULE,
  type ServiceForm,
  bodyOf,
  codeChangeWarning,
  formOf,
  formProblems,
  hasProblem,
  normaliseCode,
} from "./services-logic";
import { WordEditor } from "./word-editor";

const FORM_ID = "service-form";

export function ServiceSheet({
  service,
  services,
  onClose,
  onSave,
}: {
  /** The service being changed; null when adding. */
  service: Service | null;
  services: readonly Service[];
  onClose: () => void;
  /** Saves and closes; rejects with the server's sentence. */
  onSave: (body: ServiceBody) => Promise<void>;
}) {
  const [form, setForm] = useState<ServiceForm>(() => formOf(service));
  const [tried, setTried] = useState(false);
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const problems = formProblems(form, services, service?.id ?? null);
  const shown = tried ? problems : { code: null, name: null };
  const set = <K extends keyof ServiceForm>(key: K, value: ServiceForm[K]) =>
    setForm((before) => ({ ...before, [key]: value }));

  async function save() {
    setAsking(false);
    setBusy(true);
    setError("");
    try {
      await onSave(bodyOf(form));
    } catch (err) {
      setError(messageOf(err));
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setTried(true);
    if (hasProblem(problems)) return;
    const codeChanged = service !== null && normaliseCode(form.code) !== service.code;
    if (codeChanged) {
      setAsking(true);
      return;
    }
    void save();
  }

  return (
    <>
      <Sheet
        title={service ? `Sửa dịch vụ ${service.name}` : "Thêm dịch vụ"}
        onClose={onClose}
        footer={
          <div className="flex flex-wrap justify-end gap-2">
            <ui.Button variant="secondary" onClick={onClose}>
              Hủy
            </ui.Button>
            <ui.Button type="submit" form={FORM_ID} busy={busy}>
              {service ? "Lưu thay đổi" : "Thêm dịch vụ"}
            </ui.Button>
          </div>
        }
      >
        <form id={FORM_ID} onSubmit={submit} noValidate className="space-y-4">
          <ui.Field label="Mã dịch vụ" hint={CODE_RULE} error={shown.code ?? undefined}>
            <ui.Input
              value={form.code}
              maxLength={40}
              autoCapitalize="characters"
              placeholder="HORI"
              onChange={(event) => set("code", event.target.value.toUpperCase())}
            />
          </ui.Field>
          <ui.Field label="Tên dịch vụ" error={shown.name ?? undefined}>
            <ui.Input
              value={form.name}
              maxLength={120}
              placeholder="Bớt Hori"
              onChange={(event) => set("name", event.target.value)}
            />
          </ui.Field>
          <div>
            <p className="mb-1 text-small font-medium text-ink">Tên gọi khác</p>
            <WordEditor
              label="Tên gọi khác"
              words={form.aliases}
              placeholder="Gõ rồi bấm Enter, ví dụ: hori"
              onChange={(next) => set("aliases", next)}
            />
          </div>
          <ui.Field label="Mô tả">
            <ui.Input
              value={form.description}
              maxLength={300}
              placeholder="Một dòng mô tả ngắn"
              onChange={(event) => set("description", event.target.value)}
            />
          </ui.Field>
          <div>
            <p className="mb-1 text-small font-medium text-ink">Chi nhánh (tùy chọn)</p>
            <WordEditor
              label="Chi nhánh"
              words={form.branches}
              placeholder="Gõ rồi bấm Enter; để trống nếu chi nhánh nào cũng có"
              onChange={(next) => set("branches", next)}
            />
          </div>
          <Switch
            label="Đang bật"
            hint="Dịch vụ tắt không còn được dùng để gán nhãn và mở rộng câu hỏi"
            checked={form.enabled}
            onChange={(next) => set("enabled", next)}
          />
          {error && <ui.Notice tone="danger">{error}</ui.Notice>}
        </form>
      </Sheet>
      {asking && service && (
        <ConfirmDialog
          title={`Đổi mã ${service.code} thành ${normaliseCode(form.code)}?`}
          onClose={() => setAsking(false)}
          actions={
            <>
              <ui.Button variant="secondary" onClick={() => setAsking(false)}>
                Quay lại
              </ui.Button>
              <ui.Button onClick={() => void save()}>Đổi mã</ui.Button>
            </>
          }
        >
          {codeChangeWarning(service, normaliseCode(form.code))}
        </ConfirmDialog>
      )}
    </>
  );
}

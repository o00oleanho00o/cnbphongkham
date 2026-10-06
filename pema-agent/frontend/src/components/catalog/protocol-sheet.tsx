"use client";

// Add or edit a follow-up protocol (`POST /api/v1/protocols`, `PATCH /api/v1/protocols/{protocol_id}`). The
// protocol is the chain the CRM rules follow after a session: the day of the D+1, D+3 and D+7 tasks, the day of
// the review recommendation (D+30 for laser-co2) and how old a session may be for the chain to apply (45 days).
// In the old web that chain was hard-coded; here the owner and the manager set it (`admin.rules`) and the rules
// read it on their next run. An empty milestone box means the protocol has no such task.
import { useState, type FormEvent } from "react";

import { Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import {
  MILESTONE_KEYS,
  SERVICE_CODE_HINT,
  catalogErrorMessage,
  catalogStale,
  emptyProtocolForm,
  formFromProtocol,
  parseProtocolForm,
  type MilestoneKey,
  type ProtocolForm,
  type ProtocolRow,
} from "@/lib/catalog/catalog-view";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

const MILESTONE_LABEL: Record<MilestoneKey, string> = {
  d1: "Hỏi tình trạng (D+1)",
  d3: "Mời gửi ảnh (D+3)",
  d7: "Bác sĩ xem lại (D+7)",
};

export function ProtocolSheet({
  protocol,
  onClose,
  onSaved,
  onStale,
}: {
  /** null = add a new protocol */
  protocol: ProtocolRow | null;
  onClose: () => void;
  onSaved: () => void;
  onStale: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState<ProtocolForm>(() =>
    protocol ? formFromProtocol(protocol) : emptyProtocolForm(),
  );
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const creating = protocol === null;

  const set = <K extends keyof ProtocolForm>(key: K, value: ProtocolForm[K]) =>
    setForm((current) => ({ ...current, [key]: value }));

  async function save(e: FormEvent) {
    e.preventDefault();
    setError("");
    const parsed = parseProtocolForm(form, { create: creating });
    if (!parsed.ok) {
      setError(parsed.problem);
      return;
    }
    const { name, milestones, followupDays, windowDays, active } = parsed.value;
    setBusy(true);
    try {
      if (protocol === null) {
        await unwrap(
          http.POST("/api/v1/protocols", {
            body: {
              code: form.code.trim(),
              name,
              milestones,
              followup_days: followupDays,
              window_days: windowDays,
              active,
            },
          }),
        );
        toast.push("success", "Đã thêm giao thức.");
      } else {
        await unwrap(
          http.PATCH("/api/v1/protocols/{protocol_id}", {
            params: { path: { protocol_id: protocol.id } },
            body: {
              version: protocol.version,
              name,
              milestones,
              followup_days: followupDays,
              window_days: windowDays,
              active,
            },
          }),
        );
        toast.push("success", "Đã lưu giao thức. Luật CSKH đọc giá trị mới ở lần chạy sau.");
      }
      onSaved();
    } catch (err) {
      setError(catalogErrorMessage(err));
      if (catalogStale(err)) onStale();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={creating ? "Thêm giao thức" : "Sửa giao thức"}
      subtitle="Các mốc chăm sóc sau thủ thuật mà luật CSKH tạo việc theo."
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton type="submit" form="protocol-form" disabled={busy}>
            {busy ? "Đang lưu..." : "Lưu giao thức"}
          </PrimaryButton>
        </>
      }
    >
      <form id="protocol-form" onSubmit={(e) => void save(e)} noValidate>
        <Field
          label="Mã giao thức"
          hint={creating ? SERVICE_CODE_HINT : undefined}
          required={creating}
        >
          {(control) => (
            <input
              {...control}
              value={form.code}
              onChange={(e) => set("code", e.target.value)}
              disabled={!creating}
              maxLength={40}
              autoComplete="off"
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Tên giao thức" required>
          {(control) => (
            <input
              {...control}
              value={form.name}
              onChange={(e) => set("name", e.target.value)}
              maxLength={120}
              autoComplete="off"
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-3">
          {MILESTONE_KEYS.map((key) => (
            <Field
              key={key}
              label={MILESTONE_LABEL[key]}
              hint="Số ngày sau buổi; để trống nếu không có"
            >
              {(control) => (
                <input
                  {...control}
                  type="number"
                  inputMode="numeric"
                  value={form.milestones[key]}
                  onChange={(e) => set("milestones", { ...form.milestones, [key]: e.target.value })}
                  className={FIELD_CONTROL_CLASS}
                />
              )}
            </Field>
          ))}
        </div>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <Field
            label="Đánh giá lại sau (ngày)"
            hint="Ví dụ 30 cho laser; để trống nếu không khuyến nghị"
          >
            {(control) => (
              <input
                {...control}
                type="number"
                inputMode="numeric"
                value={form.followup}
                onChange={(e) => set("followup", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field
            label="Cửa sổ áp dụng (ngày)"
            hint="Buổi cũ hơn số ngày này không tạo việc D+1/3/7"
          >
            {(control) => (
              <input
                {...control}
                type="number"
                inputMode="numeric"
                value={form.window}
                onChange={(e) => set("window", e.target.value)}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
        </div>
        <label className="mb-3.5 inline-flex min-h-9 items-center gap-2 text-body text-ink">
          <input
            type="checkbox"
            checked={form.active}
            onChange={(e) => set("active", e.target.checked)}
            className="h-4 w-4 accent-brand-500"
          />
          Đang dùng (bỏ chọn thì buổi mới không tạo việc theo giao thức này)
        </label>
        {error && <Notice tone="error">{error}</Notice>}
      </form>
    </Sheet>
  );
}

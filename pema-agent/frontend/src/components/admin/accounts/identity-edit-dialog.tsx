"use client";

// "Sửa danh tính" (frames WM26-WM28): the name customers see, the purpose and the send limits of one identity.
// `PATCH /api/v1/identities/{id}`. No credential, token or QR here (those stay in "Sửa" and "Login QR"). A blank
// limit clears the override, so the channel's own limit applies again. The BE refuses a purpose change while
// conversations or roster entries still point at the identity; its message is shown as it is.
import { useState } from "react";

import { Notice } from "@/components/ops/ops-ui";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import {
  PURPOSE_OPTIONS,
  formOf,
  updateBody,
  validateForm,
  type IdentityForm,
} from "@/lib/admin/accounts/identity-view";
import { NHAN_KENH } from "@/lib/admin/accounts/mo-ta-loai-kenh";
import { Button } from "@/ui/button";
import { Dialog } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Identity = Schemas["IdentityOut"];

const placeholder = (value: number | null | undefined): string =>
  value === null || value === undefined ? "Theo kênh: không giới hạn" : `Theo kênh: ${value}`;

export function IdentityEditDialog({
  identity,
  onClose,
  onSaved,
}: {
  identity: Identity;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<IdentityForm>(() => formOf(identity));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const errors = validateForm(form);
  const invalid = Object.keys(errors).length > 0;
  const set = (change: Partial<IdentityForm>) => setForm((current) => ({ ...current, ...change }));

  async function save() {
    setBusy(true);
    setError("");
    try {
      await unwrap(
        http.PATCH("/api/v1/identities/{account_id}", {
          params: { path: { account_id: identity.id } },
          body: updateBody(form),
        }),
      );
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      title="Sửa danh tính"
      subtitle={`${identity.label} · ${NHAN_KENH[identity.channel]}`}
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy || invalid} onClick={() => void save()}>
            Lưu
          </Button>
        </>
      }
    >
      <Field
        label="Tên danh tính"
        hint="Tên khách nhìn thấy khi nhắn tin."
        error={errors.label}
        required
      >
        {(control) => (
          <input
            {...control}
            value={form.label}
            onChange={(e) => set({ label: e.target.value })}
            className={FIELD_CONTROL_CLASS}
          />
        )}
      </Field>
      <fieldset className="mb-3.5">
        <legend className="mb-1.5 text-label font-semibold text-ink-soft">Mục đích</legend>
        <div className="space-y-2">
          {PURPOSE_OPTIONS.map((option) => (
            <label
              key={option.id}
              className="flex cursor-pointer items-center gap-2.5 rounded-tile border border-line px-3 py-2 text-body text-ink has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50"
            >
              <input
                type="radio"
                name="identity-purpose"
                checked={form.purpose === option.id}
                onChange={() => set({ purpose: option.id })}
              />
              <span>
                <span className="font-semibold">{option.title}</span> · {option.hint}
              </span>
            </label>
          ))}
        </div>
      </fieldset>
      <Field label="Tối đa tin chủ động mỗi ngày" error={errors.dailyCap}>
        {(control) => (
          <input
            {...control}
            inputMode="numeric"
            value={form.dailyCap}
            placeholder={placeholder(identity.effective.daily_cap)}
            onChange={(e) => set({ dailyCap: e.target.value })}
            className={FIELD_CONTROL_CLASS}
          />
        )}
      </Field>
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Field label="Cách nhau tối thiểu (giây)" error={errors.gapMin}>
          {(control) => (
            <input
              {...control}
              inputMode="numeric"
              value={form.gapMin}
              placeholder={placeholder(identity.effective.send_gap_min_s)}
              onChange={(e) => set({ gapMin: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Cách nhau tối đa (giây)" error={errors.gapMax}>
          {(control) => (
            <input
              {...control}
              inputMode="numeric"
              value={form.gapMax}
              placeholder={placeholder(identity.effective.send_gap_max_s)}
              onChange={(e) => set({ gapMax: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
      </div>
      <p className="text-label text-ink-soft">Để trống = dùng giới hạn của kênh.</p>
      {error && (
        <div className="mt-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
    </Dialog>
  );
}

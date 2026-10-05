"use client";

// "＋ Hồ sơ mới" of /patients (old web: `data-modal="patient"`, screen WC3 "Thêm người bệnh"). It calls the existing
// `POST /api/v1/patients`; the code (P0xx) is made by the backend. Differences from the old modal, because this
// record is stored and not a demo: "Ngày sinh" replaces "Tuổi" (the record keeps a birth date, never an age) and
// "Mối quan tâm" is not asked (it comes from the first course, not from the identity record); "Số điện thoại" and
// "Nguồn khách" are the two identity fields the record does have. Use synthetic data only in the demo.
import { useState, type FormEvent } from "react";

import { FormError } from "@/components/ops/patient/shared";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { NAME_REQUIRED } from "@/lib/ops/patient-profile";
import { Button } from "@/ui/button";
import { Sheet } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Created = Schemas["PatientOut"];

export function NewPatientDialog({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (patient: Created) => void;
}) {
  const [form, setForm] = useState({ name: "", birth: "", phone: "", source: "" });
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const patch = (change: Partial<typeof form>) => setForm((current) => ({ ...current, ...change }));

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (form.name.trim() === "") {
      setProblem(NAME_REQUIRED);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      const created = await unwrap(
        http.POST("/api/v1/patients", {
          body: {
            full_name: form.name.trim(),
            gender: "unknown",
            birth_date: form.birth === "" ? null : form.birth,
            phone: form.phone.trim() === "" ? null : form.phone.trim(),
            source: form.source.trim() === "" ? null : form.source.trim(),
          },
        }),
      );
      onCreated(created);
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title="Thêm người bệnh"
      subtitle="Hồ sơ mới"
      onClose={onClose}
      footer={
        <Button type="submit" form="new-patient-form" disabled={busy}>
          Tạo hồ sơ
        </Button>
      }
    >
      <form id="new-patient-form" onSubmit={(e) => void submit(e)} noValidate>
        <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
          <Field label="Họ và tên" required>
            {(control) => (
              <input
                {...control}
                value={form.name}
                maxLength={120}
                placeholder="Nguyễn ..."
                onChange={(e) => patch({ name: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Ngày sinh">
            {(control) => (
              <input
                {...control}
                type="date"
                value={form.birth}
                onChange={(e) => patch({ birth: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Số điện thoại">
            {(control) => (
              <input
                {...control}
                type="tel"
                inputMode="tel"
                value={form.phone}
                maxLength={20}
                onChange={(e) => patch({ phone: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
          <Field label="Nguồn khách">
            {(control) => (
              <input
                {...control}
                value={form.source}
                maxLength={60}
                onChange={(e) => patch({ source: e.target.value })}
                className={FIELD_CONTROL_CLASS}
              />
            )}
          </Field>
        </div>
        <FormError message={problem} />
      </form>
    </Sheet>
  );
}

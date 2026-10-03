"use client";

// Add or change the 24/7 on-call contact: the Zalo number the routing ends with, who answers it, from when to when,
// and whether it is on. The number lives in the database only (never in code or the repository) and every agent
// reads it on each turn, so a change takes effect at once. The backend refuses to switch off the last active contact.
import { useId, useState } from "react";

import { Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { errorMessage } from "@/lib/api/client";
import { careApi } from "@/lib/care/care-api";
import type { OnCallContact } from "@/lib/care/care-types";
import { onCallErrors } from "@/lib/care/forms";
import { localInputToIso } from "@/lib/ops/format";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

/** ISO with offset to the `datetime-local` value ("2026-10-02T09:00"), in clinic time. */
function toLocalInput(iso: string | null): string {
  if (!iso) return "";
  const shifted = new Date(new Date(iso).getTime() + 7 * 3_600_000);
  return shifted.toISOString().slice(0, 16);
}

export function OnCallSheet({
  contact,
  onClose,
  onSaved,
}: {
  contact: OnCallContact | null;
  onClose: () => void;
  onSaved: (saved: OnCallContact) => void;
}) {
  const numberId = useId();
  const ownerId = useId();
  const fromId = useId();
  const toId = useId();
  const [number, setNumber] = useState(contact?.is_fixture ? "" : (contact?.zalo_number ?? ""));
  const [owner, setOwner] = useState(contact?.owner ?? "");
  const [validFrom, setValidFrom] = useState(toLocalInput(contact?.valid_from ?? null));
  const [validTo, setValidTo] = useState(toLocalInput(contact?.valid_to ?? null));
  const [active, setActive] = useState(contact?.active ?? true);
  const [touched, setTouched] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const errors = onCallErrors({ zalo_number: number, owner });
  const shown = touched ? errors : { number: "", owner: "" };

  async function save() {
    setTouched(true);
    if (errors.number || errors.owner) return;
    setBusy(true);
    setError("");
    const body = {
      zalo_number: number.trim(),
      owner: owner.trim(),
      valid_from: validFrom ? localInputToIso(validFrom) : null,
      valid_to: validTo ? localInputToIso(validTo) : null,
      active,
      version: contact?.version ?? null,
    };
    try {
      const saved = contact
        ? await careApi.saveOnCall(contact.id, body)
        : await careApi.createOnCall(body);
      onSaved(saved);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      title={contact ? "Sửa số trực" : "Thêm số trực"}
      subtitle="Số Zalo trực 24/24 luôn là điểm cuối của chuỗi chuyển giao"
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton onClick={() => void save()} disabled={busy}>
            Lưu
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {contact?.is_fixture && (
          <Notice tone="warn">
            Đây là số mẫu để thử. Hãy nhập số trực thật do phòng khám cung cấp trước khi dùng thật.
          </Notice>
        )}
        <Field
          label="Số Zalo trực"
          htmlFor={numberId}
          hint="8 đến 15 chữ số, có thể bắt đầu bằng +."
        >
          <input
            id={numberId}
            inputMode="tel"
            autoComplete="off"
            className={cx(FIELD_BASE_CLASS, "w-full")}
            value={number}
            onChange={(e) => setNumber(e.target.value)}
            aria-invalid={shown.number !== ""}
          />
          {shown.number && (
            <p role="alert" className="mt-1 text-label text-danger">
              {shown.number}
            </p>
          )}
        </Field>
        <Field label="Người phụ trách" htmlFor={ownerId}>
          <input
            id={ownerId}
            className={cx(FIELD_BASE_CLASS, "w-full")}
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            aria-invalid={shown.owner !== ""}
          />
          {shown.owner && (
            <p role="alert" className="mt-1 text-label text-danger">
              {shown.owner}
            </p>
          )}
        </Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Có hiệu lực từ" htmlFor={fromId}>
            <input
              id={fromId}
              type="datetime-local"
              className={cx(FIELD_BASE_CLASS, "w-full")}
              value={validFrom}
              onChange={(e) => setValidFrom(e.target.value)}
            />
          </Field>
          <Field label="Đến (để trống: không giới hạn)" htmlFor={toId}>
            <input
              id={toId}
              type="datetime-local"
              className={cx(FIELD_BASE_CLASS, "w-full")}
              value={validTo}
              onChange={(e) => setValidTo(e.target.value)}
            />
          </Field>
        </div>
        <label className="flex min-h-11 cursor-pointer items-center gap-3">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          <span className="text-body text-ink">Đang bật</span>
        </label>
        {error && <Notice tone="error">{error}</Notice>}
      </div>
    </Sheet>
  );
}

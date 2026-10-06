"use client";

// "Thêm ca trực" and "Sửa ca trực" (frames WM34-WM38): who covers which identity, on which weekdays or on one day,
// from which time to which time (an end before the start means the next morning), and a short note. Owner and
// manager only; the BE refuses everybody else. Saving an edit sends the version the person saw: when somebody got
// there first (409 `version_conflict`) the entry is loaded again and the form says so.
import { useMemo, useState } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { Notice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";
import {
  WEEKDAYS,
  WEEKDAY_CHIP,
  createBody,
  overnightText,
  toggleWeekday,
  updateBody,
  validateRoster,
  formOfEntry,
  type RosterForm,
  type RosterMode,
} from "@/lib/ops/roster-view";
import { ROLE_LABEL } from "@/lib/session/session-context";
import { useAssignableStaff } from "@/lib/staff/use-assignable-staff";
import { Button } from "@/ui/button";
import { Dialog } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Entry = Schemas["RosterEntryOut"];
type Identity = Schemas["IdentityOut"];

const MODES: { id: RosterMode; label: string }[] = [
  { id: "weekly", label: "Lặp theo thứ" },
  { id: "date", label: "Một ngày" },
];
const NOTE_MAX = 200;

export function RosterDialog({
  initial,
  entry,
  identities,
  onClose,
  onSaved,
  onDelete,
}: {
  initial: RosterForm;
  /** The entry being edited; null when adding. */
  entry: Entry | null;
  identities: readonly Identity[];
  onClose: () => void;
  onSaved: () => void;
  onDelete: (entry: Entry) => void;
}) {
  const toast = useToast();
  const { staff } = useAssignableStaff();
  const [form, setForm] = useState<RosterForm>(initial);
  const [version, setVersion] = useState(entry?.version ?? 0);
  const [info, setInfo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const errors = validateRoster(form);
  const invalid = Object.keys(errors).length > 0;
  const set = (change: Partial<RosterForm>) => setForm((current) => ({ ...current, ...change }));

  const identityOptions = useMemo<SelectOption[]>(
    () => identities.map((i) => ({ value: i.id, label: i.label })),
    [identities],
  );
  const staffOptions = useMemo<SelectOption[]>(
    () => staff.map((s) => ({ value: s.id, label: `${s.name} · ${ROLE_LABEL[s.role]}` })),
    [staff],
  );
  const staffValue = form.userId || staff[0]?.id || "";
  const overnight = overnightText(form);

  /** Somebody else changed the entry first: show what is stored now and let the person try again. */
  async function reloadEntry(current: Entry) {
    const list = await unwrap(
      http.GET("/api/v1/roster", { params: { query: { account_id: current.account_id } } }),
    );
    const fresh = list.find((e) => e.id === current.id);
    if (!fresh) {
      onSaved();
      return;
    }
    setForm(formOfEntry(fresh));
    setVersion(fresh.version);
    setInfo("Ca trực vừa được người khác sửa. Đã tải lại.");
  }

  async function save() {
    setBusy(true);
    setError("");
    setInfo("");
    const payload = { ...form, userId: staffValue };
    try {
      if (entry) {
        await unwrap(
          http.PATCH("/api/v1/roster/{entry_id}", {
            params: { path: { entry_id: entry.id } },
            body: updateBody(payload, version),
          }),
        );
      } else {
        await unwrap(http.POST("/api/v1/roster", { body: createBody(payload) }));
      }
      toast.push("success", entry ? "Đã lưu ca trực." : "Đã thêm ca trực.");
      onSaved();
    } catch (e) {
      if (entry && e instanceof ApiError && e.code === "version_conflict") {
        await reloadEntry(entry).catch((err: unknown) => setError(errorMessage(err)));
      } else {
        setError(errorMessage(e));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      title={entry ? "Sửa ca trực" : "Thêm ca trực"}
      onClose={onClose}
      wide
      footer={
        <>
          {entry && (
            <Button variant="danger" className="sm:mr-auto" onClick={() => onDelete(entry)}>
              Xóa ca
            </Button>
          )}
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy || invalid} onClick={() => void save()}>
            {entry ? "Lưu" : "Thêm ca"}
          </Button>
        </>
      }
    >
      {info && (
        <div className="mb-3">
          <Notice tone="info">{info}</Notice>
        </div>
      )}
      <Field label="Danh tính">
        {(control) => (
          <SelectMenu
            id={control.id}
            size="md"
            ariaLabel="Danh tính"
            value={form.accountId}
            options={identityOptions}
            disabled={entry !== null}
            onChange={(accountId) => set({ accountId })}
          />
        )}
      </Field>
      <Field label="Người trực" error={errors.user}>
        {(control) => (
          <SelectMenu
            id={control.id}
            size="md"
            ariaLabel="Người trực"
            value={staffValue}
            options={staffOptions}
            onChange={(userId) => set({ userId })}
          />
        )}
      </Field>
      <fieldset className="mb-3.5">
        <legend className="mb-1.5 text-label font-semibold text-ink-soft">Kiểu lịch</legend>
        <div className="flex flex-wrap gap-4">
          {MODES.map((mode) => (
            <label
              key={mode.id}
              className="flex cursor-pointer items-center gap-2 text-body text-ink"
            >
              <input
                type="radio"
                name="roster-mode"
                checked={form.mode === mode.id}
                onChange={() => set({ mode: mode.id })}
              />
              {mode.label}
            </label>
          ))}
        </div>
      </fieldset>
      {form.mode === "weekly" ? (
        <div className="mb-3.5">
          <p className="mb-1.5 text-label font-semibold text-ink-soft">Lặp vào các thứ</p>
          <div role="group" aria-label="Lặp vào các thứ" className="flex flex-wrap gap-2">
            {WEEKDAYS.map((day) => {
              const on = form.weekdays.includes(day);
              return (
                <button
                  key={day}
                  type="button"
                  aria-pressed={on}
                  onClick={() => set({ weekdays: toggleWeekday(form.weekdays, day) })}
                  className={`inline-flex min-h-9 items-center rounded-pill border px-3.5 text-small font-medium transition-colors ${
                    on
                      ? "border-brand-500 bg-brand-500 text-surface"
                      : "border-line bg-surface text-ink-soft hover:bg-tile hover:text-ink"
                  }`}
                >
                  {WEEKDAY_CHIP[day]}
                </button>
              );
            })}
          </div>
          {errors.weekdays && (
            <p role="alert" className="mt-1 text-label text-danger">
              {errors.weekdays}
            </p>
          )}
        </div>
      ) : (
        <Field label="Ngày" error={errors.date}>
          {(control) => (
            <input
              {...control}
              type="date"
              value={form.date}
              onChange={(e) => set({ date: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
      )}
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Field label="Từ">
          {(control) => (
            <input
              {...control}
              type="time"
              value={form.start}
              onChange={(e) => set({ start: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Đến" error={errors.time}>
          {(control) => (
            <input
              {...control}
              type="time"
              value={form.end}
              onChange={(e) => set({ end: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
      </div>
      {overnight && <p className="-mt-1.5 mb-3.5 text-label text-ink-soft">{overnight}</p>}
      <Field label="Ghi chú" hint="Tối đa 200 ký tự." error={errors.note}>
        {(control) => (
          <input
            {...control}
            value={form.note}
            maxLength={NOTE_MAX}
            placeholder="Ví dụ: trực thay Mai Anh"
            onChange={(e) => set({ note: e.target.value })}
            className={FIELD_CONTROL_CLASS}
          />
        )}
      </Field>
      {error && <Notice tone="error">{error}</Notice>}
    </Dialog>
  );
}

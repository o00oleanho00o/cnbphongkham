"use client";

// Edit the care profile of one staff member: skills (the routing matches `required_skill` against them), the weekly
// shift (local clinic time), the number of conversations they can hold at once and their languages. The routing
// reads these on every handoff; the backend validates them again and refuses a stale `version` (409).
import { useId, useState } from "react";

import { Field, Notice, PrimaryButton, SecondaryButton } from "@/components/ops/ops-ui";
import { Sheet } from "@/components/ops/sheet";
import { errorMessage } from "@/lib/api/client";
import { careApi } from "@/lib/care/care-api";
import type { Shift, StaffCareProfile, Weekday } from "@/lib/care/care-types";
import { WEEKDAYS } from "@/lib/care/care-types";
import {
  addInterval,
  changeInterval,
  parseBounded,
  parseSkills,
  removeInterval,
  shiftError,
} from "@/lib/care/forms";
import { WEEKDAY_LABEL, skillLabel } from "@/lib/care/labels";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

export function StaffSheet({
  profile,
  knownSkills,
  onClose,
  onSaved,
}: {
  profile: StaffCareProfile;
  knownSkills: readonly string[];
  onClose: () => void;
  onSaved: (saved: StaffCareProfile) => void;
}) {
  const capacityId = useId();
  const langId = useId();
  const extraId = useId();
  const [skills, setSkills] = useState<string[]>(profile.skills);
  const [extra, setExtra] = useState("");
  const [shift, setShift] = useState<Shift>(profile.shift);
  const [capacity, setCapacity] = useState(String(profile.capacity));
  const [languages, setLanguages] = useState(profile.languages.join(", "));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const options = [...new Set([...knownSkills, ...profile.skills])];
  const capacityValue = parseBounded(capacity, 1, 50);
  const problem =
    capacityValue === null || !Number.isInteger(capacityValue)
      ? "Số cuộc trò chuyện cùng lúc là số nguyên từ 1 đến 50."
      : shiftError(shift);

  function toggle(skill: string) {
    setSkills((current) =>
      current.includes(skill) ? current.filter((s) => s !== skill) : [...current, skill],
    );
  }

  async function save() {
    if (problem || capacityValue === null) return;
    setBusy(true);
    setError("");
    try {
      const merged = [...new Set([...skills, ...parseSkills(extra)])];
      const saved = await careApi.saveStaff(profile.user_id, {
        skills: merged,
        shift,
        capacity: capacityValue,
        languages: parseSkills(languages),
        version: profile.version,
      });
      onSaved(saved);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet
      wide
      title={profile.name}
      subtitle="Kỹ năng, ca trực và sức chứa dùng để chọn người nhận"
      onClose={onClose}
      footer={
        <>
          <SecondaryButton onClick={onClose} disabled={busy}>
            Hủy
          </SecondaryButton>
          <PrimaryButton onClick={() => void save()} disabled={busy || problem !== ""}>
            Lưu
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-5">
        <fieldset>
          <legend className="mb-1.5 text-small font-medium text-ink">Kỹ năng</legend>
          <div className="flex flex-wrap gap-2">
            {options.map((skill) => (
              <label
                key={skill}
                className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border border-line px-3 text-small has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50 lg:min-h-9"
              >
                <input
                  type="checkbox"
                  checked={skills.includes(skill)}
                  onChange={() => toggle(skill)}
                />
                {skillLabel(skill)}
              </label>
            ))}
          </div>
          <div className="mt-3">
            <Field
              label="Thêm kỹ năng khác"
              htmlFor={extraId}
              hint="Mã viết thường, không dấu, cách nhau bằng dấu phẩy (ví dụ: tiem_filler)."
            >
              <input
                id={extraId}
                className={cx(FIELD_BASE_CLASS, "w-full")}
                value={extra}
                onChange={(e) => setExtra(e.target.value)}
              />
            </Field>
          </div>
        </fieldset>

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Số cuộc trò chuyện cùng lúc" htmlFor={capacityId}>
            <input
              id={capacityId}
              inputMode="numeric"
              className={cx(FIELD_BASE_CLASS, "w-28")}
              value={capacity}
              onChange={(e) => setCapacity(e.target.value)}
            />
          </Field>
          <Field label="Ngôn ngữ" htmlFor={langId} hint="Mã ngôn ngữ, ví dụ: vi, en">
            <input
              id={langId}
              className={cx(FIELD_BASE_CLASS, "w-full")}
              value={languages}
              onChange={(e) => setLanguages(e.target.value)}
            />
          </Field>
        </div>

        <fieldset>
          <legend className="mb-1.5 text-small font-medium text-ink">Ca trực trong tuần</legend>
          <p className="mb-2 text-label text-ink-soft">
            Giờ theo múi giờ phòng khám. Giờ kết thúc sớm hơn giờ bắt đầu nghĩa là ca kéo sang sáng
            hôm sau.
          </p>
          <div className="space-y-3">
            {WEEKDAYS.map((day) => (
              <DayRow
                key={day}
                day={day}
                shift={shift}
                onAdd={() => setShift(addInterval(shift, day))}
                onRemove={(i) => setShift(removeInterval(shift, day, i))}
                onChange={(i, patch) => setShift(changeInterval(shift, day, i, patch))}
              />
            ))}
          </div>
        </fieldset>

        {problem && <Notice tone="warn">{problem}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
      </div>
    </Sheet>
  );
}

function DayRow({
  day,
  shift,
  onAdd,
  onRemove,
  onChange,
}: {
  day: Weekday;
  shift: Shift;
  onAdd: () => void;
  onRemove: (index: number) => void;
  onChange: (index: number, patch: { start?: string; end?: string }) => void;
}) {
  const intervals = shift[day];
  return (
    <div className="rounded-tile border border-line bg-tile/40 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="text-body font-medium text-ink">{WEEKDAY_LABEL[day]}</span>
        <button
          type="button"
          onClick={onAdd}
          className="min-h-11 px-2 text-small font-medium text-brand-500 hover:text-brand-600 lg:min-h-9"
        >
          Thêm ca
        </button>
      </div>
      {intervals.length === 0 && <p className="text-label text-ink-soft">Nghỉ</p>}
      <ul className="space-y-2">
        {intervals.map((interval, index) => (
          <li key={index} className="flex flex-wrap items-center gap-2">
            <input
              type="time"
              aria-label={`${WEEKDAY_LABEL[day]}, ca ${index + 1}, bắt đầu`}
              className={FIELD_BASE_CLASS}
              value={interval.start}
              onChange={(e) => onChange(index, { start: e.target.value })}
            />
            <span className="text-ink-soft">đến</span>
            <input
              type="time"
              aria-label={`${WEEKDAY_LABEL[day]}, ca ${index + 1}, kết thúc`}
              className={FIELD_BASE_CLASS}
              value={interval.end}
              onChange={(e) => onChange(index, { end: e.target.value })}
            />
            <button
              type="button"
              onClick={() => onRemove(index)}
              className="min-h-11 px-2 text-small text-danger hover:underline lg:min-h-9"
            >
              Xóa
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

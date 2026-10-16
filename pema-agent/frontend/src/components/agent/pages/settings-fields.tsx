"use client";

// Pieces of the Cài đặt page: the line above each field (label, where the value comes from, back to the profile) and
// the editor of the variables the persona and the rules fill their {{placeholders}} with.
import { Badge, Button, FIELD_CLASS, Input } from "@/components/agent/plugin-kit";
import type { VariableRow } from "@/lib/agent/agent-settings";
import { cx } from "@/ui/classnames";

export const TEXTAREA_CLASS = cx(FIELD_CLASS, "min-h-32 resize-y");

export function SourceBadge({ stored }: { stored: boolean }) {
  return stored ? <Badge tone="info">Đã chỉnh</Badge> : <Badge>Theo profile</Badge>;
}

/** `onReset` is offered only for a stored value: it sends null, the profile answers again. */
export function SettingHead({
  htmlFor,
  label,
  stored,
  onReset,
  resetLabel = "Về mặc định",
  busy,
}: {
  /** The control the label names; none for a group of controls. */
  htmlFor?: string;
  label: string;
  stored: boolean;
  onReset?: () => void;
  resetLabel?: string;
  busy?: boolean;
}) {
  return (
    <div className="mb-1.5 flex flex-wrap items-center gap-2">
      {htmlFor ? (
        <label htmlFor={htmlFor} className="text-label font-semibold text-ink-soft">
          {label}
        </label>
      ) : (
        <span className="text-label font-semibold text-ink-soft">{label}</span>
      )}
      <SourceBadge stored={stored} />
      {stored && onReset && (
        <Button
          variant="ghost"
          className="ml-auto"
          aria-label={`${resetLabel}: ${label}`}
          disabled={busy}
          onClick={onReset}
        >
          {resetLabel}
        </Button>
      )}
    </div>
  );
}

export function VariablesEditor({
  rows,
  stored,
  error,
  onChange,
  onResetRow,
}: {
  rows: readonly VariableRow[];
  /** Some variable was changed by hand, so a row can go back to the profile's value. */
  stored: boolean;
  error?: string;
  onChange: (rows: VariableRow[]) => void;
  onResetRow: (name: string) => void;
}) {
  const edit = (index: number, change: Partial<VariableRow>) =>
    onChange(rows.map((row, at) => (at === index ? { ...row, ...change } : row)));
  const drop = (index: number) => onChange(rows.filter((_, at) => at !== index));
  const add = () => onChange([...rows, { name: "", value: "", isNew: true }]);
  return (
    <div className="space-y-3">
      {rows.length === 0 && (
        <p className="text-small text-ink-soft">Chưa có biến nào. Bấm "+ Thêm biến" để thêm.</p>
      )}
      {rows.map((row, index) => (
        <div key={index} className="flex flex-wrap items-center gap-2">
          <div className="w-full sm:w-52">
            <Input
              aria-label={`Tên biến ${index + 1}`}
              value={row.name}
              readOnly={!row.isNew}
              placeholder="ten_bien"
              onChange={(e) => edit(index, { name: e.target.value })}
            />
          </div>
          <div className="min-w-0 flex-1 basis-56">
            <Input
              aria-label={`Giá trị của ${row.name || `biến ${index + 1}`}`}
              value={row.value}
              maxLength={500}
              placeholder="Giá trị"
              onChange={(e) => edit(index, { value: e.target.value })}
            />
          </div>
          {row.isNew ? (
            <Button
              variant="ghost"
              aria-label={`Bỏ biến ${row.name || index + 1}`}
              onClick={() => drop(index)}
            >
              Bỏ
            </Button>
          ) : (
            stored && (
              <Button
                variant="ghost"
                aria-label={`Về giá trị profile: ${row.name}`}
                onClick={() => onResetRow(row.name)}
              >
                Về profile
              </Button>
            )
          )}
        </div>
      ))}
      {error && (
        <p role="alert" className="text-label text-danger">
          {error}
        </p>
      )}
      <Button variant="secondary" onClick={add}>
        + Thêm biến
      </Button>
    </div>
  );
}

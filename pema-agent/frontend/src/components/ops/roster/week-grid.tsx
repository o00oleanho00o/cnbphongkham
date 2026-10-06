"use client";

// One week of the roster as seven day columns (frame WM30). A shift is a block "08:00–12:00 · name · role"; for
// owner and manager it opens the edit dialog, for everybody else it is plain text. The colours say the role group
// (CSKH, bác sĩ, chủ phòng khám và quản lý) and a legend below names them; the role is also written in each block.
import type { Schemas } from "@/lib/api";
import {
  ROLE_GROUP_LABEL,
  countText,
  dayTitle,
  entriesOn,
  roleGroup,
  shiftRange,
  weekDates,
  weekdayOf,
  type RoleGroup,
} from "@/lib/ops/roster-view";
import { cx } from "@/ui/classnames";
import { ROLE_LABEL } from "@/lib/session/session-context";

type Entry = Schemas["RosterEntryOut"];
type Weekday = Schemas["Weekday"];

const GROUP_CLASS: Record<RoleGroup, { block: string; swatch: string }> = {
  cs: { block: "border-info-line bg-info-soft text-info", swatch: "border-info" },
  doctor: { block: "border-success-line bg-success-soft text-success", swatch: "border-success" },
  manager: { block: "border-warning-line bg-warning-soft text-warning", swatch: "border-warning" },
};

function Shift({
  entry,
  canManage,
  onEdit,
}: {
  entry: Entry;
  canManage: boolean;
  onEdit: (entry: Entry) => void;
}) {
  const className = cx(
    "block w-full rounded-tile border px-2 py-1.5 text-left text-label leading-snug",
    GROUP_CLASS[roleGroup(entry.user_role)].block,
  );
  const body = (
    <>
      <span className="block font-medium">{shiftRange(entry)}</span>
      <span className="block font-bold">{entry.user_name}</span>
      <span className="block">{ROLE_LABEL[entry.user_role]}</span>
      {entry.note && <span className="block text-ink-soft">{entry.note}</span>}
    </>
  );
  if (!canManage) return <div className={className}>{body}</div>;
  return (
    <button
      type="button"
      onClick={() => onEdit(entry)}
      aria-label={`Sửa ca ${shiftRange(entry)} ${entry.user_name}`}
      className={cx(className, "hover:brightness-95")}
    >
      {body}
    </button>
  );
}

export function WeekGrid({
  monday,
  today,
  entries,
  canManage,
  onAdd,
  onEdit,
}: {
  monday: string;
  today: string;
  entries: readonly Entry[];
  canManage: boolean;
  onAdd: (weekday: Weekday) => void;
  onEdit: (entry: Entry) => void;
}) {
  return (
    <>
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-7">
        {weekDates(monday).map((date) => {
          const shifts = entriesOn(entries, date);
          return (
            <section
              key={date}
              aria-label={dayTitle(date)}
              className={cx(
                "min-w-0 space-y-1.5 rounded-tile border bg-tile/50 p-2",
                date === today ? "border-brand-500" : "border-line",
              )}
            >
              <header>
                <h3 className="text-small font-bold text-heading">{dayTitle(date)}</h3>
                <p className="text-label text-ink-soft">{countText(shifts.length)}</p>
              </header>
              {shifts.map((entry) => (
                <Shift key={entry.id} entry={entry} canManage={canManage} onEdit={onEdit} />
              ))}
              {canManage && (
                <button
                  type="button"
                  onClick={() => onAdd(weekdayOf(date))}
                  className="flex min-h-9 w-full items-center justify-center gap-1 rounded-tile border border-line-strong bg-surface text-label font-semibold text-ink hover:bg-tile"
                >
                  <span aria-hidden>+</span> Thêm ca
                </button>
              )}
            </section>
          );
        })}
      </div>
      <ul className="mt-3 flex flex-wrap gap-4 text-label text-ink-soft">
        {(Object.keys(ROLE_GROUP_LABEL) as RoleGroup[]).map((group) => (
          <li key={group} className="flex items-center gap-1.5">
            <span
              aria-hidden
              className={cx("h-3 w-3 rounded-sm border-2", GROUP_CLASS[group].swatch)}
            />
            {ROLE_GROUP_LABEL[group]}
          </li>
        ))}
      </ul>
    </>
  );
}

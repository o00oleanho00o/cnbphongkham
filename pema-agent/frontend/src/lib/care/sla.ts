// "Còn 24 phút" / "Quá hạn 5 phút" for the SLA of a handoff. Pure: `now` is passed in, so the screens tick it
// with `useNow` and the tests need no fake clock. The SLA itself is the backend's; this only words it.
import { useEffect, useState } from "react";

const MINUTE_MS = 60_000;

export type SlaState = { text: string; overdue: boolean; soon: boolean };

/** `soon`: five minutes or less are left (the screen turns the label amber). */
export function slaState(dueIso: string | null | undefined, now: Date): SlaState | null {
  if (!dueIso) return null;
  const due = new Date(dueIso).getTime();
  if (Number.isNaN(due)) return null;
  const diffMin = Math.ceil((due - now.getTime()) / MINUTE_MS);
  if (diffMin <= 0) {
    const late = Math.max(1, -diffMin);
    return { text: `Quá hạn ${late} phút`, overdue: true, soon: false };
  }
  if (diffMin < 60) return { text: `Còn ${diffMin} phút`, overdue: false, soon: diffMin <= 5 };
  const hours = Math.floor(diffMin / 60);
  const minutes = diffMin % 60;
  return {
    text: minutes === 0 ? `Còn ${hours} giờ` : `Còn ${hours} giờ ${minutes} phút`,
    overdue: false,
    soon: false,
  };
}

/** "6 phút trước", "2 giờ trước", "3 ngày trước". */
export function ageText(iso: string, now: Date): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "-";
  const minutes = Math.max(0, Math.floor((now.getTime() - then) / MINUTE_MS));
  if (minutes < 1) return "Vừa xong";
  if (minutes < 60) return `${minutes} phút trước`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} giờ trước`;
  return `${Math.floor(hours / 24)} ngày trước`;
}

/** The current time, refreshed every `everyMs` while mounted; the timer is cleared on unmount. */
export function useNow(everyMs = 30_000): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), everyMs);
    return () => clearInterval(timer);
  }, [everyMs]);
  return now;
}

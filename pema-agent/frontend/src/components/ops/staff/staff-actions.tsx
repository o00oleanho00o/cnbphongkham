"use client";

// The row buttons of the staff screen, shared by the table (desktop) and the card (phone). Which buttons exist
// is decided by `rowActions` (staff-view.ts): nothing for the manager, and nothing destructive on your own
// account. Hiding is a convenience; the backend refuses the call anyway.
import type { ReactNode } from "react";

import type { RowActions } from "@/lib/ops/staff-view";

function ActionButton({
  children,
  onClick,
  tone = "normal",
  label,
}: {
  children: ReactNode;
  onClick: () => void;
  tone?: "normal" | "danger";
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className={`inline-flex min-h-11 items-center justify-center rounded-lg border px-3 text-[13px] font-medium whitespace-nowrap transition-colors lg:min-h-9 ${
        tone === "danger"
          ? "border-red-200 bg-surface text-red-700 hover:bg-red-50 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/40"
          : "border-line bg-surface text-ink hover:bg-tile"
      }`}
    >
      {children}
    </button>
  );
}

export function StaffActions({
  name,
  active,
  actions,
  onEdit,
  onResetPassword,
  onToggleLock,
}: {
  name: string;
  active: boolean;
  actions: RowActions;
  onEdit: () => void;
  onResetPassword: () => void;
  onToggleLock: () => void;
}) {
  if (!actions.edit && !actions.resetPassword && !actions.toggleLock) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {actions.edit && (
        <ActionButton label={`Sửa ${name}`} onClick={onEdit}>
          Sửa
        </ActionButton>
      )}
      {actions.resetPassword && (
        <ActionButton label={`Đặt lại mật khẩu của ${name}`} onClick={onResetPassword}>
          Đặt lại mật khẩu
        </ActionButton>
      )}
      {actions.toggleLock && (
        <ActionButton
          label={`${active ? "Khóa" : "Mở khóa"} tài khoản của ${name}`}
          onClick={onToggleLock}
          tone={active ? "danger" : "normal"}
        >
          {active ? "Khóa" : "Mở khóa"}
        </ActionButton>
      )}
    </div>
  );
}

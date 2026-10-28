/** Pieces the pages share that the dashboard's kit does not have: a drawer, a dialog, the account list. */
import { type ReactNode, useCallback, useEffect, useState } from "react";

import { messageOf, zalo } from "./client";
import { CHANNEL_LABEL } from "./logic";
import { ui } from "./sdk";
import type { Account } from "./types";

function useEscape(onClose: () => void) {
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [onClose]);
}

export function Drawer({
  title,
  onClose,
  footer,
  children,
}: {
  title: string;
  onClose: () => void;
  footer: ReactNode;
  children: ReactNode;
}) {
  useEscape(onClose);
  return (
    <div
      className="fixed inset-0 z-50 flex justify-end bg-ink/25"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div role="dialog" aria-modal="true" aria-label={title} className="flex h-full w-full max-w-md flex-col border-l border-line bg-surface">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <h2 className="min-w-0 text-section font-bold break-words text-heading">{title}</h2>
          <ui.Button variant="secondary" onClick={onClose}>
            Đóng
          </ui.Button>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">{children}</div>
        <div className="border-t border-line px-5 py-4">{footer}</div>
      </div>
    </div>
  );
}

export function Dialog({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEscape(onClose);
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-ink/25 p-4"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="max-h-[85dvh] w-full max-w-sm overflow-y-auto rounded-card border border-line bg-surface p-6 text-center shadow-card"
      >
        <h2 className="mb-1 text-section font-bold break-words text-heading">{title}</h2>
        {children}
      </div>
    </div>
  );
}

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-3 rounded-tile border border-line p-4">
      <p className="text-micro font-semibold tracking-wider text-ink-soft uppercase">{title}</p>
      {children}
    </div>
  );
}

export function Switch({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span>
        <span className="block text-small font-medium text-ink">{label}</span>
        {hint && <span className="block text-label text-ink-soft">{hint}</span>}
      </span>
      <ui.Toggle checked={checked} label={label} onChange={onChange} />
    </div>
  );
}

export function useAccounts() {
  const [accounts, setAccounts] = useState<Account[] | null>(null);
  const [error, setError] = useState("");
  const reload = useCallback(async () => {
    try {
      setAccounts(await zalo.accounts());
      setError("");
    } catch (err) {
      setError(messageOf(err));
    }
  }, []);
  useEffect(() => {
    void reload();
  }, [reload]);
  return { accounts, error, reload };
}

export function AccountPicker({
  accounts,
  value,
  onChange,
  all,
}: {
  accounts: readonly Account[];
  value: string;
  onChange: (id: string) => void;
  all?: string;
}) {
  const options = accounts.map((a) => ({ value: a.id, label: `${a.label} (${CHANNEL_LABEL[a.channel]})` }));
  return (
    <ui.Select
      aria-label="Tài khoản"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      options={all === undefined ? options : [{ value: "", label: all }, ...options]}
    />
  );
}

"use client";

// Modal for the whole app: a centred dialog, or a bottom sheet on a phone (`Sheet`). Backdrop rule of the
// ported dashboard (`useChotNen`: close only when press AND release both land on the backdrop, so dragging
// a text selection out of a textarea never closes the form). Escape closes, Tab stays inside, focus goes
// into the dialog on open and back to the opener on close.
import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";

import { IconClose } from "@/components/admin/shared/dashboard-icons";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";

import { cx } from "./classnames";

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

/** Where Tab goes from `active` inside the panel, or null to let the browser decide. */
export function wrapFocusTarget(
  focusables: readonly HTMLElement[],
  active: Element | null,
  backwards: boolean,
): HTMLElement | null {
  const first = focusables[0];
  const last = focusables[focusables.length - 1];
  if (first === undefined || last === undefined) return null;
  const inside = focusables.some((el) => el === active);
  if (backwards && (active === first || !inside)) return last;
  if (!backwards && (active === last || !inside)) return first;
  return null;
}

type Placement = "center" | "sheet";

type ModalProps = {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
  /** Two panes side by side (the quick order: product list and order content): 1040px from `sm`. */
  xwide?: boolean;
};

function Modal({
  placement,
  title,
  subtitle,
  onClose,
  children,
  footer,
  wide = false,
  xwide = false,
}: ModalProps & { placement: Placement }) {
  const titleId = useId();
  const backdrop = useChotNen(onClose);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const opener = document.activeElement;
    panelRef.current?.focus();
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      if (opener instanceof HTMLElement) opener.focus();
    };
  }, [onClose]);

  function trapTab(e: KeyboardEvent<HTMLDivElement>): void {
    if (e.key !== "Tab" || panelRef.current === null) return;
    const focusables = [...panelRef.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const target = wrapFocusTarget(focusables, document.activeElement, e.shiftKey);
    if (target === null) return;
    e.preventDefault();
    target.focus();
  }

  const sheet = placement === "sheet";
  return (
    <div
      className={cx(
        "fixed inset-0 z-(--z-modal) flex justify-center bg-overlay backdrop-blur-[2px]",
        sheet ? "items-end sm:items-center sm:p-4" : "items-center p-4",
      )}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      {...backdrop}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        onKeyDown={trapTab}
        className={cx(
          "flex max-h-[92dvh] w-full flex-col bg-surface shadow-pop outline-none",
          sheet ? "rounded-t-modal sm:rounded-modal" : "rounded-modal",
          xwide ? "sm:max-w-[1040px]" : wide ? "sm:max-w-2xl" : "sm:max-w-lg",
        )}
      >
        <div className="flex items-start justify-between gap-3 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="text-[16px] font-semibold text-ink">
              {title}
            </h2>
            {subtitle !== undefined && <p className="mt-0.5 text-body text-ink-soft">{subtitle}</p>}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng"
            className="-mr-2 rounded-lg p-2 text-ink-soft hover:bg-tile hover:text-ink"
          >
            <IconClose size={18} />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer !== undefined && (
          <div className="flex flex-col-reverse gap-2 border-t border-line px-5 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:flex-row sm:justify-end">
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}

/** Centred dialog at every width. */
export function Dialog(props: ModalProps) {
  return <Modal placement="center" {...props} />;
}

/** Bottom sheet on a phone, centred dialog from `sm` up (forms opened from lists). */
export function Sheet(props: ModalProps) {
  return <Modal placement="sheet" {...props} />;
}

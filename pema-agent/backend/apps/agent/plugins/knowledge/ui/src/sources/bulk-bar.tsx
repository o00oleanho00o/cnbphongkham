/** The bar that shows when rows are picked: approve, unapprove, set the audience, re-read, delete. */
import { useState } from "react";

import { ConfirmDialog } from "../parts";
import { ui } from "../sdk";
import type { Source } from "../types";
import { type BulkKind, deleteText } from "./sources-logic";
import { APPROVAL_STEP, AUDIENCE_SPLIT } from "../logic";

export function BulkBar({
  picked,
  busy,
  onRun,
  onClear,
}: {
  picked: readonly Source[];
  busy: boolean;
  onRun: (kind: BulkKind) => void;
  onClear: () => void;
}) {
  const [confirming, setConfirming] = useState(false);
  const run = (kind: BulkKind) => () => onRun(kind);

  return (
    <div
      role="region"
      aria-label="Thao tác với các nguồn đã chọn"
      className="sticky bottom-3 z-10 mb-4 flex flex-wrap items-center gap-2 rounded-card border border-line bg-surface p-3 shadow-card"
    >
      <span className="mr-2 text-small font-semibold text-ink">Đã chọn {picked.length}</span>
      {APPROVAL_STEP && (
        <>
          <ui.Button variant="secondary" disabled={busy} onClick={run("approve")}>
            Duyệt
          </ui.Button>
          <ui.Button variant="secondary" disabled={busy} onClick={run("unapprove")}>
            Bỏ duyệt
          </ui.Button>
        </>
      )}
      {AUDIENCE_SPLIT && (
        <>
          <ui.Button variant="secondary" disabled={busy} onClick={run("audience-patient")}>
            Đặt: Bệnh nhân
          </ui.Button>
          <ui.Button variant="secondary" disabled={busy} onClick={run("audience-staff")}>
            Đặt: Nội bộ
          </ui.Button>
        </>
      )}
      <ui.Button variant="secondary" disabled={busy} onClick={run("reindex")}>
        Nạp lại
      </ui.Button>
      <ui.Button variant="danger" disabled={busy} onClick={() => setConfirming(true)}>
        Xóa
      </ui.Button>
      <ui.Button variant="ghost" onClick={onClear}>
        Bỏ chọn
      </ui.Button>
      {confirming && (
        <ConfirmDialog
          title={`Xóa ${picked.length} nguồn?`}
          onClose={() => setConfirming(false)}
          actions={
            <>
              <ui.Button variant="secondary" onClick={() => setConfirming(false)}>
                Hủy
              </ui.Button>
              <ui.Button
                variant="danger"
                onClick={() => {
                  setConfirming(false);
                  onRun("delete");
                }}
              >
                Xóa
              </ui.Button>
            </>
          }
        >
          {deleteText(picked)}
        </ConfirmDialog>
      )}
    </div>
  );
}

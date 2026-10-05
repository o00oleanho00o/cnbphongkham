"use client";

// The three questions the old finance page asked with the browser's `prompt()` and `confirm()`, now kit dialogs:
// why an entry is cancelled ("Lý do hủy lượt chưa thu tiền"), whether to close a month (its entries are locked) and
// the voucher of the payout ("Mã chứng từ chi"). The BE has the last word: its sentence is shown in the dialog and
// nothing closes until it says yes.
import { useId, useState, type FormEvent, type ReactNode } from "react";

import { Notice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import { closeQuestion, financeErrorMessage } from "@/lib/finance/finance-view";
import { Button } from "@/ui/button";
import { Dialog } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Tone = "primary" | "danger-solid";

function ActionDialog({
  title,
  subtitle,
  confirmLabel,
  tone = "primary",
  busy,
  error,
  disabled = false,
  onSubmit,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  confirmLabel: string;
  tone?: Tone;
  busy: boolean;
  error: string;
  disabled?: boolean;
  onSubmit: () => void;
  onClose: () => void;
  children?: ReactNode;
}) {
  const formId = useId();
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }
  return (
    <Dialog
      title={title}
      subtitle={subtitle}
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Đóng
          </Button>
          <Button variant={tone} type="submit" form={formId} disabled={busy || disabled}>
            {busy ? "Đang xử lý..." : confirmLabel}
          </Button>
        </>
      }
    >
      <form id={formId} onSubmit={submit}>
        {children}
        {error !== "" && (
          <div className="mt-2">
            <Notice tone="error">{error}</Notice>
          </div>
        )}
      </form>
    </Dialog>
  );
}

/** Runs one mutation: busy while it runs, the BE sentence on a refusal, `onDone` when it said yes. */
function useAction(run: () => Promise<unknown>, onDone: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    setError("");
    setBusy(true);
    try {
      await run();
      onDone();
    } catch (err) {
      setError(financeErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, setError, submit };
}

/** "Hủy": the reason is required; the BE refuses an entry whose invoice has money received. */
export function VoidEntryDialog({
  entryId,
  label,
  onClose,
  onDone,
}: {
  entryId: string;
  /** which entry, for the subtitle: "Tái khám & đánh giá · P001" */
  label: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reason, setReason] = useState("");
  const action = useAction(
    () =>
      unwrap(
        http.POST("/api/v1/finance/entries/{entry_id}/void", {
          params: { path: { entry_id: entryId } },
          body: { reason },
        }),
      ),
    onDone,
  );
  return (
    <ActionDialog
      title="Hủy lượt thủ thuật"
      subtitle={label}
      confirmLabel="Hủy lượt"
      tone="danger-solid"
      busy={action.busy}
      error={action.error}
      disabled={reason.trim() === ""}
      onSubmit={() => void action.submit()}
      onClose={onClose}
    >
      <Field label="Lý do hủy lượt chưa thu tiền" required>
        {(control) => (
          <input
            {...control}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className={FIELD_CONTROL_CLASS}
            autoComplete="off"
          />
        )}
      </Field>
    </ActionDialog>
  );
}

/** "Chốt tháng đã kết thúc": the question of the old `confirm()`. */
export function ClosePeriodDialog({
  month,
  onClose,
  onDone,
}: {
  month: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const action = useAction(
    () =>
      unwrap(http.POST("/api/v1/finance/periods/{month}/close", { params: { path: { month } } })),
    onDone,
  );
  return (
    <ActionDialog
      title={`Chốt tháng ${month}`}
      confirmLabel="Chốt tháng"
      busy={action.busy}
      error={action.error}
      onSubmit={() => void action.submit()}
      onClose={onClose}
    >
      <p className="text-body text-ink">{closeQuestion(month)}</p>
    </ActionDialog>
  );
}

/** "Xác nhận đã chi": the voucher of the payout. It moves no money; it records that the fees were paid out. */
export function PayPeriodDialog({
  month,
  onClose,
  onDone,
}: {
  month: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [reference, setReference] = useState("");
  const action = useAction(
    () =>
      unwrap(
        http.POST("/api/v1/finance/periods/{month}/pay", {
          params: { path: { month } },
          body: { reference },
        }),
      ),
    onDone,
  );
  return (
    <ActionDialog
      title="Xác nhận đã chi"
      subtitle={`Kỳ ${month}`}
      confirmLabel="Xác nhận đã chi"
      busy={action.busy}
      error={action.error}
      disabled={reference.trim() === ""}
      onSubmit={() => void action.submit()}
      onClose={onClose}
    >
      <Field label="Mã chứng từ chi" required>
        {(control) => (
          <input
            {...control}
            value={reference}
            onChange={(e) => setReference(e.target.value)}
            className={FIELD_CONTROL_CLASS}
            autoComplete="off"
          />
        )}
      </Field>
    </ActionDialog>
  );
}

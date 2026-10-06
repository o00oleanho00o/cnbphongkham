"use client";

// "Thu tiền": the receipt of an invoice, shared by the cashier ("Hóa đơn & thanh toán", a dialog) and by
// `/finance/payments` ("Thu tiền khách hàng", the form under the invoice select). Rules the BE keeps and this form
// helps with: a receipt carries an idempotency key (one per attempt: a retry after a lost answer reuses it and gets the
// first receipt back, the key is renewed after a success and whenever the invoice changes, like `paymentKey` of the
// old page), and an amount over the open balance is refused ("Số thu vượt công nợ").
import { useState, type FormEvent } from "react";

import { Notice, PrimaryButton } from "@/components/ops/ops-ui";
import { Dialog } from "@/ui/dialog";
import { http, newIdempotencyKey, unwrap } from "@/lib/api/client";
import {
  METHODS,
  METHOD_LABEL,
  PAYMENT_PROBLEM,
  asMethod,
  dueLine,
  financeErrorMessage,
  paymentAmount,
  type InvoiceRow,
  type PaymentMethod,
  type PaymentRow,
} from "@/lib/finance/finance-view";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

/**
 * Amount, method and the confirm button for ONE invoice. Mount it with `key={invoice.id}`: another invoice starts
 * with its own balance and its own idempotency key.
 */
export function PaymentFields({
  invoice,
  amountLabel,
  submitLabel,
  onPaid,
}: {
  invoice: InvoiceRow;
  amountLabel: string;
  submitLabel: string;
  onPaid: (receipt: PaymentRow) => void;
}) {
  const [amount, setAmount] = useState(String(invoice.due_vnd));
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [key, setKey] = useState(newIdempotencyKey);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const value = paymentAmount(amount);
    if (value === null) {
      setProblem(PAYMENT_PROBLEM);
      return;
    }
    setProblem("");
    setBusy(true);
    try {
      const receipt = await unwrap(
        http.POST("/api/v1/finance/payments", {
          body: { id: key, invoice_id: invoice.id, amount_vnd: value, method },
        }),
      );
      setKey(newIdempotencyKey());
      onPaid(receipt);
    } catch (error) {
      setProblem(financeErrorMessage(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} noValidate>
      <div className="grid grid-cols-1 gap-x-4 sm:grid-cols-2">
        <Field label={amountLabel} required>
          {(control) => (
            <input
              {...control}
              type="number"
              min={1}
              step={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Phương thức">
          {(control) => (
            <select
              {...control}
              value={method}
              onChange={(e) => setMethod(asMethod(e.target.value))}
              className={FIELD_CONTROL_CLASS}
            >
              {METHODS.map((option) => (
                <option key={option} value={option}>
                  {METHOD_LABEL[option]}
                </option>
              ))}
            </select>
          )}
        </Field>
      </div>
      <PrimaryButton type="submit" disabled={busy}>
        {busy ? "Đang ghi..." : submitLabel}
      </PrimaryButton>
      {problem !== "" && (
        <div className="mt-3">
          <Notice tone="error">{problem}</Notice>
        </div>
      )}
    </form>
  );
}

/** The dialog of the cashier: "Thu tiền · <patient>", the balance, the two fields and "Xác nhận thu tiền". */
export function PaymentDialog({
  invoice,
  onClose,
  onPaid,
}: {
  invoice: InvoiceRow;
  onClose: () => void;
  onPaid: (receipt: PaymentRow) => void;
}) {
  return (
    <Dialog title={`Thu tiền · ${invoice.patient_name}`} onClose={onClose}>
      <div className="mb-4">
        <Notice>{dueLine(invoice)}</Notice>
      </div>
      <PaymentFields
        key={invoice.id}
        invoice={invoice}
        amountLabel="Số tiền (VND)"
        submitLabel="Xác nhận thu tiền"
        onPaid={onPaid}
      />
    </Dialog>
  );
}

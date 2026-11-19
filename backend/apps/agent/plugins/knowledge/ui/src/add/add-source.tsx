import { useState } from "react";

import { ConfirmDialog, Sheet } from "../parts";
import { ui } from "../sdk";
import type { ConfirmResult } from "../types";
import { ChooseStep } from "./choose-step";
import { InfoStep } from "./info-step";
import { PreviewStep } from "./preview-step";
import { type Step, useAddFlow } from "./use-add-flow";

const STEPS: readonly { id: Step; label: string }[] = [
  { id: 1, label: "Chọn cách thêm" },
  { id: 2, label: "Thông tin" },
  { id: 3, label: "Xem trước" },
];

function Steps({ step }: { step: Step }) {
  return (
    <ol className="flex flex-wrap gap-x-4 gap-y-1 text-label">
      {STEPS.map((item) => (
        <li
          key={item.id}
          aria-current={item.id === step ? "step" : undefined}
          className={item.id === step ? "font-bold text-link" : "text-ink-soft"}
        >
          {item.id}. {item.label}
        </li>
      ))}
    </ol>
  );
}

function Outcome({ result }: { result: ConfirmResult }) {
  return (
    <div className="space-y-3">
      <ui.Notice tone={result.created.length > 0 ? "success" : "warning"}>
        Đã đưa {result.created.length} nguồn vào hàng đợi nạp; bảng Nguồn sẽ cho thấy tiến độ.
      </ui.Notice>
      {result.skipped.length > 0 && (
        <ui.Notice tone="warning">
          <span className="block font-semibold">{result.skipped.length} tệp không được nạp:</span>
          <ul className="list-disc pl-5">
            {result.skipped.map((skip) => (
              <li key={skip.key}>{skip.reason}</li>
            ))}
          </ul>
        </ui.Notice>
      )}
    </div>
  );
}

/** The three-step flow that adds sources. `initial` fills the "type text" way (a question with no document). */
export function AddSourceSheet({
  onClose,
  onAdded,
  initial,
}: {
  onClose: () => void;
  onAdded: (count: number) => void;
  initial?: { title: string; text: string };
}) {
  const flow = useAddFlow(initial);
  const [asking, setAsking] = useState(false);
  const busy = flow.progress !== "";
  const { result } = flow;

  const finish = () => {
    onAdded(result?.created.length ?? 0);
    onClose();
  };
  const requestClose = () => {
    if (asking || flow.patientAsk || busy) return;
    if (result) {
      finish();
      return;
    }
    if (flow.dirty) {
      setAsking(true);
      return;
    }
    onClose();
  };
  /** Closes at once when nothing was left out; otherwise shows why first (the sheet's last screen). */
  const submit = async () => {
    const done = await flow.confirm();
    if (done.skipped.length > 0) return;
    onAdded(done.created.length);
    onClose();
  };
  const back = () => {
    if (flow.step === 1) requestClose();
    else flow.setStep(flow.step === 3 ? 2 : 1);
  };

  const footer = (
    <div className="space-y-2">
      {flow.progress && <p role="status" className="text-small text-ink-soft">{flow.progress}</p>}
      {flow.error && <p role="alert" className="text-small text-danger">{flow.error}</p>}
      <div className="flex flex-wrap items-center justify-between gap-2">
        {result ? (
          <span />
        ) : (
          <ui.Button variant="secondary" disabled={busy} onClick={back}>
            {flow.step === 1 ? "Hủy" : "Quay lại"}
          </ui.Button>
        )}
        {!result && flow.step === 1 && (
          <ui.Button busy={busy} disabled={!flow.canLeaveChoose} onClick={flow.toInfo}>
            Tiếp tục
          </ui.Button>
        )}
        {!result && flow.step === 2 && (
          <ui.Button disabled={!flow.canLeaveInfo} onClick={flow.toPreview}>
            Xem trước
          </ui.Button>
        )}
        {!result && flow.step === 3 && (
          <ui.Button busy={busy} disabled={flow.summary.sources === 0} onClick={submit}>
            Nạp {flow.summary.sources} nguồn
          </ui.Button>
        )}
        {result && <ui.Button onClick={finish}>Xong</ui.Button>}
      </div>
    </div>
  );

  return (
    <Sheet title="Thêm nguồn" onClose={requestClose} wide footer={footer}>
      <Steps step={flow.step} />
      {result && <Outcome result={result} />}
      {!result && flow.step === 1 && <ChooseStep flow={flow} />}
      {!result && flow.step === 2 && <InfoStep flow={flow} />}
      {!result && flow.step === 3 && <PreviewStep flow={flow} />}
      {asking && (
        <ConfirmDialog
          title="Bỏ những gì đã nhập?"
          onClose={() => setAsking(false)}
          actions={
            <>
              <ui.Button variant="secondary" onClick={() => setAsking(false)}>
                Tiếp tục chỉnh
              </ui.Button>
              <ui.Button variant="danger" onClick={onClose}>
                Đóng và bỏ
              </ui.Button>
            </>
          }
        >
          Các tệp đã chọn và thông tin đã sửa sẽ mất, chưa có gì được nạp.
        </ConfirmDialog>
      )}
    </Sheet>
  );
}

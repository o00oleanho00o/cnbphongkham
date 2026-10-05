"use client";

// "Tiền sử & chẩn đoán" card of the Tư vấn tab (old web: `crm-ui.js` `clinical()`, screens WC5, WC6, WC31). A doctor
// types the history and the finding; nothing here is suggested or filled in by a model ("Bác sĩ ghi nhận, không
// dùng AI tự chẩn đoán"). Both texts are required. Without `session.write` the card only shows what was recorded.
import { useCallback, useState, type FormEvent } from "react";

import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { FormError, Muted, TEXTAREA_CLASS } from "@/components/ops/patient/shared";
import { useToast } from "@/components/ops/toast";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { formatDateTime } from "@/lib/ops/format";
import { CLINICAL_NOTE_BLANK } from "@/lib/ops/patient-profile";
import { useLoad } from "@/lib/use-load";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Field } from "@/ui/field";

export function ClinicalNoteCard({
  patientId,
  canWrite,
  onChanged,
}: {
  patientId: string;
  canWrite: boolean;
  onChanged: () => void;
}) {
  const toast = useToast();
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/patients/{patient_id}/clinical-note", {
          params: { path: { patient_id: patientId } },
          signal,
        }),
      ),
    [patientId],
  );
  const { data, error, loading, reload } = useLoad(load);
  const [edited, setEdited] = useState<{ history?: string; diagnosis?: string }>({});
  const [problem, setProblem] = useState("");
  const [busy, setBusy] = useState(false);
  const history = edited.history ?? data?.history ?? "";
  const diagnosis = edited.diagnosis ?? data?.diagnosis ?? "";

  async function save(e: FormEvent) {
    e.preventDefault();
    if (history.trim() === "" || diagnosis.trim() === "") {
      setProblem(CLINICAL_NOTE_BLANK);
      return;
    }
    setBusy(true);
    setProblem("");
    try {
      await unwrap(
        http.PUT("/api/v1/patients/{patient_id}/clinical-note", {
          params: { path: { patient_id: patientId } },
          body: { history: history.trim(), diagnosis: diagnosis.trim() },
        }),
      );
      setEdited({});
      toast.push("success", "Đã lưu nhận định có bác sĩ xác nhận");
      reload();
      onChanged();
    } catch (err) {
      setProblem(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Tiền sử & chẩn đoán" subtitle="Bác sĩ ghi nhận, không dùng AI tự chẩn đoán">
      {error !== "" && <RetryNotice message={error} onRetry={reload} />}
      {loading && data === undefined && <ListSkeleton rows={2} />}
      {data !== undefined && (
        <form onSubmit={(e) => void save(e)} noValidate>
          <div className="grid grid-cols-1 gap-x-4 md:grid-cols-2">
            <Field label="Tiền sử đã khai thác" required>
              {(control) => (
                <textarea
                  {...control}
                  value={history}
                  readOnly={!canWrite}
                  maxLength={4000}
                  onChange={(e) =>
                    setEdited((current) => ({ ...current, history: e.target.value }))
                  }
                  className={TEXTAREA_CLASS}
                />
              )}
            </Field>
            <Field label="Khám / chẩn đoán do bác sĩ xác nhận" required>
              {(control) => (
                <textarea
                  {...control}
                  value={diagnosis}
                  readOnly={!canWrite}
                  maxLength={4000}
                  onChange={(e) =>
                    setEdited((current) => ({ ...current, diagnosis: e.target.value }))
                  }
                  className={TEXTAREA_CLASS}
                />
              )}
            </Field>
          </div>
          {data.reviewed_at !== null && data.reviewed_at !== undefined && (
            <Muted>
              Ghi nhận {formatDateTime(data.reviewed_at)}
              {data.reviewed_by_name ? ` · ${data.reviewed_by_name}` : ""}
            </Muted>
          )}
          {canWrite && (
            <div className="mt-3">
              <Button variant="secondary" type="submit" disabled={busy}>
                Bác sĩ lưu nhận định
              </Button>
            </div>
          )}
          <FormError message={problem} />
        </form>
      )}
    </Card>
  );
}

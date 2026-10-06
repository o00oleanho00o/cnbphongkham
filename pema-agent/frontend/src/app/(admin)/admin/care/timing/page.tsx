"use client";

// SLA và khung giờ: bao lâu một người được hỏi phải trả lời trước khi chuyển người kế tiếp, chuỗi dài tối đa bao nhiêu,
// ngoài giờ thì từ độ sâu nào đi thẳng tới số trực. Khung giờ gửi tin nằm ở cài đặt kênh, trang này chỉ hiển thị.
import Link from "next/link";
import { useCallback, useId, useState } from "react";

import { SectionCard } from "@/components/admin/shared/ui-bits";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { ApprovalBadge, NoAccess } from "@/components/care/care-ui";
import { Field, ListSkeleton, Notice, PrimaryButton, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { errorMessage } from "@/lib/api/client";
import { careApi } from "@/lib/care/care-api";
import type { CareDepth, CareTiming } from "@/lib/care/care-types";
import { DEPTHS } from "@/lib/care/care-types";
import { parseBounded } from "@/lib/care/forms";
import { DEPTH_LABEL } from "@/lib/care/labels";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

const DEPTH_OPTIONS: SelectOption[] = DEPTHS.map((d) => ({ value: d, label: DEPTH_LABEL[d] }));

export default function CareTimingPage() {
  const { can } = useSession();
  if (!can("care.admin")) return <NoAccess what="chỉnh SLA và khung giờ" />;
  return <TimingContent />;
}

function TimingContent() {
  const load = useCallback((signal: AbortSignal) => careApi.timing(signal), []);
  const { data, error, loading, reload } = useLoad(load);
  return (
    <div>
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={2} />}
      {data && <TimingForm key={data.version} timing={data} onSaved={reload} />}
    </div>
  );
}

function TimingForm({ timing, onSaved }: { timing: CareTiming; onSaved: () => void }) {
  const toast = useToast();
  const baseId = useId();
  const [urgent, setUrgent] = useState(String(timing.sla_urgent_minutes));
  const [normal, setNormal] = useState(String(timing.sla_normal_minutes));
  const [chain, setChain] = useState(String(timing.max_candidates));
  const [direct, setDirect] = useState<CareDepth>(timing.oncall_direct_from_depth);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const urgentValue = parseBounded(urgent, 1, 240);
  const normalValue = parseBounded(normal, 1, 1440);
  const chainValue = parseBounded(chain, 2, 10);
  const problem =
    urgentValue === null || normalValue === null || chainValue === null
      ? "SLA khẩn từ 1 đến 240 phút, SLA thường từ 1 đến 1440 phút, chuỗi từ 2 đến 10 người."
      : "";

  async function save() {
    if (urgentValue === null || normalValue === null || chainValue === null) return;
    setBusy(true);
    setError("");
    try {
      await careApi.saveTiming({
        sla_urgent_minutes: Math.round(urgentValue),
        sla_normal_minutes: Math.round(normalValue),
        max_candidates: Math.round(chainValue),
        oncall_direct_from_depth: direct,
        version: timing.version,
      });
      toast.push("success", "Đã lưu. Các số này quay lại trạng thái chờ bác sĩ duyệt.");
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <ApprovalBadge pending={timing.pending_doctor_approval} />
      <form
        className="space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          void save();
        }}
      >
        <SectionCard
          title="Thời hạn trả lời (SLA)"
          subtitle="Quá hạn thì yêu cầu chuyển cho người kế tiếp trong chuỗi"
        >
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Khẩn (phút)" htmlFor={`${baseId}-u`}>
              <input
                id={`${baseId}-u`}
                inputMode="numeric"
                className={cx(FIELD_BASE_CLASS, "w-28")}
                disabled={!timing.can_edit}
                value={urgent}
                onChange={(e) => setUrgent(e.target.value)}
              />
            </Field>
            <Field label="Thường (phút)" htmlFor={`${baseId}-n`}>
              <input
                id={`${baseId}-n`}
                inputMode="numeric"
                className={cx(FIELD_BASE_CLASS, "w-28")}
                disabled={!timing.can_edit}
                value={normal}
                onChange={(e) => setNormal(e.target.value)}
              />
            </Field>
            <Field
              label="Chuỗi tối đa (người)"
              htmlFor={`${baseId}-c`}
              hint="Tính cả số trực 24/24 ở cuối"
            >
              <input
                id={`${baseId}-c`}
                inputMode="numeric"
                className={cx(FIELD_BASE_CLASS, "w-28")}
                disabled={!timing.can_edit}
                value={chain}
                onChange={(e) => setChain(e.target.value)}
              />
            </Field>
          </div>
        </SectionCard>

        <SectionCard
          title="Ngoài giờ làm việc"
          subtitle="Yêu cầu từ độ sâu này trở lên đi thẳng tới số trực; nhẹ hơn thì chờ đầu ca kế tiếp"
        >
          <div className="sm:w-72">
            <SelectMenu
              ariaLabel="Đi thẳng tới số trực từ độ sâu"
              size="md"
              value={direct}
              options={DEPTH_OPTIONS}
              disabled={!timing.can_edit}
              onChange={(v) => setDirect(v as CareDepth)}
            />
          </div>
        </SectionCard>

        <SectionCard
          title="Khung giờ gửi tin"
          subtitle="Agent chỉ gửi tin trong khung giờ này; tin ngoài khung được xếp hàng tới giờ mở"
        >
          <p className="text-body-lg font-semibold text-ink">
            {timing.send_window_start && timing.send_window_end
              ? `${timing.send_window_start} đến ${timing.send_window_end}`
              : "Mặc định của phòng khám"}
          </p>
          <p className="mt-1 text-label text-ink-soft">
            Múi giờ {timing.time_zone}. Khung giờ chỉnh ở{" "}
            <Link href="/admin/accounts" className="text-brand-500 underline">
              cài đặt kênh Zalo
            </Link>
            .
          </p>
        </SectionCard>

        {problem && <Notice tone="warn">{problem}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}
        {timing.can_edit && (
          <PrimaryButton type="submit" disabled={busy || problem !== ""}>
            Lưu
          </PrimaryButton>
        )}
      </form>
    </div>
  );
}

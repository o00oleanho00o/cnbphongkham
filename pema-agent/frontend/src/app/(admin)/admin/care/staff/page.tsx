"use client";

// Hồ sơ kỹ năng và ca trực của nhân viên: dữ liệu mà định tuyến dùng để chọn người nhận yêu cầu của agent.
import { useCallback, useState } from "react";

import { Badge } from "@/components/admin/shared/ui-bits";
import { NoAccess } from "@/components/care/care-ui";
import { StaffSheet } from "@/components/care/staff-sheet";
import { EmptyState, ListSkeleton, RetryNotice, SecondaryButton } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { careApi } from "@/lib/care/care-api";
import type { Shift, StaffCareProfile } from "@/lib/care/care-types";
import { WEEKDAYS } from "@/lib/care/care-types";
import { WEEKDAY_LABEL, skillLabel } from "@/lib/care/labels";
import { ROLE_LABEL, useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

const DAY_SHORT: Record<(typeof WEEKDAYS)[number], string> = {
  mon: "T2",
  tue: "T3",
  wed: "T4",
  thu: "T5",
  fri: "T6",
  sat: "T7",
  sun: "CN",
};

function shiftSummary(shift: Shift): string {
  const parts = WEEKDAYS.filter((d) => shift[d].length > 0).map(
    (d) => `${DAY_SHORT[d]} ${shift[d].map((i) => `${i.start}-${i.end}`).join(", ")}`,
  );
  return parts.length === 0 ? "Chưa có ca" : parts.join(" · ");
}

export default function CareStaffPage() {
  const { can } = useSession();
  if (!can("care.admin")) return <NoAccess what="chỉnh kỹ năng và ca trực" />;
  return <StaffContent />;
}

function StaffContent() {
  const toast = useToast();
  const load = useCallback((signal: AbortSignal) => careApi.staff(signal), []);
  const { data, error, loading, reload, setData } = useLoad(load);
  const [editing, setEditing] = useState<StaffCareProfile | null>(null);

  function saved(profile: StaffCareProfile) {
    if (data) {
      setData({
        ...data,
        items: data.items.map((p) => (p.user_id === profile.user_id ? profile : p)),
      });
    }
    setEditing(null);
    toast.push("success", `Đã lưu hồ sơ của ${profile.name}.`);
  }

  return (
    <div>
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {data && data.items.length === 0 && (
        <EmptyState
          title="Chưa có hồ sơ nhân viên nào"
          hint="Hồ sơ được tạo khi nhân viên được thêm vào hệ thống."
        />
      )}
      <ul className="grid gap-3 md:grid-cols-2">
        {data?.items.map((profile) => (
          <li
            key={profile.user_id}
            className="rounded-card border border-line bg-surface p-4 shadow-card"
          >
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="text-body-lg font-semibold text-ink">{profile.name}</h2>
                <p className="text-label text-ink-soft">
                  {ROLE_LABEL[profile.role as keyof typeof ROLE_LABEL] ?? "Nhân viên"} · đang giữ{" "}
                  {profile.load}/{profile.capacity} cuộc trò chuyện
                </p>
              </div>
              <SecondaryButton onClick={() => setEditing(profile)}>Sửa</SecondaryButton>
            </div>
            <div className="mt-3 flex flex-wrap gap-1.5">
              {profile.skills.length === 0 && (
                <span className="text-small text-ink-soft">Chưa có kỹ năng</span>
              )}
              {profile.skills.map((s) => (
                <Badge key={s} tone="blue" dot={false}>
                  {skillLabel(s)}
                </Badge>
              ))}
            </div>
            <p className="mt-3 text-label leading-relaxed text-ink-soft">
              {shiftSummary(profile.shift)}
            </p>
            <span className="sr-only">{WEEKDAYS.map((d) => WEEKDAY_LABEL[d]).join(", ")}</span>
          </li>
        ))}
      </ul>

      {editing && data && (
        <StaffSheet
          key={editing.user_id}
          profile={editing}
          knownSkills={data.known_skills}
          onClose={() => setEditing(null)}
          onSaved={saved}
        />
      )}
    </div>
  );
}

"use client";

// Số trực 24/24: phần tử cuối của mọi chuỗi chuyển giao. Số nằm trong cơ sở dữ liệu, không nằm trong mã nguồn.
import { useCallback, useState } from "react";

import { Badge } from "@/components/admin/shared/ui-bits";
import { NoAccess } from "@/components/care/care-ui";
import { OnCallSheet } from "@/components/care/on-call-sheet";
import {
  EmptyState,
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
  SecondaryButton,
} from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { careApi } from "@/lib/care/care-api";
import type { OnCallContact } from "@/lib/care/care-types";
import { formatDateTime } from "@/lib/ops/format";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

export default function CareOnCallPage() {
  const { can } = useSession();
  if (!can("care.admin")) return <NoAccess what="chỉnh số trực" />;
  return <OnCallContent />;
}

type Editing = { contact: OnCallContact | null } | null;

function OnCallContent() {
  const toast = useToast();
  const load = useCallback((signal: AbortSignal) => careApi.onCall(signal), []);
  const { data, error, loading, reload } = useLoad(load);
  const [editing, setEditing] = useState<Editing>(null);

  function saved() {
    setEditing(null);
    toast.push("success", "Đã lưu số trực. Mọi agent dùng số mới ngay từ lượt sau.");
    reload();
  }

  return (
    <div className="space-y-4">
      {data && !data.chain_ends_with_on_call && (
        <Notice tone="error">
          Chưa có số trực nào đang bật. Chuỗi chuyển giao không có điểm cuối, hãy thêm số trực ngay.
        </Notice>
      )}
      <div className="flex justify-end">
        <PrimaryButton onClick={() => setEditing({ contact: null })}>Thêm số trực</PrimaryButton>
      </div>
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={2} />}
      {data && data.items.length === 0 && (
        <EmptyState
          title="Chưa có số trực"
          hint="Phòng khám cung cấp số Zalo trực 24/24; nhập ở đây."
        />
      )}
      <ul className="space-y-3">
        {data?.items.map((contact) => (
          <li key={contact.id} className="gc-card p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div className="min-w-0">
                <h2 className="text-[15px] font-semibold text-ink">{contact.owner}</h2>
                <p className="mt-0.5 text-[14px] text-ink">{contact.zalo_number}</p>
                <p className="mt-1 text-[12px] text-ink-soft">
                  Từ {formatDateTime(contact.valid_from)}
                  {contact.valid_to
                    ? ` đến ${formatDateTime(contact.valid_to)}`
                    : ", không giới hạn"}
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={contact.active ? "green" : "gray"}>
                  {contact.active ? "Đang bật" : "Đã tắt"}
                </Badge>
                {contact.is_fixture && <Badge tone="amber">Số mẫu để thử</Badge>}
                <SecondaryButton onClick={() => setEditing({ contact })}>Sửa</SecondaryButton>
              </div>
            </div>
          </li>
        ))}
      </ul>
      {editing && (
        <OnCallSheet
          key={editing.contact?.id ?? "new"}
          contact={editing.contact}
          onClose={() => setEditing(null)}
          onSaved={saved}
        />
      )}
    </div>
  );
}

"use client";

// History of the price and rate snapshots of one service (`GET /api/v1/services/{service_id}`). Each row is what a
// booking or a finance entry made under that version used; nothing here can be edited (the database refuses it).
import { useCallback } from "react";

import { ListSkeleton, RetryNotice } from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import {
  BASIS_LABEL,
  formatRate,
  formatVnd,
  serviceDetails,
  type ServiceRow,
} from "@/lib/catalog/catalog-view";
import { formatDateTime } from "@/lib/ops/format";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Dialog } from "@/ui/dialog";

export function ServiceHistoryDialog({
  service,
  onClose,
}: {
  service: ServiceRow;
  onClose: () => void;
}) {
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/services/{service_id}", {
          params: { path: { service_id: service.id } },
          signal,
        }),
      ),
    [service.id],
  );
  const { data, error, loading, reload } = useLoad(load);

  return (
    <Dialog
      title={`Lịch sử giá và điều khoản: ${service.name}`}
      subtitle="Lịch đã đặt và các lượt tiền thủ thuật giữ điều khoản của phiên bản lúc tạo."
      onClose={onClose}
      wide
    >
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}
      {data && (
        <ol className="space-y-3" aria-label="Các phiên bản điều khoản">
          {data.history.map((h) => (
            <li key={h.version_no} className="rounded-tile border border-line bg-tile/40 px-4 py-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-body font-semibold text-ink">
                  Phiên bản {h.version_no}
                  {h.version_no === data.terms_version && (
                    <span className="ml-2 align-middle">
                      <Badge tone="success">Đang áp dụng</Badge>
                    </span>
                  )}
                </span>
                <span className="text-label text-ink-soft">{formatDateTime(h.created_at)}</span>
              </div>
              <p className="mt-1 text-body text-ink">
                {formatVnd(h.price_vnd)} · {serviceDetails(h).join(" + ")}
              </p>
              {h.rate_bp != null && h.basis != null && (
                <p className="text-label text-ink-soft">
                  Tiền thủ thuật {formatRate(h.rate_bp)} · {BASIS_LABEL[h.basis]}
                </p>
              )}
            </li>
          ))}
        </ol>
      )}
    </Dialog>
  );
}

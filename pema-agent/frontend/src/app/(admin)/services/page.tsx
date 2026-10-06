"use client";

// Dịch vụ: the catalog (`GET /api/v1/services`) with the price, the minutes of treatment and of room preparation,
// the rooms a service may use and, for the owner and the manager, the commission terms; the history of every
// price and rate version; and the follow-up protocols the CRM rules read (`GET /api/v1/protocols`).
// Old web: `operations-ui.js` `services()` ("Danh mục dịch vụ" + "Chỉnh dịch vụ"), the rate form of `finance.js`,
// and the laser-co2 chain of `crm-automation.js`. Everyone who sees the schedule reads; `admin.rules` changes.
// Layout: 1 column on a phone, 2 from `sm`, 3 from 1280, 4 from 1600 (`Workspace layout="cards"`).
import { useCallback, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { IconHeart, IconPlus } from "@/components/admin/shared/dashboard-icons";
import { ProtocolSheet } from "@/components/catalog/protocol-sheet";
import { ServiceHistoryDialog } from "@/components/catalog/service-history-dialog";
import { ServiceSheet } from "@/components/catalog/service-sheet";
import {
  EmptyState,
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { http, unwrap } from "@/lib/api/client";
import {
  BASIS_LABEL,
  formatRate,
  formatVnd,
  milestonesLabel,
  serviceDetails,
  type ProtocolRow,
  type RoomRow,
  type ServiceRow,
} from "@/lib/catalog/catalog-view";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Workspace } from "@/ui/workspace";

type CatalogData = {
  services: ServiceRow[];
  protocols: ProtocolRow[];
  rooms: RoomRow[];
};

function ServiceCard({
  service,
  roomNames,
  canManage,
  onEdit,
  onHistory,
}: {
  service: ServiceRow;
  roomNames: string[];
  canManage: boolean;
  onEdit: () => void;
  onHistory: () => void;
}) {
  return (
    <Card className="flex flex-col" padded>
      <div className="flex items-center justify-between gap-2">
        <span className="text-brand-500" aria-hidden>
          <IconHeart size={20} />
        </span>
        <Badge tone={service.active ? "success" : "warning"}>
          {service.active ? "Đang dùng" : "Tạm ngưng"}
        </Badge>
      </div>
      <h2 className="mt-3 text-subtitle font-bold text-heading">{service.name}</h2>
      <p className="mt-4 text-metric font-semibold text-heading tabular-nums">
        {formatVnd(service.price_vnd)}
      </p>
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-small text-ink">
        {serviceDetails(service).map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      {service.rate_bp != null && service.basis != null && (
        <p className="mt-2 text-label text-ink-soft">
          Tiền thủ thuật {formatRate(service.rate_bp)} · {BASIS_LABEL[service.basis]}
        </p>
      )}
      <p className="mt-2 text-label text-ink-soft">
        {roomNames.length > 0 ? `Phòng: ${roomNames.join(", ")}` : "Chưa chọn phòng"}
        {service.protocol_code ? ` · Giao thức ${service.protocol_code}` : ""}
      </p>
      <p className="mt-1 text-label text-ink-soft">Phiên bản điều khoản {service.terms_version}</p>
      <div className="mt-5 flex flex-wrap gap-2 pt-1">
        {canManage && (
          <Button variant="secondary" onClick={onEdit} aria-label={`Chỉnh dịch vụ ${service.name}`}>
            Chỉnh dịch vụ
          </Button>
        )}
        <Button variant="quiet" onClick={onHistory} aria-label={`Lịch sử giá ${service.name}`}>
          Lịch sử giá
        </Button>
      </div>
    </Card>
  );
}

function ProtocolRows({
  protocols,
  canManage,
  onEdit,
}: {
  protocols: ProtocolRow[];
  canManage: boolean;
  onEdit: (p: ProtocolRow) => void;
}) {
  if (protocols.length === 0) {
    return <p className="text-small text-ink-soft">Chưa có giao thức nào.</p>;
  }
  return (
    <ul className="divide-y divide-line">
      {protocols.map((p) => (
        <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
          <div className="min-w-0">
            <p className="text-body font-semibold text-ink">
              {p.name} <span className="font-normal text-ink-soft">({p.code})</span>
            </p>
            <p className="text-small text-ink-soft">
              Mốc: {milestonesLabel(p)} ·{" "}
              {p.followup_days === null
                ? "không có đánh giá lại"
                : `đánh giá lại sau ${p.followup_days} ngày`}{" "}
              · áp dụng cho buổi trong {p.window_days} ngày
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Badge tone={p.active ? "success" : "warning"}>
              {p.active ? "Đang dùng" : "Đã tắt"}
            </Badge>
            {canManage && (
              <Button
                variant="secondary"
                onClick={() => onEdit(p)}
                aria-label={`Sửa giao thức ${p.name}`}
              >
                Sửa
              </Button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

export default function ServicesPage() {
  const { can } = useSession();
  const canManage = can("admin.rules");
  const canSeeProtocols = can("admin.rules") || can("session.write");
  const [editing, setEditing] = useState<ServiceRow | "new" | null>(null);
  const [history, setHistory] = useState<ServiceRow | null>(null);
  const [editingProtocol, setEditingProtocol] = useState<ProtocolRow | "new" | null>(null);

  const load = useCallback(
    async (signal: AbortSignal): Promise<CatalogData> => {
      const [services, protocols, resources] = await Promise.all([
        unwrap(http.GET("/api/v1/services", { signal })),
        canSeeProtocols
          ? unwrap(http.GET("/api/v1/protocols", { signal }))
          : Promise.resolve<ProtocolRow[]>([]),
        unwrap(http.GET("/api/v1/resources", { signal })),
      ]);
      return { services, protocols, rooms: resources.rooms };
    },
    [canSeeProtocols],
  );
  const { data, error, loading, reload } = useLoad(load);

  const roomName = useMemo(
    () => new Map((data?.rooms ?? []).map((room) => [room.id, room.name])),
    [data],
  );
  const closeAll = useCallback(() => {
    setEditing(null);
    setEditingProtocol(null);
  }, []);
  const saved = useCallback(() => {
    closeAll();
    reload();
  }, [closeAll, reload]);

  return (
    <div>
      <PageHeader
        title="Danh mục dịch vụ"
        subtitle="Giá và thời lượng dùng cho lịch mới. Lịch đã đặt giữ giá và thời lượng tại lúc đặt."
        aside={
          canManage ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <IconPlus size={16} />
              Thêm dịch vụ
            </PrimaryButton>
          ) : undefined
        }
      />

      {!canManage && (
        <div className="mb-4">
          <Notice>
            Bạn xem được danh mục. Sửa giá và điều khoản là quyền của chủ phòng khám và quản lý.
          </Notice>
        </div>
      )}
      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={4} />}
      {data && data.services.length === 0 && (
        <EmptyState
          title="Chưa có dịch vụ nào"
          hint={canManage ? "Thêm dịch vụ đầu tiên để dùng khi đặt lịch." : undefined}
        />
      )}

      {data && data.services.length > 0 && (
        <Workspace layout="cards" className="mb-6">
          {data.services.map((service) => (
            <ServiceCard
              key={service.id}
              service={service}
              roomNames={service.room_ids.flatMap((id) => roomName.get(id) ?? [])}
              canManage={canManage}
              onEdit={() => setEditing(service)}
              onHistory={() => setHistory(service)}
            />
          ))}
        </Workspace>
      )}

      {data && canSeeProtocols && (
        <Card
          title="Giao thức theo dõi sau thủ thuật"
          subtitle="Ngày của các việc D+1, D+3, D+7 và ngày đánh giá lại mà luật CSKH tạo cho khách sau buổi điều trị."
          aside={
            canManage ? (
              <Button variant="secondary" onClick={() => setEditingProtocol("new")}>
                <IconPlus size={16} />
                Thêm giao thức
              </Button>
            ) : undefined
          }
        >
          <ProtocolRows
            protocols={data.protocols}
            canManage={canManage}
            onEdit={setEditingProtocol}
          />
        </Card>
      )}

      {data && editing !== null && (
        <ServiceSheet
          service={editing === "new" ? null : editing}
          rooms={data.rooms}
          protocols={data.protocols}
          withRate={canManage}
          onClose={closeAll}
          onSaved={saved}
          onStale={reload}
        />
      )}
      {editingProtocol !== null && (
        <ProtocolSheet
          protocol={editingProtocol === "new" ? null : editingProtocol}
          onClose={closeAll}
          onSaved={saved}
          onStale={reload}
        />
      )}
      {history && <ServiceHistoryDialog service={history} onClose={() => setHistory(null)} />}
    </div>
  );
}

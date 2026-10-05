"use client";

// Nhân viên: the staff accounts of the clinic (`GET/POST /api/v1/admin/users`, `PATCH .../{user_id}`,
// `POST .../{user_id}/password`). New screen (no zalo-agent original: the original had one dashboard password
// and no accounts). The owner and the manager LIST (`admin.users.read`); only the owner changes anything
// (`admin.users`): add, edit name and role, lock and unlock, reset a password. A lock or a role change ends
// every session of that person, which the confirmation says before it is sent. Nobody is deleted. The rules
// (own account, last owner, rate limit) are the backend's; the screen words its answers (`staff-view.ts`).
import { useCallback, useEffect, useMemo, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { IconPlus, IconSearch } from "@/components/admin/shared/dashboard-icons";
import { Badge, InitialAvatar, Pager, TableShell } from "@/components/admin/shared/ui-bits";
import {
  ChipRow,
  EmptyState,
  FilterChip,
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
} from "@/components/ops/ops-ui";
import { ResetPasswordSheet } from "@/components/ops/staff/reset-password-sheet";
import { StaffActions } from "@/components/ops/staff/staff-actions";
import { StaffSheet } from "@/components/ops/staff/staff-sheet";
import { useToast } from "@/components/ops/toast";
import { http, unwrap } from "@/lib/api/client";
import { formatDate, formatDateTime } from "@/lib/ops/format";
import {
  PAGE_SIZE,
  STAFF_ROLES,
  STATUS_FILTER_LABEL,
  activeQuery,
  lastLoginLabel,
  lockConfirmation,
  rowActions,
  staffErrorMessage,
  staleAfter,
  type RoleFilter,
  type StaffUser,
  type StatusFilter,
} from "@/lib/ops/staff-view";
import { ROLE_LABEL, useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";
import { cx } from "@/ui/classnames";
import { FIELD_BASE_CLASS } from "@/ui/field";

const SEARCH_DEBOUNCE_MS = 300;
const STATUS_FILTERS: StatusFilter[] = ["all", "active", "locked"];
const TABLE_HEADERS = ["Nhân viên", "Vai trò", "Trạng thái", "Đăng nhập cuối", "Ngày tạo"];
const ACTION_HEADER = "Thao tác";

function StatusBadge({ active }: { active: boolean }) {
  return active ? <Badge tone="green">Đang hoạt động</Badge> : <Badge tone="red">Đã khóa</Badge>;
}

export default function StaffPage() {
  const { user, can } = useSession();
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const [query, setQuery] = useState("");
  const [q, setQ] = useState("");
  const [role, setRole] = useState<RoleFilter>("all");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [page, setPage] = useState(0);
  const [editing, setEditing] = useState<StaffUser | "new" | null>(null);
  const [resetting, setResetting] = useState<StaffUser | null>(null);

  const canRead = can("admin.users.read");
  const canManage = can("admin.users");

  useEffect(() => {
    const timer = setTimeout(() => {
      setQ(query.trim());
      setPage(0);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query]);

  const load = useCallback(
    (signal: AbortSignal) =>
      canRead
        ? unwrap(
            http.GET("/api/v1/admin/users", {
              params: {
                query: {
                  q: q || undefined,
                  role: role === "all" ? undefined : role,
                  active: activeQuery(status),
                  limit: PAGE_SIZE,
                  offset: page * PAGE_SIZE,
                },
              },
              signal,
            }),
          )
        : Promise.resolve(undefined),
    [canRead, q, role, status, page],
  );
  const { data, error, loading, reload } = useLoad(load);
  const items = useMemo(() => data?.items ?? [], [data]);
  const filtered = q !== "" || role !== "all" || status !== "all";

  const pickRole = useCallback((next: RoleFilter) => {
    setRole(next);
    setPage(0);
  }, []);
  const pickStatus = useCallback((next: StatusFilter) => {
    setStatus(next);
    setPage(0);
  }, []);

  const closeSheets = useCallback(() => {
    setEditing(null);
    setResetting(null);
  }, []);
  const saved = useCallback(() => {
    closeSheets();
    reload();
  }, [closeSheets, reload]);

  async function toggleLock(target: StaffUser) {
    const words = lockConfirmation(target);
    const ok = await confirm({
      title: words.title,
      message: words.message,
      confirmLabel: words.confirmLabel,
      tone: words.tone,
    });
    if (!ok) return;
    try {
      await unwrap(
        http.PATCH("/api/v1/admin/users/{user_id}", {
          params: { path: { user_id: target.id } },
          body: { version: target.version, active: !target.active },
        }),
      );
      toast.push(
        "success",
        target.active
          ? `Đã khóa tài khoản của ${target.display_name}. Họ đã bị đăng xuất.`
          : `Đã mở khóa tài khoản của ${target.display_name}.`,
      );
    } catch (e) {
      toast.push("error", staffErrorMessage(e));
      if (!staleAfter(e)) return;
    }
    reload();
  }

  const renderActions = (target: StaffUser) => (
    <StaffActions
      name={target.display_name}
      active={target.active}
      actions={rowActions(target, { id: user.id, canManage })}
      onEdit={() => setEditing(target)}
      onResetPassword={() => setResetting(target)}
      onToggleLock={() => void toggleLock(target)}
    />
  );

  const roleLine = (target: StaffUser) => (
    <Badge tone="blue" dot={false}>
      {ROLE_LABEL[target.role]}
    </Badge>
  );

  return (
    <div>
      <PageHeader
        title="Nhân viên"
        subtitle="Tài khoản đăng nhập của phòng khám: vai trò, trạng thái và mật khẩu"
        aside={
          canManage ? (
            <PrimaryButton onClick={() => setEditing("new")}>
              <IconPlus size={16} />
              Thêm nhân viên
            </PrimaryButton>
          ) : undefined
        }
      />

      {!canRead && (
        <EmptyState
          title="Bạn không có quyền xem danh sách nhân viên"
          hint="Chỉ chủ phòng khám và quản lý xem được mục này."
        />
      )}

      {canRead && (
        <>
          {!canManage && (
            <div className="mb-4">
              <Notice>
                Bạn chỉ xem được danh sách. Thêm, sửa, khóa tài khoản và đặt lại mật khẩu là quyền
                của chủ phòng khám.
              </Notice>
            </div>
          )}

          <div className="mb-4 space-y-3">
            <div className="relative sm:max-w-md">
              <IconSearch
                size={15}
                className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-ink-soft/60"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                aria-label="Tìm nhân viên"
                placeholder="Tìm theo họ tên hoặc email"
                className={cx(FIELD_BASE_CLASS, "w-full pl-9")}
              />
            </div>
            <ChipRow label="Vai trò">
              <FilterChip selected={role === "all"} onClick={() => pickRole("all")}>
                Mọi vai trò
              </FilterChip>
              {STAFF_ROLES.map((r) => (
                <FilterChip key={r} selected={role === r} onClick={() => pickRole(r)}>
                  {ROLE_LABEL[r]}
                </FilterChip>
              ))}
            </ChipRow>
            <ChipRow label="Trạng thái">
              {STATUS_FILTERS.map((s) => (
                <FilterChip key={s} selected={status === s} onClick={() => pickStatus(s)}>
                  {STATUS_FILTER_LABEL[s]}
                </FilterChip>
              ))}
            </ChipRow>
          </div>

          {error && <RetryNotice message={error} onRetry={reload} />}
          {loading && !data && <ListSkeleton rows={4} />}
          {data && items.length === 0 && !loading && (
            <EmptyState
              title={filtered ? "Không có nhân viên phù hợp" : "Chưa có nhân viên nào"}
              hint={filtered ? "Đổi từ khóa hoặc bỏ bớt bộ lọc." : undefined}
            />
          )}

          {items.length > 0 && (
            <>
              <div className="hidden min-[1360px]:block" data-testid="staff-table">
                <TableShell
                  headers={canManage ? [...TABLE_HEADERS, ACTION_HEADER] : TABLE_HEADERS}
                  minWidth={canManage ? 940 : 760}
                >
                  {items.map((s) => (
                    <tr key={s.id} className="border-b border-line last:border-0">
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-3">
                          <InitialAvatar name={s.display_name} />
                          <div className="min-w-0">
                            <div className="truncate font-semibold text-ink">
                              {s.display_name}
                              {s.id === user.id && (
                                <span className="ml-2 text-label font-normal text-ink-soft">
                                  (Bạn)
                                </span>
                              )}
                            </div>
                            <div className="truncate text-label text-ink-soft">{s.email}</div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">{roleLine(s)}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <StatusBadge active={s.active} />
                      </td>
                      <td className="px-4 py-3 text-small whitespace-nowrap text-ink-soft">
                        {s.last_login_at ? formatDateTime(s.last_login_at) : "Chưa đăng nhập"}
                      </td>
                      <td className="px-4 py-3 text-small whitespace-nowrap text-ink-soft">
                        {formatDate(s.created_at)}
                      </td>
                      {canManage && <td className="px-4 py-3">{renderActions(s)}</td>}
                    </tr>
                  ))}
                </TableShell>
              </div>

              <ul
                className="grid grid-cols-1 gap-3 min-[1360px]:hidden md:grid-cols-2"
                data-testid="staff-cards"
              >
                {items.map((s) => (
                  <li
                    key={s.id}
                    className="rounded-card border border-line bg-surface p-4 shadow-card"
                  >
                    <div className="flex items-start gap-3">
                      <InitialAvatar name={s.display_name} />
                      <div className="min-w-0 flex-1">
                        <div className="truncate text-body-lg font-semibold text-ink">
                          {s.display_name}
                          {s.id === user.id && (
                            <span className="ml-2 text-label font-normal text-ink-soft">(Bạn)</span>
                          )}
                        </div>
                        <div className="truncate text-label text-ink-soft">{s.email}</div>
                      </div>
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {roleLine(s)}
                      <StatusBadge active={s.active} />
                    </div>
                    <p className="mt-2 text-label text-ink-soft">
                      {lastLoginLabel(s, formatDateTime)} · Tạo {formatDate(s.created_at)}
                    </p>
                    <div className="mt-3">{renderActions(s)}</div>
                  </li>
                ))}
              </ul>
            </>
          )}

          {data && data.total > PAGE_SIZE && (
            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-small text-ink-soft">
                {data.offset + 1}-{data.offset + items.length} / {data.total}
              </span>
              <Pager
                page={page}
                hasMore={data.offset + items.length < data.total}
                onPage={setPage}
              />
            </div>
          )}
        </>
      )}

      {editing && (
        <StaffSheet
          staff={editing === "new" ? null : editing}
          isSelf={editing !== "new" && editing.id === user.id}
          onClose={closeSheets}
          onSaved={saved}
          onStale={reload}
        />
      )}
      {resetting && (
        <ResetPasswordSheet
          staff={resetting}
          onClose={closeSheets}
          onDone={saved}
          onStale={reload}
        />
      )}
      {confirmDialog}
    </div>
  );
}

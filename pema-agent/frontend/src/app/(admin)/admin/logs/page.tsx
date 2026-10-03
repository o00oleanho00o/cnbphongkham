// ported from: web/src/pages/logs-page.tsx
"use client";

// Deviations: `GET /admin/logs/app` (cursor `before`/`next_cursor`, snake_case); new tab "Nhật ký thao tác"
// for the append-only audit log (`GET /admin/logs/audit`), the record of who changed what.

import { useEffect, useState } from "react";
import { AuditLogTable } from "@/components/admin/logs/audit-log-table";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type LogEntry = Schemas["LogEntry"];
import { PageHeader } from "@/components/admin/layout/page-header";
import { DongLog } from "@/components/admin/logs/log-row";
import { SelectMenu } from "@/components/admin/shared/select-menu";

/**
 * Log toàn hệ thống, đọc từ file `data/logs/bot.<ngày>.log`.
 *
 * Khác trang Trace: Trace chỉ có lượt agent, còn đây là MỌI thứ - kết nối Zalo,
 * login QR, định tuyến tin, lỗi của 30 scope trong hệ thống.
 *
 * File ghi cả mức debug bất kể LOG_LEVEL của terminal, nên xem ở đây luôn đầy
 * đủ hơn nhìn terminal.
 */

/**
 * Số dòng mỗi trang. Nhỏ hơn trần 500 của server để lần bấm "Xem thêm" phản hồi
 * nhanh - đọc log là việc dò tìm, người dùng bấm nhiều lần chứ không ngồi đợi
 * một cục lớn.
 */
const MOI_TRANG = 150;

const MUC_LOC = [
  { value: "", label: "Mọi mức" },
  { value: "debug", label: "Debug trở lên" },
  { value: "info", label: "Info trở lên" },
  { value: "warn", label: "Warn trở lên" },
  { value: "error", label: "Chỉ Error" },
];

export default function LogsPage() {
  const [tab, setTab] = useState<"app" | "audit">("app");
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [scopes, setScopes] = useState<string[]>([]);
  const [tat, setTat] = useState(false);
  const [goiY, setGoiY] = useState("");
  const [level, setLevel] = useState("");
  const [scope, setScope] = useState("");
  const [search, setSearch] = useState("");
  const [dangTai, setDangTai] = useState(true);
  const [loi, setLoi] = useState("");
  /** Con trỏ trang sau; `null` = đã hết log, ẩn nút "Xem thêm" */
  const [conTro, setConTro] = useState<string | null>(null);
  const [dangTaiThem, setDangTaiThem] = useState(false);

  /**
   * `before` rỗng = tải lại từ đầu (đổi bộ lọc, bấm Làm mới); có `before` =
   * NỐI THÊM trang cũ hơn. Gộp một hàm để hai đường không trôi khỏi nhau.
   */
  async function nap(before?: string) {
    const noiThem = Boolean(before);
    if (noiThem) setDangTaiThem(true);
    else setDangTai(true);
    setLoi("");
    try {
      const r = await unwrap(
        http.GET("/api/v1/admin/logs/app", {
          params: {
            query: {
              // the filter menu only offers values of the enum, so the cast cannot widen it
              level: (level || undefined) as LogEntry["level"] | undefined,
              scope: scope || undefined,
              search: search || undefined,
              limit: MOI_TRANG,
              before,
            },
          },
        }),
      );
      setEntries((cu) => (noiThem ? [...cu, ...r.entries] : r.entries));
      // Danh sách scope chỉ nạp khi CHƯA lọc, không thì lọc xong ô chọn rỗng dần
      if (!noiThem && !scope && !search) setScopes(r.scopes ?? []);
      setConTro(r.next_cursor ?? null);
      setTat(r.disabled ?? false);
      setGoiY(r.hint ?? "");
    } catch (e) {
      setLoi(errorMessage(e));
    } finally {
      setDangTai(false);
      setDangTaiThem(false);
    }
  }

  useEffect(() => {
    if (tab !== "app") return;
    void nap();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [level, scope, tab]);

  return (
    <>
      <PageHeader
        title="Logs"
        subtitle="Log toàn hệ thống đọc từ file. File ghi cả mức debug nên đầy đủ hơn nhìn terminal."
      />

      <div role="tablist" aria-label="Loại nhật ký" className="mb-4 flex gap-2">
        {(
          [
            ["app", "Log hệ thống"],
            ["audit", "Nhật ký thao tác"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`min-h-11 rounded-full border px-4 text-small font-medium lg:min-h-9 ${
              tab === key
                ? "border-brand-500 bg-brand-500 text-white"
                : "border-line bg-surface text-ink-soft hover:bg-tile"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "audit" && <AuditLogTable />}

      {tab === "app" && (
        <>
          {tat && (
            <div className="mb-4 rounded-tile border border-warning-line bg-warning-soft px-4 py-2.5 text-small text-warning">
              {goiY || "Ghi log ra file đang tắt"}
            </div>
          )}
          {loi && (
            <div className="mb-4 rounded-tile border border-danger-line bg-danger-soft px-4 py-2.5 text-small text-danger">
              {loi}
            </div>
          )}

          <div className="mb-4 flex flex-wrap items-center gap-2">
            <div className="min-w-[150px]">
              <SelectMenu
                value={level}
                onChange={setLevel}
                options={MUC_LOC}
                ariaLabel="Lọc theo mức"
              />
            </div>
            <div className="min-w-[170px]">
              <SelectMenu
                value={scope}
                onChange={setScope}
                options={[
                  { value: "", label: "Mọi scope" },
                  ...scopes.map((s) => ({ value: s, label: s })),
                ]}
                ariaLabel="Lọc theo scope"
              />
            </div>
            <input
              className="gc-input min-w-[200px] flex-1"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void nap()}
              placeholder="Tìm trong log rồi Enter..."
            />
            <button
              type="button"
              onClick={() => void nap()}
              disabled={dangTai}
              className="rounded-control border border-line bg-surface px-4 py-2 text-small font-medium text-ink hover:bg-tile disabled:opacity-50"
            >
              {dangTai ? "Đang tải..." : "Tải lại"}
            </button>
          </div>

          <div className="overflow-hidden rounded-card border border-line bg-surface">
            {entries.map((e, i) => (
              <DongLog key={i} e={e} />
            ))}
            {entries.length === 0 && !dangTai && !tat && (
              <p className="py-10 text-center text-small text-ink-soft/60">
                Không có dòng log nào khớp.
              </p>
            )}
          </div>

          {/* Chỉ hiện khi server nói còn log phía sau. Không dùng cuộn-vô-tận: đọc
          log là việc dò tìm, tự nạp thêm lúc người dùng đang đọc làm trang nhảy
          mất chỗ vừa nhìn. */}
          {conTro && (
            <div className="mt-4 flex justify-center">
              <button
                type="button"
                onClick={() => void nap(conTro)}
                disabled={dangTaiThem}
                className="rounded-control border border-line bg-surface px-4 py-2 text-small font-medium text-ink hover:bg-tile disabled:opacity-50"
              >
                {dangTaiThem ? "Đang tải..." : `Xem thêm ${MOI_TRANG} dòng cũ hơn`}
              </button>
            </div>
          )}

          {!conTro && entries.length > 0 && (
            <p className="mt-4 text-center text-label text-ink-soft/60">
              Đã hết log lưu lại. Log cũ hơn bị xoay vòng theo thời hạn lưu của máy chủ.
            </p>
          )}
        </>
      )}
    </>
  );
}

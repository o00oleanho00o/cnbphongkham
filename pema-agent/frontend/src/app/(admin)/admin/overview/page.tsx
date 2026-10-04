// ported from: web/src/pages/overview-page.tsx
"use client";

// Deviations: `GET /admin/usage/overview` (`OverviewOut`, snake_case). The contract has no contacts,
// memory-fact or total-message counts, no `nodeVersion` and no "LLM configured" flag: the cards and tiles
// that need them are gone (open items), the LLM warning reads `GET /admin/model/provider` instead (ignored
// when the role lacks `admin.model`), and the runtime tile shows the backend's Python and app version.

import { useEffect, useState } from "react";
import Link from "next/link";
import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import { PageHeader } from "@/components/admin/layout/page-header";
import {
  IconBolt,
  IconChat,
  IconClock,
  IconCpu,
  IconDatabase,
  IconGrid,
  IconHeart,
  IconMessage,
  IconSignal,
} from "@/components/admin/shared/dashboard-icons";
import {
  Badge,
  formatNumber,
  formatUptime,
  InfoTile,
  SectionCard,
  StatCard,
} from "@/components/admin/shared/ui-bits";
import { SelectMenu } from "@/components/admin/shared/select-menu";
import { UsageBarChart, type UsageDay } from "@/components/admin/overview/usage-bar-chart";

type OverviewData = Schemas["OverviewOut"];

export default function OverviewPage() {
  const [data, setData] = useState<OverviewData | null>(null);
  /** null = unknown (no permission or request failed): then no warning is shown */
  const [llmReady, setLlmReady] = useState<boolean | null>(null);
  const [chiSo, setChiSo] = useState<"turns" | "tokens">("turns");
  const [soNgay, setSoNgay] = useState<7 | 14 | 30>(7);

  useEffect(() => {
    unwrap(http.GET("/api/v1/admin/usage/overview", { params: { query: { days: soNgay } } }))
      .then(setData)
      .catch(() => setData(null));
  }, [soNgay]);

  useEffect(() => {
    unwrap(http.GET("/api/v1/admin/model/provider"))
      .then((p) => setLlmReady(Boolean(p.model && (p.base_url || p.api_key_masked))))
      .catch(() => setLlmReady(null));
  }, []);

  if (!data) return <p className="text-ink-soft">Đang tải...</p>;

  // Tổng hợp mọi account: gộp daily theo ngày, cộng dồn stats
  const dailyByDay = new Map<
    string,
    { turns: number; inputTokens: number; outputTokens: number }
  >();
  for (const { daily } of data.usage_by_account) {
    for (const d of daily) {
      const agg = dailyByDay.get(d.day) ?? { turns: 0, inputTokens: 0, outputTokens: 0 };
      agg.turns += d.turns;
      agg.inputTokens += d.input_tokens;
      agg.outputTokens += d.output_tokens;
      dailyByDay.set(d.day, agg);
    }
  }
  const stats = data.stats_by_account.reduce(
    (acc, s) => ({
      threads: acc.threads + (s.threads ?? 0),
      messagesToday: acc.messagesToday + (s.messages_today ?? 0),
    }),
    { threads: 0, messagesToday: 0 },
  );
  // todayKey do server tính theo BOT_TIMEZONE (không phải new Date() của trình
  // duyệt) - tự tính lại ở đây từng làm 2 ô "hôm nay" hiện 0 suốt 7 tiếng đầu
  // ngày VN vì khóa ngày UTC của trình duyệt không khớp khóa ngày VN của server.
  const todayUsage = dailyByDay.get(data.today_key);
  // Sparkline chạy trái -> phải theo thời gian
  const series: UsageDay[] = [...dailyByDay.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([day, agg]) => ({ day, ...agg }));

  const tongLuot = series.reduce((n, d) => n + d.turns, 0);
  const tongToken = series.reduce((n, d) => n + d.inputTokens + d.outputTokens, 0);
  const trungBinhNgay = series.length > 0 ? Math.round(tongToken / series.length) : 0;

  return (
    <div>
      <PageHeader icon={IconGrid} title="Tổng quan" subtitle="Trạng thái bot và mức dùng LLM" />

      {/* Bot khởi động BÌNH THƯỜNG khi chưa cấu hình LLM (cố ý - phải vào được
          dashboard mới nhập được). Không có dải này thì bức tranh người dùng
          thấy là: dashboard xanh, account online, mà mọi tin nhắn đều nhận câu
          "chưa cài đặt xong". Cảnh báo duy nhất trước đây là một dòng log lúc
          boot, thứ không ai mở dashboard để đọc. */}
      {llmReady === false && (
        <div className="mb-5 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 dark:border-amber-800 dark:bg-amber-950/40">
          <div className="text-[13px] font-semibold text-amber-900 dark:text-amber-200">
            Chưa cấu hình LLM - bot chưa trả lời được tin nhắn nào
          </div>
          <div className="mt-1 text-[12px] leading-relaxed text-amber-800 dark:text-amber-300">
            Thiếu API key, tên model hoặc base URL.{" "}
            <Link
              href="/admin/tuning/providers"
              className="font-medium underline underline-offset-2"
            >
              Nhập ở trang Cấu hình
            </Link>
          </div>
        </div>
      )}

      <div className="mb-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          icon={IconMessage}
          label="Tin nhắn hôm nay"
          value={formatNumber(stats.messagesToday)}
          // KHÔNG truyền `series`: dãy theo ngày chỉ có `turns` (lượt agent), mà
          // card ngay bên cạnh đã vẽ đúng dãy đó. Vẽ lại ở đây thì hai card khác
          // đầu đề lại có đường biểu diễn giống hệt nhau - đọc ra như thể "tin
          // nhắn" và "lượt agent" là một.
        />
        <StatCard
          icon={IconBolt}
          label="Lượt agent hôm nay"
          value={formatNumber(todayUsage?.turns ?? 0)}
          series={series.map((d) => d.turns)}
        />
        <StatCard
          icon={IconCpu}
          label="Token hôm nay"
          value={formatNumber((todayUsage?.inputTokens ?? 0) + (todayUsage?.outputTokens ?? 0))}
          sub={
            <span className="text-[12px] text-ink-soft">
              {formatNumber(todayUsage?.inputTokens ?? 0)} vào /{" "}
              {formatNumber(todayUsage?.outputTokens ?? 0)} ra
            </span>
          }
          series={series.map((d) => d.inputTokens + d.outputTokens)}
        />
        <StatCard icon={IconChat} label="Phiên chat" value={formatNumber(stats.threads)} />
      </div>

      <SectionCard
        icon={IconHeart}
        title="Tình trạng hệ thống"
        subtitle="Bot đang chạy ra sao và giữ bao nhiêu dữ liệu"
        aside={
          <Badge tone="gray" dot={false}>
            Python {data.system.python} · v{data.system.version}
          </Badge>
        }
      >
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
          <InfoTile
            icon={IconClock}
            label="Uptime"
            value={formatUptime(data.system.uptime_seconds)}
            hint="Thời gian hoạt động"
          />
          <InfoTile
            icon={IconDatabase}
            label="Múi giờ"
            value={data.timezone}
            hint="Ngày và trần mỗi ngày tính theo múi giờ này"
          />
          <InfoTile
            icon={IconSignal}
            label="Accounts online"
            value={`${data.accounts.filter((a) => a.online).length} / ${data.accounts.length}`}
            hint="Tài khoản đang online"
          />
          <InfoTile
            icon={IconChat}
            label="Phiên chat"
            value={formatNumber(stats.threads)}
            hint="Phiên hội thoại của trợ lý AI"
          />
        </div>

        <div className="mt-5">
          <div className="mb-2 text-[11px] font-semibold tracking-wider text-ink-soft uppercase">
            Kênh
          </div>
          <div className="flex flex-wrap gap-2">
            {data.accounts.map((a) => (
              <Badge key={a.id} tone={a.online ? "green" : a.enabled ? "red" : "gray"}>
                {a.label}
              </Badge>
            ))}
          </div>
        </div>
      </SectionCard>

      {series.length > 0 && (
        <div className="mt-5">
          <SectionCard
            icon={IconBolt}
            title="Mức sử dụng"
            subtitle={`Theo dõi hoạt động ${data.days} ngày gần nhất`}
            aside={
              <div className="flex flex-wrap items-center gap-2">
                {/* Hai chỉ số KHÔNG vẽ chung một trục: số token lớn hơn số lượt
                    cả nghìn lần, chồng lên nhau thì cột "lượt" dẹp thành đường kẻ */}
                <div className="flex rounded-lg border border-line p-0.5">
                  {(
                    [
                      ["turns", "Lượt dùng"],
                      ["tokens", "Token"],
                    ] as const
                  ).map(([key, nhan]) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setChiSo(key)}
                      className={`rounded-md px-3 py-1 text-[13px] font-medium transition-colors ${
                        chiSo === key
                          ? "bg-brand-50 text-brand-700"
                          : "text-ink-soft hover:text-ink"
                      }`}
                    >
                      {nhan}
                    </button>
                  ))}
                </div>
                <ChonKhoang giaTri={soNgay} onChange={setSoNgay} />
              </div>
            }
          >
            <div className="mb-5 grid grid-cols-1 gap-3 sm:grid-cols-3">
              <TongKet nhan="Tổng lượt" giaTri={formatNumber(tongLuot)} mau="bg-brand-500" />
              <TongKet nhan="Tổng token" giaTri={formatNumber(tongToken)} mau="bg-emerald-500" />
              <TongKet
                nhan="Trung bình/ngày"
                giaTri={formatNumber(trungBinhNgay)}
                mau="bg-violet-500"
              />
            </div>

            <UsageBarChart data={series} metric={chiSo} />

            <p className="mt-3 text-[12px] text-ink-soft">
              Đưa chuột lên từng cột để xem cả số lượt lẫn số token của ngày đó.
            </p>
          </SectionCard>
        </div>
      )}
    </div>
  );
}

/**
 * Chọn cửa sổ thời gian của biểu đồ.
 *
 * Trước đây cố ý để `<select>` native vì chỉ có 3 lựa chọn và native sẵn có bàn
 * phím lẫn bộ chọn quen thuộc trên di động. Đổi sang `SelectMenu` vì tính nhất
 * quán thắng: đây là ô chọn DUY NHẤT còn lại mở ra popup của hệ điều hành, và
 * một ô lạc điệu giữa trang thì đập vào mắt hơn là lợi ích nó giữ được.
 * `SelectMenu` cũng đã có bàn phím và vai ARIA riêng.
 *
 * Ba mốc khớp đúng `SO_NGAY_CHO_PHEP` ở server (`overview-routes.ts`) - server
 * kẹp lại giá trị lạ nên UI không thể xin một cửa sổ mà server không cho.
 */
function ChonKhoang({ giaTri, onChange }: { giaTri: number; onChange: (n: 7 | 14 | 30) => void }) {
  return (
    <SelectMenu
      icon={IconClock}
      ariaLabel="Khoảng thời gian của biểu đồ"
      value={String(giaTri)}
      options={[7, 14, 30].map((n) => ({ value: String(n), label: `${n} ngày qua` }))}
      onChange={(v) => onChange(Number(v) as 7 | 14 | 30)}
    />
  );
}

/** Ô tổng kết nhỏ phía trên biểu đồ - chấm màu nối số với ý nghĩa của nó */
function TongKet({ nhan, giaTri, mau }: { nhan: string; giaTri: string; mau: string }) {
  return (
    <div className="gc-tile">
      <div className="flex items-center gap-2">
        <span className={`h-2 w-2 shrink-0 rounded-full ${mau}`} />
        <span className="text-[12px] text-ink-soft">{nhan}</span>
      </div>
      <div className="mt-1 text-[20px] font-semibold text-ink">{giaTri}</div>
    </div>
  );
}

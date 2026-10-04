"use client";

// New in Pema (no zalo-agent original): the switchboard of the clinic channels, shown at the top of
// the accounts page. One card per channel of `GET /admin/channels`: feature switch, daily cap, gap
// between proactive messages, send window, bridge state, today's proactive count, and the KILL
// SWITCH of the channel (`POST /admin/channels/{channel}/kill-switch`, audited by the BE).
//
// A save needs the `version` the card was loaded with. On `version_conflict` somebody else changed the
// channel meanwhile: the panel reloads and says so instead of overwriting. Every rule (cap, window,
// kill switch) is enforced by the BE at send time; this panel only edits the settings. The kill switch
// control is shown only with `admin.kill_switch`.
import { useCallback, useEffect, useRef, useState } from "react";

import { IconSignal } from "@/components/admin/shared/dashboard-icons";
import { IconPower } from "@/components/admin/shared/ops-icons";
import { Badge, SectionCard, ToggleKnob, formatTime } from "@/components/admin/shared/ui-bits";
import { NHAN_KENH } from "@/lib/admin/accounts/mo-ta-loai-kenh";
import {
  buildFields,
  draftFromChannel,
  hasChanges,
  usageRatio,
  MAX_DAILY_CAP,
  MAX_GAP_SECONDS,
  type ChannelDraft,
  type ChannelFields,
} from "@/lib/admin/channels/channel-draft";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import type { Schemas } from "@/lib/api";
import { ApiError, errorMessage, http, unwrap } from "@/lib/api/client";
import { useSession } from "@/lib/session/session-context";

type ChannelSettings = Schemas["ChannelSettingsOut"];
type BridgeState = Schemas["BridgeState"];
type Notice = { tone: "red" | "amber" | "green"; text: string };

const BRIDGE_BADGE: Record<
  BridgeState,
  { tone: "gray" | "amber" | "green" | "red"; text: string }
> = {
  not_configured: { tone: "gray", text: "Bridge chưa cấu hình" },
  awaiting_qr: { tone: "amber", text: "Bridge chờ quét QR" },
  connected: { tone: "green", text: "Bridge đã kết nối" },
  blocked: { tone: "red", text: "Zalo đã khóa hoặc giới hạn" },
  down: { tone: "red", text: "Bridge không phản hồi" },
};

const NOTICE_TEXT_CLASS: Record<Notice["tone"], string> = {
  red: "text-red-600 dark:text-red-400",
  amber: "text-amber-700 dark:text-amber-300",
  green: "text-emerald-700 dark:text-emerald-300",
};

const FIELD_LABEL = "mb-1 block text-[12px] font-medium text-ink-soft";
const FIELD_INPUT = "gc-input w-full max-sm:min-h-11";

/** Nói thẳng rủi ro của kênh cá nhân: đây là chỗ duy nhất người vận hành quyết định mức gửi chủ động. */
const CANH_BAO_KENH_CA_NHAN =
  "Kênh zalo_personal dùng nick Zalo thật qua giao thức không chính thức: gửi chủ động nhiều hoặc " +
  "dồn dập CÓ THỂ khiến Zalo KHÓA tài khoản. Giữ trần mỗi ngày thấp, khoảng cách giữa các tin dài và " +
  "khung giờ gửi hẹp.";

const GIAI_THICH_CONG_TAC_KHAN =
  "Công tắc khẩn DỪNG MỌI tin nhắn chủ động của kênh này (nhắc lịch, chăm sóc, tin theo lịch) cho " +
  "tới khi tắt. Tin trả lời khách vừa nhắn tới không bị công tắc này chặn.";

/** Kênh chưa hỗ trợ: hiện để thấy đủ danh sách nhưng không cho sửa cấu hình. */
const KENH_CHUA_HO_TRO: readonly ChannelSettings["channel"][] = ["zalo_oa"];

function isSupported(c: ChannelSettings): boolean {
  return !KENH_CHUA_HO_TRO.includes(c.channel);
}

/** Hộp thoại xác nhận công tắc khẩn: BẬT thì bắt buộc nhập lý do, TẮT chỉ cần xác nhận. */
function KillSwitchDialog({
  channel,
  turningOn,
  onClose,
  onUpdated,
}: {
  channel: ChannelSettings;
  turningOn: boolean;
  onClose: () => void;
  onUpdated: (c: ChannelSettings) => void;
}) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const nen = useChotNen(onClose);
  const reasonRef = useRef<HTMLTextAreaElement>(null);
  const trimmed = reason.trim();
  const missingReason = turningOn && trimmed === "";

  useEffect(() => {
    reasonRef.current?.focus();
    // Esc để hủy, giống hộp xác nhận dùng chung
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    if (missingReason) return;
    setBusy(true);
    setError("");
    try {
      const updated = await unwrap(
        http.POST("/api/v1/admin/channels/{channel}/kill-switch", {
          params: { path: { channel: channel.channel } },
          body: { on: turningOn, reason: trimmed === "" ? null : trimmed },
        }),
      );
      onUpdated(updated);
      onClose();
    } catch (e) {
      setError(errorMessage(e));
      setBusy(false);
    }
  }

  const title = turningOn
    ? `BẬT công tắc khẩn của ${NHAN_KENH[channel.channel]}?`
    : `Tắt công tắc khẩn của ${NHAN_KENH[channel.channel]}?`;
  const confirmClass = turningOn
    ? "bg-red-600 hover:bg-red-700"
    : "bg-brand-500 hover:bg-brand-600";

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/30 p-4 backdrop-blur-[2px]"
      {...nen}
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      <div className="max-h-[85dvh] w-full max-w-md overflow-y-auto rounded-2xl bg-surface p-5 shadow-xl">
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{GIAI_THICH_CONG_TAC_KHAN}</p>
        {turningOn && channel.channel === "zalo_personal" && (
          <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">{CANH_BAO_KENH_CA_NHAN}</p>
        )}
        {!turningOn && (
          <p className="mt-2 text-[13px] leading-relaxed text-ink-soft">
            Tắt công tắc: tin chủ động sẽ được gửi lại theo trần, khoảng cách và khung giờ đang cài.
          </p>
        )}

        <label className="mt-4 block text-[13px] font-medium text-ink" htmlFor="kill-switch-reason">
          Lý do {turningOn ? "(bắt buộc, ghi vào nhật ký kiểm toán)" : "(không bắt buộc)"}
        </label>
        <textarea
          id="kill-switch-reason"
          ref={reasonRef}
          value={reason}
          maxLength={500}
          onChange={(e) => setReason(e.target.value)}
          className="gc-input mt-1.5 min-h-20 w-full resize-y"
          placeholder={turningOn ? "vd: Zalo nhắc tài khoản có dấu hiệu gửi quá nhiều" : ""}
        />
        {error && <p className="mt-2 text-[13px] text-red-600 dark:text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="min-h-11 rounded-lg border border-line px-4 py-2 text-[14px] font-medium text-ink-soft hover:bg-tile sm:min-h-0"
          >
            Hủy
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={busy || missingReason}
            className={`min-h-11 rounded-lg px-4 py-2 text-[14px] font-medium text-white disabled:opacity-50 sm:min-h-0 ${confirmClass}`}
          >
            {turningOn ? "Bật công tắc khẩn" : "Tắt công tắc khẩn"}
          </button>
        </div>
      </div>
    </div>
  );
}

function UsageLine({ channel }: { channel: ChannelSettings }) {
  const cap = channel.daily_cap;
  const ratio = usageRatio(channel.proactive_sent_today, cap);
  const capText = cap === null || cap === undefined ? "không giới hạn" : String(cap);
  return (
    <div>
      <div className="text-[13px] text-ink">
        Đã gửi chủ động hôm nay{" "}
        <span className="font-semibold">
          {channel.proactive_sent_today}/{capText}
        </span>
      </div>
      {ratio !== null && (
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-tile" aria-hidden="true">
          <div
            className={`h-full rounded-full ${ratio >= 1 ? "bg-red-500" : "bg-brand-500"}`}
            style={{ width: `${Math.round(ratio * 100)}%` }}
          />
        </div>
      )}
    </div>
  );
}

function KillSwitchBanner({ channel }: { channel: ChannelSettings }) {
  if (!channel.kill_switch_on) return null;
  const when = channel.kill_switch_changed_at
    ? ` lúc ${formatTime(channel.kill_switch_changed_at)}`
    : "";
  return (
    <div
      className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-[13px] leading-[1.6] text-red-700 dark:border-red-900/50 dark:bg-red-950/40 dark:text-red-300"
      role="alert"
    >
      <span className="font-semibold">CÔNG TẮC KHẨN ĐANG BẬT{when}</span> - mọi tin chủ động của
      kênh này đang bị chặn.
      {channel.kill_switch_reason && <span> Lý do: {channel.kill_switch_reason}</span>}
    </div>
  );
}

/** Một thẻ kênh. `key` gồm `version` nên bản nháp tự nạp lại sau mỗi lần lưu hoặc tải lại. */
function ChannelCard({
  channel,
  canKill,
  onUpdated,
  onConflict,
  onNotice,
}: {
  channel: ChannelSettings;
  canKill: boolean;
  onUpdated: (c: ChannelSettings) => void;
  onConflict: () => void;
  onNotice: (n: Notice) => void;
}) {
  const [draft, setDraft] = useState<ChannelDraft>(() => draftFromChannel(channel));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [killDialog, setKillDialog] = useState<{ turningOn: boolean } | null>(null);
  const supported = isSupported(channel);
  const bridge = channel.bridge_state ? BRIDGE_BADGE[channel.bridge_state] : null;
  const dirty = hasChanges(draft, channel);

  const setField = useCallback(
    (key: keyof ChannelDraft, value: string) => setDraft((prev) => ({ ...prev, [key]: value })),
    [],
  );
  const closeKill = useCallback(() => setKillDialog(null), []);

  async function save(fields: ChannelFields & { enabled?: boolean }) {
    setBusy(true);
    setError("");
    try {
      const updated = await unwrap(
        http.PUT("/api/v1/admin/channels/{channel}", {
          params: { path: { channel: channel.channel } },
          body: { version: channel.version, ...fields },
        }),
      );
      onUpdated(updated);
      onNotice({ tone: "green", text: `Đã lưu cấu hình ${NHAN_KENH[channel.channel]}.` });
    } catch (e) {
      if (e instanceof ApiError && e.code === "version_conflict") {
        onConflict();
        return;
      }
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function saveDraft() {
    const result = buildFields(draft, channel);
    if (!result.ok) {
      setError(result.error);
      return;
    }
    void save(result.fields);
  }

  return (
    <section className="gc-card flex flex-col gap-4 p-5" aria-label={NHAN_KENH[channel.channel]}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[15px] font-semibold break-words text-ink">
            {NHAN_KENH[channel.channel]}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            {bridge && <Badge tone={bridge.tone}>{bridge.text}</Badge>}
            {!supported && <Badge tone="gray">Chưa hỗ trợ</Badge>}
            {channel.requires_friend && <Badge tone="blue">Chỉ gửi cho bạn bè</Badge>}
          </div>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={channel.enabled}
          aria-label={`Bật kênh ${NHAN_KENH[channel.channel]}`}
          disabled={busy || !supported}
          onClick={() => void save({ enabled: !channel.enabled })}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg disabled:opacity-50 sm:h-auto sm:w-auto"
          title={channel.enabled ? "Đang bật - bấm để tắt" : "Đang tắt - bấm để bật"}
        >
          <ToggleKnob on={channel.enabled} />
        </button>
      </div>

      <KillSwitchBanner channel={channel} />
      <UsageLine channel={channel} />

      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <label className={FIELD_LABEL} htmlFor={`cap-${channel.channel}`}>
            Trần tin chủ động mỗi ngày (0-{MAX_DAILY_CAP})
          </label>
          <input
            id={`cap-${channel.channel}`}
            inputMode="numeric"
            className={FIELD_INPUT}
            value={draft.dailyCap}
            disabled={!supported}
            onChange={(e) => setField("dailyCap", e.target.value)}
            placeholder="Không giới hạn"
          />
        </div>
        <div>
          <label className={FIELD_LABEL} htmlFor={`min-${channel.channel}`}>
            Cách nhau tối thiểu (giây, 0-{MAX_GAP_SECONDS})
          </label>
          <input
            id={`min-${channel.channel}`}
            inputMode="numeric"
            className={FIELD_INPUT}
            value={draft.minGap}
            disabled={!supported}
            onChange={(e) => setField("minGap", e.target.value)}
          />
        </div>
        <div>
          <label className={FIELD_LABEL} htmlFor={`max-${channel.channel}`}>
            Cách nhau tối đa (giây, 0-{MAX_GAP_SECONDS})
          </label>
          <input
            id={`max-${channel.channel}`}
            inputMode="numeric"
            className={FIELD_INPUT}
            value={draft.maxGap}
            disabled={!supported}
            onChange={(e) => setField("maxGap", e.target.value)}
          />
        </div>
        <div>
          <label className={FIELD_LABEL} htmlFor={`from-${channel.channel}`}>
            Khung giờ gửi: từ
          </label>
          <input
            id={`from-${channel.channel}`}
            type="time"
            className={FIELD_INPUT}
            value={draft.windowStart}
            disabled={!supported}
            onChange={(e) => setField("windowStart", e.target.value)}
          />
        </div>
        <div>
          <label className={FIELD_LABEL} htmlFor={`to-${channel.channel}`}>
            Khung giờ gửi: đến
          </label>
          <input
            id={`to-${channel.channel}`}
            type="time"
            className={FIELD_INPUT}
            value={draft.windowEnd}
            disabled={!supported}
            onChange={(e) => setField("windowEnd", e.target.value)}
          />
        </div>
      </div>

      {channel.channel === "zalo_personal" && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-[12px] leading-[1.6] text-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          {CANH_BAO_KENH_CA_NHAN}
        </p>
      )}

      {error && <p className="text-[13px] text-red-600 dark:text-red-400">{error}</p>}

      <button
        type="button"
        onClick={saveDraft}
        disabled={busy || !supported || !dirty}
        className="min-h-11 rounded-lg bg-brand-500 px-4 py-2 text-[14px] font-medium text-white hover:bg-brand-600 disabled:opacity-50 sm:min-h-0 sm:self-start"
      >
        {busy ? "Đang lưu..." : "Lưu cấu hình"}
      </button>

      {canKill && (
        <div className="border-t border-line pt-4">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-ink">
            <IconPower size={16} />
            Công tắc khẩn
          </div>
          <p className="mt-1 text-[12px] leading-[1.6] text-ink-soft">{GIAI_THICH_CONG_TAC_KHAN}</p>
          <button
            type="button"
            onClick={() => setKillDialog({ turningOn: !channel.kill_switch_on })}
            className={`mt-2 min-h-11 rounded-lg px-4 py-2 text-[14px] font-medium sm:min-h-0 ${
              channel.kill_switch_on
                ? "border border-line text-ink hover:bg-tile"
                : "bg-red-600 text-white hover:bg-red-700"
            }`}
          >
            {channel.kill_switch_on ? "Tắt công tắc khẩn" : "Bật công tắc khẩn"}
          </button>
        </div>
      )}

      {killDialog && (
        <KillSwitchDialog
          channel={channel}
          turningOn={killDialog.turningOn}
          onClose={closeKill}
          onUpdated={onUpdated}
        />
      )}
    </section>
  );
}

/** Bảng điều khiển kênh, hiện khi có quyền `admin.channels`. */
export function ChannelSettingsPanel() {
  const { can } = useSession();
  const canView = can("admin.channels");
  const canKill = can("admin.kill_switch");
  const [channels, setChannels] = useState<ChannelSettings[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);

  const reload = useCallback(async () => {
    const items = await unwrap(http.GET("/api/v1/admin/channels"));
    setChannels(items);
    setLoadError("");
  }, []);

  useEffect(() => {
    if (!canView) return;
    reload().catch((e: unknown) => setLoadError(errorMessage(e)));
  }, [canView, reload]);

  const onUpdated = useCallback((updated: ChannelSettings) => {
    setChannels((prev) =>
      prev === null ? prev : prev.map((c) => (c.channel === updated.channel ? updated : c)),
    );
  }, []);

  const onConflict = useCallback(() => {
    setNotice({
      tone: "amber",
      text: "Cấu hình kênh vừa được người khác thay đổi nên đã tải lại bản mới nhất. Kiểm tra rồi lưu lại.",
    });
    reload().catch((e: unknown) => setLoadError(errorMessage(e)));
  }, [reload]);

  if (!canView) return null;

  return (
    <div className="mb-8">
      <SectionCard
        icon={IconSignal}
        title="Kênh gửi tin"
        subtitle="Cấu hình chung của từng kênh Zalo: bật/tắt, trần tin chủ động, khung giờ và công tắc khẩn"
      >
        {notice && (
          <p className={`mb-3 text-[13px] ${NOTICE_TEXT_CLASS[notice.tone]}`} role="status">
            {notice.text}
          </p>
        )}
        {loadError && (
          <p className="mb-3 text-[13px] text-red-600 dark:text-red-400">{loadError}</p>
        )}
        {channels === null && !loadError && (
          <p className="text-[13px] text-ink-soft">Đang tải...</p>
        )}
        {channels !== null && channels.length === 0 && (
          <p className="text-[13px] text-ink-soft">Chưa có kênh nào được cấu hình.</p>
        )}
        <div className="grid gap-4 xl:grid-cols-2 2xl:grid-cols-3">
          {(channels ?? []).map((c) => (
            <ChannelCard
              key={`${c.channel}-${c.version}`}
              channel={c}
              canKill={canKill}
              onUpdated={onUpdated}
              onConflict={onConflict}
              onNotice={setNotice}
            />
          ))}
        </div>
      </SectionCard>
    </div>
  );
}

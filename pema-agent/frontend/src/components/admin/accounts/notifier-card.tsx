"use client";

// "Tài khoản thông báo nội bộ" (frames WM24, WM25, WM29): the internal Zalo account that calls staff when they have
// not opened a notice and posts to the team group. It never writes to a customer. Status and facts come from the
// identity list and `GET /api/v1/notifications/settings`; "Cài đặt thông báo" (owner, manager) saves
// `PUT /api/v1/notifications/settings`. No credential, group id or token is shown: the team group is only "Đã đặt".
import { useCallback, useMemo, useState } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { notifierFacts } from "@/lib/admin/accounts/identity-view";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Dialog } from "@/ui/dialog";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

type Identity = Schemas["IdentityOut"];
type Settings = Schemas["NotifySettingsOut"];

const SUBTITLE =
  "Gọi nhân viên qua Zalo khi họ chưa mở thông báo và đăng nhóm Zalo của đội. Chỉ gửi cho nhân viên, không bao giờ nhắn cho khách.";
const TITLE = "Tài khoản thông báo nội bộ";
const MIN_TIMEOUT_MIN = 1;
const MAX_TIMEOUT_MIN = 60;

export function NotifierCard({
  identities,
  running,
  canManage,
  onIdentityChanged,
}: {
  identities: readonly Identity[];
  /** Whether the internal account is running (from the account list). */
  running: boolean;
  canManage: boolean;
  onIdentityChanged: () => void;
}) {
  const internal = identities.find((i) => i.purpose === "internal" && i.enabled) ?? null;
  const load = useCallback(
    (signal: AbortSignal) => unwrap(http.GET("/api/v1/notifications/settings", { signal })),
    [],
  );
  const { data: settings, error, loading, reload } = useLoad(load);
  const [dialog, setDialog] = useState<"settings" | "choose" | null>(null);

  if (!internal) {
    return (
      <Card title={TITLE} subtitle={SUBTITLE}>
        <Notice
          tone="warn"
          action={
            canManage ? (
              <Button onClick={() => setDialog("choose")}>Chọn tài khoản nội bộ</Button>
            ) : undefined
          }
        >
          Chưa có tài khoản thông báo nội bộ. Chuông Zalo và nhóm Zalo của đội bị bỏ qua; nhân viên
          chỉ nhận thông báo trong ứng dụng.
        </Notice>
        {dialog === "choose" && (
          <ChooseInternalDialog
            identities={identities}
            onClose={() => setDialog(null)}
            onSaved={() => {
              setDialog(null);
              onIdentityChanged();
            }}
          />
        )}
      </Card>
    );
  }

  return (
    <Card
      title={TITLE}
      subtitle={SUBTITLE}
      aside={
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={running ? "success" : "neutral"}>
            {running ? "Đang chạy" : "Chưa chạy"}
          </Badge>
          {canManage && settings && (
            <Button variant="secondary" onClick={() => setDialog("settings")}>
              Cài đặt thông báo
            </Button>
          )}
        </div>
      }
    >
      {error && !settings && <RetryNotice message={error} onRetry={reload} />}
      {loading && !settings && <ListSkeleton rows={2} />}
      {settings && (
        <dl className="divide-y divide-line text-body">
          {notifierFacts(internal, settings).map(([name, value]) => (
            <div key={name} className="flex items-center justify-between gap-3 py-2.5">
              <dt className="text-ink-soft">{name}</dt>
              <dd className="font-semibold text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      )}
      {dialog === "settings" && settings && (
        <NotifySettingsDialog
          internal={internal}
          settings={settings}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            reload();
          }}
        />
      )}
    </Card>
  );
}

function CheckField({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string;
  hint: string;
  checked: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <label className="mb-3.5 flex cursor-pointer items-start gap-2.5">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-1"
      />
      <span>
        <span className="block text-body font-semibold text-ink">{label}</span>
        <span className="block text-label text-ink-soft">{hint}</span>
      </span>
    </label>
  );
}

function NotifySettingsDialog({
  internal,
  settings,
  onClose,
  onSaved,
}: {
  internal: Identity;
  settings: Settings;
  onClose: () => void;
  onSaved: () => void;
}) {
  const toast = useToast();
  const [bell, setBell] = useState(settings.bell_enabled);
  const [group, setGroup] = useState(settings.group_enabled);
  const [push, setPush] = useState(settings.push_enabled);
  const [minutes, setMinutes] = useState(String(Math.round(settings.ack_timeout_s / 60)));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const value = Number(minutes);
  const validMinutes =
    Number.isInteger(value) && value >= MIN_TIMEOUT_MIN && value <= MAX_TIMEOUT_MIN;

  async function save() {
    setBusy(true);
    setError("");
    try {
      await unwrap(
        http.PUT("/api/v1/notifications/settings", {
          body: {
            bell_enabled: bell,
            group_enabled: group,
            push_enabled: push,
            ack_timeout_s: value * 60,
          },
        }),
      );
      toast.push("success", "Đã lưu cài đặt thông báo.");
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      title="Cài đặt thông báo"
      subtitle="Áp dụng cho cả phòng khám"
      onClose={onClose}
      wide
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy || !validMinutes} onClick={() => void save()}>
            Lưu
          </Button>
        </>
      }
    >
      <CheckField
        label="Chuông Zalo cho nhân viên"
        hint={`Gọi nhân viên qua tài khoản "${internal.label}" khi họ chưa mở thông báo.`}
        checked={bell}
        onChange={setBell}
      />
      <CheckField
        label="Đăng nhóm Zalo của đội"
        hint={`Nhóm Zalo của đội: ${settings.team_group_id ? "Đã đặt" : "Chưa đặt"}.`}
        checked={group}
        onChange={setGroup}
      />
      <CheckField
        label="Đẩy lên điện thoại"
        hint="Chưa bật: cần khóa dịch vụ đẩy của phòng khám."
        checked={push}
        onChange={setPush}
      />
      <Field
        label="Chờ xác nhận trước khi gọi qua Zalo (phút)"
        error={validMinutes ? undefined : "Nhập số phút từ 1 đến 60."}
      >
        {(control) => (
          <input
            {...control}
            inputMode="numeric"
            value={minutes}
            onChange={(e) => setMinutes(e.target.value)}
            className={FIELD_CONTROL_CLASS}
          />
        )}
      </Field>
      {error && <Notice tone="error">{error}</Notice>}
    </Dialog>
  );
}

/** WM25: nothing is internal yet; pick one of the identities. The BE refuses it while threads still use it. */
function ChooseInternalDialog({
  identities,
  onClose,
  onSaved,
}: {
  identities: readonly Identity[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const options = useMemo<SelectOption[]>(
    () =>
      identities
        .filter((i) => i.purpose !== "internal")
        .map((i) => ({ value: i.id, label: i.label })),
    [identities],
  );
  const [picked, setPicked] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const value = picked ?? options[0]?.value ?? "";

  async function save() {
    setBusy(true);
    setError("");
    try {
      await unwrap(
        http.PATCH("/api/v1/identities/{account_id}", {
          params: { path: { account_id: value } },
          body: { purpose: "internal" },
        }),
      );
      onSaved();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      title="Chọn tài khoản nội bộ"
      subtitle="Tài khoản này chỉ gửi thông báo cho nhân viên, không bao giờ nhắn cho khách."
      onClose={onClose}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button disabled={busy || value === ""} onClick={() => void save()}>
            Lưu
          </Button>
        </>
      }
    >
      <Field label="Tài khoản">
        {(control) => (
          <SelectMenu
            id={control.id}
            size="md"
            ariaLabel="Tài khoản nội bộ"
            value={value}
            options={options}
            onChange={setPicked}
          />
        )}
      </Field>
      {error && <Notice tone="error">{error}</Notice>}
    </Dialog>
  );
}

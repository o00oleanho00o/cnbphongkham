"use client";

// Thông báo của tôi (frames WM42-WM51): how Pema reaches the signed-in operator when a conversation needs taking,
// is taken over or a shift ends. In-app is always on; push to a phone waits for the mobile app; the Zalo bell
// needs the personal Zalo linked with a one-time code and is silenced by quiet hours (an urgent notice still
// rings); the team group is the clinic's and needs nothing from the operator. A notice carries no customer name:
// a short code, the identity, urgency and a link that needs a login. Every call is the operator's own row.
import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { ZaloLinkDialog } from "@/components/ops/notifications/zalo-link-dialog";
import { ListSkeleton, Notice, RetryNotice } from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/ops/format";
import {
  NO_INTERNAL_TEXT,
  quietBody,
  quietError,
  quietFormOf,
  type QuietForm,
} from "@/lib/ops/notify-view";
import { useIdentities } from "@/lib/identities/use-identities";
import { useLoad } from "@/lib/use-load";
import { Badge } from "@/ui/badge";
import { Button } from "@/ui/button";
import { Card } from "@/ui/card";
import { Field, FIELD_CONTROL_CLASS } from "@/ui/field";

const NO_PII_TEXT = "Tin chỉ có mã hội thoại, tên danh tính và đường dẫn, không có tên khách.";
const TEAM_GROUP_TEXT =
  "Mọi lần nhận, tiếp quản và hết ca được đăng lên nhóm Zalo của đội để cả đội thấy ai giữ hội thoại nào. Bạn không cần cài đặt gì cho nhóm này.";

function ZaloCard({
  linked,
  consentedAt,
  noInternal,
  onLink,
  onUnlink,
}: {
  linked: boolean;
  consentedAt: string | null | undefined;
  noInternal: boolean;
  onLink: () => void;
  onUnlink: () => void;
}) {
  return (
    <Card
      title="Chuông Zalo"
      subtitle="Pema nhắn bạn qua Zalo khi bạn chưa mở thông báo sau 3 phút."
      aside={
        <Badge tone={linked ? "success" : "neutral"}>
          {linked ? "Đã liên kết" : "Chưa liên kết"}
        </Badge>
      }
    >
      <div className="space-y-3">
        {linked ? (
          <p className="text-body text-ink">
            <strong>Đồng ý nhận thông báo:</strong> ngày {formatDate(consentedAt)}
          </p>
        ) : (
          <>
            {noInternal && <Notice tone="warn">{NO_INTERNAL_TEXT}</Notice>}
            <p className="text-small text-ink-soft">
              Liên kết Zalo cá nhân để Pema gọi bạn khi bạn chưa mở thông báo sau 3 phút.
            </p>
          </>
        )}
        <p className="text-small text-ink-soft">{NO_PII_TEXT}</p>
        {linked ? (
          <Button variant="secondary" onClick={onUnlink}>
            Hủy liên kết
          </Button>
        ) : (
          <Button disabled={noInternal} onClick={onLink}>
            Liên kết Zalo
          </Button>
        )}
      </div>
    </Card>
  );
}

function QuietCard({
  initial,
  onSaved,
}: {
  initial: QuietForm;
  onSaved: (next: QuietForm) => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const problem = quietError(form);

  async function save() {
    setBusy(true);
    setError("");
    try {
      await unwrap(http.PUT("/api/v1/me/notify-preferences", { body: quietBody(form) }));
      toast.push("success", "Đã lưu giờ yên tĩnh.");
      onSaved(form);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card title="Giờ yên tĩnh" subtitle="Không đổ chuông Zalo trong khoảng giờ này.">
      <label className="mb-3.5 flex cursor-pointer items-start gap-2.5">
        <input
          type="checkbox"
          checked={form.enabled}
          onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          className="mt-1"
        />
        <span>
          <span className="block text-body font-semibold text-ink">Bật giờ yên tĩnh</span>
          <span className="block text-label text-ink-soft">Tin khẩn vẫn đổ chuông.</span>
        </span>
      </label>
      <div className="grid gap-x-4 sm:grid-cols-2">
        <Field label="Từ">
          {(control) => (
            <input
              {...control}
              type="time"
              disabled={!form.enabled}
              value={form.start}
              onChange={(e) => setForm({ ...form, start: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
        <Field label="Đến" error={problem ?? undefined}>
          {(control) => (
            <input
              {...control}
              type="time"
              disabled={!form.enabled}
              value={form.end}
              onChange={(e) => setForm({ ...form, end: e.target.value })}
              className={FIELD_CONTROL_CLASS}
            />
          )}
        </Field>
      </div>
      {error && (
        <div className="mb-3">
          <Notice tone="error">{error}</Notice>
        </div>
      )}
      <Button disabled={busy || problem !== null} onClick={() => void save()}>
        Lưu
      </Button>
    </Card>
  );
}

export default function MyNotificationsPage() {
  const toast = useToast();
  const { identities } = useIdentities();
  const { confirm, confirmDialog } = useConfirmDialog();
  const [linking, setLinking] = useState(false);
  const loadAll = useCallback(async (signal: AbortSignal) => {
    const [zalo, pref, settings] = await Promise.all([
      unwrap(http.GET("/api/v1/me/notify-zalo", { signal })),
      unwrap(http.GET("/api/v1/me/notify-preferences", { signal })),
      unwrap(http.GET("/api/v1/notifications/settings", { signal })),
    ]);
    return { zalo, pref, settings };
  }, []);
  const { data, error, loading, reload, setData } = useLoad(loadAll);
  const [quiet, setQuiet] = useState<QuietForm | null>(null);
  useEffect(() => {
    if (data) setQuiet((current) => current ?? quietFormOf(data.pref));
  }, [data]);

  const hasInternal = identities.some((i) => i.purpose === "internal" && i.enabled);
  // Until the identity list has arrived do not claim there is none: it is only a hint that blocks the link button.
  const noInternal = identities.length > 0 && !hasInternal;

  const onLinked = useCallback(() => {
    setLinking(false);
    toast.push("success", "Đã liên kết Zalo.");
    reload();
  }, [toast, reload]);

  async function unlink() {
    const ok = await confirm({
      title: "Hủy liên kết Zalo?",
      message: "Pema sẽ không gọi bạn qua Zalo nữa. Bạn vẫn nhận thông báo trong ứng dụng.",
      confirmLabel: "Hủy liên kết",
    });
    if (!ok) return;
    try {
      const zalo = await unwrap(http.DELETE("/api/v1/me/notify-zalo"));
      if (data) setData({ ...data, zalo });
      toast.push("success", "Đã hủy liên kết Zalo.");
    } catch (e) {
      toast.push("error", errorMessage(e));
    }
  }

  const header = (
    <PageHeader
      title="Thông báo của tôi"
      subtitle="Cách Pema báo cho bạn khi có hội thoại cần nhận, bị tiếp quản hoặc hết ca"
    />
  );

  if (error && !data) {
    return (
      <div>
        {header}
        <RetryNotice message="Không tải được cài đặt thông báo." onRetry={reload} />
      </div>
    );
  }
  if (loading && !data) {
    return (
      <div>
        {header}
        <ListSkeleton rows={3} />
      </div>
    );
  }
  if (!data || !quiet) return <div>{header}</div>;

  return (
    <div>
      {header}
      <div className="max-w-3xl space-y-4">
        <Card
          title="Trong ứng dụng"
          subtitle="Chuông trên thanh trên và trang Inbox cập nhật ngay."
          aside={<Badge tone="success">Luôn bật</Badge>}
        >
          <p className="text-small text-ink-soft">Thông báo trong ứng dụng không tắt được.</p>
        </Card>
        <Card
          title="Đẩy lên điện thoại"
          subtitle="Thông báo tới ứng dụng Pema trên điện thoại."
          aside={<Badge tone="neutral">Chưa đăng ký</Badge>}
        >
          <p className="text-small text-ink-soft">
            Chưa có thiết bị nào đăng ký. Ứng dụng Pema trên điện thoại sẽ đăng ký thiết bị khi bạn
            đăng nhập; hiện chưa có bản nhận thông báo đẩy.
          </p>
        </Card>
        <ZaloCard
          linked={data.zalo.linked}
          consentedAt={data.zalo.consented_at}
          noInternal={noInternal}
          onLink={() => setLinking(true)}
          onUnlink={() => void unlink()}
        />
        <QuietCard initial={quiet} onSaved={setQuiet} />
        <Notice tone="info">{TEAM_GROUP_TEXT}</Notice>
      </div>
      {linking && <ZaloLinkDialog onClose={() => setLinking(false)} onLinked={onLinked} />}
      {confirmDialog}
    </div>
  );
}

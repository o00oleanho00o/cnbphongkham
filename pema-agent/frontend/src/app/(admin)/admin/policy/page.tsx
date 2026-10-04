"use client";

// Hồ sơ chính sách (new, no zalo-agent original): the two policy profiles side by side (as data from the
// BE), the profile of every account and agent with a way to change it, and the Zalo accounts waiting to be
// linked to a patient record. patient_channel is the safe default; changing an account or agent to
// staff_assistant is asked twice because it removes the review step. The BE audits every change.
import { useCallback, useState } from "react";

import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { IconShieldCheck } from "@/components/admin/shared/ops-icons";
import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { Badge } from "@/components/admin/shared/ui-bits";
import {
  EmptyState,
  ListSkeleton,
  Notice,
  PrimaryButton,
  RetryNotice,
  SecondaryButton,
} from "@/components/ops/ops-ui";
import { useToast } from "@/components/ops/toast";
import { POLICY_ROWS } from "@/lib/admin/policy/policy-text";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { CHANNEL_KIND_LABEL, POLICY_PROFILE_LABEL } from "@/lib/ops/labels";
import { useSession } from "@/lib/session/session-context";
import { useLoad } from "@/lib/use-load";

type ProfileKey = Schemas["PolicyProfileKey"];

const PROFILE_OPTIONS: SelectOption[] = (Object.keys(POLICY_PROFILE_LABEL) as ProfileKey[]).map(
  (value) => ({
    value,
    label: POLICY_PROFILE_LABEL[value],
  }),
);

const PROFILE_ORDER: ProfileKey[] = ["patient_channel", "staff_assistant"];

function ProfileTable({ profiles }: { profiles: Schemas["PolicyProfile"][] }) {
  const ordered = PROFILE_ORDER.map((key) => profiles.find((p) => p.key === key)).filter(
    (p): p is Schemas["PolicyProfile"] => p !== undefined,
  );
  return (
    <>
      {/* Phone: one card per rule, the two profiles stacked (no wide table to scroll sideways) */}
      <ul className="space-y-2 md:hidden">
        {POLICY_ROWS.map((row) => (
          <li key={row.key} className="gc-card p-3.5">
            <div className="text-[13px] font-semibold text-ink">{row.label}</div>
            <dl className="mt-2 space-y-2">
              {ordered.map((p) => (
                <div key={p.key}>
                  <dt className="text-[11px] font-semibold tracking-wide text-ink-soft uppercase">
                    {POLICY_PROFILE_LABEL[p.key]}
                  </dt>
                  <dd className="text-[13px] text-ink">{row.text(p)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
      <div className="gc-card hidden overflow-x-auto md:block">
        <table className="w-full text-left text-[13px]">
          <thead>
            <tr className="border-b border-line text-[11px] tracking-wider text-ink-soft uppercase">
              <th className="px-4 py-3 font-semibold">Quy tắc</th>
              {ordered.map((p) => (
                <th key={p.key} className="px-4 py-3 font-semibold">
                  {POLICY_PROFILE_LABEL[p.key]}
                  <span className="ml-1.5 font-mono text-[10px] text-ink-soft/70 normal-case">
                    {p.key}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {POLICY_ROWS.map((row) => (
              <tr key={row.key} className="border-b border-line/60 last:border-0">
                <th scope="row" className="px-4 py-3 align-top font-medium text-ink">
                  {row.label}
                </th>
                {ordered.map((p) => (
                  <td key={p.key} className="px-4 py-3 align-top text-ink-soft">
                    {row.text(p)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

type Assignment = {
  kind: "account" | "agent";
  id: string;
  label: string;
  profile: ProfileKey;
  detail: string;
};

export default function PolicyPage() {
  const { can } = useSession();
  const toast = useToast();
  const { confirm, confirmDialog } = useConfirmDialog();
  const [busyId, setBusyId] = useState<string | null>(null);

  const canAccounts = can("admin.accounts");
  const canAgents = can("admin.agents");

  const load = useCallback(
    async (signal: AbortSignal) => {
      const [profiles, accounts, agents, pending] = await Promise.all([
        unwrap(http.GET("/api/v1/admin/policy/profiles", { signal })),
        canAccounts ? unwrap(http.GET("/api/v1/admin/accounts", { signal })) : Promise.resolve([]),
        canAgents ? unwrap(http.GET("/api/v1/admin/agents", { signal })) : Promise.resolve([]),
        unwrap(http.GET("/api/v1/admin/policy/identity/pending", { signal })),
      ]);
      return { profiles: profiles.profiles, accounts, agents, pending };
    },
    [canAccounts, canAgents],
  );
  const { data, error, loading, reload } = useLoad(load);

  const assignments: Assignment[] = [
    ...(data?.accounts ?? []).map((a) => ({
      kind: "account" as const,
      id: a.id,
      label: a.label,
      profile: a.policy_profile ?? "patient_channel",
      detail: CHANNEL_KIND_LABEL[a.channel],
    })),
    ...(data?.agents ?? []).map((a) => ({
      kind: "agent" as const,
      id: a.id,
      label: a.name,
      profile: a.policy_profile ?? "patient_channel",
      detail: "Agent",
    })),
  ];

  async function change(item: Assignment, profile: ProfileKey) {
    if (profile === item.profile) return;
    if (profile === "staff_assistant") {
      const ok = await confirm({
        title: `Chuyển "${item.label}" sang Trợ lý nội bộ?`,
        message:
          "Tin gửi ra ngoài sẽ đi thẳng, không qua hàng đợi duyệt; cờ đỏ không còn chuyển bác sĩ tự động và thông tin cá nhân không bắt buộc che. Chỉ dùng cho trợ lý của nhân viên, không dùng để trả lời bệnh nhân.",
        confirmLabel: "Chuyển sang Trợ lý nội bộ",
      });
      if (!ok) return;
    }
    setBusyId(`${item.kind}:${item.id}`);
    try {
      if (item.kind === "account") {
        await unwrap(
          http.PUT("/api/v1/admin/policy/accounts/{account_id}", {
            params: { path: { account_id: item.id } },
            body: { policy_profile: profile },
          }),
        );
      } else {
        await unwrap(
          http.PATCH("/api/v1/admin/agents/{agent_id}", {
            params: { path: { agent_id: item.id } },
            body: { policy_profile: profile, clear_model_override: false },
          }),
        );
      }
      toast.push("success", "Đã đổi hồ sơ chính sách.");
      reload();
    } catch (e) {
      toast.push("error", errorMessage(e));
    } finally {
      setBusyId(null);
    }
  }

  async function decide(link: Schemas["IdentityLink"], reject: boolean) {
    if (!link.patient_id) return;
    setBusyId(`identity:${link.external_user_id}`);
    try {
      await unwrap(
        http.POST("/api/v1/admin/policy/identity/confirm", {
          body: {
            channel: link.channel,
            external_user_id: link.external_user_id,
            patient_id: link.patient_id,
            reject,
          },
        }),
      );
      toast.push("success", reject ? "Đã từ chối liên kết." : "Đã xác nhận liên kết danh tính.");
      reload();
    } catch (e) {
      toast.push("error", errorMessage(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader
        icon={IconShieldCheck}
        title="Hồ sơ chính sách"
        subtitle="An toàn bệnh nhân là cài đặt, không phải tính năng bị xóa: cùng một trợ lý chạy với hồ sơ khác nhau"
      />

      {error && <RetryNotice message={error} onRetry={reload} />}
      {loading && !data && <ListSkeleton rows={3} />}

      {data && (
        <div className="space-y-8">
          <section aria-labelledby="pp-compare">
            <h2 id="pp-compare" className="mb-2 text-[16px] font-semibold text-ink">
              Hai hồ sơ
            </h2>
            <ProfileTable profiles={data.profiles} />
            <p className="mt-2 text-[12px] text-ink-soft">
              Khi một agent chạy trong một tài khoản, hồ sơ nghiêm hơn của hai bên được áp dụng. Mặc
              định của cả hai là Kênh bệnh nhân.
            </p>
          </section>

          <section aria-labelledby="pp-assign">
            <h2 id="pp-assign" className="mb-2 text-[16px] font-semibold text-ink">
              Hồ sơ của từng tài khoản và agent
            </h2>
            {assignments.length === 0 ? (
              <EmptyState title="Chưa có tài khoản hay agent nào" />
            ) : (
              <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {assignments.map((item) => (
                  <li
                    key={`${item.kind}:${item.id}`}
                    className="gc-card flex items-center gap-3 p-3.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[14px] font-semibold text-ink">
                        {item.label}
                      </div>
                      <div className="text-[12px] text-ink-soft">{item.detail}</div>
                    </div>
                    <div className="w-44 shrink-0">
                      <SelectMenu
                        size="md"
                        ariaLabel={`Hồ sơ chính sách của ${item.label}`}
                        value={item.profile}
                        options={PROFILE_OPTIONS}
                        disabled={busyId === `${item.kind}:${item.id}`}
                        onChange={(value) => void change(item, value as ProfileKey)}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="pp-identity">
            <h2 id="pp-identity" className="mb-2 text-[16px] font-semibold text-ink">
              Liên kết danh tính Zalo chờ xác nhận ({data.pending.length})
            </h2>
            <div className="mb-3">
              <Notice>
                Trợ lý chỉ được nhắc tên, lịch hẹn hay thuốc của một bệnh nhân sau khi tài khoản
                Zalo đó được nhân viên xác nhận là đúng người. Đối chiếu bằng hồ sơ hoặc gọi xác
                minh trước khi xác nhận.
              </Notice>
            </div>
            {data.pending.length === 0 ? (
              <EmptyState title="Không có liên kết nào chờ xác nhận" />
            ) : (
              <ul className="grid grid-cols-1 gap-2 md:grid-cols-2">
                {data.pending.map((link) => (
                  <li
                    key={`${link.channel}:${link.external_user_id}`}
                    className="gc-card flex flex-wrap items-center gap-3 p-3.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="text-[14px] font-semibold text-ink">
                        {link.patient_code ? `Hồ sơ ${link.patient_code}` : "Chưa có hồ sơ gợi ý"}
                      </div>
                      <div className="text-[12px] text-ink-soft">
                        {CHANNEL_KIND_LABEL[link.channel]} · {link.external_user_id}
                      </div>
                      <Badge tone="amber" dot={false}>
                        {link.status === "unlinked" ? "Chưa liên kết" : "Chờ xác nhận"}
                      </Badge>
                    </div>
                    {link.patient_id && (
                      <div className="flex gap-2">
                        <PrimaryButton
                          disabled={busyId === `identity:${link.external_user_id}`}
                          onClick={() => void decide(link, false)}
                        >
                          Xác nhận
                        </PrimaryButton>
                        <SecondaryButton
                          disabled={busyId === `identity:${link.external_user_id}`}
                          onClick={() => void decide(link, true)}
                        >
                          Từ chối
                        </SecondaryButton>
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      )}
      {confirmDialog}
    </div>
  );
}

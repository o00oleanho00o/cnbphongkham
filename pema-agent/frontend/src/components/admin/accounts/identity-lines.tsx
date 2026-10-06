"use client";

// What the accounts page adds under an account card for its clinic identity (frame WM24): the limits that really
// apply (with where they come from), who is on duty now, and the buttons "Sửa danh tính" and "Lịch trực". An
// internal identity never writes to a customer, so it shows that sentence instead of limits and roster.
import Link from "next/link";
import { useCallback } from "react";

import type { Schemas } from "@/lib/api";
import { http, unwrap } from "@/lib/api/client";
import { limitsText, onDutyText } from "@/lib/admin/accounts/identity-view";
import { useLoad } from "@/lib/use-load";
import { Button, buttonClass } from "@/ui/button";

type Identity = Schemas["IdentityOut"];

function OnDuty({ accountId }: { accountId: string }) {
  const load = useCallback(
    (signal: AbortSignal) =>
      unwrap(
        http.GET("/api/v1/identities/{account_id}/on-duty", {
          params: { path: { account_id: accountId } },
          signal,
        }),
      ),
    [accountId],
  );
  const { data } = useLoad(load);
  if (!data) return null;
  const who = onDutyText(data.operators);
  return (
    <p className="text-body text-ink">
      <strong>Đang trực:</strong> {who ?? "chưa có ai trực, hội thoại mới vào hàng chờ"}
    </p>
  );
}

export function IdentityLines({
  identity,
  canEdit,
  canRoster,
  onEdit,
}: {
  identity: Identity;
  canEdit: boolean;
  canRoster: boolean;
  onEdit: () => void;
}) {
  const internal = identity.purpose === "internal";
  return (
    <div className="mt-3 w-full space-y-1.5 border-t border-line pt-3">
      {internal ? (
        <p className="text-small text-ink-soft">
          Chỉ gửi thông báo cho nhân viên, không bao giờ nhắn cho khách.
        </p>
      ) : (
        <>
          <p className="text-body text-ink">
            <strong>Giới hạn đang áp dụng:</strong> {limitsText(identity)}
          </p>
          <OnDuty accountId={identity.id} />
        </>
      )}
      <div className="flex flex-wrap gap-2 pt-1">
        {canEdit && (
          <Button variant="secondary" onClick={onEdit}>
            Sửa danh tính
          </Button>
        )}
        {canRoster && !internal && (
          <Link
            href={`/admin/roster?identity=${encodeURIComponent(identity.id)}`}
            className={buttonClass("secondary")}
          >
            Lịch trực
          </Link>
        )}
      </div>
    </div>
  );
}

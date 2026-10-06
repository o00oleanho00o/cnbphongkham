"use client";

// The line above the messages that says who holds the thread and offers the one action that fits: Nhận when nobody
// does, Trả lại when it is mine, Tiếp quản when a colleague holds it. A role that may only read gets one sentence.
// Nothing here decides anything: the BE refuses a claim, takeover or release that is not allowed.
import { Notice } from "@/components/ops/ops-ui";
import type { HolderState } from "@/lib/ops/inbox-view";
import { lockedNotice } from "@/lib/ops/inbox-view";
import { Button } from "@/ui/button";

export const VIEW_ONLY_TEXT =
  "Vai trò của bạn chỉ xem được hội thoại, không nhận hay trả lời được.";
export const UNASSIGNED_TEXT =
  "Chưa có người phụ trách. Bấm Nhận để phụ trách hội thoại này; gửi tin trả lời cũng tự nhận.";
export const MINE_TEXT = "Bạn đang phụ trách hội thoại này.";

type Props = {
  holder: HolderState;
  holderName: string | null;
  canClaim: boolean;
  onClaim: () => void;
  onTakeover: () => void;
  onRelease: () => void;
};

export function HolderBanner({
  holder,
  holderName,
  canClaim,
  onClaim,
  onTakeover,
  onRelease,
}: Props) {
  if (!canClaim) return <Notice tone="info">{VIEW_ONLY_TEXT}</Notice>;
  if (holder === "unassigned") {
    return (
      <Notice tone="info" action={<Button onClick={onClaim}>Nhận</Button>}>
        {UNASSIGNED_TEXT}
      </Notice>
    );
  }
  if (holder === "mine") {
    return (
      <Notice
        tone="success"
        action={
          <Button variant="secondary" onClick={onRelease}>
            Trả lại
          </Button>
        }
      >
        {MINE_TEXT}
      </Notice>
    );
  }
  return (
    <Notice tone="warn" action={<Button onClick={onTakeover}>Tiếp quản</Button>}>
      {lockedNotice(holderName)}
    </Notice>
  );
}

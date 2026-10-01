"use client";

// New in Pema: badge of the policy profile on an account card or row.
import { Badge } from "@/components/admin/shared/ui-bits";
import { NHAN_HO_SO } from "@/lib/admin/accounts/policy-profile-text";
import type { Schemas } from "@/lib/api";

type PolicyProfileKey = Schemas["PolicyProfileKey"];

/** patient_channel is the safe one (green); staff_assistant sends directly, so it stands out (amber). */
const TONE: Record<PolicyProfileKey, "green" | "amber"> = {
  patient_channel: "green",
  staff_assistant: "amber",
};

export function PolicyProfileBadge({ profile }: { profile: PolicyProfileKey }) {
  return (
    <span title={`Hồ sơ chính sách: ${profile}`}>
      <Badge tone={TONE[profile]}>{NHAN_HO_SO[profile]}</Badge>
    </span>
  );
}

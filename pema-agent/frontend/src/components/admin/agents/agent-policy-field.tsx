"use client";

// New in Pema (no zalo-agent original): the "Hồ sơ chính sách" choice of an agent, shared by the create
// modal and the detail form. Radio cards, not a dropdown: the person must READ what each profile does
// before choosing (PLAN-AI01 section 5). The BE enforces the profile; the restrictive one wins when the
// agent runs inside an account.
import { AgentFormField } from "@/components/admin/agents/agent-form-field";
import {
  GHI_CHU_HO_SO_THANG,
  MO_TA_HO_SO,
  NHAN_HO_SO,
  THU_TU_HO_SO,
  type PolicyProfileKey,
} from "@/lib/admin/agents/agent-policy-profile";

export function AgentPolicyField({
  value,
  onChange,
}: {
  value: PolicyProfileKey;
  onChange: (next: PolicyProfileKey) => void;
}) {
  return (
    <AgentFormField label="Hồ sơ chính sách" hint={GHI_CHU_HO_SO_THANG}>
      <div role="radiogroup" aria-label="Hồ sơ chính sách" className="grid gap-2 sm:grid-cols-2">
        {THU_TU_HO_SO.map((key) => {
          const selected = value === key;
          return (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={selected}
              onClick={() => onChange(key)}
              className={`rounded-xl border p-3 text-left transition-colors ${
                selected
                  ? "border-brand-500 bg-brand-50"
                  : "border-line bg-surface hover:bg-tile/60"
              }`}
            >
              <span className="flex items-center gap-2 text-[14px] font-semibold text-ink">
                <span
                  className={`flex h-4 w-4 items-center justify-center rounded-full border ${
                    selected ? "border-brand-500" : "border-line"
                  }`}
                >
                  {selected && <span className="h-2 w-2 rounded-full bg-brand-500" />}
                </span>
                {NHAN_HO_SO[key]}
              </span>
              <span className="mt-1.5 block text-[12px] leading-relaxed text-ink-soft">
                {MO_TA_HO_SO[key][0]}
              </span>
              <span className="mt-1 block text-[12px] leading-relaxed text-ink-soft">
                {MO_TA_HO_SO[key][1]}
              </span>
            </button>
          );
        })}
      </div>
    </AgentFormField>
  );
}

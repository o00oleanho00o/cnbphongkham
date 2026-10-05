// ported from: web/src/dashboard-api-client.ts (type AccountInfo)
//
// The original read this from `GET /api/overview`. Here the signed-in shell builds it from
// `GET /api/v1/admin/accounts` (`AccountOut.running` = online) and shares it through
// `AccountsProvider`, so every admin page filters by account without its own request.

export type AccountInfo = {
  id: string;
  label: string;
  enabled: boolean;
  online: boolean;
  /** zalo_bot, zalo_personal or zalo_oa: the friends page lists personal accounts only */
  channel?: "zalo_bot" | "zalo_personal" | "zalo_oa";
  /** Policy profile of the account: the schedule form warns about patient_channel */
  policy_profile?: "staff_assistant" | "patient_channel";
};

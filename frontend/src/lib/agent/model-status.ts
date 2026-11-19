// Whether the agent has a model it can call (`GET /v1/admin/model`), worded for the overview's warning. The agent
// starts without one on purpose (the model is set on its Model page), but then every message gets the failure reply.
// The base URL is not needed: each provider has a default host.

export interface ModelShown {
  provider: string;
  model: string;
  base_url: string | null;
  api_key: string;
  api_key_broken: boolean;
}

/** What is missing, in the words of the warning ("tên model", "khóa API"); empty when the agent can answer. */
export function missingModelParts(shown: ModelShown): string[] {
  const parts: [boolean, string][] = [
    [shown.model.trim() === "", "tên model"],
    [shown.api_key === "", "khóa API"],
    [shown.api_key !== "" && shown.api_key_broken, "khóa API đã lưu không đọc được (nhập lại)"],
  ];
  return parts.filter(([missing]) => missing).map(([, word]) => word);
}

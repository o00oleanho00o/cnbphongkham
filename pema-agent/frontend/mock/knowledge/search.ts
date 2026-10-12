// Routes of the fake knowledge store: "Thử tìm" (search/debug) and the questions with no document (gaps).
import { type Ctx, type Reply, type Router, bodyOf } from "../core";
import type {
  Gap,
  GapState,
  SearchDebugQuery,
} from "../../../backend/apps/agent/plugins/knowledge/ui/src/types";
import { runSearch } from "./search-engine";
import { store } from "./store";

const GAP_STATES: readonly string[] = ["open", "ignored", "answered"];
const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

const refuse = (detail: string): Reply => ({ status: 400, body: { detail } });

function searchDebug(ctx: Ctx): Reply {
  const body = bodyOf<Partial<SearchDebugQuery>>(ctx);
  const question = (body.question ?? "").trim();
  if (!question) return refuse("Nhập câu hỏi để thử tìm.");
  if (body.channel !== "patient" && body.channel !== "staff") return refuse("Kênh phải là bệnh nhân hoặc nhân viên.");
  if (!body.as_of || !ISO_DAY.test(body.as_of)) return refuse("Ngày hỏi phải có dạng năm-tháng-ngày.");
  return { body: runSearch(store, { question, channel: body.channel, as_of: body.as_of }) };
}

function listGaps(ctx: Ctx): Reply {
  const state = ctx.query.get("state") ?? "open";
  if (!GAP_STATES.includes(state)) return refuse("Trạng thái không hợp lệ.");
  const items = store.gaps
    .filter((gap) => gap.state === state)
    .toSorted((a, b) => b.last_asked_at.localeCompare(a.last_asked_at));
  return { body: items };
}

function patchGap(ctx: Ctx): Reply {
  const gap = store.gaps.find((item) => item.id === ctx.params.id);
  if (!gap) return { status: 404, body: { detail: "Không có câu hỏi này." } };
  const { state } = bodyOf<{ state?: string }>(ctx);
  if (!state || !GAP_STATES.includes(state)) return refuse("Trạng thái không hợp lệ.");
  const next: Gap = { ...gap, state: state as GapState }; // checked against GAP_STATES above
  store.gaps = store.gaps.map((item) => (item.id === gap.id ? next : item));
  return { body: next };
}

export function registerSearch(router: Router): void {
  router.post("/v1/plugins/knowledge/search/debug", null, searchDebug);
  router.get("/v1/plugins/knowledge/gaps", null, listGaps);
  router.patch("/v1/plugins/knowledge/gaps/{id}", null, patchGap);
}

// Mock of the knowledge-base sources: statuses move on while the page polls (cho_xu_ly -> dang_xu_ly ->
// san_sang), one source is broken, one is not approved by a doctor. The texts are generic fictional
// aftercare wording for the demo, not medical advice.
import { agents } from "./agents";
import {
  bodyOf,
  fail,
  isoFromNow,
  uid,
  DAY,
  HOUR,
  type Ctx,
  type Reply,
  type Router,
  type Schemas,
} from "../core";

type S = Schemas;

type Stored = {
  source: S["KbSource"];
  chunks: S["KbChunk"][];
  /** polls left before a pending source becomes ready */
  pollsLeft: number;
};

/** Defaults the contract marks as always present */
const BASE = { error: "", path: "", raw_text: "", agent_count: 0 };

const AFTERCARE_CHUNKS: S["KbChunk"][] = [
  {
    order: 1,
    title: "Chăm sóc da sau laser > Ngày đầu",
    content:
      "Da có thể đỏ nhẹ, hơi rát trong 2 đến 3 ngày đầu. Dùng kem dưỡng ẩm dịu nhẹ theo hướng dẫn, không tự bóc vảy.",
  },
  {
    order: 2,
    title: "Chăm sóc da sau laser > Chống nắng",
    content:
      "Tránh nắng trực tiếp, dùng kem chống nắng phổ rộng mỗi ngày và che chắn khi ra ngoài.",
  },
  {
    order: 3,
    title: "Chăm sóc da sau laser > Khi nào cần liên hệ",
    content:
      "Liên hệ phòng khám ngay khi đỏ rát tăng dần, chảy dịch, chảy máu, sốt hoặc sưng nhiều.",
  },
];

const store: Stored[] = [
  {
    source: {
      ...BASE,
      id: "kb-sau-laser",
      name: "Hướng dẫn chăm sóc da sau laser",
      kind: "file",
      format: "docx",
      status: "san_sang",
      chunk_count: 3,
      byte_size: 48_213,
      attempts: 1,
      approved_by_clinical_owner: true,
      created_at: isoFromNow(-20 * DAY),
      updated_at: isoFromNow(-19 * DAY),
    },
    chunks: AFTERCARE_CHUNKS,
    pollsLeft: 0,
  },
  {
    source: {
      ...BASE,
      id: "kb-dau-hieu",
      name: "Dấu hiệu cần liên hệ phòng khám",
      kind: "text",
      format: "",
      status: "san_sang",
      chunk_count: 1,
      byte_size: 0,
      attempts: 1,
      approved_by_clinical_owner: true,
      created_at: isoFromNow(-18 * DAY),
      updated_at: isoFromNow(-18 * DAY),
    },
    chunks: [
      {
        order: 1,
        title: "Dấu hiệu",
        content:
          "Chảy máu, sốt, mưng mủ hoặc khó thở: nhân viên chuyển ngay cho bác sĩ, không trả lời tự động.",
      },
    ],
    pollsLeft: 0,
  },
  {
    source: {
      ...BASE,
      id: "kb-bang-gia",
      name: "Bảng giá dịch vụ (nháp)",
      kind: "file",
      format: "xlsx",
      status: "san_sang",
      chunk_count: 2,
      byte_size: 21_904,
      attempts: 1,
      approved_by_clinical_owner: false,
      created_at: isoFromNow(-3 * DAY),
      updated_at: isoFromNow(-3 * DAY),
    },
    chunks: [
      {
        order: 1,
        title: "Bảng giá > Peel da",
        content: "Giá tham khảo, chờ xác nhận của chủ phòng khám trước khi dùng.",
      },
      {
        order: 2,
        title: "Bảng giá > Laser",
        content: "Giá tham khảo, chờ xác nhận của chủ phòng khám trước khi dùng.",
      },
    ],
    pollsLeft: 0,
  },
  {
    source: {
      ...BASE,
      id: "kb-quy-trinh-tai-kham",
      name: "Quy trình nhắc tái khám",
      kind: "file",
      format: "pdf",
      status: "dang_xu_ly",
      chunk_count: 0,
      byte_size: 130_552,
      attempts: 1,
      approved_by_clinical_owner: false,
      created_at: isoFromNow(-2 * HOUR),
      updated_at: isoFromNow(-1 * HOUR),
    },
    chunks: [
      {
        order: 1,
        title: "Nhắc tái khám",
        content:
          "Nhắc khách khi đến hạn tái khám, hỏi khung giờ thuận tiện và ghi lại kết quả liên hệ.",
      },
    ],
    pollsLeft: 2,
  },
  {
    source: {
      ...BASE,
      id: "kb-scan-hong",
      name: "Phiếu quét (ảnh chụp)",
      kind: "file",
      format: "pdf",
      status: "hong",
      chunk_count: 0,
      byte_size: 902_114,
      attempts: 3,
      error: "Không đọc được chữ trong tệp (có thể là ảnh quét không có lớp chữ).",
      approved_by_clinical_owner: false,
      created_at: isoFromNow(-5 * DAY),
      updated_at: isoFromNow(-5 * DAY),
    },
    chunks: [],
    pollsLeft: 0,
  },
];

const agentSources = new Map<string, Set<string>>([
  ["cskh-da-lieu", new Set(["kb-sau-laser", "kb-dau-hieu"])],
  ["tro-ly-noi-bo", new Set(["kb-sau-laser", "kb-bang-gia", "kb-quy-trinh-tai-kham"])],
  ["bao-cao-tuan", new Set()],
]);

function advance(): void {
  store.forEach((s) => {
    if (s.source.status !== "cho_xu_ly" && s.source.status !== "dang_xu_ly") return;
    s.pollsLeft -= 1;
    if (s.pollsLeft > 0) {
      s.source.status = "dang_xu_ly";
      return;
    }
    s.source.status = "san_sang";
    s.source.chunk_count = Math.max(s.chunks.length, 1);
    s.source.updated_at = isoFromNow(0);
  });
}

function storedOr404(id: string | undefined): Stored {
  const found = store.find((s) => s.source.id === id);
  if (!found) fail(404, "not_found", "Không tìm thấy nguồn.");
  return found;
}

function idsOf(agentId: string): string[] {
  return [...(agentSources.get(agentId) ?? new Set<string>())];
}

function agentsOfSource(sourceId: string): string[] {
  return agents.filter((a) => agentSources.get(a.id)?.has(sourceId)).map((a) => a.id);
}

function filenameOf(ctx: Ctx): string {
  const head = ctx.raw.subarray(0, 600).toString("latin1");
  return /filename="([^"]+)"/.exec(head)?.[1] ?? "tai-lieu.txt";
}

function fieldOf(ctx: Ctx, field: string): string {
  const text = ctx.raw.toString("utf8");
  return new RegExp(`name="${field}"\\r\\n\\r\\n([^\\r\\n]*)`).exec(text)?.[1] ?? "";
}

export function register(r: Router): void {
  r.get("/api/v1/admin/kb/sources", "kb.read", (): Reply => {
    advance();
    return {
      body: store.map((s) => ({ ...s.source, agent_count: agentsOfSource(s.source.id).length })),
    };
  });

  r.post("/api/v1/admin/kb/sources/file", "kb.manage", (ctx): Reply => {
    const file = filenameOf(ctx);
    const format = file.split(".").pop() ?? "txt";
    const name = fieldOf(ctx, "name") || file;
    const source: S["KbSource"] = {
      ...BASE,
      id: uid("kb"),
      name,
      kind: "file",
      format,
      status: "cho_xu_ly",
      chunk_count: 0,
      byte_size: ctx.raw.length,
      attempts: 0,
      approved_by_clinical_owner: false,
      created_at: isoFromNow(0),
      updated_at: isoFromNow(0),
    };
    store.push({
      source,
      chunks: [{ order: 1, title: name, content: "Nội dung mẫu được cắt từ tệp vừa tải lên." }],
      pollsLeft: 3,
    });
    return { status: 202, body: source };
  });

  r.post("/api/v1/admin/kb/sources/text", "kb.manage", (ctx): Reply => {
    const { name, text } = bodyOf<S["KbTextSourceCreate"]>(ctx);
    if (!name.trim() || !text.trim()) fail(422, "validation_failed", "Nhập tên và nội dung nguồn.");
    const source: S["KbSource"] = {
      ...BASE,
      id: uid("kb"),
      name: name.trim(),
      kind: "text",
      format: "",
      status: "cho_xu_ly",
      chunk_count: 0,
      byte_size: 0,
      attempts: 0,
      approved_by_clinical_owner: false,
      created_at: isoFromNow(0),
      updated_at: isoFromNow(0),
    };
    store.push({ source, chunks: [{ order: 1, title: name.trim(), content: text }], pollsLeft: 2 });
    return { status: 201, body: source };
  });

  r.delete("/api/v1/admin/kb/sources/{source_id}", "kb.manage", (ctx): Reply => {
    const stored = storedOr404(ctx.params.source_id);
    store.splice(store.indexOf(stored), 1);
    agentSources.forEach((set) => set.delete(stored.source.id));
    return { status: 204 };
  });

  r.get("/api/v1/admin/kb/sources/{source_id}/agents", "kb.read", (ctx): Reply => ({
    body: { ids: agentsOfSource(storedOr404(ctx.params.source_id).source.id) },
  }));

  r.put("/api/v1/admin/kb/sources/{source_id}/agents", "kb.manage", (ctx): Reply => {
    const stored = storedOr404(ctx.params.source_id);
    const { ids } = bodyOf<S["IdList"]>(ctx);
    agents.forEach((a) => {
      const set = agentSources.get(a.id) ?? new Set<string>();
      if (ids.includes(a.id)) set.add(stored.source.id);
      else set.delete(stored.source.id);
      agentSources.set(a.id, set);
    });
    return { body: { ids: agentsOfSource(stored.source.id) } };
  });

  r.patch("/api/v1/admin/kb/sources/{source_id}/approval", "kb.manage", (ctx): Reply => {
    const stored = storedOr404(ctx.params.source_id);
    stored.source.approved_by_clinical_owner = bodyOf<S["KbApprove"]>(ctx).approved;
    stored.source.updated_at = isoFromNow(0);
    return { body: stored.source };
  });

  r.get("/api/v1/admin/kb/sources/{source_id}/chunks", "kb.read", (ctx): Reply => {
    const stored = storedOr404(ctx.params.source_id);
    const offset = Number.parseInt(ctx.query.get("offset") ?? "0", 10) || 0;
    const limit = Number.parseInt(ctx.query.get("limit") ?? "20", 10) || 20;
    return { body: stored.chunks.slice(offset, offset + limit) };
  });

  r.post("/api/v1/admin/kb/sources/{source_id}/reindex", "kb.manage", (ctx): Reply => {
    const stored = storedOr404(ctx.params.source_id);
    if (stored.source.status === "dang_xu_ly") {
      fail(409, "invalid_state", "Nguồn đang được xử lý, chờ xong rồi thử lại.");
    }
    stored.source.status = "cho_xu_ly";
    stored.source.attempts = 0;
    stored.source.error = "";
    stored.pollsLeft = 2;
    return { body: stored.source };
  });

  r.get("/api/v1/admin/kb/agents/{agent_id}/sources", "kb.read", (ctx): Reply => ({
    body: { ids: idsOf(ctx.params.agent_id ?? "") },
  }));

  r.put("/api/v1/admin/kb/agents/{agent_id}/sources", "kb.manage", (ctx): Reply => {
    const agentId = ctx.params.agent_id ?? "";
    if (!agents.some((a) => a.id === agentId)) fail(404, "not_found", "Không tìm thấy agent.");
    const { ids } = bodyOf<S["IdList"]>(ctx);
    agentSources.set(agentId, new Set(ids.filter((id) => store.some((s) => s.source.id === id))));
    return { body: { ids: idsOf(agentId) } };
  });

  r.post("/api/v1/admin/kb/search", "kb.read", (ctx): Reply => {
    const { agent_id, query } = bodyOf<S["KbSearchRequest"]>(ctx);
    const readable = new Set(idsOf(agent_id));
    const needle = query.toLowerCase().split(/\s+/).filter(Boolean);
    const hits: S["KbHit"][] = store
      .filter((s) => readable.has(s.source.id) && s.source.status === "san_sang")
      .flatMap((s) =>
        s.chunks.map((c) => ({
          source_id: s.source.id,
          source_name: s.source.name,
          title: c.title ?? "",
          content: c.content,
          score:
            needle.filter((w) => `${c.title} ${c.content}`.toLowerCase().includes(w)).length /
            Math.max(needle.length, 1),
        })),
      )
      .filter((h) => h.score > 0)
      .toSorted((a, b) => b.score - a.score)
      .slice(0, 5);
    return { body: { hits } };
  });
}

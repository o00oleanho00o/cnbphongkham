"use client";

// New in Pema (no zalo-agent original): "Thử tìm". Staff pick an agent, type a question and see the
// passages `kb_search` would return, with source and score, before a patient ever sees an answer built
// from them. `POST /admin/kb/search`; read-only, nothing is stored.
import { useEffect, useState, type FormEvent } from "react";

import { SelectMenu, type SelectOption } from "@/components/admin/shared/select-menu";
import { useChotNen } from "@/lib/admin/shared/backdrop-close-guard";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";

type Hit = Schemas["KbHit"];

export function KbSearchModal({ onClose }: { onClose: () => void }) {
  const nen = useChotNen(onClose);
  const [agents, setAgents] = useState<SelectOption[]>([]);
  const [agentId, setAgentId] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[] | null>(null);
  const [loi, setLoi] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let huy = false;
    unwrap(http.GET("/api/v1/admin/agents"))
      .then((list) => {
        if (huy) return;
        setAgents(list.map((a) => ({ value: a.id, label: a.name })));
        setAgentId((cu) => cu || list[0]?.id || "");
      })
      .catch((e: unknown) => !huy && setLoi(errorMessage(e)));
    return () => {
      huy = true;
    };
  }, []);

  async function tim(e: FormEvent) {
    e.preventDefault();
    if (!agentId || !query.trim()) return;
    setBusy(true);
    setLoi("");
    try {
      const res = await unwrap(
        http.POST("/api/v1/admin/kb/search", {
          body: { agent_id: agentId, query: query.trim(), limit: 5 },
        }),
      );
      setHits(res.hits);
    } catch (err) {
      setLoi(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-ink/30 p-0 backdrop-blur-[2px] sm:items-center sm:p-4"
      {...nen}
    >
      <div className="flex max-h-[90dvh] w-full max-w-2xl flex-col rounded-t-2xl bg-surface shadow-xl sm:rounded-card">
        <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
          <div>
            <div className="font-semibold text-ink">Thử tìm trong kho</div>
            <div className="text-label text-ink-soft">
              Xem agent sẽ trích đoạn nào cho một câu hỏi. Chỉ nguồn đã gán cho agent mới hiện.
            </div>
          </div>
          <button
            onClick={onClose}
            className="shrink-0 rounded-control border border-line px-3 py-1 text-small text-ink-soft hover:bg-tile"
          >
            Đóng
          </button>
        </div>

        <form onSubmit={(e) => void tim(e)} className="space-y-3 border-b border-line px-5 py-4">
          <div>
            <label
              htmlFor="kb-search-agent"
              className="mb-1.5 block text-small font-medium text-ink"
            >
              Agent
            </label>
            <SelectMenu
              id="kb-search-agent"
              size="md"
              value={agentId}
              options={agents}
              onChange={setAgentId}
              placeholder="Chọn agent"
            />
          </div>
          <div>
            <label
              htmlFor="kb-search-query"
              className="mb-1.5 block text-small font-medium text-ink"
            >
              Câu hỏi
            </label>
            <input
              id="kb-search-query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ví dụ: chăm sóc da sau laser cần lưu ý gì"
              className="gc-input w-full"
            />
          </div>
          <button
            type="submit"
            disabled={busy || !agentId || !query.trim()}
            className="min-h-11 w-full rounded-control bg-brand-500 px-4 text-body font-medium text-white hover:bg-brand-600 disabled:opacity-50 sm:w-auto"
          >
            {busy ? "Đang tìm..." : "Tìm"}
          </button>
        </form>

        <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
          {loi && <p className="text-small text-danger">{loi}</p>}
          {hits !== null && hits.length === 0 && !loi && (
            <p className="py-6 text-center text-small text-ink-soft">
              Không có đoạn nào khớp. Agent sẽ không có nguồn để trích dẫn cho câu hỏi này.
            </p>
          )}
          {hits?.map((h, i) => (
            <div key={`${h.source_id}-${i}`} className="gc-tile space-y-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-small font-semibold text-ink">{h.source_name}</span>
                <span className="shrink-0 text-micro text-ink-soft">
                  độ khớp {Math.round(h.score * 100)}%
                </span>
              </div>
              {h.title && <div className="text-label font-medium text-brand-600">{h.title}</div>}
              <p className="text-small leading-[1.6] whitespace-pre-wrap text-ink">{h.content}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

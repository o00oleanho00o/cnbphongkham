// ported from: web/src/pages/knowledge-page.tsx
"use client";

// Deviations: the typed client replaces `api.kb`; `GET /admin/kb/sources` carries no `soAgent`, so the page
// counts agents per source with ONE request per AGENT (a handful), never one per source, on load and after
// an assignment (not on every 4s poll); new column and permission-gated toggle for the doctor sign-off.

import { useCallback, useEffect, useState } from "react";
import type { Schemas } from "@/lib/api";
import { errorMessage, http, unwrap } from "@/lib/api/client";
import { useSession } from "@/lib/session/session-context";
import { PageHeader } from "@/components/admin/layout/page-header";
import { useConfirmDialog } from "@/components/admin/shared/confirm-dialog";
import { useVungTha } from "@/components/admin/shared/file-drop-zone";
import { nhanKhopTuKhoa } from "@/lib/admin/shared/fold-for-search";
import { EmptyRow, ListToolbar, TableShell } from "@/components/admin/shared/ui-bits";
import { KbAddSourceModal } from "@/components/admin/kb/kb-add-source-modal";
import { KbAssignAgentsModal } from "@/components/admin/kb/kb-assign-agents-modal";
import { KbChunksModal } from "@/components/admin/kb/kb-chunks-modal";
import { KbGuideTagsModal } from "@/components/admin/kb/kb-guide-tags-modal";
import { KbGuideModal } from "@/components/admin/kb/kb-guide-modal";
import { KbSearchModal } from "@/components/admin/kb/kb-search-modal";
import { xayThongDiepXoaNguon } from "@/lib/admin/kb/kb-delete-warning-message";
import { trangCuoiCungConDuLieu } from "@/lib/admin/kb/kb-page-clamp";
import { KbSourceRow } from "@/components/admin/kb/kb-source-row";

type KbSourceListItem = Schemas["KbSource"];

// Phân trang phía CLIENT - `GET /api/kb/sources` chưa hỗ trợ offset/limit,
// và số nguồn của một kho thực tế hiếm khi vượt vài chục.
const KICH_TRANG = 20;

/**
 * Trang Kho tri thức: nạp tài liệu (file hoặc gõ tay) để agent tra cứu qua
 * tool `kb_search`. Xử lý (đọc file, cắt đoạn) chạy NỀN - trang này tự làm
 * mới định kỳ để thấy trạng thái `cho_xu_ly` -> `san_sang` mà không cần F5.
 *
 * LÙI CÓ CHỦ Ý (rà soát vòng 6, phase 06): 5 vòng liền đã thử tối ưu "dừng
 * poll khi hết việc" (B7) bằng vòng lặp tự quản lý lịch hẹn giờ
 * (`kb-poll-loop.ts` nối qua một lớp hook React đã xóa) - hạng mục đó CHỈ là
 * Minor của đợt rà soát trước, không nằm trong 5 lỗi Important (I17-I21) mà
 * phase 06 sinh ra để sửa. Cả 5 vòng đều đẻ ra hồi quy MỚI (chết sau 1 lần
 * tải hỏng, không tự khởi động lại, chồng lượt tái nhập, ghi sổ sai thứ tự,
 * rồi tới "25/540 kịch bản hệ thống tự mâu thuẫn" ở vòng thứ năm) - trạng
 * thái cuối cùng vẫn HẸP HƠN `setInterval` nguyên bản ở những chiều đo được.
 * `setInterval` đơn giản hơn vì đúng cấu trúc: không bao giờ dừng nên không
 * bao giờ "quên khởi động lại", không chết sau một lần tải hỏng, không có
 * cửa sổ tái nhập của riêng nó. Cái giá đổi lại: ~900 request/giờ mỗi tab
 * đang mở trên một endpoint đã bỏ toàn văn (`danhSachNguonGon`) - đây là
 * hành vi đã chạy suốt đời tính năng trước phase 06, không phải hồi quy.
 *
 * `kb-poll-loop.ts`/`kb-poll-guard.ts` (khóa được 8/9 chiều) + bộ test của
 * chúng GIỮ LẠI nguyên vẹn, KHÔNG nối vào giao diện - xem docstring đầu 2
 * file đó. Đây là tri thức sống về các bất biến đã học được qua 5 vòng vá,
 * và điểm khởi đầu cho ai làm lại tối ưu này (đã có hướng vá đo được đóng
 * nốt chiều 9 - ghi ở "Vấn đề / băn khoăn" của report phase 06).
 */
/** Số agent đọc được từng nguồn, từ `GET /kb/agents/{id}/sources` của mỗi agent; null khi không có quyền xem agent */
async function demAgentMoiNguon(): Promise<Map<string, number> | null> {
  try {
    const agents = await unwrap(http.GET("/api/v1/admin/agents"));
    const gan = await Promise.all(
      agents.map((a) =>
        unwrap(
          http.GET("/api/v1/admin/kb/agents/{agent_id}/sources", {
            params: { path: { agent_id: a.id } },
          }),
        ),
      ),
    );
    return gan.reduce((dem, { ids }) => {
      ids.forEach((id) => dem.set(id, (dem.get(id) ?? 0) + 1));
      return dem;
    }, new Map<string, number>());
  } catch {
    return null;
  }
}

export default function KnowledgePage() {
  const { can } = useSession();
  const [demAgent, setDemAgent] = useState<Map<string, number> | null>(null);
  const [sources, setSources] = useState<KbSourceListItem[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [adding, setAdding] = useState(false);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(0);
  const [xemDoanCua, setXemDoanCua] = useState<KbSourceListItem | null>(null);
  const [ganAgentCho, setGanAgentCho] = useState<KbSourceListItem | null>(null);
  const [xemHuongDan, setXemHuongDan] = useState(false);
  // Package U7: which sources are articles of the staff guide (`GET /guide/articles`), and the one being tagged.
  const [baiHuongDan, setBaiHuongDan] = useState<Map<string, Schemas["GuideArticleSummary"]>>(
    () => new Map(),
  );
  const [ganNhanCho, setGanNhanCho] = useState<KbSourceListItem | null>(null);
  const [thuTim, setThuTim] = useState(false);
  const [fileTha, setFileTha] = useState<File | null>(null);
  const { confirm, confirmDialog } = useConfirmDialog();

  // Thả file vào bảng = mở modal Thêm nguồn với file đã chọn sẵn. Không tự nạp
  // thẳng: mỗi nguồn cần một TÊN, và tên gợi ý từ tên file phải cho người dùng
  // xem lại được trước khi nó đi vào mọi kết quả kb_search sau này.
  const { dangKeo: dangKeoFile, handlers: handlersTha } = useVungTha(
    useCallback((f: File) => {
      setFileTha(f);
      setAdding(true);
    }, []),
  );

  const reload = useCallback(() => {
    unwrap(http.GET("/api/v1/admin/kb/sources"))
      .then((items) => {
        setSources(items);
        setLoadError("");
      })
      .catch((err: unknown) => {
        setSources((cu) => cu ?? []);
        setLoadError(errorMessage(err));
      });
  }, []);

  const tinhLaiAgent = useCallback(() => {
    void demAgentMoiNguon().then(setDemAgent);
  }, []);

  // Not on the 4 s poll: the tags only change when someone saves them here (or in another tab, on the next visit).
  const taiLaiBaiHuongDan = useCallback(() => {
    unwrap(http.GET("/api/v1/guide/articles"))
      .then((bai) => setBaiHuongDan(new Map(bai.map((b) => [b.id, b]))))
      .catch(() => setBaiHuongDan(new Map()));
  }, []);

  useEffect(() => {
    reload();
    tinhLaiAgent();
    taiLaiBaiHuongDan();
    // Việc cắt đoạn chạy ở worker nền (kb-ingest-worker.ts, quét mỗi 5s) - tự
    // làm mới để trạng thái cho_xu_ly/dang_xu_ly chuyển sang san_sang/hong mà
    // người dùng không phải tự bấm F5.
    const timer = window.setInterval(reload, 4000);
    return () => window.clearInterval(timer);
  }, [reload, tinhLaiAgent, taiLaiBaiHuongDan]);

  const daLoc = (sources ?? []).filter((s) => nhanKhopTuKhoa(s.name, query));

  useEffect(() => setPage(0), [query]);
  // Việc 4.1: xóa nguồn cuối cùng của trang đang xem (hoặc gõ tìm kiếm hẹp
  // hơn) làm số trang thật GIẢM - trang đang đứng có thể vượt quá số trang
  // mới, hiện rỗng dù người dùng không hề đổi từ khóa. Kẹp về TRANG CUỐI còn
  // dữ liệu (không phải luôn về 0 - đang xem trang 5 mà mất 1 dòng thì về
  // trang 4, không ném thẳng về trang 1). Dùng `daLoc.length` (số nguyên) chứ
  // không phải `sources`/`daLoc` (mảng đổi tham chiếu mỗi lần poll) - để
  // không kéo người dùng về trang khác mỗi 4 giây khi SỐ LƯỢNG không hề đổi.
  useEffect(() => {
    const trangCuoi = trangCuoiCungConDuLieu(daLoc.length, KICH_TRANG);
    if (page > trangCuoi) setPage(trangCuoi);
  }, [daLoc.length, page]);

  async function reindex(id: string) {
    await unwrap(
      http.POST("/api/v1/admin/kb/sources/{source_id}/reindex", {
        params: { path: { source_id: id } },
      }),
    );
    reload();
  }

  async function doiDuyet(source: KbSourceListItem) {
    await unwrap(
      http.PATCH("/api/v1/admin/kb/sources/{source_id}/approval", {
        params: { path: { source_id: source.id } },
        body: { approved: !source.approved_by_clinical_owner },
      }),
    );
    reload();
  }

  async function remove(source: KbSourceListItem) {
    // I19: hỏi ĐÚNG trước khi xóa - lấy trước số agent đang gán nguồn này để
    // nói thật họ sẽ mất quyền tra cứu. Route lỗi thì vẫn cho xóa tiếp (không
    // chặn cả luồng chỉ vì không đếm được), nhưng câu chữ phải nói thật là
    // "không kiểm tra được", không ngầm định 0 (xem kb-delete-warning-message.ts).
    let agentIds: string[] | null;
    try {
      agentIds = (
        await unwrap(
          http.GET("/api/v1/admin/kb/sources/{source_id}/agents", {
            params: { path: { source_id: source.id } },
          }),
        )
      ).ids;
    } catch {
      agentIds = null;
    }
    const ok = await confirm({
      title: `Xóa nguồn "${source.name}"?`,
      message: xayThongDiepXoaNguon(agentIds),
    });
    if (!ok) return;
    setActionError("");
    try {
      await unwrap(
        http.DELETE("/api/v1/admin/kb/sources/{source_id}", {
          params: { path: { source_id: source.id } },
        }),
      );
      reload();
      tinhLaiAgent();
    } catch (err) {
      setActionError(errorMessage(err));
    }
  }

  const hasMore = (page + 1) * KICH_TRANG < daLoc.length;
  const trang = daLoc.slice(page * KICH_TRANG, (page + 1) * KICH_TRANG);

  return (
    <div>
      <PageHeader
        title="Kho tri thức"
        subtitle="Tài liệu nạp ở đây được cắt đoạn để agent tra cứu qua công cụ kb_search - nạp xong phải GÁN cho agent thì bot mới đọc được"
        aside={
          <div className="flex items-center gap-2">
            <button
              onClick={() => setThuTim(true)}
              className="cursor-pointer rounded-control border border-line px-3 py-2 text-body font-medium text-ink-soft hover:bg-tile hover:text-ink"
            >
              Thử tìm
            </button>
            <button
              onClick={() => setXemHuongDan(true)}
              className="cursor-pointer rounded-control border border-line px-3 py-2 text-body font-medium text-ink-soft hover:bg-tile hover:text-ink"
            >
              Hướng dẫn
            </button>
            <button
              onClick={() => setAdding(true)}
              className="cursor-pointer rounded-control bg-brand-500 px-4 py-2 text-body font-medium text-white hover:bg-brand-600"
            >
              Thêm nguồn
            </button>
          </div>
        }
      />

      {actionError && <p className="mb-4 text-small text-danger">{actionError}</p>}
      {loadError && <p className="mb-4 text-small text-danger">{loadError}</p>}

      {sources !== null && sources.length > 0 && (
        <ListToolbar
          query={query}
          onQuery={setQuery}
          placeholder="Tìm theo tên nguồn..."
          page={page}
          hasMore={hasMore}
          onPage={setPage}
        />
      )}

      {/* Vùng thả bao trọn bảng: thả file ở đâu trong khu vực này cũng mở modal
          Thêm nguồn với file đã chọn sẵn. Viền sáng khi đang kéo là phản hồi
          duy nhất cho biết thả được - không có nó thì tính năng vô hình. */}
      <div {...handlersTha} className="relative">
        <TableShell
          headers={[
            "Tên",
            "Định dạng",
            "Trạng thái",
            "Agent đang dùng",
            "Bác sĩ duyệt",
            "Số đoạn",
            "Dung lượng",
            "Ngày",
            "",
          ]}
          minWidth={1100}
          ghimCotCuoi
        >
          {sources === null ? (
            <EmptyRow colSpan={9} text="Đang tải..." />
          ) : sources.length === 0 ? (
            <EmptyRow
              colSpan={9}
              text='Chưa có nguồn nào - bấm "Thêm nguồn" hoặc kéo thả file vào đây'
            />
          ) : trang.length === 0 ? (
            <EmptyRow colSpan={9} text={`Không có nguồn nào khớp "${query}"`} />
          ) : (
            trang.map((s) => (
              <KbSourceRow
                key={s.id}
                source={s}
                agentCount={demAgent ? (demAgent.get(s.id) ?? 0) : null}
                canApprove={can("kb.manage")}
                onToggleApproval={() => doiDuyet(s)}
                onReindex={() => reindex(s.id)}
                onDelete={() => void remove(s)}
                onViewChunks={() => setXemDoanCua(s)}
                onAssignAgents={() => setGanAgentCho(s)}
                guideTopic={baiHuongDan.get(s.id)?.topic ?? null}
                onEditGuide={can("kb.manage") ? () => setGanNhanCho(s) : undefined}
              />
            ))
          )}
        </TableShell>
        {dangKeoFile && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-card border-2 border-dashed border-brand-500 bg-brand-50/80 dark:bg-brand-50/60">
            <span className="text-body-lg font-medium text-brand-700 dark:text-brand-700">
              Thả file để thêm nguồn
            </span>
          </div>
        )}
      </div>

      {adding && (
        <KbAddSourceModal
          fileBanDau={fileTha ?? undefined}
          onClose={() => {
            setAdding(false);
            setFileTha(null);
          }}
          onCreated={() => {
            setAdding(false);
            setFileTha(null);
            reload();
          }}
        />
      )}

      {ganAgentCho && (
        <KbAssignAgentsModal
          source={ganAgentCho}
          onClose={() => setGanAgentCho(null)}
          // Tải lại để cột "Agent đang dùng" đổi ngay, không phải chờ nhịp poll
          // kế tiếp - người vừa bấm Lưu cần thấy kết quả của chính thao tác đó.
          onSaved={() => {
            reload();
            tinhLaiAgent();
          }}
        />
      )}

      {xemHuongDan && <KbGuideModal onClose={() => setXemHuongDan(false)} />}

      {ganNhanCho && (
        <KbGuideTagsModal
          sourceId={ganNhanCho.id}
          sourceName={ganNhanCho.name}
          tags={baiHuongDan.get(ganNhanCho.id)?.tags ?? []}
          onClose={() => setGanNhanCho(null)}
          onSaved={taiLaiBaiHuongDan}
        />
      )}

      {thuTim && <KbSearchModal onClose={() => setThuTim(false)} />}

      {xemDoanCua && <KbChunksModal source={xemDoanCua} onClose={() => setXemDoanCua(null)} />}

      {confirmDialog}
    </div>
  );
}

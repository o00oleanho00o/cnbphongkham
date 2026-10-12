/** The questions the header asks before an action that cannot be undone or that opens a source to patients. */
import { ConfirmDialog } from "../parts";
import { ui } from "../sdk";
import type { Source } from "../types";
import { APPROVAL_STEP } from "../logic";

interface DialogProps {
  busy: boolean;
  onClose: () => void;
  onConfirm: () => void;
}

export function ExpireDialog({ busy, onClose, onConfirm }: DialogProps) {
  return (
    <ConfirmDialog
      title="Cho nguồn này hết hiệu lực?"
      onClose={onClose}
      actions={
        <>
          <ui.Button variant="secondary" onClick={onClose}>
            Không
          </ui.Button>
          <ui.Button variant="danger" busy={busy} onClick={onConfirm}>
            Hết hiệu lực
          </ui.Button>
        </>
      }
    >
      Từ hôm nay agent không còn dùng nguồn này để trả lời. Nguồn và lịch sử vẫn được giữ lại.
    </ConfirmDialog>
  );
}

export function DeleteDialog({ source, busy, onClose, onConfirm }: DialogProps & { source: Source }) {
  return (
    <ConfirmDialog
      title="Xóa nguồn này?"
      onClose={onClose}
      actions={
        <>
          <ui.Button variant="secondary" onClick={onClose}>
            Không xóa
          </ui.Button>
          <ui.Button variant="danger" busy={busy} onClick={onConfirm}>
            Xóa nguồn
          </ui.Button>
        </>
      }
    >
      Xóa &quot;{source.title}&quot; sẽ mất {source.chunk_count} đoạn; agent không còn dẫn chứng từ nguồn này. Không hoàn tác được.
    </ConfirmDialog>
  );
}

export function AudienceDialog({
  sections,
  approved,
  busy,
  onClose,
  onConfirm,
}: DialogProps & { sections: readonly string[]; approved: boolean }) {
  return (
    <ConfirmDialog
      title="Cho bệnh nhân thấy nguồn này?"
      onClose={onClose}
      actions={
        <>
          <ui.Button variant="secondary" onClick={onClose}>
            Giữ nội bộ
          </ui.Button>
          <ui.Button busy={busy} onClick={onConfirm}>
            Đổi sang Bệnh nhân
          </ui.Button>
        </>
      }
    >
      <p>Agent sẽ được trả lời bệnh nhân từ nguồn này{approved || !APPROVAL_STEP ? "" : " sau khi bạn duyệt"}.</p>
      {sections.length > 0 && (
        <div className="mt-3 space-y-1">
          <ui.Notice tone="warning">Có mục trông như nội dung nội bộ. Nên tách chúng ra trước khi đổi:</ui.Notice>
          <ul className="list-disc pl-5 text-small">
            {sections.map((title) => (
              <li key={title}>{title}</li>
            ))}
          </ul>
        </div>
      )}
    </ConfirmDialog>
  );
}

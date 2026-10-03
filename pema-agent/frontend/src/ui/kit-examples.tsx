"use client";

// Story-like examples of every kit component, shown on `/dev/kit` (development only). Nothing here is
// real data; it exists so a change to tokens.css or a component can be looked at in one place, in light
// and dark, at every viewport, before the screens that use it are touched.
import { useState } from "react";

import { Badge, type BadgeTone } from "./badge";
import { Card } from "./card";
import { Dialog, Sheet } from "./dialog";
import { EmptyState } from "./empty-state";
import { Field, FIELD_CONTROL_CLASS } from "./field";
import { IconCalendar } from "./icons";
import { TabPanel, Tabs } from "./tabs";
import { EmptyRow, TableShell } from "./table-shell";
import { Tile } from "./tile";
import { PageHeading, Workspace } from "./workspace";

const TONES: readonly BadgeTone[] = ["neutral", "brand", "info", "success", "warning", "danger"];
const TABS = [
  { id: "overview", label: "Tổng quan" },
  { id: "consult", label: "Khám", count: 2 },
  { id: "plan", label: "Liệu trình" },
  { id: "photos", label: "Ảnh" },
] as const;

export function KitExamples() {
  const [tab, setTab] = useState<string>("overview");
  const [dialog, setDialog] = useState<"none" | "dialog" | "sheet">("none");
  const closeDialog = () => setDialog("none");

  return (
    <div>
      <PageHeading
        title="Bộ thành phần giao diện"
        subtitle="Ví dụ mẫu của src/ui: dữ liệu giả, chỉ dùng khi phát triển"
        actions={
          <>
            <button
              type="button"
              onClick={() => setDialog("dialog")}
              className="min-h-10 rounded-control border border-line-strong bg-surface px-3.5 text-label font-semibold text-ink hover:bg-tile"
            >
              Mở hộp thoại
            </button>
            <button
              type="button"
              onClick={() => setDialog("sheet")}
              className="min-h-10 rounded-control bg-brand-500 px-3.5 text-label font-semibold text-surface hover:bg-brand-600"
            >
              Mở sheet
            </button>
          </>
        }
      />

      <div className="mb-4 grid grid-cols-2 gap-3 xl:grid-cols-4">
        <Tile label="Lịch hẹn hôm nay" value="24" note="6 chưa xác nhận" tone="warning" />
        <Tile label="Đang chờ khám" value="3" note="Ổn định" tone="success" />
        <Tile label="Việc quá hạn" value="2" note="Cần xử lý hôm nay" tone="danger" />
        <Tile label="Bệnh nhân mới" value="5" icon={<IconCalendar size={16} />} />
      </div>

      <Workspace
        aside={
          <Card title="Cột phụ" subtitle="Từ 1280px hiện bên phải, dưới đó xếp xuống dưới">
            <p className="text-body text-ink-soft">Nội dung phụ của màn hai cột.</p>
          </Card>
        }
      >
        <Card
          title="Trạng thái"
          subtitle="Chữ luôn nói trạng thái, màu chỉ hỗ trợ"
          className="mb-4"
        >
          <div className="flex flex-wrap gap-2">
            {TONES.map((tone) => (
              <Badge key={tone} tone={tone}>
                {tone}
              </Badge>
            ))}
          </div>
        </Card>

        <Card title="Thẻ ngăn" className="mb-4">
          <Tabs label="Ví dụ thẻ ngăn" idPrefix="kit" items={TABS} value={tab} onChange={setTab} />
          {TABS.map((t) => (
            <TabPanel key={t.id} idPrefix="kit" id={t.id} value={tab}>
              <p className="text-body text-ink-soft">Nội dung thẻ “{t.label}”.</p>
            </TabPanel>
          ))}
        </Card>

        <Card title="Trường nhập" className="mb-4">
          <Field label="Họ và tên" hint="Như trên hồ sơ" required>
            {(control) => (
              <input className={FIELD_CONTROL_CLASS} defaultValue="Nguyễn Văn A" {...control} />
            )}
          </Field>
          <Field label="Số điện thoại" error="Số điện thoại chưa đúng định dạng">
            {(control) => (
              <input className={FIELD_CONTROL_CLASS} defaultValue="09xx" {...control} />
            )}
          </Field>
        </Card>

        <TableShell headers={["Khách", "Dịch vụ", "Giờ"]} minWidth={420}>
          <tr className="border-t border-line hover:bg-row-hover">
            <td className="px-4 py-3">Khách mẫu 1</td>
            <td className="px-4 py-3">Điều trị mụn</td>
            <td className="px-4 py-3">09:30</td>
          </tr>
          <EmptyRow colSpan={3} text="Hết dữ liệu mẫu" />
        </TableShell>
      </Workspace>

      <h2 className="mt-6 mb-3 text-body-lg font-bold text-heading">Lưới thẻ (4 cột từ 1600px)</h2>
      <Workspace layout="cards">
        {["Bác sĩ A", "Bác sĩ B", "Phòng 1", "Phòng 2"].map((name) => (
          <Card key={name} title={name} subtitle="Thẻ mẫu">
            <p className="text-body text-ink-soft">Ca sáng · 8 lịch</p>
          </Card>
        ))}
      </Workspace>

      <div className="mt-6">
        <EmptyState
          title="Chưa có dữ liệu"
          hint="Thêm bản ghi đầu tiên để bắt đầu."
          icon={<IconCalendar size={20} />}
        />
      </div>

      {dialog === "dialog" && (
        <Dialog
          title="Hộp thoại mẫu"
          subtitle="Esc để đóng"
          onClose={closeDialog}
          footer={
            <button
              type="button"
              onClick={closeDialog}
              className="min-h-11 rounded-control bg-brand-500 px-4 text-body font-semibold text-surface"
            >
              Đóng
            </button>
          }
        >
          <p className="text-body text-ink-soft">Nội dung hộp thoại.</p>
        </Dialog>
      )}
      {dialog === "sheet" && (
        <Sheet title="Sheet mẫu" subtitle="Trên điện thoại trượt từ dưới lên" onClose={closeDialog}>
          <p className="text-body text-ink-soft">Nội dung sheet.</p>
        </Sheet>
      )}
    </div>
  );
}

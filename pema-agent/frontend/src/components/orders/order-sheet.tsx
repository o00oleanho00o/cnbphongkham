// The A5 sheets of an order, drawn on the review page and on the print page. Old web: `order-review.js` `sheet()`
// (logo, clinic name, title, draft mark, patient block, numbered products with usage and note, "Dặn dò", the
// reminder for the sheet and the doctor's signature). Every text is a React child, so a usage typed as HTML is
// shown as text and never runs (the old page escaped it by hand). Line breaks of a usage are kept by CSS.
import { formatDate } from "@/lib/ops/format";
import {
  DRAFT_MARK,
  ageGender,
  sheetReminder,
  sheetTitle,
  signerTitle,
  type OrderItemRow,
  type OrderPrint,
} from "@/lib/orders/order-view";

import "./order-sheet.css";

export type SheetRoute = "PRESCRIPTION" | "CONSULTATION";

export function OrderSheets({ print }: { print: OrderPrint }) {
  return (
    <div className="order-docs grid grid-cols-1 gap-5 xl:grid-cols-2">
      <OrderSheet print={print} route="PRESCRIPTION" items={print.prescription} />
      <OrderSheet print={print} route="CONSULTATION" items={print.consultation} />
    </div>
  );
}

export function OrderSheet({
  print,
  route,
  items,
}: {
  print: OrderPrint;
  route: SheetRoute;
  items: readonly OrderItemRow[];
}) {
  if (items.length === 0) return null;
  const { order, patient } = print;
  const title = sheetTitle(route);
  const signer = order.reviewed_by_name ?? order.doctor_name;
  const date = formatDate(order.order_date);
  return (
    <section className="order-doc-set" data-doc={route} aria-label={title}>
      <h2 className="order-screen-only mb-2 text-label font-bold text-heading">
        {title} · {items.length} sản phẩm
      </h2>
      <div className="order-doc-scroll">
        <article className="order-sheet">
          <header className="order-sheet-header">
            {/* eslint-disable-next-line @next/next/no-img-element -- fixed brand asset */}
            <img src="/pema-logo.png" alt="Pema" width={294} height={156} />
            <div>
              <strong>PEMA DIGITAL CLINIC</strong>
              <small>Phòng khám da liễu · dữ liệu demo</small>
            </div>
          </header>
          <h1>{title}</h1>
          {order.status !== "approved" && <p className="order-sheet-draft">{DRAFT_MARK}</p>}
          <div className="order-patient-grid">
            <div>
              <b>Họ tên:</b> {patient.full_name}
            </div>
            <div>
              <b>Tuổi:</b> {ageGender(patient)}
            </div>
            <div>
              <b>Mã hồ sơ:</b> {patient.code}
            </div>
            <div>
              <b>Ngày:</b> {date}
            </div>
            <div className="order-wide">
              <b>Chẩn đoán / nội dung tư vấn:</b>{" "}
              <span className="order-sheet-note">{order.diagnosis}</span>
            </div>
          </div>
          <div>
            {items.map((item, index) => (
              <div className="order-item" key={item.line_no}>
                <div className="order-item-line">
                  <strong>
                    {index + 1}. {item.name}
                  </strong>
                  <span>
                    × {item.quantity} {item.unit}
                  </span>
                </div>
                <div className="order-item-usage">{item.usage || "Chưa nhập cách dùng"}</div>
                {item.note !== "" && <div className="order-item-note">Ghi chú: {item.note}</div>}
              </div>
            ))}
          </div>
          <footer className="order-sheet-footer">
            <div>
              <b>Dặn dò:</b> <span className="order-sheet-note">{order.note}</span>
            </div>
            <p>{sheetReminder(route)}</p>
            <div className="order-signature">
              <span>Ngày {date}</span>
              <strong>{signerTitle(route)}</strong>
              <b>{signer}</b>
            </div>
          </footer>
        </article>
      </div>
    </section>
  );
}

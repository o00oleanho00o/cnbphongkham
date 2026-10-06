import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import {
  ENTRY_PROBLEMS,
  FINANCE_TABS,
  OVERPAYMENT,
  PAYMENT_PROBLEM,
  STATUS_LABEL,
  asMethod,
  barPercent,
  baseLine,
  canAct,
  closeQuestion,
  csvFileName,
  currentMonth,
  dueChoiceLabel,
  dueLine,
  emptyEntryForm,
  financeErrorMessage,
  financeHref,
  heroOver,
  invoiceTotals,
  matchesFilter,
  monthFromParam,
  notConnected,
  notificationTime,
  overviewTiles,
  parseEntryForm,
  patchPerson,
  paymentAmount,
  periodAction,
  rateChanged,
  rateFormOf,
  scopeFor,
  tabOfPath,
  visibleTabs,
  vndFromText,
  withService,
  type EntryForm,
  type InvoiceRow,
} from "./finance-view";

const TODAY = "2026-09-20";
const SERVICE = { id: "svc-1", price_vnd: 300_000, rate_bp: 1000 };

function filled(over: Partial<EntryForm> = {}): EntryForm {
  return {
    ...emptyEntryForm(TODAY, SERVICE, "doc-1"),
    patientId: "patient-1",
    note: "Đã thực hiện",
    ...over,
  };
}

function invoice(over: Partial<InvoiceRow> = {}): InvoiceRow {
  return {
    id: "inv-1",
    number: "HD-2609-0001",
    patient_id: "patient-1",
    patient_code: "P001",
    patient_name: "Nguyễn Thu Hà",
    source: "finance",
    order_id: null,
    invoice_date: "2026-09-06",
    amount_vnd: 300_000,
    received_vnd: 150_000,
    due_vnd: 150_000,
    ...over,
  };
}

describe("labels of the old web", () => {
  it("names_every_period_and_entry_status_the_way_finance_js_did", () => {
    expect(STATUS_LABEL).toEqual({
      open: "Đang đối soát",
      closed: "Đã chốt tháng",
      paid: "Đã chi",
      pending: "Chờ duyệt",
      approved: "Đã duyệt",
      void: "Đã hủy",
    });
  });

  it("falls_back_to_cash_for_an_unknown_method", () => {
    expect(asMethod("transfer")).toBe("transfer");
    expect(asMethod("cheque")).toBe("cash");
  });

  it("words_the_failure_to_load_and_the_close_question", () => {
    expect(notConnected("Lỗi 500")).toBe("Chưa kết nối dữ liệu tài chính: Lỗi 500");
    expect(closeQuestion("2026-08")).toBe(
      "Chốt số liệu tháng 2026-08? Các lượt trong kỳ sẽ bị khóa.",
    );
    expect(csvFileName("2026-09")).toBe("Pema-tien-thu-thuat-2026-09.csv");
  });

  it("reads_a_message_from_an_api_error_and_a_generic_one_from_anything_else", () => {
    expect(financeErrorMessage(new ApiError(422, "Kỳ đã chốt"))).toBe("Kỳ đã chốt");
    expect(financeErrorMessage("boom")).toBe("Có lỗi xảy ra");
  });
});

describe("month and scope", () => {
  it("takes_the_month_of_the_address_or_the_clinic_month_of_today", () => {
    const now = new Date("2026-09-20T03:00:00Z");

    expect(monthFromParam("2026-08", now)).toBe("2026-08");
    expect(monthFromParam("2026-13", now)).toBe("2026-09");
    expect(monthFromParam(null, now)).toBe("2026-09");
    expect(currentMonth(new Date("2026-09-30T20:00:00Z"))).toBe("2026-10");
  });

  it("makes_a_doctor_personal_an_accountant_clinic_and_lets_the_owner_choose", () => {
    const doctor = { canRead: false, canReadOwn: true };
    const accountant = { canRead: true, canReadOwn: false };
    const owner = { canRead: true, canReadOwn: true };

    expect(scopeFor(doctor, "clinic")).toBe("own");
    expect(scopeFor(accountant, "own")).toBe("clinic");
    expect(scopeFor(owner, null)).toBe("clinic");
    expect(scopeFor(owner, "own")).toBe("own");
  });

  it("keeps_the_month_and_only_a_personal_scope_in_the_address", () => {
    expect(financeHref("/finance/entries", "2026-09", "clinic")).toBe(
      "/finance/entries?month=2026-09",
    );
    expect(financeHref("/finance", "2026-09", "own")).toBe("/finance?month=2026-09&scope=own");
  });
});

describe("the tabs", () => {
  it("shows_the_clinic_every_tab_in_the_order_of_the_old_web_then_the_two_new_screens", () => {
    expect(visibleTabs("clinic").map((t) => t.label)).toEqual([
      "Tổng quan",
      "Tiền thủ thuật",
      "Chính sách tỷ lệ",
      "Phiếu thu & thông báo",
      "Chốt kỳ",
      "Xuất CSV",
    ]);
  });

  it("shows_the_personal_view_only_the_overview_the_table_and_the_export", () => {
    expect(visibleTabs("own").map((t) => t.id)).toEqual(["overview", "entries", "export"]);
    expect(FINANCE_TABS.filter((t) => t.clinicOnly).map((t) => t.id)).toEqual([
      "rates",
      "payments",
      "periods",
    ]);
  });

  it("finds_the_tab_of_a_path", () => {
    expect(tabOfPath("/finance")).toBe("overview");
    expect(tabOfPath("/finance/entries")).toBe("entries");
    expect(tabOfPath("/finance/periods")).toBe("periods");
  });
});

describe("the overview numbers", () => {
  const summary = {
    revenue_vnd: 13_200_000,
    fee_vnd: 2_187_000,
    pending_vnd: 90_000,
    collected_vnd: 11_000_000,
    debt_vnd: 1_250_000,
  };

  it("gives_the_clinic_four_tiles_with_the_cash_and_the_debt_next_to_the_revenue", () => {
    const tiles = overviewTiles(summary, "clinic");

    expect(tiles.map((t) => t.label)).toEqual([
      "Doanh số thực hiện",
      "Thực thu trong tháng",
      "Công nợ hiện tại",
      "Tiền thủ thuật đã duyệt",
    ]);
    expect(tiles[1]?.value).toBe("11.000.000 ₫");
    expect(tiles[3]?.note).toBe("Không phải lợi nhuận phòng khám");
  });

  it("gives_the_personal_view_three_tiles_and_no_cash", () => {
    const tiles = overviewTiles({ ...summary, collected_vnd: null, debt_vnd: null }, "own");

    expect(tiles.map((t) => t.label)).toEqual([
      "Doanh số của tôi",
      "Tiền chờ duyệt",
      "Tiền thủ thuật đã duyệt",
    ]);
  });

  it("says_who_is_looking_over_the_hero_title", () => {
    expect(heroOver("own", false)).toBe("GÓC NHÌN CÁ NHÂN");
    expect(heroOver("clinic", false)).toBe("KẾ TOÁN • ĐỐI SOÁT");
    expect(heroOver("clinic", true)).toBe("CHỦ PHÒNG KHÁM • TỔNG QUAN ĐIỀU HÀNH");
  });

  it("sizes_a_bar_by_the_share_of_the_revenue_and_never_past_the_full_width", () => {
    expect(barPercent(900_000, 13_200_000)).toBe(6.8);
    expect(barPercent(5, 0)).toBe(100);
    expect(barPercent(0, 0)).toBe(0);
  });
});

describe("the table of a month", () => {
  it("shows_the_base_and_the_rate_of_a_row", () => {
    expect(baseLine({ base_vnd: 300_000, rate_bp: 1000 })).toBe("300.000 ₫ × 10%");
    expect(baseLine({ base_vnd: 1_000_000, rate_bp: 1250 })).toBe("1.000.000 ₫ × 12,5%");
  });

  it("lets_only_a_writer_act_on_a_live_row_of_an_open_month", () => {
    const open = { month: "2026-09", status: "open" as const };
    const closed = { month: "2026-08", status: "closed" as const };

    expect(canAct(open, true, "pending")).toBe(true);
    expect(canAct(open, true, "void")).toBe(false);
    expect(canAct(open, false, "pending")).toBe(false);
    expect(canAct(closed, true, "pending")).toBe(false);
  });

  it("offers_to_close_an_open_month_and_to_confirm_the_payout_of_a_closed_one", () => {
    expect(periodAction("open", true)).toBe("close");
    expect(periodAction("closed", true)).toBe("pay");
    expect(periodAction("paid", true)).toBeNull();
    expect(periodAction("open", false)).toBeNull();
  });

  it("closes_by_the_close_permission_and_confirms_the_payout_by_the_write_permission", () => {
    expect(periodAction("open", false, true)).toBe("close");
    expect(periodAction("open", true, false)).toBeNull();
    expect(periodAction("closed", true, false)).toBe("pay");
    expect(periodAction("closed", false, true)).toBeNull();
  });
});

describe("the form to record a procedure", () => {
  it("starts_with_the_price_and_the_rate_of_the_service_and_a_whole_share_for_the_main_performer", () => {
    const form = emptyEntryForm(TODAY, SERVICE, "doc-1");

    expect(form.list).toBe("300000");
    expect(form.people[0]).toEqual({ doctorId: "doc-1", share: "100", rate: "10" });
    expect(form.people[1]).toEqual({ doctorId: "", share: "0", rate: "0" });
  });

  it("changes_the_price_and_the_main_rate_when_another_service_is_chosen", () => {
    const next = withService(filled(), { id: "svc-2", price_vnd: 2_500_000, rate_bp: 2000 });

    expect(next.serviceId).toBe("svc-2");
    expect(next.list).toBe("2500000");
    expect(next.people[0].rate).toBe("20");
    expect(next.people[1]).toEqual({ doctorId: "", share: "0", rate: "0" });
  });

  it("converts_percent_boxes_to_basis_points", () => {
    const parsed = parseEntryForm(
      patchPerson(patchPerson(filled(), 0, { share: "33,33", rate: "12.5" }), 1, {
        doctorId: "doc-2",
        share: "66.67",
        rate: "15",
      }),
      TODAY,
    );

    expect(parsed).toEqual({
      ok: true,
      body: {
        patient_id: "patient-1",
        service_id: "svc-1",
        entry_date: TODAY,
        list_vnd: 300_000,
        discount_vnd: 0,
        invoice_id: null,
        note: "Đã thực hiện",
        people: [
          { doctor_id: "doc-1", share_bp: 3333, rate_bp: 1250 },
          { doctor_id: "doc-2", share_bp: 6667, rate_bp: 1500 },
        ],
      },
    });
  });

  it("ignores_a_second_performer_that_was_left_empty_and_attaches_a_chosen_invoice", () => {
    const parsed = parseEntryForm(filled({ invoiceId: "inv-1", note: "  Xong  " }), TODAY);

    expect(parsed).toMatchObject({
      ok: true,
      body: { invoice_id: "inv-1", note: "Xong" },
    });
    expect(parsed.ok && parsed.body.people).toHaveLength(1);
  });

  it.each([
    [{ patientId: "" }, ENTRY_PROBLEMS.patient],
    [{ serviceId: "" }, ENTRY_PROBLEMS.service],
    [{ date: "2026-09-21" }, ENTRY_PROBLEMS.day],
    [{ date: "20/09/2026" }, ENTRY_PROBLEMS.day],
    [{ list: "0" }, ENTRY_PROBLEMS.amount],
    [{ list: "abc" }, ENTRY_PROBLEMS.amount],
    [{ discount: "400000" }, ENTRY_PROBLEMS.amount],
    [{ note: "   " }, ENTRY_PROBLEMS.note],
  ])("tells_the_old_sentence_when_the_form_is_wrong (%o)", (over, problem) => {
    expect(parseEntryForm(filled(over), TODAY)).toEqual({ ok: false, problem });
  });

  it("refuses_shares_that_do_not_add_up_to_a_hundred_percent", () => {
    const form = patchPerson(filled(), 0, { share: "50" });

    expect(parseEntryForm(form, TODAY)).toEqual({ ok: false, problem: ENTRY_PROBLEMS.shares });
  });

  it("refuses_rates_over_a_hundred_percent_together", () => {
    const form = patchPerson(patchPerson(filled(), 0, { share: "50", rate: "60" }), 1, {
      doctorId: "doc-2",
      share: "50",
      rate: "60",
    });

    expect(parseEntryForm(form, TODAY)).toEqual({ ok: false, problem: ENTRY_PROBLEMS.rates });
  });

  it("refuses_the_same_performer_twice_and_a_form_with_no_performer", () => {
    const twice = patchPerson(patchPerson(filled(), 0, { share: "50" }), 1, {
      doctorId: "doc-1",
      share: "50",
    });
    const nobody = patchPerson(filled(), 0, { doctorId: "" });

    expect(parseEntryForm(twice, TODAY)).toEqual({ ok: false, problem: ENTRY_PROBLEMS.duplicate });
    expect(parseEntryForm(nobody, TODAY)).toEqual({ ok: false, problem: ENTRY_PROBLEMS.people });
  });

  it("refuses_a_performer_with_no_share_or_a_rate_with_three_decimals", () => {
    const noShare = patchPerson(filled(), 1, { doctorId: "doc-2", share: "0" });
    const badRate = patchPerson(filled(), 0, { rate: "10,123" });

    expect(parseEntryForm(noShare, TODAY)).toEqual({ ok: false, problem: ENTRY_PROBLEMS.amount });
    expect(parseEntryForm(badRate, TODAY)).toEqual({ ok: false, problem: ENTRY_PROBLEMS.amount });
  });

  it("reads_whole_dong_only", () => {
    expect(vndFromText(" 300000 ")).toBe(300_000);
    expect(vndFromText("300.5")).toBeNull();
    expect(vndFromText("-1")).toBeNull();
  });
});

describe("the rate form", () => {
  it("shows_the_rate_as_a_percentage_and_notices_a_change_of_rate_or_basis", () => {
    const service = { rate_bp: 1250, basis: "list" as const };
    const form = rateFormOf(service);

    expect(form).toEqual({ basis: "list", rate: "12.5" });
    expect(rateChanged(service, form)).toBe(false);
    expect(rateChanged(service, { ...form, rate: "13" })).toBe(true);
    expect(rateChanged(service, { ...form, basis: "net" })).toBe(true);
  });
});

describe("receipts and invoices", () => {
  it("accepts_a_whole_amount_above_zero_only", () => {
    expect(paymentAmount("150000")).toBe(150_000);
    expect(paymentAmount("0")).toBeNull();
    expect(paymentAmount("")).toBeNull();
    expect(PAYMENT_PROBLEM).toBe("Số tiền phải lớn hơn 0 và không vượt số còn lại.");
    expect(OVERPAYMENT).toBe("Số thu vượt công nợ");
  });

  it("words_the_balance_of_an_invoice", () => {
    expect(dueLine(invoice())).toBe("HD-2609-0001 · Còn lại 150.000 ₫");
    expect(dueChoiceLabel(invoice())).toBe("P001 · 150.000 ₫ · HD-2609-0001");
  });

  it("filters_the_invoices_like_the_three_chips_of_the_cashier", () => {
    const paid = invoice({ received_vnd: 300_000, due_vnd: 0 });
    const open = invoice();

    expect(matchesFilter(open, "due")).toBe(true);
    expect(matchesFilter(paid, "due")).toBe(false);
    expect(matchesFilter(paid, "paid")).toBe(true);
    expect(matchesFilter(open, "paid")).toBe(false);
    expect(matchesFilter(paid, "all")).toBe(true);
  });

  it("totals_what_was_received_and_what_is_still_due", () => {
    const totals = invoiceTotals([
      invoice(),
      invoice({ received_vnd: 300_000, due_vnd: 0 }),
      invoice({ amount_vnd: 0, received_vnd: 0, due_vnd: 0 }),
    ]);

    expect(totals).toEqual({ count: 3, received: 450_000, due: 150_000 });
  });

  it("shows_a_notification_time_in_clinic_time", () => {
    expect(notificationTime("2026-09-12T10:30:00+07:00")).toBe("2026-09-12 10:30");
  });
});

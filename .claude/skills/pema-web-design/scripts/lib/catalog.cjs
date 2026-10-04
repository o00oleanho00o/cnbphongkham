// Hand-kept catalog of EVERY screen of the old Pema web (owner rule: nothing is filtered out).
// web-inventory.cjs verifies each entry against the live web and writes design-specs/web/inventory.json.
// Ids are frozen: never renumber; append new ids at the end of their group.
//
// Entry fields
//   id, group, name (the old web's Vietnamese title), kind: page | tab | modal | dialog | state
//   reach   steps run from a fresh page (see lib/old-web.cjs); expect = what must be visible afterwards
//   role    optional account id that overrides the inventory role
//   sources the old code that draws the screen
//   next_route / next_status   Next.js target (FEATURE-INVENTORY.md, PLAN-AI01-U.md section 3)
//   app_canvas   cross-reference to app canvas codes only; [] = no app counterpart (never a filter)
//   legacy_shot  name used by prototype/review-desktop.cjs (<width>-<name>.png)
//   covers  UI entry points this screen accounts for (checked against what the live web offers)
//   notes   what a later step must know (variants, native dialogs, not captured states)

const OWNER = 'owner-tam';
const DOCTOR = 'doctor-mai';
const CARE = 'care-maianh';
const ACCOUNTANT = 'accountant';

const groups = [
  { code: 'WA', name: 'Khung & điều hướng' },
  { code: 'WB', name: 'Vận hành: tổng quan, hôm nay, lịch' },
  { code: 'WC', name: 'Hồ sơ & Patient 360' },
  { code: 'WD', name: 'CSKH & theo dõi' },
  { code: 'WE', name: 'Ảnh, bác sĩ & phòng, dịch vụ' },
  { code: 'WF', name: 'Thu ngân & lên đơn' },
  { code: 'WG', name: 'Tài chính PB02' },
  { code: 'WH', name: 'Ask Pema & Hướng dẫn' },
];

const START = { goto: '/clinic-web/?staff={role}' };
const nav = (name) => ({ click: `.sidebar [data-nav="${name}"]` });
const tab = (name) => ({ click: `[data-tab="${name}"]` });
const P360 = [nav('patients'), { click: 'tr[data-patient="P001"]' }, { wait: '.patient-hero' }];
const MODAL = '.modal-backdrop .modal';
const finTab = (name) => ({ click: `[data-finance-tab="${name}"]` });
const FIN = [nav('finance'), { wait: '.finance-workspace .metric, .finance-workspace .hero' }];

const S = (id, group, name, kind, reach, expect, extra) => ({ id, group, name, kind, reach, expect, ...extra });

const GUIDE_ARTICLES = [
  ['roles', 'Bắt đầu theo vai trò'],
  ['records', 'Hồ sơ & Patient 360'],
  ['schedule', 'Lịch hẹn & tiếp đón'],
  ['resources', 'Bác sĩ, phòng & dịch vụ'],
  ['clinical', 'Từ tư vấn đến buổi điều trị'],
  ['care', 'Chăm sóc & phản hồi tại nhà'],
  ['billing', 'Hóa đơn & thu tiền'],
  ['exceptions', 'Khi cần kiểm tra lại'],
  ['crm01', 'CSKH chủ động & tài khoản nhân viên'],
  ['mobile-finance', 'Mobile, CSKH & tài chính theo vai trò'],
];

// Open the quick-order dialog from Thu ngân and add products by catalog code; `usage` fills "Cách dùng" of each
// line (the doctor cannot approve a line without it).
const draftSteps = (codes, usage = true) => [
  nav('cashier'),
  { click: '[data-ops="quick-order"]' },
  { wait: '#catalog-order-form' },
  ...codes.map((c) => ({ click: `[data-quick-add="${c}"]` })),
  ...(usage ? codes.map((_, i) => ({ fill: [`#usage-${i}`, 'Bôi lớp mỏng, sáng và tối, 14 ngày'] })) : []),
];

const screens = [
  // ---------------------------------------------------------------- WA shell
  S('WA1', 'WA', 'Khung ứng dụng · Chủ phòng khám', 'state', [START, { wait: '.sidebar' }], { selector: '.sidebar .brand-logo', text: 'Không gian làm việc' }, {
    sources: ['prototype/shared/clinic.js#shell', 'prototype/shared/staff-context.js#picker', 'prototype/shared/workspace-layout.css'],
    next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: ['A5', 'A6'],
    covers: ['staff:owner-tam'],
    notes: 'Sidebar (3 sections, 13 items, nav badge, user card), topbar (breadcrumbs, account picker, demo label, global search, bell, reset). The account picker is a native select; its open list is not capturable. Reset asks a native confirm(). finance-bridge.js adds a small link in the topbar ("Tài chính đã đồng bộ", "Đang đồng bộ tài chính…", "Tài chính chờ kết nối · thử lại") that follows the finance API. A skip link "Đến nội dung chính" shows on keyboard focus.',
  }),
  S('WA2', 'WA', 'Khung · CSKH (trang chủ CSKH hôm nay)', 'state', [START, { wait: '.sidebar' }], { text: 'CSKH hôm nay' }, {
    role: CARE, sources: ['prototype/shared/staff-context.js#pages', 'prototype/shared/clinic.js#shell'],
    next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: ['C1', 'A6'],
    covers: ['staff:care-maianh', 'staff:care-thu'],
    notes: 'Role shell: 4 nav items (schedule, patients, crm, guide), lands on crm. The doctor shell is WB2, the owner shell is WA1.',
  }),
  S('WA3', 'WA', 'Khung · Kế toán (trang chủ Thu ngân)', 'state', [START, { wait: '.sidebar' }], { text: 'Thu ngân' }, {
    role: ACCOUNTANT, sources: ['prototype/shared/staff-context.js#pages', 'prototype/shared/clinic.js#shell'],
    next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: ['D1', 'A6'],
    covers: ['staff:accountant'],
    notes: 'Role shell: 4 nav items (patients, cashier, finance, guide), lands on cashier.',
  }),
  S('WA4', 'WA', 'Thông báo nổi (toast)', 'state', [START, nav('today'), { click: '[data-crm="arrive"]' }, { wait: '.toast' }], { selector: '.toast', text: 'Đã cập nhật hàng đợi' }, {
    sources: ['prototype/shared/clinic.js#toast', 'prototype/shared/crm-ui.js#handle'],
    next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: ['A7'],
    covers: ['crm:arrive', 'crm:missed', 'crm:start', 'dialog:today→Check-in'],
    notes: 'Check-in and Vắng in the reception list act at once and show this toast; they open no dialog. After Check-in the row offers "Bắt đầu" (crm:start). The toast disappears after 2.8 s.',
  }),

  // ---------------------------------------------------------------- WB operations
  S('WB1', 'WB', 'Tổng quan', 'page', [START, nav('dashboard')], { selector: '.page-title', text: 'Tổng quan' }, {
    sources: ['prototype/shared/crm-ui.js#dashboard', 'prototype/shared/clinic.js#metric'],
    next_route: '/dashboard', next_status: 'built (U2)', app_canvas: ['I1', 'A1'], legacy_shot: 'dashboard',
    covers: ['nav:dashboard', 'crm:queue', 'crm:filter'],
  }),
  S('WB2', 'WB', 'Tổng quan · Bác sĩ', 'state', [START, nav('dashboard')], { text: 'Doanh số của tôi' }, {
    role: DOCTOR, sources: ['prototype/shared/crm-ui.js#doctorHome'],
    next_route: '/dashboard', next_status: 'built (U2)', app_canvas: ['B1', 'B2'],
    covers: ['staff:doctor-tam', 'staff:doctor-mai', 'staff:doctor-an', 'staff:doctor-lan', 'crm:doctor-today', 'crm:doctor-patients', 'crm:doctor-followups'],
    notes: 'Doctor role: sidebar of 8 items; dashboard is doctorHome, not the owner dashboard.',
  }),
  S('WB3', 'WB', 'Hôm nay', 'page', [START, nav('today')], { selector: '#crm-today-search' }, {
    sources: ['prototype/shared/crm-ui.js#today'],
    next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I2', 'A1'], legacy_shot: 'today',
    covers: ['nav:today', 'crm:today-status', 'crm:today-page', 'crm:profile'],
  }),
  S('WB4', 'WB', 'Hôm nay · lọc không có kết quả', 'state', [START, nav('today'), { click: '[data-crm="today-status"][data-id="cancelled"]' }], { selector: '#crm-today-search' }, {
    sources: ['prototype/shared/crm-ui.js#today'],
    next_route: '/today', next_status: 'restyle (U1)', app_canvas: [],
    notes: 'Status tile "Đã hủy" selected: the list shows its empty message.',
  }),
  S('WB5', 'WB', 'Điều phối lịch', 'page', [START, nav('schedule')], { selector: '#ops-date' }, {
    sources: ['prototype/shared/operations-ui.js#schedule', 'prototype/shared/operations-data.js'],
    next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I3', 'A2'], legacy_shot: 'schedule',
    covers: ['nav:schedule', 'ops:previous', 'ops:next', 'ops:today', 'ops:view', 'ops:doctor', 'ops:profile'],
    notes: 'Room columns by half hour, doctor and room filters, waiting list with "Xếp lịch →". Dragging a booking onto a free slot opens the booking dialog (WB8).',
  }),
  S('WB6', 'WB', 'Điều phối lịch · 7 ngày', 'state', [START, nav('schedule'), { click: '[data-ops="view"][data-value="week"]' }], { selector: '.week-grid' }, {
    sources: ['prototype/shared/operations-ui.js#schedule'],
    next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I3'],
    notes: 'Seven day columns, each with its count, cards and "＋ Đặt lịch". Every day of the demo week has bookings, so the empty-day text "Chưa có lịch" exists in code only.',
  }),
  S('WB7', 'WB', 'Đặt lịch hẹn', 'dialog', [START, nav('today'), { click: '[data-ops="new"]' }, { wait: '#booking-form' }], { selector: '#booking-form', text: 'Đặt lịch hẹn' }, {
    sources: ['prototype/shared/operations-ui.js#edit', 'prototype/shared/operations-ui.js#preview'],
    next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I4', 'F8'],
    covers: ['ops:new', 'ops:suggest', 'dialog:today→Đặt lịch mới', 'dialog:schedule→Đặt lịch', 'modal:appointment'],
    notes: 'Opened from Hôm nay (Đặt lịch mới), Điều phối lịch (Đặt lịch, an empty slot) and, after the CSKH outcome "Đã đặt lịch", from the Xử lý dialog. Same form each time. "Tìm giờ trống" fills the first free time.',
  }),
  S('WB8', 'WB', 'Chi tiết lịch hẹn', 'dialog', [START, nav('schedule'), { click: '[data-ops="edit"]' }, { wait: '#booking-form' }], { selector: '.cancel-section', text: 'Chi tiết lịch hẹn' }, {
    sources: ['prototype/shared/operations-ui.js#edit'],
    next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['F9'],
    covers: ['ops:edit', 'ops:confirm', 'ops:arrive', 'ops:cancel'],
    notes: 'Status chip, Xác nhận lịch, Check-in, Patient 360 →, the booking form and the cancel section with reason.',
  }),
  S('WB9', 'WB', 'Xếp lịch từ danh sách chờ', 'state', [START, nav('schedule'), { click: '[data-ops="wait"]' }, { wait: '#booking-form' }], { selector: '#booking-form', text: 'Đặt lịch hẹn' }, {
    sources: ['prototype/shared/operations-ui.js#handle'],
    next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['F8'], covers: ['ops:wait'],
    notes: 'Booking dialog prefilled from a waiting-list row (patient, service, note).',
  }),

  // ---------------------------------------------------------------- WC patients and Patient 360
  S('WC1', 'WC', 'Tìm bệnh nhân', 'page', [START, nav('patients')], { selector: '#patient-search' }, {
    sources: ['prototype/shared/clinic.js#patients'],
    next_route: '/patients', next_status: 'built (U1)', app_canvas: ['A3', 'I5'], legacy_shot: 'patients',
    covers: ['nav:patients', 'patientFilter:all', 'patientFilter:active', 'patientFilter:next', 'patientFilter:alerts', 'patient:row'],
  }),
  S('WC2', 'WC', 'Tìm bệnh nhân · không có hồ sơ', 'state', [START, nav('patients'), { fill: ['#patient-search', 'zzzz'] }, { wait: '#clear-search' }], { selector: '#clear-search', text: 'Không tìm thấy hồ sơ' }, {
    sources: ['prototype/shared/clinic.js#patients'],
    next_route: '/patients', next_status: 'built (U1)', app_canvas: [],
  }),
  S('WC3', 'WC', 'Thêm người bệnh', 'modal', [START, nav('patients'), { click: '[data-modal="patient"]' }, { wait: MODAL }], { selector: '#new-name', text: 'Thêm người bệnh' }, {
    sources: ['prototype/shared/clinic.js#modalHtml'],
    next_route: null, next_status: 'none', app_canvas: ['I5'], covers: ['modal:patient', 'action:create-patient', 'dialog:patients→Hồ sơ mới'],
  }),
  S('WC4', 'WC', 'Patient 360 · Tổng quan', 'tab', [START, ...P360], { selector: '.patient-hero', text: 'Hồ sơ P001' }, {
    sources: ['prototype/shared/clinic.js#patient360', 'prototype/shared/clinic.js#overview', 'prototype/shared/crm-ui.js#summary', 'prototype/shared/care-finance.js#planPanel'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['F1'], legacy_shot: 'patient-overview',
    covers: ['tab:overview', 'patient:row', 'crm:patient-crm', 'careNav:cashier', 'careAction:approve-prescription', 'careAction:add-prescription'],
    notes: 'Hero (avatar, chips, AI brief, Nhắn tin, Ghi buổi điều trị), tab bar, summary cards, plus the linked workspace panels (Dịch vụ & liệu trình, Đơn thuốc, order history) that care-finance.js injects under every tab except crm and history.',
  }),
  S('WC5', 'WC', 'Patient 360 · Tư vấn', 'tab', [START, ...P360, tab('consult')], { selector: '#consult-input' }, {
    sources: ['prototype/shared/clinic.js#consult', 'prototype/shared/crm-ui.js#clinical'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['J1', 'F2'], legacy_shot: 'patient-consult',
    covers: ['tab:consult', 'action:generate-note'],
  }),
  S('WC6', 'WC', 'Patient 360 · Tư vấn · bản nháp ghi chú', 'state', [START, ...P360, tab('consult'), { fill: ['#consult-input', 'Đáp ứng tốt, da dịu hơn.'] }, { click: '[data-action="generate-note"]' }, { wait: '#editable-draft' }], { selector: '#editable-draft' }, {
    sources: ['prototype/shared/clinic.js#consult'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['F2'], covers: ['action:approve-note'],
    notes: 'AI draft state: editable draft with Duyệt (the rule "AI chỉ là bản nháp" must stay).',
  }),
  S('WC7', 'WC', 'Patient 360 · Kế hoạch', 'tab', [START, ...P360, tab('plan')], { selector: '[data-modal="plan-edit"]' }, {
    sources: ['prototype/shared/clinic.js#plan'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['J3'], legacy_shot: 'patient-plan', covers: ['tab:plan'],
  }),
  S('WC8', 'WC', 'Patient 360 · Buổi điều trị', 'tab', [START, ...P360, tab('session')], { selector: '#session-note' }, {
    sources: ['prototype/shared/clinic.js#session'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['J5', 'F3'], legacy_shot: 'patient-session',
    covers: ['tab:session', 'action:save-session'],
  }),
  S('WC9', 'WC', 'Patient 360 · Ảnh trước / sau', 'tab', [START, ...P360, tab('photos')], { selector: '#studio-view' }, {
    sources: ['prototype/shared/clinic.js#photos'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['I7'], legacy_shot: 'patient-photos',
    covers: ['tab:photos', 'action:studio-mode', 'action:capture'],
  }),
  S('WC10', 'WC', 'Patient 360 · Dịch vụ & tài chính', 'tab', [START, ...P360, tab('finance')], { text: 'Dịch vụ & liệu trình' }, {
    sources: ['prototype/shared/crm-ui.js#financial', 'prototype/shared/care-finance.js#planPanel'],
    next_route: null, next_status: 'none', app_canvas: ['J6'], covers: ['tab:finance', 'careAction:add-service'],
    notes: 'No Next.js target yet: invoices, deposits and service plans of one patient (U5/U6 decide).',
  }),
  S('WC11', 'WC', 'Patient 360 · CRM & CSKH', 'tab', [START, ...P360, tab('crm')], { selector: '[data-crm="expected"]' }, {
    sources: ['prototype/shared/crm-ui.js#patient'],
    next_route: '/patients/[id]', next_status: 'built (U1)', app_canvas: ['J7', 'C5'], covers: ['tab:crm'],
    notes: 'Mapped to the care cards of the Tổng quan tab in the Next.js app.',
  }),
  S('WC12', 'WC', 'Patient 360 · Lịch sử', 'tab', [START, ...P360, tab('history')], { text: 'Lịch sử' }, {
    sources: ['prototype/shared/crm-ui.js#timeline'],
    next_route: '/patients/[id]', next_status: 'built (U1)', app_canvas: ['J8'], covers: ['tab:history'],
    notes: 'Mapped to the timeline card of the Tổng quan tab in the Next.js app.',
  }),
  S('WC13', 'WC', 'Brief trước buổi hẹn', 'modal', [START, ...P360, { click: '[data-modal="note"]' }, { wait: MODAL }], { selector: '#brief-edit', text: 'Brief trước buổi hẹn' }, {
    sources: ['prototype/shared/clinic.js#modalHtml'],
    next_route: null, next_status: 'none', app_canvas: ['J2'], covers: ['modal:note', 'action:copy-brief', 'action:approve-brief'],
    notes: 'AI draft modal: "Pema AI · bản nháp", source line, Sao chép, Duyệt & lưu brief.',
  }),
  S('WC14', 'WC', 'Gửi cập nhật cho người bệnh', 'modal', [START, ...P360, { click: '[data-modal="message"]' }, { wait: MODAL }], { selector: '#message-input', text: 'Gửi cập nhật' }, {
    sources: ['prototype/shared/clinic.js#modalHtml'],
    next_route: '/inbox', next_status: 'restyle (U1)', app_canvas: ['J9'], covers: ['modal:message', 'action:send-message'],
  }),
  S('WC15', 'WC', 'Thông tin cần nhớ', 'modal', [START, ...P360, { click: '[data-modal="edit"]' }, { wait: MODAL }], { selector: '#alerts-edit', text: 'Thông tin cần nhớ' }, {
    sources: ['prototype/shared/clinic.js#modalHtml'],
    next_route: null, next_status: 'none', app_canvas: ['J10'], covers: ['modal:edit', 'action:save-facts'],
  }),
  S('WC16', 'WC', 'Chăm sóc tại nhà', 'modal', [START, ...P360, { click: '[data-modal="care"]' }, { wait: MODAL }], { selector: '#care-edit', text: 'Chăm sóc tại nhà' }, {
    sources: ['prototype/shared/clinic.js#modalHtml'],
    next_route: null, next_status: 'none', app_canvas: ['J11'], covers: ['modal:care', 'action:save-care'],
  }),
  S('WC17', 'WC', 'Điều chỉnh kế hoạch', 'modal', [START, ...P360, tab('plan'), { click: '[data-modal="plan-edit"]' }, { wait: MODAL }], { selector: '#plan-name', text: 'Điều chỉnh kế hoạch' }, {
    sources: ['prototype/shared/clinic.js#modalHtml'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['J4'], covers: ['modal:plan-edit', 'action:save-plan'],
  }),
  S('WC18', 'WC', 'Ngày dự kiến quay lại', 'dialog', [START, ...P360, { click: '[data-crm="expected"]' }, { wait: '#crm-expected-form' }], { selector: '#crm-expected-form', text: 'Ngày dự kiến quay lại' }, {
    sources: ['prototype/shared/crm-ui.js#handle'],
    next_route: null, next_status: 'none', app_canvas: ['J7'], covers: ['crm:expected'],
  }),
  S('WC19', 'WC', 'Thêm dịch vụ vào liệu trình', 'dialog', [START, ...P360, { click: '[data-care-action="add-service"]' }, { wait: '#linked-service-form' }], { selector: '#linked-service-form', text: 'Thêm dịch vụ vào liệu trình' }, {
    sources: ['prototype/shared/care-finance.js#addService'],
    next_route: null, next_status: 'none', app_canvas: ['J6'], covers: ['careAction:add-service'],
    notes: 'Only roles with the billing capability (owner, accountant) get the button.',
  }),

  S('WC20', 'WC', 'Patient 360 · hồ sơ vừa tạo', 'state', [START, nav('patients'), { click: '[data-modal="patient"]' }, { fill: ['#new-name', 'Nguyễn Thử Nghiệm'] }, { click: '[data-action="create-patient"]' }, { wait: '.patient-hero' }], { selector: '.patient-hero', text: 'Chờ bác sĩ thiết lập kế hoạch' }, {
    sources: ['prototype/shared/clinic.js#action', 'prototype/shared/clinic.js#overview', 'prototype/shared/crm-ui.js#summary'],
    next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['F1'],
    notes: 'Right after "Tạo hồ sơ": a patient with no plan, sessions or invoices (empty variants of the cards, "Cần khai thác tiền sử" alert, "Chờ bác sĩ thiết lập kế hoạch"). The new record is added to the demo data of the browser only.',
  }),
  S('WC21', 'WC', 'Patient 360 · Lịch sử · chưa có hoạt động', 'state', [START, nav('patients'), { click: '[data-modal="patient"]' }, { fill: ['#new-name', 'Nguyễn Thử Nghiệm'] }, { click: '[data-action="create-patient"]' }, { wait: '.patient-hero' }, tab('history'), { wait: '.content' }], { text: 'Chưa có hoạt động CSKH được ghi nhận.' }, {
    sources: ['prototype/shared/crm-ui.js#timeline'],
    next_route: '/patients/[id]', next_status: 'built (U1)', app_canvas: ['J8'],
    notes: 'Empty variant of the history tab.',
  }),

  // ---------------------------------------------------------------- WD CSKH and follow-up
  S('WD1', 'WD', 'CSKH hôm nay', 'page', [START, nav('crm')], { selector: '#crm-search' }, {
    sources: ['prototype/shared/crm-ui.js#queue'],
    next_route: '/crm', next_status: 'built (U7)', app_canvas: ['C1', 'C2', 'C3', 'C4'],
    covers: ['nav:crm', 'crm:queue-page', 'crm:filter', 'crm:queue'],
  }),
  S('WD2', 'WD', 'Ghi nhận CSKH (Xử lý)', 'dialog', [START, nav('crm'), { click: '[data-crm="task"]' }, { wait: '#crm-task-form' }], { selector: '#crm-task-form', text: 'Chăm sóc' }, {
    sources: ['prototype/shared/crm-ui.js#task'],
    next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I13', 'C6'],
    covers: ['crm:task', 'dialog:crm→Xử lý'],
    notes: 'The submit button reads "Tiếp tục → Đặt lịch" when the outcome is "Đã đặt lịch" and then opens the booking dialog (WB7). The Xử lý button of Theo dõi opens WD7, not this dialog.',
  }),
  S('WD3', 'WD', 'Protocol chăm sóc mẫu', 'dialog', [START, nav('crm'), { click: '[data-crm="protocol"]' }, { wait: MODAL }], { text: 'Protocol chăm sóc mẫu' }, {
    sources: ['prototype/shared/crm-ui.js#handle'],
    next_route: '/crm', next_status: 'built (U7)', app_canvas: [], covers: ['crm:protocol'],
  }),
  S('WD4', 'WD', 'Kết quả chăm sóc đã ghi', 'dialog', [START, nav('crm'), { click: '[data-crm="activity"]' }, { wait: MODAL }], { text: 'Kết quả chăm sóc đã ghi' }, {
    sources: ['prototype/shared/crm-ui.js#handle'],
    next_route: '/crm', next_status: 'built (U7)', app_canvas: [], covers: ['crm:activity'],
  }),
  S('WD5', 'WD', 'Nhóm khách (vòng đời)', 'dialog', [START, nav('dashboard'), { click: '[data-crm="segment"][data-id="treating"]' }, { wait: MODAL }], { text: 'Đang điều trị' }, {
    sources: ['prototype/shared/crm-ui.js#handle', 'prototype/shared/crm-ui.js#dashboard'],
    next_route: '/crm', next_status: 'built (U7)', app_canvas: [], covers: ['crm:segment'],
    notes: 'Opened from a lifecycle tile of the dashboard; the title is the stage label (5 stages).',
  }),
  S('WD6', 'WD', 'Theo dõi', 'page', [START, nav('followups')], { selector: '.followup-card' }, {
    sources: ['prototype/shared/clinic.js#followups'],
    next_route: '/inbox', next_status: 'restyle (U1)', app_canvas: ['I6', 'A4'], legacy_shot: 'followups',
    covers: ['nav:followups', 'followupFilter:all', 'followupFilter:image', 'followupFilter:urgent', 'followupFilter:overdue', 'patient:link'],
    notes: 'The bell icon in the topbar opens this page. The empty message "Inbox đã sạch" appears only when every item is resolved (not scripted).',
  }),
  S('WD7', 'WD', 'Duyệt phản hồi follow-up', 'dialog', [START, nav('followups'), { click: '[data-action="view-followup"]' }, { wait: MODAL }], { selector: '#review-reply' }, {
    sources: ['prototype/shared/clinic.js#action'],
    next_route: '/review', next_status: 'restyle (U1)', app_canvas: ['F10'],
    covers: ['action:view-followup', 'action:review-submit', 'dialog:followups→Xử lý'],
    notes: 'Shows the patient image when the item has one; the reply is edited before "Duyệt, phản hồi & đóng mục".',
  }),

  S('WD8', 'WD', 'CSKH hôm nay · không có việc phù hợp', 'state', [START, nav('crm'), { fill: ['#crm-search', 'zzzz'] }, { press: ['#crm-search', 'Enter'] }, { wait: '#crm-search' }], { text: 'Không có việc phù hợp' }, {
    sources: ['prototype/shared/crm-ui.js#queue'],
    next_route: '/crm', next_status: 'built (U7)', app_canvas: ['C4'],
    notes: 'Search with no match: the list shows its empty message. Other empty variants not scripted: "Không còn việc CSKH mở", "Inbox đã sạch", "Đã xếp hết danh sách chờ".',
  }),

  // ---------------------------------------------------------------- WE studio, resources, services
  S('WE1', 'WE', 'Ảnh trước / sau', 'page', [START, nav('studio')], { selector: '#studio-view' }, {
    sources: ['prototype/shared/clinic.js#studio', 'prototype/shared/clinic.js#photos'],
    next_route: '/studio', next_status: 'planned (U4)', app_canvas: ['I7'], legacy_shot: 'studio', covers: ['nav:studio'],
  }),
  S('WE2', 'WE', 'Ảnh trước / sau · so sánh trượt', 'state', [START, nav('studio'), { click: '[data-action="studio-mode"]' }, { wait: '#comparison-slider' }], { selector: '#comparison-slider' }, {
    sources: ['prototype/shared/clinic.js#photos'],
    next_route: '/studio', next_status: 'planned (U4)', app_canvas: ['I7'],
    notes: 'Illustrative photos only; no efficacy score.',
  }),
  S('WE3', 'WE', 'Bác sĩ & phòng', 'page', [START, nav('resources')], { selector: '[data-ops="block"]' }, {
    sources: ['prototype/shared/operations-ui.js#resources'],
    next_route: '/resources', next_status: 'planned (U4)', app_canvas: ['F14'], legacy_shot: 'resources',
    covers: ['nav:resources', 'ops:doctor', 'ops:unblock'],
  }),
  S('WE4', 'WE', 'Khóa thời gian phòng', 'dialog', [START, nav('resources'), { click: '[data-ops="block"]' }, { wait: MODAL }], { text: 'Khóa thời gian phòng' }, {
    sources: ['prototype/shared/operations-ui.js#handle'],
    next_route: '/resources', next_status: 'planned (U4)', app_canvas: ['I8'], covers: ['ops:block', 'ops:save-block', 'dialog:resources→Khóa phòng'],
  }),
  S('WE5', 'WE', 'Dịch vụ', 'page', [START, nav('services')], { selector: '[data-ops="service"]' }, {
    sources: ['prototype/shared/operations-ui.js#services'],
    next_route: '/services', next_status: 'planned (U4)', app_canvas: ['F13'], legacy_shot: 'services', covers: ['nav:services'],
  }),
  S('WE6', 'WE', 'Chỉnh dịch vụ', 'dialog', [START, nav('services'), { click: '[data-ops="service"]' }, { wait: MODAL }], { text: 'Chỉnh dịch vụ' }, {
    sources: ['prototype/shared/operations-ui.js#handle'],
    next_route: '/services', next_status: 'planned (U4)', app_canvas: ['I9'], covers: ['ops:service', 'ops:save-service', 'dialog:services→Chỉnh dịch vụ'],
  }),

  // ---------------------------------------------------------------- WF cashier and orders
  S('WF1', 'WF', 'Thu ngân', 'page', [START, nav('cashier')], { selector: '[data-ops="quick-order"]' }, {
    sources: ['prototype/shared/operations-ui.js#cashier', 'prototype/shared/operations-ui.js#invoices', 'prototype/shared/order-ui.js#history'],
    next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['I10', 'F11', 'D1'], legacy_shot: 'cashier',
    covers: ['nav:cashier', 'ops:invoice-filter', 'ops:invoice-page', 'ops:print-order', 'careNav:cashier', 'order:preview'],
    notes: 'Invoice list (filters Tất cả, Còn phải thu, Đã thanh toán, paging) and the order history panel (Xem / in, Sửa nháp).',
  }),
  S('WF2', 'WF', 'Thu tiền', 'dialog', [START, nav('cashier'), { click: '[data-ops="pay"]' }, { wait: MODAL }], { text: 'Thu tiền' }, {
    sources: ['prototype/shared/operations-ui.js#handle'],
    next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['I11', 'F12'], covers: ['ops:pay', 'ops:save-pay', 'dialog:cashier→Thu tiền'],
  }),
  S('WF3', 'WF', 'Tạo đơn thuốc / phiếu tư vấn', 'dialog', [START, nav('cashier'), { click: '[data-ops="quick-order"]' }, { wait: '#catalog-order-form' }], { selector: '#catalog-order-form', text: 'Tạo đơn thuốc / phiếu tư vấn' }, {
    sources: ['prototype/shared/order-ui.js#open'],
    next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['F4'],
    covers: ['ops:quick-order', 'dialog:cashier→Mở form lên đơn nhanh', 'careAction:add-prescription'],
    notes: 'Product search over the 115-item Excel catalog, empty cart, total, general note, the rule that "Không in" only removes a line from the sheets.',
  }),
  S('WF4', 'WF', 'Lên đơn · đã chọn sản phẩm', 'state', [START, ...draftSteps(['H002', 'H005']), { wait: '[data-line]' }], { selector: '[data-line]' }, {
    sources: ['prototype/shared/order-ui.js#open'],
    next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['F5'],
    notes: 'Cart lines with quantity, sheet type (Đơn thuốc, Phiếu tư vấn, Không in, Cần phân loại), usage, note and reason for a changed type. Lines: one prescription product and one consultation product.',
  }),
  S('WF5', 'WF', 'Tách đơn · bản nháp', 'page', [START, ...draftSteps(['H002', 'H005']), { clickPopup: '#quick-save' }, { wait: '.order-sheet' }], { selector: '.order-sheet', text: 'BẢN NHÁP' }, {
    sources: ['prototype/shared/order-review.js#sheet', 'prototype/order-review/index.html', 'prototype/shared/order-review.css'],
    next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F6', 'F7'],
    covers: ['order:review-page', 'order:print', 'order:approve', 'print:PRESCRIPTION', 'print:CONSULTATION', 'print:all'],
    notes: 'Standalone page /order-review/ opened in a new tab: toolbar (print buttons disabled until approved), draft mark, A5 portrait sheets "ĐƠN THUỐC" and "PHIẾU TƯ VẤN". The A5 print layout is the print media of the same page.',
  }),
  S('WF6', 'WF', 'Tách đơn · đã duyệt', 'state', [START, ...draftSteps(['H002', 'H005']), { clickPopup: '#quick-save' }, { wait: '#approve' }, { click: '#approve' }, { wait: 'body[data-approved="true"]' }], { selector: 'body[data-approved="true"]', text: 'Đã duyệt' }, {
    sources: ['prototype/shared/order-review.js#refresh'],
    next_route: '/orders/[id]/print', next_status: 'planned (U5)', app_canvas: ['F7'], covers: ['order:approve'],
    notes: 'Approved: print buttons enabled, draft mark gone, signature block shows the reviewer. window.print() is a native dialog.',
  }),
  S('WF7', 'WF', 'Tách đơn · sản phẩm cần phân loại', 'state', [START, ...draftSteps(['H002', 'H095'], false), { clickPopup: '#quick-save' }, { wait: '#review-excluded .warning' }], { selector: '#review-excluded .warning', text: 'Cần phân loại' }, {
    sources: ['prototype/shared/order-review.js#refresh'],
    next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F5'],
    notes: 'A product without a type in the Excel catalog: warning above the sheets, approve button disabled.',
  }),
  S('WF8', 'WF', 'Tách đơn · thiếu mã đơn', 'state', [{ goto: '/order-review/' }, { wait: '#review-error' }], { selector: '#review-error', text: 'Thiếu mã bệnh nhân hoặc mã đơn.' }, {
    sources: ['prototype/shared/order-review.js#refresh'],
    next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: [],
    notes: 'Error state of the standalone page opened without patient and order codes.',
  }),
  S('WF9', 'WF', 'Sửa đơn nháp', 'state', [START, ...draftSteps(['H002']), { clickPopup: '#quick-save' }, { wait: '.order-sheet' }, { main: true }, { goto: '/clinic-web/?staff={role}&screen=cashier' }, { click: '[data-order-edit]' }, { wait: '#catalog-order-form' }], { selector: '#catalog-order-form', text: 'Sửa đơn nháp' }, {
    sources: ['prototype/shared/order-ui.js#open', 'prototype/shared/order-ui.js#history'],
    next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['F5'], covers: ['order:edit'],
    notes: 'The quick-order dialog opened on an existing draft: title "Sửa đơn nháp", patient locked.',
  }),

  S('WF10', 'WF', 'Lên đơn · không tìm thấy sản phẩm', 'state', [START, nav('cashier'), { click: '[data-ops="quick-order"]' }, { wait: '#catalog-order-form' }, { fill: ['#quick-product-search', 'zzzz'] }, { wait: '#quick-results .empty' }], { selector: '#quick-results .empty', text: 'Không tìm thấy sản phẩm phù hợp.' }, {
    sources: ['prototype/shared/order-ui.js#open'],
    next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['F4'],
  }),

  // ---------------------------------------------------------------- WG finance
  S('WG1', 'WG', 'Tài chính & tiền thủ thuật · Tổng quan', 'page', [START, ...FIN], { selector: '.finance-workspace .hero', text: 'Một màn hình, nắm rõ dòng tiền' }, {
    sources: ['prototype/finance/finance.js#overview', 'prototype/shared/finance-bridge.js'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H1'],
    covers: ['nav:finance', 'financeTab:overview', 'role:finance-owner'],
    notes: 'Header tools: month picker, Làm mới. Needs the finance API (4174). prototype/finance/index.html is only a redirect stub to this page.',
  }),
  S('WG2', 'WG', 'Tài chính · Tiền thủ thuật', 'tab', [START, ...FIN, finTab('work'), { wait: '#export' }], { selector: '#export', text: 'Bảng tiền thủ thuật' }, {
    sources: ['prototype/finance/finance.js#work', 'prototype/finance/finance.js#table'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H3', 'H4'], covers: ['financeTab:work'],
    notes: 'Duyệt, Hủy (native prompt for the reason), Chốt tháng đã kết thúc (native confirm), Xác nhận đã chi (native prompt for the voucher), Xuất CSV (download).',
  }),
  S('WG3', 'WG', 'Tài chính · Ghi lượt thủ thuật đã hoàn tất', 'state', [START, ...FIN, finTab('work'), { click: '#content details > summary' }, { wait: '#entry' }], { selector: '#entry' }, {
    sources: ['prototype/finance/finance.js#entryForm'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H9'],
    notes: 'The collapsible form (patient, service, date, list price, discount, invoice, note, two people with share and rate).',
  }),
  S('WG4', 'WG', 'Tài chính · Chính sách tỷ lệ', 'tab', [START, ...FIN, finTab('rates')], { selector: 'form.rate' }, {
    sources: ['prototype/finance/finance.js#rates'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H8'], covers: ['financeTab:rates'],
  }),
  S('WG5', 'WG', 'Tài chính · Phiếu thu & thông báo', 'tab', [START, ...FIN, finTab('receipts')], { selector: '#payment' }, {
    sources: ['prototype/finance/finance.js#receipts'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H5', 'H6'], covers: ['financeTab:receipts'],
  }),
  S('WG6', 'WG', 'Doanh số của tôi · Tổng quan (bác sĩ)', 'state', [START, ...FIN], { text: 'Công việc được ghi nhận, thu nhập rõ ràng' }, {
    role: DOCTOR, sources: ['prototype/finance/finance.js#overview'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H2'], covers: ['role:finance-doctor'],
    notes: 'Doctor projection: personal hero, tiles "Doanh số của tôi", "Tiền chờ duyệt", only two tabs (Tổng quan, Tiền thủ thuật).',
  }),
  S('WG7', 'WG', 'Doanh số của tôi · Tiền thủ thuật (bác sĩ)', 'state', [START, ...FIN, finTab('work'), { wait: '#export' }], { selector: '#export' }, {
    role: DOCTOR, sources: ['prototype/finance/finance.js#work'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H2', 'H3'],
    notes: 'Doctor projection of the work table: no entry form, no approve or void buttons, no period buttons. The rates and receipts tabs are hidden for a doctor (their placeholder panels are unreachable).',
  }),
  S('WG8', 'WG', 'Tài chính · Tổng quan (kế toán)', 'state', [START, ...FIN], { text: 'KẾ TOÁN • ĐỐI SOÁT' }, {
    role: ACCOUNTANT, sources: ['prototype/finance/finance.js#overview'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['D1', 'H1'], covers: ['role:finance-accountant'],
    notes: 'Accountant projection: hero reads "KẾ TOÁN • ĐỐI SOÁT"; four tabs; the notification box says the accountant does not read the owner inbox.',
  }),
  S('WG9', 'WG', 'Tài chính · Chưa kết nối dữ liệu', 'state', [START, { block: 'http://127.0.0.1:4174/**' }, nav('finance'), { wait: '#error' }], { selector: '#error', text: 'Chưa kết nối dữ liệu tài chính' }, {
    sources: ['prototype/finance/finance.js#load'],
    next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H7'],
    notes: 'Reached by blocking the finance API; the page keeps "Đang tải dữ liệu…" under the error line and the topbar sync link reads "Tài chính chờ kết nối · thử lại".',
  }),

  // ---------------------------------------------------------------- WH ask and guide
  S('WH1', 'WH', 'Ask Pema', 'page', [START, nav('ask')], { selector: '#ask-input' }, {
    sources: ['prototype/shared/clinic.js#ask'],
    next_route: '/ask', next_status: 'built (U7)', app_canvas: ['I12', 'F15'], legacy_shot: 'ask',
    covers: ['nav:ask', 'action:ask-sample', 'action:ask', 'question:chip'],
  }),
  S('WH2', 'WH', 'Ask Pema · có câu trả lời', 'state', [START, nav('ask'), { click: '[data-question]' }, { click: '[data-action="ask"]' }, { wait: '#ask-result' }], { selector: '#ask-result' }, {
    sources: ['prototype/shared/clinic.js#action'],
    next_route: '/ask', next_status: 'built (U7)', app_canvas: ['I12', 'F15'],
    notes: 'Answer card with how it was counted and the source records. "Bộ truy vấn mô phỏng ... chưa tích hợp mô hình AI".',
  }),
  S('WH3', 'WH', 'Hướng dẫn sử dụng', 'page', [START, nav('guide')], { selector: '#guide-search', text: 'Hiểu hệ thống Pema' }, {
    sources: ['prototype/shared/guide.js#render', 'prototype/shared/guide.js#navigation', 'prototype/shared/guide.css'],
    next_route: '/guide', next_status: 'built (U7)', app_canvas: ['F16'], legacy_shot: 'guide',
    covers: ['nav:guide', 'guide:system'],
    notes: 'Default article "Hiểu hệ thống Pema" with the five-step care map. Each other article is its own state (WH4..WH13); the article text is content, the layout is this one.',
  }),
  ...GUIDE_ARTICLES.map(([id, title], i) =>
    S(`WH${4 + i}`, 'WH', `Hướng dẫn · ${title}`, 'state', [START, nav('guide'), { click: `[data-guide="${id}"]` }, { wait: '#guide-title' }], { selector: '#guide-title', text: title }, {
      sources: ['prototype/shared/guide.js#topics', 'prototype/shared/guide.js#render'],
      next_route: '/guide', next_status: 'built (U7)', app_canvas: ['F16'], covers: [`guide:${id}`],
    }),
  ),
  S('WH14', 'WH', 'Hướng dẫn · không tìm thấy chủ đề', 'state', [START, nav('guide'), { fill: ['#guide-search', 'zzzz'] }, { wait: '#guide-topics .notice' }], { selector: '#guide-topics .notice', text: 'Không tìm thấy' }, {
    sources: ['prototype/shared/guide.js#navigation'],
    next_route: '/guide', next_status: 'built (U7)', app_canvas: [],
  }),
];

// ====================================================================================================================
// W6a: gaps closed after W0 (owner rule: no screen or state of the old web may be missing).
// New ids are appended at the end of their group; nothing above this line was renumbered. Group WI is new: the
// Patient Mobile web (prototype/patient-mobile, shared/patient.js, the mobile injection of shared/care-finance.js).
// Entry fields added in W6a: `viewport` (the walk and the captures open this page at that size), `frames` (override of
// the per-kind frame list), `native` (a native confirm / prompt / print / download / select popup: the entry is the page
// before the call, `native.trigger` fires it, the walk checks the captured message), `covers` with `text:` and `id:`
// claims (checked against the live page), `sources` as <file>#<function> (claimed by the static guard).
// ====================================================================================================================

const BLOCK_FIN = { block: 'http://127.0.0.1:4174/**' };
const HOLD_FIN = { hold: 'http://127.0.0.1:4174/**' };
const patientRow = (id) => [nav('patients'), { click: `tr[data-patient="${id}"]` }, { wait: '.patient-hero' }];
const NEWP = [nav('patients'), { click: '[data-modal="patient"]' }, { fill: ['#new-name', 'Nguyễn Thử Nghiệm'] }, { click: '[data-action="create-patient"]' }, { wait: '.patient-hero' }];
const CRM_TASK = [nav('crm'), { click: '[data-crm="task"]' }, { wait: '#crm-task-form' }];
const BOOK = [nav('today'), { click: '[data-ops="new"]' }, { wait: '#booking-form' }];
const BOOK_SUBMIT = { click: '#booking-form [type=submit]' };
const EDIT_FIRST = [nav('schedule'), { click: '[data-ops="edit"]' }, { wait: '#booking-form' }];
const QUICK_FORM = [nav('cashier'), { click: '[data-ops="quick-order"]' }, { wait: '#catalog-order-form' }];
// draft order steps with the finance API blocked: saving an order creates an invoice that the finance bridge would
// otherwise mirror into the shared finance database
const draftBlocked = (codes, usage = true) => [BLOCK_FIN, START, ...draftSteps(codes, usage)];
const SAVE_ORDER = [{ clickPopup: '#quick-save' }, { wait: '.order-sheet, #review-error' }];
const FIN_WORK = [...FIN, finTab('work')];
const FIN_RECEIPTS = [...FIN, finTab('receipts')];
// Set-up of the closed and paid period states. The finance server only closes a month that has rows and no pending
// row, and the shared month 2026-09 must stay open, so a month in the past gets one entry (linked to an existing web
// invoice, so no invoice and no debt is added), is approved and closed. Every step is guarded: a second run changes
// nothing.
const finPeriod = (month, patient, invoice, day) => [
  { setValue: ['#month', month] },
  { wait: '#export' },
  { ifVisible: ['td:has-text("Chưa có lượt thủ thuật")', [
    { click: '#content details > summary' }, { wait: '#entry' },
    { select: ['#entry [name=patient]', patient] }, { setValue: ['#entry [name=date]', day] },
    { select: ['#entry [name=invoice]', invoice] }, { fill: ['#entry [name=note]', 'Đã thực hiện, chờ đối soát'] },
    { click: '#entry [type=submit]' }, { wait: '[data-command="approve"]' },
  ] ] },
  { ifVisible: ['[data-command="approve"]', [{ click: '[data-command="approve"]' }, { wait: '[data-command="close"]' }]] },
  { ifVisible: ['[data-command="close"]', [{ dialog: 'accept' }, { click: '[data-command="close"]' }, { wait: '[data-command="paid"]' }]] },
];
const FIN_CLOSED = [...FIN_WORK, ...finPeriod('2026-08', 'P002', 'WEB:P002:HD-0002', '2026-08-10')];
const FIN_PAID = [
  ...FIN_WORK, ...finPeriod('2026-07', 'P003', 'WEB:P003:HD-0003', '2026-07-10'),
  { ifVisible: ['[data-command="paid"]', [{ dialog: 'accept' }, { click: '[data-command="paid"]' }, { wait: '.finance-workspace .badge:has-text("Đã chi")' }]] },
];
// Patient Mobile web
const MOBILE = [{ goto: '/patient-mobile/' }, { wait: '.mobile-app' }];
const mnav = (screen) => ({ click: `.mobile-nav [data-screen="${screen}"]` });
const MPROFILE = [...MOBILE, mnav('profile')];
const mgroup = (g) => [...MPROFILE, { select: ['#case-group', g] }];
const mrow = (screen) => ({ click: `.doc-row[data-screen="${screen}"]` });
const MSEND = [...MOBILE, mnav('messages'), { click: '.btn[data-screen="send"]' }, { wait: '#patient-message' }];
const MNEW = [START, ...NEWP, ...MOBILE, mnav('profile'), { select: ['#identity-select', 'P047'] }, { gone: '.mobile-toast' }];
const MV = [390, 844];
// the clinic web resolves one open CSKH task of the first row
const resolveTask = [{ click: '[data-crm="task"]' }, { wait: '#crm-task-form' }, { select: ['#crm-outcome', 'no_need'] }, { fill: ['#crm-note', 'Đã trao đổi, chưa có nhu cầu.'] }, { click: '#crm-submit' }, { wait: '.patient-hero, .crm-queue' }];
const WAIT_ROOM = ['R0', 'R0', 'R2', 'R3', 'R0', 'R0'];
const waitSteps = WAIT_ROOM.flatMap((room) => [
  { ifVisible: ['[data-ops="wait"]', [{ click: '[data-ops="wait"]' }, { wait: '#booking-form' }, { select: ['#booking-room', room] }, { click: '[data-ops="suggest"]' }, BOOK_SUBMIT, { gone: '.modal' }]] },
]);

const MOBILE_COMMON = { next_route: null, next_status: 'none', viewport: MV, frames: ['390x844'] };
const STEP_CARDS = {
  d1: ['Sau thủ thuật D+1', 'Hôm nay bạn cảm thấy thế nào?'],
  d3: ['D+3 cần ảnh', 'Cập nhật ảnh tiến triển'],
  d7: ['D+7 bác sĩ review', 'Cùng bác sĩ xem lại tiến triển'],
  overdue: ['Quá hạn tái khám', 'Sắp xếp lần tái khám tiếp theo'],
  no_show: ['Vắng/hủy chưa đặt lại', 'Chọn lại một lịch hẹn phù hợp'],
  abandoned: ['Nguy cơ bỏ liệu trình', 'Tiếp tục kế hoạch chăm sóc'],
  dormant90: ['90 ngày chưa quay lại', 'Pema sẵn sàng đồng hành'],
  dormant180: ['180 ngày chưa quay lại', 'Kết nối lại với Pema'],
  birthday: ['Sinh nhật trong tuần', 'Một lời chúc từ Pema'],
};

const added = {
  WA: [
    S('WA5', 'WA', 'Đặt lại dữ liệu demo (hộp xác nhận)', 'state', [START, { wait: '#reset-demo' }], { selector: '#reset-demo' }, {
      sources: ['prototype/shared/clinic.js#bind'], next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: [],
      native: { type: 'confirm', message: 'Đặt lại dữ liệu demo?', trigger: [{ dialog: 'dismiss' }, { click: '#reset-demo' }] },
      notes: 'Native confirm() raised by the reset icon in the topbar. The shot is the page right before the call; W3 draws the dialog with this exact text. Accepting it restores the demo data and shows the toast "Đã khôi phục dữ liệu demo".',
    }),
    S('WA6', 'WA', 'Chọn tài khoản demo (danh sách của trình duyệt)', 'state', [START, { wait: '#staff-account' }], { selector: '#staff-account', text: 'Tài khoản demo' }, {
      sources: ['prototype/shared/staff-context.js#picker'], next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: ['A6'],
      native: { type: 'select', selector: '#staff-account', options: ['BS. Tâm · Chủ phòng khám', 'BS. Tâm · Bác sĩ điều trị', 'BS. Mai · Bác sĩ điều trị', 'BS. An · Bác sĩ điều trị', 'BS. Lan · Bác sĩ điều trị', 'Mai Anh · CSKH', 'Thu · CSKH', 'Kế toán · Đối soát & thu ngân'], trigger: [] },
      notes: 'The role picker is a native <select>: the open list is drawn by the browser and cannot be captured, so the eight options are recorded here (owner, four doctors, two CSKH, accountant). Choosing one reloads the shell for that role (WA1, WA2, WA3, WB2).',
    }),
    S('WA7', 'WA', 'Liên kết "Đến nội dung chính" (khi focus bàn phím)', 'state', [START, { key: 'Tab' }], { selector: '.skip-link:focus', text: 'Đến nội dung chính' }, {
      sources: ['prototype/shared/clinic.js#shell', 'prototype/shared/workspace-layout.css'], next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: [],
      notes: 'First Tab press: the skip link appears at the top left of the content column (hidden until focused).',
    }),
    S('WA8', 'WA', 'Khung · liên kết đồng bộ tài chính chờ kết nối', 'state', [BLOCK_FIN, START, { wait: '#finance-sync' }], { selector: '#finance-sync', text: 'Tài chính chờ kết nối · thử lại' }, {
      sources: ['prototype/shared/finance-bridge.js#status'], next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: ['H7'],
      notes: 'finance-bridge.js puts a small link before the topbar controls. With the finance API unreachable it reads "Tài chính chờ kết nối · thử lại" (WA1 shows it as "Tài chính đã đồng bộ").',
    }),
    S('WA9', 'WA', 'Khung · liên kết đang đồng bộ tài chính', 'state', [HOLD_FIN, START, { wait: '#finance-sync' }], { selector: '#finance-sync', text: 'Đang đồng bộ tài chính…' }, {
      sources: ['prototype/shared/finance-bridge.js#status'], next_route: '(app shell)', next_status: 'restyle (U1)', app_canvas: [],
      notes: 'Request to the finance API is pending: the link reads "Đang đồng bộ tài chính…" until the 7 s timeout turns it into WA8.',
    }),
    S('WA10', 'WA', 'Duyệt template native Flutter (trang xem trước)', 'page', [{ goto: '/native-review/' }, { wait: '#device' }], { selector: '#device', text: 'FLUTTER TEMPLATE' }, {
      sources: ['prototype/native-review/index.html'], next_route: null, next_status: 'none', app_canvas: [],
      notes: 'Standalone review page of the old prototype: logo, "Chăm sóc liên tục. Trải nghiệm native.", four review steps, a device-size select (390×844, 360×800, 430×932, 768×1024), a link "Mở app toàn màn hình ↗" and a framed iframe of ../native-preview/ (that folder is not in prototype/, so the frame shows the server 404 page). No link in the Clinic or Patient web leads here; it is reachable by URL only and is listed because it is a page of the old web.',
    }),
  ],
  WB: [
    S('WB10', 'WB', 'Hôm nay · Bác sĩ', 'state', [START, nav('today')], { selector: '#crm-today-search' }, {
      role: DOCTOR, sources: ['prototype/shared/crm-ui.js#today'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I2'],
      notes: 'Doctor projection: only the doctor\'s own appointments, and the tile "Phát sinh hóa đơn hôm nay" is not drawn (8 tiles instead of 9).',
    }),
    S('WB11', 'WB', 'Điều phối lịch · Bác sĩ', 'state', [START, nav('schedule')], { selector: '#ops-doctor:disabled' }, {
      role: DOCTOR, sources: ['prototype/shared/operations-ui.js#schedule', 'prototype/shared/staff-context.js#apply'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I3'],
      notes: 'Doctor projection: the doctor filter is locked to the signed-in doctor (disabled select) and only that doctor\'s bookings are drawn; the waiting list is unchanged.',
    }),
    S('WB12', 'WB', 'Điều phối lịch · ngày không có lịch', 'state', [START, nav('schedule'), { setValue: ['#ops-date', '2026-12-01'] }, { wait: '.day-grid' }], { selector: '.day-grid', text: '0 lịch' }, {
      sources: ['prototype/shared/operations-ui.js#schedule'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I3'],
      notes: 'Day view of a date with no booking: four empty room columns, every header reads "0 lịch", stats show 0.',
    }),
    S('WB13', 'WB', 'Điều phối lịch · 7 ngày · tuần không có lịch', 'state', [START, nav('schedule'), { click: '[data-ops="view"][data-value="week"]' }, { setValue: ['#ops-date', '2026-12-01'] }, { wait: '.week-grid' }], { selector: '.week-grid', text: 'Chưa có lịch' }, {
      sources: ['prototype/shared/operations-ui.js#schedule'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I3'], covers: ['text:Chưa có lịch'],
      notes: 'Seven-day view of a week with no booking: every day column shows "Chưa có lịch" above its "＋ Đặt lịch" button. WB6 is the same view on the demo week.',
    }),
    S('WB14', 'WB', 'Điều phối lịch · đã xếp hết danh sách chờ', 'state', [START, nav('schedule'), ...waitSteps], { selector: '.ops-side', text: 'Đã xếp hết danh sách chờ' }, {
      sources: ['prototype/shared/operations-ui.js#schedule'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I3'], covers: ['text:Đã xếp hết danh sách chờ'],
      notes: 'The six waiting-list cards were each booked through "Xếp lịch →" (room chosen to fit the service); the side panel then reads "Đã xếp hết danh sách chờ.". Browser-local data only.',
    }),
    S('WB15', 'WB', 'Đặt lịch hẹn · đã chọn giờ trống', 'state', [START, ...BOOK, { click: '[data-ops="suggest"]' }], { selector: '#ops-error', text: 'Đã chọn giờ trống. Bấm xác nhận để lưu.' }, {
      sources: ['prototype/shared/operations-ui.js#handle'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I4'], covers: ['id:ops-error'],
      notes: '"Tìm giờ trống" filled the first free time; the confirmation sits in the same line as the errors (#ops-error).',
    }),
    S('WB16', 'WB', 'Đặt lịch hẹn · không có giờ trống', 'state', [START, ...BOOK, { setValue: ['#booking-date', ''] }, { click: '[data-ops="suggest"]' }], { selector: '#ops-error', text: 'Không có giờ trống cho lựa chọn này. Hãy đổi ngày, bác sĩ hoặc phòng.' }, {
      sources: ['prototype/shared/operations-ui.js#handle'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I4'], covers: ['text:Không có giờ trống cho lựa chọn này*', 'id:ops-error'],
      notes: 'Error line #ops-error of the booking dialog after "Tìm giờ trống" finds nothing (reached with the date cleared).',
    }),
    S('WB17', 'WB', 'Đặt lịch hẹn · phòng không phù hợp với dịch vụ', 'state', [START, ...BOOK, { select: ['#booking-service', 'S2'] }, { select: ['#booking-room', 'R1'] }, BOOK_SUBMIT], { selector: '#ops-error', text: 'Phòng không phù hợp với dịch vụ đã chọn.' }, {
      sources: ['prototype/shared/operations-data.js#validate'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I4'], covers: ['id:ops-error'],
      notes: 'Laser service in a room that does not host it. Same error line, text from the room rules.',
    }),
    S('WB18', 'WB', 'Đặt lịch hẹn · ngoài ca hoặc giờ nghỉ', 'state', [START, ...BOOK, { setValue: ['#booking-time', '12:30'] }, BOOK_SUBMIT], { selector: '#ops-error', text: 'Ngoài ca bác sĩ hoặc trùng giờ nghỉ 12:00–13:00.' }, {
      sources: ['prototype/shared/operations-data.js#validate'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I4'], covers: ['id:ops-error'],
    }),
    S('WB19', 'WB', 'Đặt lịch hẹn · trùng lịch của bệnh nhân', 'state', [START, ...BOOK, { setValue: ['#booking-date', '2026-09-20'] }, { setValue: ['#booking-time', '08:00'] }, { select: ['#booking-room', 'R0'] }, BOOK_SUBMIT], { selector: '#ops-error', text: 'Trùng bệnh nhân với lịch 08:00 của Nguyễn Minh Linh.' }, {
      sources: ['prototype/shared/operations-data.js#validate'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I4'], covers: ['id:ops-error'],
    }),
    S('WB20', 'WB', 'Đặt lịch hẹn · ngày giờ không hợp lệ', 'state', [START, ...BOOK, { setValue: ['#booking-date', ''] }, BOOK_SUBMIT], { selector: '#ops-error', text: 'Ngày, giờ hoặc thời lượng không hợp lệ.' }, {
      sources: ['prototype/shared/operations-data.js#validate'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['I4'], covers: ['id:ops-error'],
    }),
    S('WB21', 'WB', 'Chi tiết lịch hẹn · thiếu lý do hủy', 'state', [START, ...EDIT_FIRST, { click: '[data-ops="cancel"]' }], { selector: '#ops-error', text: 'Cần lý do hủy cho lịch đang hoạt động.' }, {
      sources: ['prototype/shared/operations-ui.js#handle'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['F9'], covers: ['id:ops-error'],
    }),
    S('WB22', 'WB', 'Chi tiết lịch hẹn · lịch đã đổi ở cửa sổ khác', 'state', [START, ...EDIT_FIRST,
      { tab: [START, ...EDIT_FIRST, { fill: ['#cancel-reason', 'Khách báo bận'] }, { click: '[data-ops="cancel"]' }, { wait: '.toast' }] },
      { click: '[data-ops="confirm"]' }], { selector: '#ops-error', text: 'Không thể chuyển trạng thái lịch này.' }, {
      sources: ['prototype/shared/operations-data.js#setStatus'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['F9'], covers: ['text:Không thể chuyển trạng thái lịch này*', 'id:ops-error'],
      notes: 'Two browser tabs: the booking dialog stays open in the first tab while the second tab cancels the same booking; "Xác nhận lịch" then fails with this line.',
    }),
    S('WB23', 'WB', 'Chi tiết lịch hẹn · đã xác nhận', 'state', [START, ...EDIT_FIRST, { click: '[data-ops="confirm"]' }, { wait: '.toast' }, { click: '[data-ops="edit"]' }, { wait: '#booking-form' }], { selector: '.booking-status .chip', text: 'Đã xác nhận' }, {
      sources: ['prototype/shared/operations-ui.js#edit'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['F9'],
      notes: 'Status chip of an appointment after "Xác nhận lịch" (toast "Đã cập nhật trạng thái lịch"). Statuses of a booking: Đặt hẹn (WB8), Đã xác nhận (this), Đã đến (WB24); cancelled and missed bookings are not shown on the schedule.',
    }),
    S('WB24', 'WB', 'Chi tiết lịch hẹn · đã check-in', 'state', [START, ...EDIT_FIRST, { click: '[data-ops="arrive"]' }, { wait: '.toast' }, { click: '[data-ops="edit"]' }, { wait: '#booking-form' }], { selector: '.booking-status .chip', text: 'Đã đến' }, {
      sources: ['prototype/shared/operations-ui.js#edit'], next_route: '/schedule', next_status: 'built (U2)', app_canvas: ['F9'],
    }),
    S('WB25', 'WB', 'Hôm nay · Đang chờ (đã check-in)', 'state', [START, nav('today'), { click: 'tr:has([data-crm="profile"][data-id="P001"]) [data-crm="arrive"]' }, { click: '[data-crm="today-status"][data-id="arrived"]' }], { selector: '.crm-reception-table', text: 'Mời vào phòng' }, {
      sources: ['prototype/shared/crm-ui.js#today'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I2'],
      notes: 'Reception status "Đang chờ": the row offers "Mời vào phòng". Reached by Check-in on the first row and the status tile.',
    }),
    S('WB26', 'WB', 'Hôm nay · Đang khám / điều trị', 'state', [START, nav('today'), { click: 'tr:has([data-crm="profile"][data-id="P001"]) [data-crm="arrive"]' }, { click: 'tr:has([data-crm="profile"][data-id="P001"]) [data-crm="start"]' }, { click: '[data-crm="today-status"][data-id="in_progress"]' }], { selector: '.crm-reception-table', text: 'Đang khám/điều trị' }, {
      sources: ['prototype/shared/crm-ui.js#today'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I2'],
    }),
    S('WB27', 'WB', 'Hôm nay · Hoàn tất', 'state', [START, nav('today'), { click: 'tr:has([data-crm="profile"][data-id="P001"]) [data-crm="arrive"]' }, ...patientRow('P001'), tab('session'), { wait: '#session-note' }, { fill: ['#session-note', 'Da ổn định, đáp ứng tốt.'] }, { upload: ['#session-photo', 'png'] }, { click: '[data-action="save-session"]' }, nav('today'), { click: '[data-crm="today-status"][data-id="completed"]' }], { selector: '.crm-reception-table', text: 'Hoàn tất' }, {
      sources: ['prototype/shared/crm-ui.js#today', 'prototype/shared/clinic.js#action'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I2'],
      notes: 'Saving a treatment session (with a synthetic photo) on a checked-in patient completes the appointment.',
    }),
    S('WB28', 'WB', 'Hôm nay · Vắng hẹn', 'state', [START, nav('today'), { click: 'tr:has([data-crm="profile"][data-id="P001"]) [data-crm="missed"]' }, { click: '[data-crm="today-status"][data-id="missed"]' }], { selector: '.crm-reception-table', text: 'Vắng hẹn' }, {
      sources: ['prototype/shared/crm-ui.js#today'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I2'],
    }),
    S('WB29', 'WB', 'Hôm nay · Đã hủy (có lịch hủy)', 'state', [START, ...EDIT_FIRST, { fill: ['#cancel-reason', 'Khách báo bận'] }, { click: '[data-ops="cancel"]' }, { wait: '.toast' }, nav('today'), { click: '[data-crm="today-status"][data-id="cancelled"]' }], { selector: '.crm-reception-table', text: 'Đã hủy' }, {
      sources: ['prototype/shared/crm-ui.js#today'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I2'],
      notes: 'After a cancellation from the schedule dialog (toast "Đã hủy lịch, giữ lại lịch sử") the cancelled list is no longer empty (WB4 is the empty list).',
    }),
  ],
  WC: [
    S('WC22', 'WC', 'Patient 360 · Bác sĩ (không có thu ngân)', 'state', [START, ...patientRow('P001')], { selector: '.patient-hero', text: 'Hồ sơ P001' }, {
      role: 'doctor-tam', sources: ['prototype/shared/staff-context.js#apply', 'prototype/shared/clinic.js#patient360'], next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['F1'],
      notes: 'Doctor projection: all eight tabs and the hero buttons stay; "＋ Thêm dịch vụ" and "Mở thu ngân →" (billing) are removed. Only the doctor\'s own patients are listed (22 for BS. Tâm).',
    }),
    S('WC23', 'WC', 'Patient 360 · CSKH · Tổng quan', 'state', [START, ...patientRow('P001')], { selector: '.patient-hero', text: 'Hồ sơ P001' }, {
      role: CARE, sources: ['prototype/shared/staff-context.js#apply', 'prototype/shared/clinic.js#patient360'], next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['F1', 'C5'],
      notes: 'CSKH projection: tabs Tổng quan, Kế hoạch, Dịch vụ & tài chính, CRM & CSKH, Lịch sử (Tư vấn, Buổi điều trị, Ảnh trước / sau removed); the hero actions (AI brief, Nhắn tin, Ghi buổi điều trị), "Sửa", "Xem & chỉnh sửa →", "Mở studio →", "Tạo đơn nháp", "＋ Thêm dịch vụ" and "Mở thu ngân →" are removed. All 46 patients are listed.',
    }),
    S('WC24', 'WC', 'Patient 360 · CSKH · Kế hoạch (chỉ xem)', 'state', [START, ...patientRow('P001'), tab('plan')], { selector: '.patient-hero', text: 'Hồ sơ P001' }, {
      role: CARE, sources: ['prototype/shared/staff-context.js#apply', 'prototype/shared/clinic.js#plan'], next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['J3'],
      notes: 'The plan tab without "Chỉnh sửa" (clinical capability).',
    }),
    S('WC25', 'WC', 'Patient 360 · CSKH · Dịch vụ & tài chính', 'state', [START, ...patientRow('P001'), tab('finance')], { selector: '.patient-hero', text: 'Hồ sơ P001' }, {
      role: CARE, sources: ['prototype/shared/staff-context.js#apply', 'prototype/shared/crm-ui.js#financial'], next_route: null, next_status: 'none', app_canvas: ['J6'],
      notes: 'Invoices and linked panels without "Mở thu ngân →", "＋ Thêm dịch vụ" and "＋ Tạo đơn nháp".',
    }),
    S('WC26', 'WC', 'Patient 360 · Kế toán · Tổng quan', 'state', [START, ...patientRow('P001')], { selector: '.patient-hero', text: 'Hồ sơ P001' }, {
      role: ACCOUNTANT, sources: ['prototype/shared/staff-context.js#apply', 'prototype/shared/clinic.js#patient360'], next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['F1', 'D1'],
      notes: 'Accountant projection: tabs Tổng quan, Kế hoạch, Dịch vụ & tài chính, Lịch sử (also CRM & CSKH removed); clinical buttons removed but billing buttons kept.',
    }),
    S('WC27', 'WC', 'Patient 360 · Kế toán · Dịch vụ & tài chính', 'state', [START, ...patientRow('P001'), tab('finance')], { selector: '.patient-hero', text: 'Hồ sơ P001' }, {
      role: ACCOUNTANT, sources: ['prototype/shared/staff-context.js#apply', 'prototype/shared/crm-ui.js#financial'], next_route: null, next_status: 'none', app_canvas: ['J6', 'D1'],
      notes: 'Keeps "＋ Thêm dịch vụ", "Mở thu ngân →" and the quick-order button (billing); no "＋ Tạo đơn nháp" because that needs the clinical capability.',
    }),
    S('WC28', 'WC', 'Patient 360 · Đơn thuốc chờ bác sĩ duyệt', 'state', [START, ...patientRow('P002')], { selector: '.linked-rx', text: 'Bản nháp cần bác sĩ duyệt' }, {
      sources: ['prototype/shared/care-finance.js#prescriptionPanel'], next_route: null, next_status: 'none', app_canvas: ['F4'],
      notes: 'Prescription card in the draft state: status "Chờ duyệt" and "✓ Bác sĩ duyệt & gửi app". The approved card ("Đơn đã duyệt", reviewer line) is on WC4 (P001). Only approved prescriptions reach Patient Mobile (WI1).',
    }),
    S('WC29', 'WC', 'Patient 360 · hồ sơ tổng hợp chưa có liệu trình và đơn thuốc', 'state', [START, ...patientRow('P037')], { selector: '.linked-care-panel', text: 'Chưa có dịch vụ gắn với hồ sơ' }, {
      sources: ['prototype/shared/care-finance.js#planPanel', 'prototype/shared/care-finance.js#prescriptionPanel'], next_route: null, next_status: 'none', app_canvas: ['J6'],
      covers: ['text:Chưa có dịch vụ gắn với hồ sơ', 'text:Chưa có đơn thuốc', 'text:Chưa có lịch hôm nay'],
      notes: 'One of the ten CRM demo patients (P037): empty service-plan panel, empty prescription panel and the status "Chưa có lịch hôm nay" in the hero eyebrow.',
    }),
    S('WC30', 'WC', 'Patient 360 · hồ sơ vừa tạo · chưa có buổi điều trị', 'state', [START, ...NEWP, tab('session')], { selector: '#session-note', text: 'Chưa có buổi nào trong bản demo' }, {
      sources: ['prototype/shared/clinic.js#session'], next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['J5'], covers: ['text:Chưa có buổi nào trong bản demo'],
    }),
    S('WC31', 'WC', 'Patient 360 · Tư vấn · lỗi nhận định', 'state', [START, ...patientRow('P001'), tab('consult'), { fill: ['#crm-history', '  '] }, { fill: ['#crm-diagnosis', '  '] }, { click: '#crm-clinical-form [type=submit]' }], { selector: '.crm-clinical .crm-error', text: 'Nhập tiền sử và nhận định/chẩn đoán do bác sĩ xác nhận.' }, {
      sources: ['prototype/shared/crm-ui.js#clinical', 'prototype/shared/crm-automation.js#clinical'], next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['J1'],
      notes: 'Error line (class crm-error, role alert) of the clinical form. Whitespace passes the browser\'s "required" check and fails the domain check.',
    }),
    S('WC32', 'WC', 'Brief trước buổi hẹn · hồ sơ vừa tạo', 'state', [START, ...NEWP, { click: '[data-modal="note"]' }, { wait: '#brief-edit' }], { selector: '#brief-edit' }, {
      sources: ['prototype/shared/clinic.js#modalHtml', 'prototype/shared/data.js#brief'], next_route: null, next_status: 'none', app_canvas: ['J2'],
      covers: ['text:Chưa có cập nhật sau điều trị', 'text:Không có mục theo dõi đang mở'],
      notes: 'The draft brief of a patient without events or follow-ups ("Chưa có cập nhật sau điều trị. Không có mục theo dõi đang mở."); WC13 is the brief of P001.',
    }),
    S('WC33', 'WC', 'Patient 360 · CRM & CSKH · không còn việc mở', 'state', [START, ...patientRow('P001'), tab('crm'), ...resolveTask], { selector: '.crm-summary', text: 'Không còn việc CSKH mở' }, {
      sources: ['prototype/shared/crm-ui.js#patient'], next_route: '/patients/[id]', next_status: 'built (U1)', app_canvas: ['J7'], covers: ['text:Không còn việc CSKH mở'],
      notes: 'After the only open task of P001 is recorded ("Đã liên hệ, chưa có nhu cầu"), the "Việc còn mở" panel reads "Không còn việc CSKH mở." Home of Patient Mobile then shows "Việc hôm nay" (WI20).',
    }),
    S('WC34', 'WC', 'Ngày dự kiến quay lại · lỗi', 'state', [START, ...patientRow('P001'), { click: '[data-crm="expected"]' }, { wait: '#crm-expected-form' }, { fill: ['#crm-expected-reason', '   '] }, { click: '#crm-expected-form [type=submit]' }], { selector: '#crm-error', text: 'Nhập ngày hợp lệ, lý do và nguồn khuyến nghị.' }, {
      sources: ['prototype/shared/crm-ui.js#handle'], next_route: null, next_status: 'none', app_canvas: ['J7'], covers: ['id:crm-error'],
    }),
    S('WC35', 'WC', 'Patient 360 · Ảnh trước / sau · có ảnh upload', 'state', [START, ...patientRow('P001'), tab('session'), { wait: '#session-note' }, { fill: ['#session-note', 'Da ổn định, đáp ứng tốt.'] }, { upload: ['#session-photo', 'png'] }, { click: '[data-action="save-session"]' }, tab('photos'), { wait: '.clinical-photo img' }], { selector: '.clinical-photo img' }, {
      sources: ['prototype/shared/clinic.js#photos', 'prototype/shared/clinic.js#renderImage'], next_route: '/patients/[id]', next_status: 'built (U3)', app_canvas: ['I7'],
      notes: 'Studio with one uploaded photo (a synthetic 1×1 image): "1 ảnh gắn với buổi điều trị, lọc cùng góc khai báo: Chính diện." replaces the illustrative-photos line of WC9.',
    }),
  ],
  WD: [
    S('WD9', 'WD', 'Kết quả chăm sóc đã ghi · có kết quả', 'state', [START, ...CRM_TASK, { select: ['#crm-outcome', 'no_need'] }, { fill: ['#crm-note', 'Đã trao đổi, chưa có nhu cầu.'] }, { click: '#crm-submit' }, { wait: '.crm-queue' }, { click: '[data-crm="activity"]' }, { wait: '.crm-activity-list article' }], { selector: '.crm-activity-list article', text: 'Đã liên hệ, chưa có nhu cầu' }, {
      sources: ['prototype/shared/crm-ui.js#handle'], next_route: '/crm', next_status: 'built (U7)', app_canvas: [],
      notes: 'The populated list of WD4: one article per recorded outcome (patient, outcome label, note, actor and time).',
    }),
    S('WD10', 'WD', 'Nhóm khách · chưa có khách trong nhóm', 'state', [START, nav('dashboard'), { click: '[data-crm="segment"][data-id="reactivated"]' }, { wait: '.modal' }], { selector: '.modal', text: 'Chưa có khách trong nhóm.' }, {
      sources: ['prototype/shared/crm-ui.js#handle'], next_route: '/crm', next_status: 'built (U7)', app_canvas: [], covers: ['text:Chưa có khách trong nhóm'],
      notes: 'Lifecycle stage with no patient (Đã quay lại sau CSKH; "Khách mới" and "Khách quay lại" are empty too).',
    }),
    S('WD11', 'WD', 'Ghi nhận CSKH · thiếu ngày giờ gọi lại', 'state', [START, ...CRM_TASK, { select: ['#crm-outcome', 'callback'] }, { fill: ['#crm-note', 'Gọi lại sau'] }, { click: '#crm-submit' }], { selector: '#crm-error', text: 'Cần ngày giờ gọi lại.' }, {
      sources: ['prototype/shared/crm-ui.js#task', 'prototype/shared/crm-automation.js#resolve'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I13', 'C6'], covers: ['id:crm-error'],
    }),
    S('WD12', 'WD', 'Ghi nhận CSKH · thiếu nội dung trao đổi', 'state', [START, ...CRM_TASK, { select: ['#crm-outcome', 'no_need'] }, { fill: ['#crm-note', '   '] }, { click: '#crm-submit' }], { selector: '#crm-error', text: 'Chọn kênh, kết quả, người phụ trách và nhập ghi chú.' }, {
      sources: ['prototype/shared/crm-ui.js#task', 'prototype/shared/crm-automation.js#resolve'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I13', 'C6'], covers: ['id:crm-error'],
    }),
    S('WD13', 'WD', 'Ghi nhận CSKH · đồng ý đặt lịch', 'state', [START, ...CRM_TASK, { select: ['#crm-outcome', 'booked'] }, { fill: ['#crm-note', 'Khách đồng ý đặt lịch.'] }], { selector: '#crm-submit', text: 'Tiếp tục → Đặt lịch' }, {
      sources: ['prototype/shared/crm-ui.js#bind'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I13', 'C6'],
      notes: 'The submit button changes to "Tiếp tục → Đặt lịch"; submitting opens the booking dialog prefilled with "Sau CSKH: …" (WB7).',
    }),
    S('WD14', 'WD', 'Ghi nhận CSKH · việc đã được xử lý ở cửa sổ khác', 'state', [START, ...CRM_TASK, { select: ['#crm-outcome', 'no_need'] }, { fill: ['#crm-note', 'Đã trao đổi.'] },
      { tab: [START, ...CRM_TASK, { select: ['#crm-outcome', 'no_need'] }, { fill: ['#crm-note', 'Đã trao đổi.'] }, { click: '#crm-submit' }, { wait: '.crm-queue' }] },
      { click: '#crm-submit' }], { selector: '#crm-error', text: 'Việc đã được xử lý hoặc không còn hợp lệ. Tải lại danh sách.' }, {
      sources: ['prototype/shared/crm-automation.js#resolve'], next_route: '/today', next_status: 'restyle (U1)', app_canvas: ['I13'], covers: ['text:Việc đã được xử lý hoặc không còn hợp lệ*', 'id:crm-error'],
      notes: 'Two tabs: the second tab records the same first task while the dialog of the first tab is still open.',
    }),
    S('WD15', 'WD', 'Theo dõi · inbox đã sạch', 'state', [START, nav('followups'), { click: '[data-action="view-followup"]' }, { wait: '#review-reply' }, { click: '[data-action="review-submit"]' }, { wait: '.followup-card, .empty' }], { text: 'Inbox đã sạch' }, {
      role: 'doctor-lan', sources: ['prototype/shared/clinic.js#followups'], next_route: '/inbox', next_status: 'restyle (U1)', app_canvas: ['I6', 'A4'],
      covers: ['text:Inbox đã sạch', 'text:Không có follow-up đang mở'],
      notes: 'BS. Lan owns one open follow-up; after "Duyệt, phản hồi & đóng mục" the panel reads "Inbox đã sạch. Không có follow-up đang mở." and the nav badge shows 0.',
    }),
    S('WD16', 'WD', 'Theo dõi · thiếu ảnh mốc sau buổi điều trị', 'state', [START, ...patientRow('P001'), tab('session'), { wait: '#session-note' }, { fill: ['#session-note', 'Da ổn định, đáp ứng tốt.'] }, { click: '[data-action="save-session"]' }, nav('followups')], { selector: '.followup-card', text: 'Buổi điều trị vừa lưu chưa có ảnh mốc.' }, {
      sources: ['prototype/shared/clinic.js#action'], next_route: '/inbox', next_status: 'restyle (U1)', app_canvas: ['I6'], covers: ['text:Buổi điều trị vừa lưu chưa có ảnh mốc'],
      notes: 'Saving a session without a photo opens a follow-up of type "Thiếu ảnh mốc đánh giá".',
    }),
  ],
  WE: [
    S('WE7', 'WE', 'Bác sĩ & phòng · không có khoảng khóa', 'state', [START, nav('resources'), { click: '[data-ops="unblock"]' }, { wait: '.table' }], { selector: '.table', text: 'Không có khoảng khóa.' }, {
      sources: ['prototype/shared/operations-ui.js#resources'], next_route: '/resources', next_status: 'planned (U4)', app_canvas: ['F14'], covers: ['text:Không có khoảng khóa'],
      notes: 'After "Gỡ khóa" of the only demo block the table shows "Không có khoảng khóa."',
    }),
    S('WE8', 'WE', 'Khóa thời gian phòng · lỗi', 'state', [START, nav('resources'), { click: '[data-ops="block"]' }, { wait: '#block-reason' }, { fill: ['#block-reason', ''] }, { click: '[data-ops="save-block"]' }], { selector: '#ops-error', text: 'Khoảng khóa phải hợp lệ trong 08:00–18:00 và có lý do.' }, {
      sources: ['prototype/shared/operations-ui.js#handle'], next_route: '/resources', next_status: 'planned (U4)', app_canvas: ['I8'], covers: ['id:ops-error'],
    }),
    S('WE9', 'WE', 'Khóa thời gian phòng · trùng lịch hẹn', 'state', [START, nav('resources'), { click: '[data-ops="block"]' }, { wait: '#block-reason' }, { click: '[data-ops="save-block"]' }], { selector: '#ops-error', text: 'Có lịch hẹn trong khoảng này. Hãy dời lịch trước khi khóa phòng.' }, {
      sources: ['prototype/shared/operations-data.js#block'], next_route: '/resources', next_status: 'planned (U4)', app_canvas: ['I8'], covers: ['id:ops-error'],
    }),
    S('WE10', 'WE', 'Chỉnh dịch vụ · lỗi', 'state', [START, nav('services'), { click: '[data-ops="service"]' }, { wait: '#service-name' }, { fill: ['#service-name', ''] }, { click: '[data-ops="save-service"]' }], { selector: '#ops-error', text: 'Kiểm tra tên, thời lượng 15–180 phút, đệm 0–60 phút và giá không âm.' }, {
      sources: ['prototype/shared/operations-ui.js#handle'], next_route: '/services', next_status: 'planned (U4)', app_canvas: ['I9'], covers: ['id:ops-error'],
    }),
    S('WE11', 'WE', 'Dịch vụ · có dịch vụ tạm ngưng', 'state', [START, nav('services'), { click: '[data-ops="service"]' }, { wait: '#service-active' }, { select: ['#service-active', 'no'] }, { click: '[data-ops="save-service"]' }, { wait: '.service-grid' }], { selector: '.service-top .status-yellow', text: 'Tạm ngưng' }, {
      sources: ['prototype/shared/operations-ui.js#services'], next_route: '/services', next_status: 'planned (U4)', app_canvas: ['F13'],
      notes: 'Service card with the yellow status "Tạm ngưng" (the others read "Đang dùng", green).',
    }),
  ],
  WF: [
    S('WF11', 'WF', 'Lên đơn · chưa chọn sản phẩm', 'state', [START, ...QUICK_FORM, { click: '#quick-save' }], { selector: '#quick-error', text: 'Chọn ít nhất một sản phẩm.' }, {
      sources: ['prototype/shared/order-ui.js#open'], next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['F4'], covers: ['id:quick-error'],
    }),
    S('WF12', 'WF', 'Tách đơn · chỉ có đơn thuốc', 'state', [...draftBlocked(['H002']), ...SAVE_ORDER], { selector: '.order-sheet', text: 'ĐƠN THUỐC' }, {
      sources: ['prototype/shared/order-review.js#sheet'], next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F6'],
      notes: 'One sheet only (a prescription product): no "PHIẾU TƯ VẤN" sheet is drawn. Created with the finance API blocked so no invoice is mirrored into the shared finance data.',
    }),
    S('WF13', 'WF', 'Tách đơn · chỉ có phiếu tư vấn', 'state', [...draftBlocked(['H005']), ...SAVE_ORDER], { selector: '.order-sheet', text: 'PHIẾU TƯ VẤN' }, {
      sources: ['prototype/shared/order-review.js#sheet'], next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F7'],
    }),
    S('WF14', 'WF', 'Tách đơn · có sản phẩm "Không in"', 'state', [...draftBlocked(['H002', 'H005']), { select: ['#route-0', 'NONE'] }, { fill: ['#reason-0', 'Không cần in'] }, ...SAVE_ORDER], { selector: '#review-excluded', text: 'Không in (1)' }, {
      sources: ['prototype/shared/order-review.js#refresh'], next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F5'],
      notes: 'A line set to "Không in" with its reason: listed above the sheets ("… Vẫn tính trong hóa đơn.") and removed from both sheets.',
    }),
    S('WF15', 'WF', 'Tách đơn · lỗi khi duyệt (thiếu cách dùng)', 'state', [...draftBlocked(['H002'], false), ...SAVE_ORDER, { click: '#approve' }], { selector: '#review-error', text: 'Dòng 1: cần cách dùng trước khi duyệt.' }, {
      sources: ['prototype/shared/order-review.js#refresh', 'prototype/shared/order-data.js#approveOrder'], next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F5'], covers: ['id:review-error'],
      notes: 'Error line #review-error of the review page after "Bác sĩ duyệt & gửi app" with a line that has no usage text.',
    }),
    S('WF16', 'WF', 'Tách đơn · không có sản phẩm để phát hành', 'state', [...draftBlocked(['H002']), { select: ['#route-0', 'NONE'] }, { fill: ['#reason-0', 'Không cần in'] }, { clickPopup: '#quick-save' }, { wait: '#approve' }, { click: '#approve' }], { selector: '#review-error', text: 'Đơn không có sản phẩm để phát hành.' }, {
      sources: ['prototype/shared/order-data.js#approveOrder'], next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F5'], covers: ['text:Đơn không có sản phẩm để phát hành*', 'id:review-error'],
    }),
    S('WF17', 'WF', 'Tách đơn · không tìm thấy đơn', 'state', [{ goto: '/order-review/?patient=P001&order=NOPE' }, { wait: '#review-error' }], { selector: '#review-error', text: 'Không tìm thấy đơn.' }, {
      sources: ['prototype/shared/order-review.js#refresh'], next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: [], covers: ['id:review-error'],
      notes: 'Patient code present, order code unknown (a stale link). WF8 is the page opened without codes.',
    }),
    S('WF18', 'WF', 'Tách đơn · bản nháp · tài khoản không phải bác sĩ', 'state', [...draftBlocked(['H002', 'H005']), ...SAVE_ORDER], { selector: '#review-status', text: 'Bản nháp' }, {
      role: ACCOUNTANT, sources: ['prototype/shared/order-review.js#refresh'], next_route: '/orders/[id]', next_status: 'planned (U5)', app_canvas: ['F6'],
      notes: 'Accountant opens a draft order: the toolbar has no "Bác sĩ duyệt & gửi app" button (clinical capability) and the print buttons stay disabled.',
    }),
    S('WF19', 'WF', 'In đơn thuốc (hộp thoại in của trình duyệt)', 'state', [...draftBlocked(['H002', 'H005']), ...SAVE_ORDER, { click: '#approve' }, { wait: 'body[data-approved="true"]' }], { selector: '[data-print="PRESCRIPTION"]:enabled', text: 'In đơn thuốc' }, {
      sources: ['prototype/shared/order-review.js#refresh'], next_route: '/orders/[id]/print', next_status: 'planned (U5)', app_canvas: ['F7'],
      native: { type: 'print', message: null, trigger: [{ hookPrint: true }, { click: '[data-print="PRESCRIPTION"]' }] },
      notes: 'window.print() after "In đơn thuốc", "In phiếu tư vấn" or "In tất cả" (body data-print-filter selects the sheets). The browser print dialog is native and cannot be captured; the A5 sheets are drawn by the print media of WF5/WF6.',
    }),
    S('WF20', 'WF', 'Sửa đơn nháp · đơn đã thu tiền, không thể sửa', 'state', [...draftBlocked(['H002']), { clickPopup: '#quick-save' }, { wait: '.order-sheet' }, { main: true }, { goto: '/clinic-web/?staff={role}&screen=cashier' }, { wait: '.order-history-row' },
      { click: 'tr:has-text("Đơn sản phẩm") [data-ops="pay"]' }, { wait: '#pay-amount' }, { click: '[data-ops="save-pay"]' }, { wait: '.toast' }, { click: '[data-order-edit]' }, { wait: '#catalog-order-form' }, { click: '#quick-save' }], { selector: '#quick-error', text: 'Đơn đã thu tiền hoặc thiếu hóa đơn; không thể sửa.' }, {
      sources: ['prototype/shared/order-ui.js#open', 'prototype/shared/order-data.js#saveOrder'], next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['F5'], covers: ['text:Đơn đã thu tiền hoặc thiếu hóa đơn; không thể sửa*', 'id:quick-error'],
      notes: 'The draft\'s invoice was paid in Thu ngân, then "Sửa nháp" → "Lưu nháp" is refused. Finance API blocked so the payment is not mirrored.',
    }),
    S('WF21', 'WF', 'Thu ngân · có đơn nháp', 'state', [...draftBlocked(['H002']), { clickPopup: '#quick-save' }, { wait: '.order-sheet' }, { main: true }, { goto: '/clinic-web/?staff={role}&screen=cashier' }, { wait: '.order-history-row' }], { selector: '.order-history-row', text: 'Bản nháp' }, {
      sources: ['prototype/shared/order-ui.js#history'], next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['I10'],
      notes: 'Order history row with "Xem / in" and "Sửa nháp", and the new invoice row "Đơn sản phẩm" in the invoice table (WF1 shows the empty history "Chưa có đơn từ catalog.").',
    }),
    S('WF22', 'WF', 'Thu ngân · có đơn đã duyệt', 'state', [...draftBlocked(['H002', 'H005']), { clickPopup: '#quick-save' }, { wait: '#approve' }, { click: '#approve' }, { wait: 'body[data-approved="true"]' }, { main: true }, { goto: '/clinic-web/?staff={role}&screen=cashier' }, { wait: '.order-history-row' }], { selector: '.order-history-row', text: 'Đã duyệt' }, {
      sources: ['prototype/shared/order-ui.js#history', 'prototype/shared/operations-ui.js#printOrder'], next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['I10'], covers: ['ops:print-order'],
      notes: 'Approved order: only "Xem / in" (no "Sửa nháp"); the invoice row carries the order code and "In tách đơn" (data-ops print-order, opens the review page in a new tab).',
    }),
    S('WF23', 'WF', 'Thu tiền · lỗi số tiền', 'state', [START, nav('cashier'), { click: '[data-ops="pay"]' }, { wait: '#pay-amount' }, { setValue: ['#pay-amount', '0'] }, { click: '[data-ops="save-pay"]' }], { selector: '#ops-error', text: 'Số tiền phải lớn hơn 0 và không vượt số còn lại.' }, {
      sources: ['prototype/shared/operations-data.js#pay'], next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['I11'], covers: ['id:ops-error'],
    }),
    S('WF24', 'WF', 'Thu ngân · lọc "Còn phải thu"', 'state', [START, nav('cashier'), { click: '[data-ops="invoice-filter"][data-value="due"]' }], { selector: '.invoice-pagination', text: '6 hóa đơn' }, {
      sources: ['prototype/shared/operations-ui.js#cashier'], next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['I10'],
      notes: 'Invoice list filtered to the 6 unpaid invoices (every row has "Thu tiền"). The filter "Đã thanh toán" and the paging buttons ("← Trước", "Sau →") change only the rows.',
    }),
    S('WF25', 'WF', 'Thu ngân · không có hóa đơn', 'state', [BLOCK_FIN, START, nav('cashier'), { click: '[data-ops="invoice-filter"][data-value="due"]' },
      ...Array.from({ length: 6 }, () => ({ ifVisible: ['[data-ops="pay"]', [{ click: '[data-ops="pay"]' }, { wait: '#pay-amount' }, { click: '[data-ops="save-pay"]' }, { gone: '.modal' }]] }))], { selector: '.table', text: 'Không có hóa đơn.' }, {
      sources: ['prototype/shared/operations-ui.js#cashier'], next_route: '/cashier', next_status: 'planned (U5)', app_canvas: ['I10'], covers: ['text:Không có hóa đơn'],
      notes: 'After the six unpaid invoices are paid in the browser (finance API blocked so nothing reaches the shared finance data) the filter "Còn phải thu" shows "Không có hóa đơn."',
    }),
  ],
  WG: [
    S('WG10', 'WG', 'Tài chính · đang tải dữ liệu', 'state', [START, HOLD_FIN, nav('finance'), { wait: '#content' }], { selector: '#content', text: 'Đang tải dữ liệu…' }, {
      sources: ['prototype/finance/finance.js#html', 'prototype/finance/finance.js#load'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H7'],
      notes: 'Finance API request pending: header, tabs and "Đang tải dữ liệu…" (WG9 is the same page after the request fails).',
    }),
    S('WG11', 'WG', 'Tài chính · tháng không có lượt thủ thuật', 'state', [START, ...FIN_WORK, { setValue: ['#month', '2026-06'] }, { wait: '#export' }], { selector: '#content', text: 'Chưa có lượt thủ thuật trong kỳ này.' }, {
      sources: ['prototype/finance/finance.js#table'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H3'], covers: ['text:Chưa có lượt thủ thuật trong kỳ này'],
      notes: 'Month picker set to a month without entries: empty table row, the entry form and "Chốt tháng đã kết thúc" stay.',
    }),
    S('WG12', 'WG', 'Tài chính · phiếu thu · tháng không có giao dịch', 'state', [START, ...FIN_RECEIPTS, { setValue: ['#month', '2026-06'] }, { wait: '#payment' }], { selector: '#content', text: 'Chưa có phiếu thu.' }, {
      sources: ['prototype/finance/finance.js#receipts'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H5'], covers: ['text:Chưa có phiếu thu'],
      notes: 'Owner notification box: "Thanh toán thành công sẽ xuất hiện tại đây và trên app BS. Tâm." (no notification yet; the unread/read list needs a real payment and is not scripted because it would write to the shared finance data).',
    }),
    S('WG13', 'WG', 'Tài chính · kỳ đã chốt', 'state', [START, ...FIN_CLOSED], { selector: '.finance-workspace .badge', text: 'Đã chốt tháng' }, {
      sources: ['prototype/finance/finance.js#work', 'prototype/finance/finance.js#table'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H3', 'H4'], covers: ['command:paid'],
      notes: 'Period 2026-08: badge "Đã chốt tháng", rows without Duyệt/Hủy, no entry form, button "Xác nhận đã chi". Set-up caveat: the finance server closes only a month that has an approved row, so the reach adds one approved entry (P002, linked to the existing invoice WEB:P002:HD-0002, so no invoice or debt is added) to 2026-08 on the first run and closes it; every step is guarded, later runs change nothing. Month 2026-09 stays open.',
    }),
    S('WG14', 'WG', 'Tài chính · kỳ đã chi', 'state', [START, ...FIN_PAID], { selector: '.finance-workspace .badge', text: 'Đã chi' }, {
      sources: ['prototype/finance/finance.js#work', 'prototype/finance/finance.js#table'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H3', 'H4'],
      notes: 'Period 2026-07: badge "Đã chi", no period button. Same guarded set-up as WG13 (entry P003 linked to WEB:P003:HD-0003), then "Xác nhận đã chi" with a voucher code.',
    }),
    S('WG15', 'WG', 'Tài chính · Phiếu thu & thông báo (kế toán)', 'state', [START, ...FIN_RECEIPTS], { selector: '#content', text: 'Kế toán không đọc inbox của chủ.' }, {
      role: ACCOUNTANT, sources: ['prototype/finance/finance.js#receipts'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['D1', 'H5'],
      notes: 'Accountant projection of the receipts tab: the notification box is replaced by "Kế toán không đọc inbox của chủ."',
    }),
    S('WG16', 'WG', 'Hủy lượt thủ thuật (nhập lý do)', 'state', [START, ...FIN_WORK, { wait: '[data-command="void"]' }], { selector: '[data-command="void"]', text: 'Hủy' }, {
      sources: ['prototype/finance/finance.js#bind'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H4'], covers: ['command:void', 'command:approve', 'command:close', 'command:read'],
      native: { type: 'prompt', message: 'Lý do hủy lượt chưa thu tiền', trigger: [{ dialog: 'dismiss' }, { click: '[data-command="void"]' }] },
      notes: 'Native prompt() for the void reason (cancelled in the walk, so nothing is written). A void only sticks with a non-empty reason.',
    }),
    S('WG17', 'WG', 'Chốt tháng (hộp xác nhận)', 'state', [START, ...FIN_WORK, { wait: '[data-command="close"]' }], { selector: '[data-command="close"]', text: 'Chốt tháng đã kết thúc' }, {
      sources: ['prototype/finance/finance.js#bind'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H4'],
      native: { type: 'confirm', message: 'Chốt số liệu tháng 2026-09? Các lượt trong kỳ sẽ bị khóa.', trigger: [{ dialog: 'dismiss' }, { click: '[data-command="close"]' }] },
      notes: 'Native confirm() before closing the period (cancelled in the walk). The month in the text is the picker month (2026-09 on the frozen clock).',
    }),
    S('WG18', 'WG', 'Xác nhận đã chi (nhập mã chứng từ)', 'state', [START, ...FIN_CLOSED], { selector: '[data-command="paid"]', text: 'Xác nhận đã chi' }, {
      sources: ['prototype/finance/finance.js#bind'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H4'],
      native: { type: 'prompt', message: 'Mã chứng từ chi', trigger: [{ dialog: 'dismiss' }, { click: '[data-command="paid"]' }] },
      notes: 'Native prompt() for the payout voucher code on a closed period (cancelled in the walk). Uses the closed period of WG13.',
    }),
    S('WG19', 'WG', 'Xuất CSV cho Excel (tải tệp)', 'state', [START, ...FIN_WORK, { wait: '#export' }], { selector: '#export', text: 'Xuất CSV cho Excel' }, {
      sources: ['prototype/finance/finance.js#bind'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H3'],
      native: { type: 'download', filename: 'Pema-tien-thu-thuat-2026-09.csv', trigger: [{ click: '#export' }] },
      notes: 'The button downloads Pema-tien-thu-thuat-<month>.csv (BOM, columns Ngay, Ho so, Thu thuat, Bac si, Doanh so, Co so, Ty le %, Tien thu thuat, Trang thai). The browser\'s download UI is native.',
    }),
    S('WG20', 'WG', 'Xuất CSV · lỗi', 'state', [START, ...FIN_WORK, { wait: '#export' }, { block: 'http://127.0.0.1:4174/export*' }, { click: '#export' }], { selector: '#error', text: 'Không xuất được bảng' }, {
      sources: ['prototype/finance/finance.js#bind'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H7'],
      notes: 'Export request fails: the red #error line reads "Không xuất được bảng" (the exact network text follows).',
    }),
    S('WG21', 'WG', 'Ghi nhận lượt · lỗi tỷ trọng', 'state', [START, ...FIN_WORK, { click: '#content details > summary' }, { wait: '#entry' }, { fill: ['#entry [name=note]', 'Đã thực hiện'] }, { setValue: ['#entry [name=share0]', '50'] }, { click: '#entry [type=submit]' }], { selector: '#error', text: 'Tổng tỷ trọng doanh số phải là 100%' }, {
      sources: ['prototype/finance/finance.js#entryForm'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H9'],
      notes: 'Validation error of the "Ghi nhận lượt thủ thuật đã hoàn tất" form, returned by the finance server and shown in #error. Nothing is stored.',
    }),
    S('WG22', 'WG', 'Ghi nhận lượt · thiếu ghi chú hoàn tất', 'state', [START, ...FIN_WORK, { click: '#content details > summary' }, { wait: '#entry' }, { fill: ['#entry [name=note]', '   '] }, { click: '#entry [type=submit]' }], { selector: '#error', text: 'Ghi chú xác nhận hoàn tất là bắt buộc' }, {
      sources: ['prototype/finance/finance.js#entryForm'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H9'],
    }),
    S('WG23', 'WG', 'Phiếu thu · số thu vượt công nợ', 'state', [START, ...FIN_RECEIPTS, { setValue: ['#payment [name=amount]', '99999999'] }, { click: '#payment .primary' }], { selector: '#error', text: 'Số thu vượt công nợ' }, {
      sources: ['prototype/finance/finance.js#receipts'], next_route: '/finance', next_status: 'planned (U6)', app_canvas: ['H5', 'H6'],
    }),
  ],
  WH: [
    S('WH15', 'WH', 'Ask Pema · kế hoạch đang chạy', 'state', [START, nav('ask'), { click: '[data-question="Có bao nhiêu kế hoạch đang chạy?"]' }, { click: '[data-action="ask"]' }, { wait: '#ask-result' }], { selector: '#ask-result', text: 'kế hoạch chưa hoàn tất' }, {
      sources: ['prototype/shared/clinic.js#action'], next_route: '/ask', next_status: 'built (U7)', app_canvas: ['I12', 'F15'],
    }),
    S('WH16', 'WH', 'Ask Pema · quá hạn tái khám', 'state', [START, nav('ask'), { click: '[data-question="Ai quá hạn tái khám hơn 30 ngày?"]' }, { click: '[data-action="ask"]' }, { wait: '#ask-result' }], { selector: '#ask-result', text: 'lần điều trị gần nhất hơn 30 ngày' }, {
      sources: ['prototype/shared/clinic.js#action'], next_route: '/ask', next_status: 'built (U7)', app_canvas: ['I12', 'F15'],
    }),
    S('WH17', 'WH', 'Ask Pema · câu hỏi ngoài nhóm hỗ trợ', 'state', [START, nav('ask'), { fill: ['#ask-input', 'xyz'] }, { click: '[data-action="ask"]' }, { wait: '#ask-result' }], { selector: '#ask-result', text: 'Demo hỗ trợ 3 nhóm câu hỏi' }, {
      sources: ['prototype/shared/clinic.js#action'], next_route: '/ask', next_status: 'built (U7)', app_canvas: ['I12'],
      notes: 'Free text that matches none of the three prepared questions: the result card lists the three supported groups.',
    }),
    S('WH18', 'WH', 'Ask Pema · gợi ý câu hỏi', 'state', [START, nav('ask'), { click: '[data-action="ask-sample"]' }], { selector: '#ask-input' }, {
      sources: ['prototype/shared/clinic.js#action'], next_route: '/ask', next_status: 'built (U7)', app_canvas: ['I12'],
      notes: '"Gợi ý câu hỏi" fills the input with "Ai có ảnh gửi sau laser đang chờ xem?" (no answer yet).',
    }),
    S('WH19', 'WH', 'Ask Pema · không có ảnh chờ xem', 'state', [START, nav('followups'), { click: '[data-followup-filter="image"]' },
      { ifVisible: ['[data-action="view-followup"]', [{ click: '[data-action="view-followup"]' }, { wait: '#review-reply' }, { click: '[data-action="review-submit"]' }, { wait: '.page-title' }]] },
      { ifVisible: ['[data-action="view-followup"]', [{ click: '[data-action="view-followup"]' }, { wait: '#review-reply' }, { click: '[data-action="review-submit"]' }, { wait: '.page-title' }]] },
      nav('ask'), { click: '[data-question="Ai có ảnh gửi sau laser đang chờ xem?"]' }, { click: '[data-action="ask"]' }, { wait: '#ask-result' }], { selector: '#ask-result', text: 'Không có' }, {
      sources: ['prototype/shared/clinic.js#action'], next_route: '/ask', next_status: 'built (U7)', app_canvas: ['I12'], covers: ['text:Không có'],
      notes: 'After the two image follow-ups are closed the answer reads "Có 0 ảnh chờ xem: Không có. Nguồn: Follow-up Inbox, status=open, có ảnh."',
    }),
    S('WH20', 'WH', 'Hướng dẫn · kết quả tìm kiếm', 'state', [START, nav('guide'), { fill: ['#guide-search', 'lịch'] }, { wait: '#guide-topics' }], { selector: '#guide-topics', text: 'Lịch hẹn & tiếp đón' }, {
      sources: ['prototype/shared/guide.js#navigation'], next_route: '/guide', next_status: 'built (U7)', app_canvas: ['F16'],
      notes: 'Topic list filtered by the search text; WH14 is the no-match message.',
    }),
  ],
  WI: [
    // ---- the nine screens (data-screen) for the first demo patient P001 (Nguyễn Minh Linh)
    S('WI1', 'WI', 'Trang chủ', 'page', [...MOBILE], { selector: '.mobile-heading', text: 'Hôm nay của bạn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#home', 'prototype/shared/patient.js#app', 'prototype/shared/patient.js#nextStep', 'prototype/shared/patient.js#appointmentDisplay', 'prototype/shared/care-finance.js#injectMobile', 'prototype/patient-mobile/index.html'],
      app_canvas: ['E1'], legacy_shot: null,
      covers: ['screen:profile', 'screen:journey', 'screen:appointments', 'screen:home', 'screen:messages'],
      notes: 'Patient P001 (Nguyễn Minh Linh): top bar (logo, avatar button to Hồ sơ), greeting, "Hôm nay của bạn", next-step card ("Đến mốc tái khám" → "Xem lịch hẹn"), journey hero with session rail, "Lịch hẹn tiếp theo", the approved prescription card "Đơn & phiếu đã duyệt" (injected by care-finance.js), bottom nav (Trang chủ, Lịch hẹn, Hành trình, Tin nhắn, Hồ sơ). The next-step card, the appointment block and the prescription card change with the patient: WI10–WI21.',
    }),
    S('WI2', 'WI', 'Lịch hẹn', 'page', [...MOBILE, mnav('appointments')], { selector: '.mobile-page-title', text: 'Lịch hẹn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#appointments'], app_canvas: ['K1', 'G3'],
      covers: ['action:confirm-appointment'],
      notes: '"Sắp tới" card with the chip "Đã đặt lịch", date tile, "Xác nhận tôi sẽ đến"; "Các lịch đã đặt" (rows from the clinic schedule), "Lịch đã qua", the notice about changing an appointment at least 4 hours ahead.',
    }),
    S('WI3', 'WI', 'Hành trình', 'page', [...MOBILE, mnav('journey')], { selector: '.mobile-page-title', text: 'Hành trình của bạn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#journey'], app_canvas: ['E2', 'K3'],
      covers: ['action:more-history'],
      notes: 'Journey summary with the sessions progress bar ("Tiến độ số buổi, không phải mức cải thiện da."), the photo shortcut "Ảnh trước & sau", "Cập nhật gần đây" with 3 of 4 events as <details> rows and "Xem thêm lịch sử".',
    }),
    S('WI4', 'WI', 'Tin nhắn', 'page', [...MOBILE, mnav('messages')], { selector: '.mobile-page-title', text: 'Tin nhắn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#messages'], app_canvas: ['E3'],
      notes: 'Thread "Pema Care Team" with the status "Đang hỗ trợ", clinic messages left and the patient\'s own messages right (class mine), "＋ Gửi tin nhắn".',
    }),
    S('WI5', 'WI', 'Hồ sơ', 'page', [...MPROFILE], { selector: '.mobile-page-title', text: 'Hồ sơ' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#profile'], app_canvas: ['E4', 'G8'],
      covers: ['screen:docs', 'screen:care', 'action:privacy-info'],
      notes: 'Avatar, name, age · phone · code, the demo notice ("Tài khoản và dữ liệu thật sẽ cần xác thực riêng."), three rows (Tài liệu & hóa đơn, Chăm sóc tại nhà, Quyền riêng tư with the consent state), and "Đổi hồ sơ demo": two native selects (Nhóm tài khoản mẫu: Tất cả hồ sơ + ten CRM groups; Chọn người bệnh tổng hợp: 46 patients). The prescription card of care-finance.js is injected here too.',
    }),
    S('WI6', 'WI', 'Tiến độ số buổi & ảnh', 'page', [...MOBILE, mnav('journey'), { click: '.photo-shortcut' }, { wait: '.mobile-photo-row' }], { selector: '.mobile-photo-row', text: 'Tiến độ số buổi & ảnh' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#progress', 'prototype/shared/data.js#face'], app_canvas: ['G5'], covers: ['screen:progress'],
      notes: 'Reached from the journey row "Ảnh trước & sau". Photo comparison (illustrative faces "Trước" and "Gần nhất", chip "Chính diện"), the notice about angle and light, and "Gửi ảnh cập nhật →". Bottom nav keeps "Hành trình" active.',
    }),
    S('WI7', 'WI', 'Chăm sóc tại nhà', 'page', [...MPROFILE, mrow('care')], { selector: '.mobile-page-title', text: 'Chăm sóc tại nhà' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#care'], app_canvas: ['G1'], covers: ['action:ack-aftercare'],
      notes: 'Reached from Hồ sơ. After-care text of the last session, one row per medication, "Khi nào cần nhắn Pema?", "Tôi đã đọc hướng dẫn" and "Gửi cập nhật →".',
    }),
    S('WI8', 'WI', 'Gửi cập nhật cho Pema', 'page', [...MSEND], { selector: '#patient-message', text: 'Gửi cập nhật cho Pema' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#send'], app_canvas: ['G2'], covers: ['action:send-update', 'screen:send'],
      notes: 'Reached from Tin nhắn, Chăm sóc tại nhà, Tiến độ or the next-step card. Textarea "Bạn đang cảm thấy thế nào?", photo picker ("Chọn ảnh", png/jpeg/webp), consent checkbox, "Gửi cho Pema", the notice "Đây không phải kênh cấp cứu."',
    }),
    S('WI9', 'WI', 'Tài liệu & hóa đơn', 'page', [...MPROFILE, mrow('docs')], { selector: '.mobile-page-title', text: 'Tài liệu & hóa đơn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#docs', 'prototype/shared/care-finance.js#injectMobile'], app_canvas: ['K2', 'G7'], covers: ['action:open-aftercare'],
      notes: 'Reached from Hồ sơ. "Hóa đơn của bạn" (paid and part-paid invoices), "Hướng dẫn đã gửi" (row to Chăm sóc tại nhà) and the injected card "Đơn & phiếu đã duyệt".',
    }),
    // ---- Trang chủ: next-step card per CRM demo group (profile → Nhóm tài khoản mẫu → home)
    ...Object.entries(STEP_CARDS).map(([group, [label, title]], i) =>
      S(`WI${10 + i}`, 'WI', `Trang chủ · ${label}`, 'state', [...mgroup(group), mnav('home')], { selector: '[data-next-step]', text: title }, {
        ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#nextStep', 'prototype/shared/patient.js#home'], app_canvas: ['E1'],
        notes: `Demo patient of the CRM group "${label}" (group select on Hồ sơ): next-step card "${title}" (data-next-step="${group}"). These patients have no booked appointment ("Chọn lịch", "Liên hệ Pema để đặt lịch") and no approved prescription ("Chưa có"). WI1 is the card "Đến mốc tái khám" (due).`,
      }),
    ),
    S('WI19', 'WI', 'Trang chủ · đơn thuốc chờ duyệt (chưa hiện trên app)', 'state', [...MPROFILE, { select: ['#identity-select', 'P002'] }, { gone: '.mobile-toast' }, mnav('home')], { selector: '.mobile-linked-prescriptions', text: 'Đơn và phiếu sẽ xuất hiện sau khi bác sĩ duyệt.' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/care-finance.js#injectMobile', 'prototype/shared/patient.js#home'], app_canvas: ['E1'], covers: ['text:Chưa có'],
      notes: 'P002 has a draft prescription (WC28): Patient Mobile shows nothing of it, only the chip "Chưa có" and the hint. Approved prescription: WI1.',
    }),
    S('WI20', 'WI', 'Trang chủ · việc hôm nay (không còn việc CSKH)', 'state', [START, ...patientRow('P001'), tab('crm'), ...resolveTask, ...MOBILE], { selector: '.home-tasks', text: 'Việc hôm nay' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#home'], app_canvas: ['E1'],
      notes: 'When the patient has no open CSKH task the next-step card is replaced by the card "Việc hôm nay · Pema đồng hành" with three quick actions (Chăm sóc, Ảnh tiến trình, Gửi cập nhật). Reached by recording P001\'s only task in the clinic web, then opening the mobile web in the same browser.',
    }),
    S('WI21', 'WI', 'Trang chủ · hồ sơ vừa tạo', 'state', [...MNEW, mnav('home')], { selector: '.mobile-heading', text: 'Chờ bác sĩ thiết lập kế hoạch' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#home'], app_canvas: ['E1'],
      notes: 'A patient created in the clinic web (WC20), picked in the identity select: plan "Chờ bác sĩ thiết lập kế hoạch", "Buổi 0 / 1 · Cập nhật Chưa ghi nhận", appointment 21/09 10:30, "Việc hôm nay" tasks card.',
    }),
    // ---- appointments
    S('WI22', 'WI', 'Lịch hẹn · chưa có lịch', 'state', [...mgroup('overdue'), mnav('appointments')], { selector: '[data-action="confirm-appointment"]:disabled', text: 'Chưa có lịch hẹn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#appointments', 'prototype/shared/patient.js#appointmentDisplay'], app_canvas: ['K1'], covers: ['text:Chưa có lịch hẹn', 'text:Chưa có lịch đã đặt'],
      notes: 'Demo patient without a booking: chip "Chưa có lịch", calendar icon tile "Chọn lịch", "Liên hệ Pema để đặt lịch", "Xác nhận tôi sẽ đến" disabled, "Chưa có lịch đã đặt.". The toast "Chưa có lịch hẹn để xác nhận" in the code cannot fire: the button is disabled (non_screens).',
    }),
    S('WI23', 'WI', 'Lịch hẹn · đã xác nhận', 'state', [...MOBILE, mnav('appointments'), { click: '[data-action="confirm-appointment"]' }], { selector: '.mobile-toast', text: 'Đã xác nhận lịch hẹn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#action', 'prototype/shared/patient.js#showToast'], app_canvas: ['K1', 'G3'],
      notes: 'Success toast; a clinic message "Lịch hẹn ngày … đã được xác nhận" is added to Tin nhắn and an event to the journey. The toast disappears after 2.8 s.',
    }),
    // ---- journey
    S('WI24', 'WI', 'Hành trình · đã mở thêm lịch sử', 'state', [...MOBILE, mnav('journey'), { click: '[data-action="more-history"]' }], { selector: '.mobile-timeline', text: 'Bắt đầu liệu trình kiểm soát sắc tố' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#journey'], app_canvas: ['E2', 'K3'],
      notes: 'All four events visible; the button "Xem thêm lịch sử" is gone.',
    }),
    S('WI25', 'WI', 'Hành trình · mở chi tiết một mốc', 'state', [...MOBILE, mnav('journey'), { click: '.event-disclosure summary' }], { selector: '.event-disclosure[open] p', text: 'Đỏ nhẹ khoảng 2 ngày' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#journey'], app_canvas: ['E2', 'K3'],
      notes: 'First event expanded (<details open>): the detail paragraph shows under its title.',
    }),
    S('WI26', 'WI', 'Hành trình · chưa có sự kiện', 'state', [...MNEW, mnav('journey')], { selector: '.mobile-timeline', text: 'Chưa có sự kiện trong hành trình.' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#journey'], app_canvas: ['E2'], covers: ['text:Chưa có sự kiện trong hành trình'],
      notes: 'New patient: "0/1 buổi", "0 mốc" and the empty line.',
    }),
    // ---- messages
    S('WI27', 'WI', 'Tin nhắn · chưa có tin', 'state', [...MNEW, mnav('messages')], { selector: '.mobile-card', text: 'Pema Care Team' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#messages'], app_canvas: ['E3'],
      notes: 'New patient: only the thread header and "＋ Gửi tin nhắn".',
    }),
    S('WI28', 'WI', 'Tin nhắn · đã gửi cập nhật', 'state', [...MSEND, { fill: ['#patient-message', 'Da hơi khô ở hai má từ tối qua.'] }, { click: '[data-action="send-update"]' }], { selector: '.mobile-toast', text: 'Đã gửi cập nhật tới đội ngũ Pema' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#action'], app_canvas: ['E3', 'G2'],
      notes: 'After "Gửi cho Pema": the app switches to Tin nhắn, the message is on the right with "20/09 · vừa xong", toast "Đã gửi cập nhật tới đội ngũ Pema". A follow-up "Phản hồi từ patient app" is added to the clinic Theo dõi inbox.',
    }),
    // ---- care
    S('WI29', 'WI', 'Chăm sóc tại nhà · đã đọc hướng dẫn', 'state', [...MPROFILE, mrow('care'), { click: '[data-action="ack-aftercare"]' }], { selector: '.mobile-toast', text: 'Đã ghi nhận bạn đã đọc hướng dẫn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#care', 'prototype/shared/patient.js#action'], app_canvas: ['G1'],
      notes: 'The button reads "✓ Đã đọc hướng dẫn" and the toast confirms; an event "Người bệnh đã đọc hướng dẫn chăm sóc" is added.',
    }),
    S('WI30', 'WI', 'Chăm sóc tại nhà · chưa có hướng dẫn', 'state', [...MNEW, mrow('care')], { selector: '.mobile-card', text: 'Chưa có hướng dẫn được duyệt.' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#care'], app_canvas: ['G1'], covers: ['text:Chưa có hướng dẫn được duyệt'],
      notes: 'New patient: "SAU BUỔI ĐIỀU TRỊ · CHƯA GHI NHẬN", no medication rows, "Chưa có hướng dẫn được duyệt.". The demo patients of the CRM groups also have no medication rows.',
    }),
    // ---- send
    S('WI31', 'WI', 'Gửi cập nhật · chưa nhập nội dung', 'state', [...MSEND, { click: '[data-action="send-update"]' }], { selector: '.mobile-toast', text: 'Hãy viết vài dòng cập nhật' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#action'], app_canvas: ['G2'],
    }),
    S('WI32', 'WI', 'Gửi cập nhật · đã chọn ảnh', 'state', [...MSEND, { fill: ['#patient-message', 'Da hơi khô ở hai má.'] }, { upload: ['#patient-photo', 'png'] }], { selector: '#patient-photo-preview' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#send'], app_canvas: ['G2'],
      notes: 'A synthetic 1×1 image: "Đã chọn: anh-demo.png (đã giữ trong phiên demo)", preview, consent checkbox unchecked.',
    }),
    S('WI33', 'WI', 'Gửi cập nhật · thiếu đồng ý xem ảnh', 'state', [...MSEND, { fill: ['#patient-message', 'Da hơi khô ở hai má.'] }, { upload: ['#patient-photo', 'png'] }, { click: '[data-action="send-update"]' }], { selector: '.mobile-toast', text: 'Bạn cần đồng ý để Pema xem ảnh cập nhật' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#action'], app_canvas: ['G2'],
    }),
    S('WI34', 'WI', 'Gửi cập nhật · tệp không phải ảnh', 'state', [...MSEND, { upload: ['#patient-photo', 'txt'] }], { selector: '.mobile-toast', text: 'Chỉ hỗ trợ PNG, JPEG hoặc WebP.' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#bind', 'prototype/shared/data.js#imageData'], app_canvas: ['G2'],
      notes: 'Other image errors from Pema.imageData: "Ảnh demo tối đa 2,5 MB.", "Tệp không phải ảnh hợp lệ.", "Không đọc được ảnh.". The browser-storage-full toast "Không lưu được thay đổi. Dữ liệu và bản nháp vẫn được giữ lại." is not scripted.',
    }),
    // ---- docs and profile
    S('WI35', 'WI', 'Tài liệu & hóa đơn · chờ thanh toán', 'state', [...MPROFILE, { select: ['#identity-select', 'P002'] }, { gone: '.mobile-toast' }, mrow('docs')], { selector: '.mobile-card', text: 'Chờ thanh toán' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#docs'], app_canvas: ['K2', 'G7'],
      notes: 'P002: one paid invoice and one "Chờ thanh toán" invoice (WI9 shows paid and "Đã thu một phần · còn …").',
    }),
    S('WI36', 'WI', 'Tài liệu & hóa đơn · chưa có hóa đơn', 'state', [...mgroup('d1'), mrow('docs')], { selector: '.mobile-card', text: 'Chưa có hóa đơn trong demo.' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#docs'], app_canvas: ['K2'], covers: ['text:Chưa có hóa đơn trong demo'],
      notes: 'Demo patient without invoices; the card "Đơn & phiếu đã duyệt" shows "Chưa có".',
    }),
    S('WI37', 'WI', 'Tài liệu & hóa đơn · đơn và phiếu đã duyệt từ thu ngân', 'state', [...draftBlocked(['H002', 'H005']), { clickPopup: '#quick-save' }, { wait: '#approve' }, { click: '#approve' }, { wait: 'body[data-approved="true"]' }, { main: true }, ...MOBILE, mnav('profile'), mrow('docs')], { selector: '[data-mobile-order]', text: 'Phiếu tư vấn' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/care-finance.js#injectMobile', 'prototype/shared/patient.js#docs'], app_canvas: ['K2', 'G7'],
      notes: 'An order approved in the clinic web (WF6) appears under "Đơn & phiếu đã duyệt" as a block (date, "Đã duyệt bởi …", groups "Đơn thuốc" and "Phiếu tư vấn", lines with usage) next to the prescription; its invoice "Đơn sản phẩm · 2 dòng" is listed as "Chờ thanh toán". The invoice id differs on every run.',
    }),
    S('WI38', 'WI', 'Hồ sơ · đã tắt đồng ý ảnh', 'state', [...MPROFILE, { click: '[data-action="privacy-info"]' }], { selector: '.mobile-toast', text: 'Đã tắt đồng ý ảnh chăm sóc trong demo' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#action'], app_canvas: ['G8', 'E4'],
      notes: 'The row "Quyền riêng tư" toggles the photo consent (there is no separate privacy panel): subtitle "Ảnh chăm sóc: chưa đồng ý" and the toast.',
    }),
    S('WI39', 'WI', 'Hồ sơ · đã bật lại đồng ý ảnh', 'state', [...MPROFILE, { click: '[data-action="privacy-info"]' }, { gone: '.mobile-toast' }, { click: '[data-action="privacy-info"]' }], { selector: '.mobile-toast', text: 'Đã đồng ý ảnh cho chăm sóc trong demo' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#action'], app_canvas: ['G8', 'E4'],
    }),
    S('WI40', 'WI', 'Hồ sơ · đã đổi hồ sơ demo', 'state', [...MPROFILE, { select: ['#identity-select', 'P002'] }], { selector: '.mobile-toast', text: 'Đã đổi hồ sơ demo' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#bind'], app_canvas: ['E4'],
      notes: 'Choosing another synthetic patient in "Chọn người bệnh tổng hợp" resets the drafts, stores the identity (localStorage pema-patient-identity) and shows the toast. The group select alone (no toast) filters the patient list and jumps to its first patient.',
    }),
    S('WI41', 'WI', 'Hồ sơ · hồ sơ vừa tạo', 'state', [...MNEW], { selector: '.mobile-page-title', text: 'Hồ sơ' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#profile'], app_canvas: ['E4', 'G8'],
      notes: 'New patient P047: "28 tuổi · Chưa nhập · P047" and "Ảnh chăm sóc: chưa đồng ý".',
    }),
    S('WI42', 'WI', 'Lịch hẹn · hồ sơ vừa tạo (chưa có lịch đã đặt)', 'state', [...MNEW, mnav('appointments')], { selector: '.mobile-card', text: 'Chưa có lịch đã đặt.' }, {
      ...MOBILE_COMMON, sources: ['prototype/shared/patient.js#appointments'], app_canvas: ['K1'], covers: ['text:Chưa có lịch đã đặt'],
      notes: 'New patient: an upcoming date (21/09 10:30, "Đã đặt lịch") but no booked rows, and a past row "Buổi 1 · Tư vấn ban đầu · Chưa ghi nhận".',
    }),
  ],
};

// Claims added to entries that already existed (W0 ids stay as they are; only `covers` and `sources` grow, so the static
// guard sees what these screens already show). Each text claim is checked against the live page of its entry.
const extraCovers = {
  WB4: ['text:Không có lịch phù hợp'],
  WC5: ['text:Chưa có bản nháp'],
  WC9: ['text:Chưa có ảnh upload ở góc này'],
  WC20: ['text:Chưa có đồng ý'],
  WC21: ['text:Chưa có hoạt động CSKH được ghi nhận'],
  WD2: ['text:Đã liên hệ, chưa có nhu cầu', 'id:crm-error'],
  WD4: ['text:Chưa có kết quả'],
  WD6: ['text:Chưa có phản hồi kiểm tra sau buổi điều trị'],
  WD8: ['text:Không có việc phù hợp'],
  WB7: ['id:ops-error'],
  WB8: ['id:ops-error'],
  WE4: ['id:ops-error'],
  WE6: ['id:ops-error'],
  WF1: ['text:Chưa có đơn từ catalog'],
  WF2: ['id:ops-error'],
  WF3: ['text:Chưa có loại', 'text:Sản phẩm chưa có loại trong Excel cần được phân loại', 'id:quick-error'],
  WF8: ['id:review-error'],
  WH3: ['text:Có lịch hẹn không có nghĩa đã điều trị*'],
  WH4: ['text:Đây là hướng dẫn phân công công việc*'],
  WH5: ['text:Hiện ca bác sĩ là ca cố định*'],
  WH8: ['text:Hiện đặt lịch chưa tự tạo hóa đơn*'],
  WH11: ['text:Xử lý lỗi và hiểu phạm vi đang sử dụng', 'text:Khi hệ thống từ chối một thao tác*', 'text:Không thể khóa phòng*', 'text:Chưa có đăng nhập/phân quyền thực*'],
};
const extraSources = {
  WF3: ['prototype/shared/order-ui.js#results', 'prototype/shared/operations-ui.js#openQuickOrder'],
  WF4: ['prototype/shared/order-ui.js#lines'],
  WG1: ['prototype/finance/finance.js#html'],
  WB7: ['prototype/shared/operations-ui.js#openBooking'],
  WF5: ['prototype/shared/order-review.js#lines'],
};
for (const s of screens) {
  if (extraCovers[s.id]) s.covers = [...(s.covers || []), ...extraCovers[s.id]];
  if (extraSources[s.id]) s.sources = [...s.sources, ...extraSources[s.id]];
}

// New groups and the ids appended at the end of each group, in group order.
groups.push({ code: 'WI', name: 'Patient Mobile web' });
const allScreens = groups.flatMap((g) => [...screens.filter((s) => s.group === g.code), ...(added[g.code] || [])]);
screens.length = 0;
screens.push(...allScreens);

// Where each UI entry point of the old web goes. Key = `<attribute>:<value>`. Filled in after the first
// walk (see web-inventory.cjs, which fails on any entry point that is not listed here or in `covers`).
const actions = {};

// Things that exist in the old code but are NOT screens or states of the old web: no UI path reaches them. Every entry
// carries the search that proves it (run from the repo root) and, where the guard would otherwise list a string or a hook
// of it, the claim in `covers`.
const non_screens = [
  {
    what: 'prototype/finance/index.html',
    why: 'Redirect stub ("Đang mở tài chính trong Pema Clinic…" and a link "Mở Clinic") that location.replace()s to clinic-web/?screen=finance (WG1) before it is drawn. The app never links to it.',
    proof: 'grep -rn "finance/\'\\|finance/\\"" prototype/shared prototype/finance/finance.js prototype/clinic-web prototype/patient-mobile  → only finance-bridge.js#status (href="../finance/", a link inside WA1 that WA8 shows) points at it; following that link lands on WG1.',
    covers: [],
  },
  {
    what: 'data-modal="appointment" (clinic.js#modalHtml "Đặt lịch nhanh", data-action="book", #appt-time)',
    why: 'Dead code: no button opens it. clinic.js#bind routes the value to PemaOpsUI.openBooking (WB7) before modalHtml is reached.',
    proof: 'cat prototype/shared/*.js | grep -oE \'data-modal=[^ >]{1,25}\' | sort -u  → care, edit, message, note, patient, plan-edit; no data-modal="appointment" is ever rendered.',
    covers: ['action:book'],
  },
  {
    what: 'clinic.js#modalHtml fallback "Chưa có form trong demo"',
    why: 'Dead code: every data-modal value rendered by the UI has a form (see the search of the previous entry).',
    proof: 'same search: the six rendered values are all handled by modalHtml before its fallback.',
    covers: ['text:Chưa có form trong demo'],
  },
  {
    what: 'care-finance.js#prescriptionPanel fallback "Chưa có chỉ định"',
    why: 'A prescription is only created by makePrescription (indication always set) and the UI offers no way to blank it.',
    proof: 'grep -n "indication" prototype/shared/*.js  → only two assignments, both non-empty (care-finance.js:50 and :61); "Tạo đơn nháp" opens the catalog order dialog (WF3), not a prescription.',
    covers: ['text:Chưa có chỉ định'],
  },
  {
    what: 'crm-ui.js#summary fallbacks "Chưa có ngày dự kiến" and "Chưa có nguồn"',
    why: 'Every one of the 46 demo patients (and a new one) has an expected return date and a source; the form "Ngày dự kiến quay lại" refuses an empty date or source.',
    proof: 'live check on 4173: PemaCRM.profile() over all 46 patients returns expectedNextVisitAt and a known expectedVisitSource for each; grep -n "Nhập ngày hợp lệ, lý do và nguồn khuyến nghị" prototype/shared/crm-automation.js (WC34 shows the refusal).',
    covers: ['text:Chưa có ngày dự kiến', 'text:Chưa có nguồn'],
  },
  {
    what: 'order-data.js#approveOrder "Đơn không thể duyệt."',
    why: 'Only fires for an order that is neither draft nor approved; the UI has no way to delete or void an order.',
    proof: 'grep -oE "status *[:=]=* *\'[a-z]*\'" prototype/shared/order-data.js | sort -u  → \'draft\' and \'approved\' only.',
    covers: ['text:Đơn không thể duyệt'],
  },
  {
    what: 'crm-automation.js#reception "Lịch không thể chuyển trạng thái."',
    why: 'Only fires when the appointment of a reception row changed in another window before the click; the list re-renders on the storage event, so the stale row is gone before it can be clicked (the same race with an open dialog is WB22).',
    proof: 'live check on 4173 (two tabs): after the second tab marks P001 "Vắng", the first tab\'s row already shows "Mở 360" instead of "Check-in". Call sites: grep -n "C.reception(" prototype/shared/crm-ui.js → only the three buttons arrive/start/missed.',
    covers: ['text:Lịch không thể chuyển trạng thái'],
  },
  {
    what: 'staff-context.js#assert "… không có tác vụ này"',
    why: 'Guard behind buttons the UI never draws for that role: apply() removes them, pages are gated by allowed(), and switching the account closes any open dialog.',
    proof: 'grep -n "assert(" prototype/shared/*.js  → clinical (crm-automation, order-data, order-review), crm, booking, billing, config; each is reachable only from controls removed by staff-context.js#apply for the roles that lack the capability (see WC22–WC27, WF18).',
    covers: ['text:không có tác vụ này'],
  },
  {
    what: 'patient.js#action confirm-appointment toast "Chưa có lịch hẹn để xác nhận"',
    why: 'The button is rendered disabled when the patient has no appointment, so the click never happens (WI22).',
    proof: 'grep -o \'data-action="confirm-appointment" \\${ap.valid?\\x27\\x27:\\x27disabled\\x27}\' prototype/shared/patient.js  → disabled when invalid.',
    covers: ['text:Chưa có lịch hẹn để xác nhận'],
  },
  {
    what: 'finance.js#rates and #receipts doctor placeholders ("Bác sĩ xem tỷ lệ trên các lượt của mình…", "Tài khoản bác sĩ không xem thu tiền toàn phòng khám.")',
    why: 'The doctor\'s tab bar has only Tổng quan and Tiền thủ thuật, and the tab variable changes only through those buttons.',
    proof: 'grep -o "role===.doctor.?\\[\\]:\\[\\[.rates" prototype/finance/finance.js  → the two tab buttons are omitted for a doctor (WG6, WG7).',
    covers: [],
  },
  {
    what: 'finance.js role switch ("Đang chuyển không gian…")',
    why: 'The #role input is hidden and nothing in the UI changes it; the role comes from the staff account picker, which re-renders the whole page.',
    proof: 'grep -o "id=\\"role\\"" prototype/finance/finance.js  → <input type="hidden" id="role">; no other code sets its value after mount.',
    covers: [],
  },
];

// HTML-building helpers of the old code that draw no screen of their own: each one is a part of the screens that call
// it, which are listed by their own functions. Allow-list for the static guard, with the reason.
const helperFns = [
  ['care-finance.js#modal', 'frame of the add-service dialog (WC19)'],
  ['clinic.js#pageHead', 'page heading shared by every page'],
  ['crm-ui.js#btn', 'button factory'],
  ['crm-ui.js#field', 'form field factory'],
  ['crm-ui.js#select', 'select factory'],
  ['crm-ui.js#head', 'page heading of the CSKH pages'],
  ['crm-ui.js#badge', 'status chip factory'],
  ['crm-ui.js#tile', 'KPI tile factory'],
  ['crm-ui.js#modal', 'dialog frame of the CSKH dialogs (WC18, WD2–WD5)'],
  ['data.js#face', 'illustrative face used by the photo comparisons'],
  ['operations-ui.js#button', 'button factory'],
  ['operations-ui.js#options', 'option list factory'],
  ['operations-ui.js#field', 'form field factory'],
  ['operations-ui.js#select', 'select factory'],
  ['operations-ui.js#input', 'input factory'],
  ['operations-ui.js#head', 'page heading of the operations pages'],
  ['operations-ui.js#stat', 'stat tile factory'],
  ['operations-ui.js#card', 'booking card (part of WB5, WB6)'],
  ['operations-ui.js#dialog', 'dialog frame of the operations dialogs (WB7, WB8, WE4, WE6, WF2)'],
  ['ui.js#icon', 'SVG icon factory'],
  ['finance.js#metric', 'metric tile factory'],
];
const helpers = helperFns.map(([name, why]) => ({ key: `fn:${name}`, why }));

module.exports = { OWNER, DOCTOR, CARE, ACCOUNTANT, groups, screens, actions, non_screens, helpers };

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
    notes: 'Sidebar (3 sections, 13 items, nav badge, user card), topbar (breadcrumbs, account picker, demo label, global search, bell, reset). The account picker is a native select; its open list is not capturable. Reset asks a native confirm(). finance-bridge.js adds a small link in the topbar ("Tài chính đã đồng bộ", "Đang đồng bộ tài chính…", "Tài chính chờ kết nối · thử lại") that follows the finance API.',
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
    covers: ['crm:arrive', 'crm:missed', 'dialog:today→Check-in'],
    notes: 'Check-in and Vắng in the reception list act at once and show this toast; they open no dialog. The toast disappears after 2.8 s.',
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

// Where each UI entry point of the old web goes. Key = `<attribute>:<value>`. Filled in after the first
// walk (see web-inventory.cjs, which fails on any entry point that is not listed here or in `covers`).
const actions = {};

// Things that exist in the old code but are NOT screens of the Clinic Web. Listed so the audit sees them.
const non_screens = [
  { what: 'prototype/patient-mobile/**', why: 'Patient Mobile web: out of scope, covered by app canvas groups E, G, K (plan section 1).' },
  { what: 'prototype/finance/index.html', why: 'Redirect stub ("Đang mở tài chính trong Pema Clinic…") that sends the browser to clinic-web/?screen=finance (WG1).' },
  { what: 'data-modal="appointment" (clinic.js#modalHtml "Đặt lịch nhanh")', why: 'Dead code: no button opens it; the click handler routes it to the booking dialog (WB7).' },
  { what: 'clinic.js#modalHtml fallback "Chưa có form trong demo"', why: 'Dead code: every data-modal value in the UI has a form.' },
  { what: 'native confirm()/prompt()/print()', why: 'Reset demo, void a finance entry, close month, pay out, print an order: browser dialogs, not capturable as a page; named in the notes of WA1, WG2, WF6.' },
  { what: 'role picker option list', why: 'Native select popup; the closed picker is part of WA1.' },
];

module.exports = { OWNER, DOCTOR, CARE, ACCOUNTANT, groups, screens, actions, non_screens };

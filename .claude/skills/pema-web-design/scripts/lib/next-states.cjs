// W8: how the Next.js inventory ids (WJ, WK, WL) are put in the state they describe, against the front end's mock back end.
//
// The inventory `reach` (catalog-nextjs.cjs) says what a person does; where a state needs data the mock does not give by
// default (an empty list, an error answer, a role the mock has no user for) a `note` step says so, and this file turns the
// note into code. An entry here is
//   { pre(page, h)    runs before the page opens: intercept API calls of the page (h.mutate, h.failWith, h.stall)
//     after(page, h)  runs after the reach: the clicks the note describes
//     steps           replaces the inventory reach (needed when a name is ambiguous, e.g. a "Khóa" chip and a "Khóa" button)
//     unreachable     the mock cannot give this state: the reason, recorded in the manifest; no frame is faked }
// Interception happens in the browser (Playwright routes on the page's own /api/v1 calls): the front end and the mock are
// untouched, and the real answer is the base of every change, so what is left is the real shape of the contract.
// Every text below is a label the front end shows, read from its code.

const api = (p) => new RegExp(`/api/v1${p}(\\?.*)?$`);

/** A list answer with no row: a bare array stays [], a page keeps its envelope. */
const emptyList = (j) => (Array.isArray(j) ? [] : j && Array.isArray(j.items) ? { ...j, items: [], total: 0 } : j);

/** Click the button named `name` inside the first element matching `css` (a row, a card, a dialog). */
async function within(page, css, name) {
  await page.locator(css).first().getByRole('button', { name }).first().click({ timeout: 10000 });
}

/** Click the button `name` inside the row/card that shows `rowText`. */
async function inRow(page, rowText, name) {
  const row = page.locator('tr, li, article, [data-row]').filter({ hasText: rowText }).filter({ has: page.getByRole('button', { name }) }).last();
  await row.getByRole('button', { name }).first().click({ timeout: 10000 });
}

/** Open a SelectMenu (button with aria-haspopup=listbox) by its accessible name and pick the option showing `text`. */
async function pick(scope, trigger, text) {
  const page = typeof scope.page === 'function' ? scope.page() : scope;
  await scope.getByRole('button', { name: trigger }).first().click({ timeout: 10000 });
  await page.getByRole('option', { name: text }).first().click({ timeout: 10000 });
}

/** Click the button `name` in the row of the tools table that shows the tool key `key`. */
async function inToolRow(page, key, name) {
  await page.locator(`div.justify-between:has(code:text-is("${key}"))`).first().getByRole('button', { name, exact: true }).click({ timeout: 10000 });
}

/** Scroll the scrolling area of the app shell (`main`) to its end. */
async function scrollMainToEnd(page) {
  await page.evaluate(() => {
    const main = document.querySelector('main');
    if (main) main.scrollTo(0, main.scrollHeight);
    window.scrollTo(0, document.body.scrollHeight);
  });
}

/** Drag a file over the element `css` without dropping it (the drop zone lights up on dragenter). */
async function dragOver(page, css) {
  await page.evaluate((sel) => {
    const el = document.querySelector(sel);
    const dt = new DataTransfer();
    dt.items.add(new File(['ghi chú'], 'tai-lieu.txt', { type: 'text/plain' }));
    el.dispatchEvent(new DragEvent('dragenter', { dataTransfer: dt, bubbles: true, cancelable: true }));
  }, css);
}

const KILL_ON = (j) =>
  Array.isArray(j)
    ? j.map((c) => (c.channel === 'zalo_bot' ? { ...c, kill_switch_on: true, kill_switch_changed_at: '2026-09-20T08:40:00+07:00', kill_switch_reason: 'Tạm dừng tin chủ động để kiểm tra nội dung.' } : c))
    : j;

/** The live-event stream never connects (blocked before the page opens); the screen says so 10 s later, when it falls back to a refresh timer. */
const blockStream = async (page) => page.context().route(/\/api\/v1\/events(\?.*)?$/, (route) => route.abort());
const waitStreamDown = async (page) => page.getByText('Mất kết nối cập nhật trực tiếp').first().waitFor({ state: 'visible', timeout: 25000 });

/**
 * The approval badge of the care matrix: the mock keeps ONE matrix whose "pending doctor approval" flag a captured click
 * would flip for every later shot, so both the read and the approval call are answered here. `approved` is where it starts.
 */
async function matrixApproval(page, h, { approved, canEdit = true }) {
  let ok = approved;
  let last = null;
  await h.mutate(page, api('/care/admin/matrix'), (j) => {
    last = { ...j, pending_doctor_approval: !ok, can_edit: canEdit };
    return last;
  });
  await h.mutate(page, api('/care/admin/matrix/approval'), (j, req) => {
    ok = JSON.parse(req.postData() || '{}').approved === true;
    return { ...last, pending_doctor_approval: !ok };
  }, { method: 'POST' });
}

/** Apply `fn` to the care timeline of a patient (the answer has a patient_id; a page navigation to the same path is passed on). */
const timelineOf = (fn) => (j) => (j && j.patient_id ? fn(j) : j);

const states = {
  // ===================================================================================================================
  // WJ  /admin/users
  // ===================================================================================================================
  WJ5: {
    // the mock answers a taken e-mail with exactly this 409; it is answered here so the capture never counts against the
    // mock's 5-per-minute limit for staff creation (the clock is frozen, the window never rolls over)
    pre: async (page, h) => h.mutate(page, api('/admin/users'), () => h.failWith(409, 'invalid_state', 'Email đăng nhập này đã được dùng trong phòng khám. Hãy chọn email khác.'), { method: 'POST' }),
    after: async (page, h) => {
      const d = h.dialog(page);
      await d.getByLabel('Họ tên', { exact: true }).fill('Trần Thị Mẫu');
      await d.getByLabel('Email đăng nhập', { exact: true }).fill('owner@pema.test');
      await d.getByLabel('Mật khẩu ban đầu', { exact: true }).fill('matkhau-demo-1');
      await d.getByLabel('Nhập lại mật khẩu', { exact: true }).fill('matkhau-demo-1');
      await d.getByRole('button', { name: 'Thêm nhân viên', exact: true }).click();
      await d.getByRole('alert').first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
      await h.ready(page, 300);
    },
  },
  WJ7: {
    steps: [{ login: 'owner' }, { goto: '/admin/users' }, { run: (page) => inRow(page, '(Bạn)', /^Sửa /) }],
  },
  WJ9: {
    steps: [{ login: 'owner' }, { goto: '/admin/users' }, { run: (page) => within(page, 'tbody tr', /^Khóa /) }],
  },

  // ===================================================================================================================
  // WJ  /admin/overview
  // ===================================================================================================================
  WJ13: {
    // the warning shows when the provider has no model (or neither a base URL nor a key)
    pre: async (page, h) => h.mutate(page, api('/admin/model/provider'), (j) => ({ ...j, model: '', base_url: '', api_key_masked: '' })),
  },
  WJ14: {
    pre: async (page, h) =>
      h.mutate(page, api('/admin/usage/overview'), (j) => ({
        ...j,
        usage_by_account: (j.usage_by_account || []).map((u) => ({ ...u, daily: [] })),
      })),
  },

  // ===================================================================================================================
  // WJ  /admin/threads
  // ===================================================================================================================
  WJ18: {
    pre: async (page, h) => h.mutate(page, /\/api\/v1\/admin\/traces\/[^/]+\/[^/?]+(\?.*)?$/, (j) => ({ ...j, turns: [], next_cursor: null })),
  },
  WJ22: { pre: async (page, h) => h.mutate(page, api('/admin/threads'), emptyList) },

  // ===================================================================================================================
  // WJ  /admin/contacts, /admin/friends
  // ===================================================================================================================
  WJ25: { pre: async (page, h) => h.mutate(page, api('/admin/contacts'), emptyList) },
  WJ28: {
    // no personal Zalo account: the page filters the shell's account list on channel zalo_personal
    pre: async (page, h) => h.mutate(page, api('/admin/accounts'), (j) => (Array.isArray(j) ? j.filter((a) => a.channel !== 'zalo_personal') : j)),
  },
  WJ29: {
    pre: async (page, h) => h.mutate(page, /\/api\/v1\/admin\/friends\/[^/]+\/list(\?.*)?$/, () => h.failWith(409, 'invalid_state', 'Tài khoản chưa chạy.')),
  },

  // ===================================================================================================================
  // WJ  /admin/schedules
  // ===================================================================================================================
  WJ31: { pre: async (page, h) => h.mutate(page, api('/admin/schedules'), emptyList) },
  WJ32: {
    pre: async (page, h) =>
      h.mutate(page, api('/admin/schedules'), (j) =>
        Array.isArray(j)
          ? j.map((job, i) =>
              i === 0
                ? { ...job, last_status: 'error', last_error: 'Zalo trả lỗi khi gửi tin: kênh tạm thời không gửi được.' }
                : i === 1
                  ? { ...job, last_status: 'blocked', last_error: 'Công tắc khẩn của kênh đang bật nên lịch này không chạy.' }
                  : job,
            )
          : j,
      ),
  },
WJ34: {
    // the form opens on the first account (the Zalo Bot, profile patient_channel) and says so: nothing to click
    after: async () => {},
  },

  // ===================================================================================================================
  // WJ  /admin/memory, /admin/kb
  // ===================================================================================================================
  WJ39: { pre: async (page, h) => h.mutate(page, api('/admin/memories'), emptyList) },
  WJ41: { pre: async (page, h) => h.mutate(page, api('/admin/kb/sources'), emptyList) },
  WJ43: { after: async (page) => dragOver(page, 'div.relative:has(table)') },
  WJ44: {
    pre: async (page, h) => {
      const set = (j) => (Array.isArray(j) ? j.map((src, i) => (i === 0 ? { ...src, status: 'hong', error: 'Không đọc được nội dung file (định dạng không hỗ trợ).' } : i === 1 ? { ...src, status: 'dang_xu_ly' } : i === 2 ? { ...src, status: 'cho_xu_ly' } : src)) : j);
      await h.mutate(page, api('/admin/kb/sources'), set);
    },
  },

  // ===================================================================================================================
  // WJ  /admin/accounts
  // ===================================================================================================================
  // the empty sentence of the account list sits below the channel panel: scroll to it
  WJ55: { pre: async (page, h) => h.mutate(page, api('/admin/accounts'), emptyList), after: async (page, h) => { await scrollMainToEnd(page); await h.ready(page, 200); } },
  WJ56: { pre: async (page, h) => h.mutate(page, api('/admin/channels'), KILL_ON), after: async () => {} },
  WJ57: {
    pre: async (page, h) => h.mutate(page, api('/admin/channels/zalo_bot'), () => h.failWith(409, 'version_conflict', 'Kênh vừa được người khác cập nhật. Tải lại rồi thử lại.'), { method: 'PUT' }),
    after: async (page, h) => {
      const section = page.locator('section[aria-label]').filter({ has: page.locator('#cap-zalo_bot') }).first();
      await page.locator('#cap-zalo_bot').fill('15');
      await section.getByRole('button', { name: 'Lưu cấu hình' }).click();
      await h.ready(page, 400);
    },
  },
  WJ59: { pre: async (page, h) => h.mutate(page, api('/admin/channels'), KILL_ON) },
  WJ61: {
    after: async (page, h) => {
      await pick(h.dialog(page), 'Loại kênh', 'Tài khoản bot chính thức');
      await h.ready(page, 250);
    },
  },
  WJ64: {
    pre: async (page, h) => {
      const scanned = () => ({ state: 'scanned', qr_png_base64: null, detail: null });
      await h.mutate(page, /\/api\/v1\/admin\/accounts\/[^/]+\/login\/status$/, scanned);
      await h.mutate(page, /\/api\/v1\/admin\/accounts\/[^/]+\/login$/, scanned, { method: 'POST' });
    },
  },
  WJ65: {
    pre: async (page, h) => {
      // the entry names "error or expired" and expects the expired sentence ("Hết thời gian chờ quét (3 phút)")
      const failed = () => ({ state: 'expired', qr_png_base64: null, detail: null });
      await h.mutate(page, /\/api\/v1\/admin\/accounts\/[^/]+\/login\/status$/, failed);
      await h.mutate(page, /\/api\/v1\/admin\/accounts\/[^/]+\/login$/, failed, { method: 'POST' });
    },
  },
  // ===================================================================================================================
  // WJ  /admin/agents
  // ===================================================================================================================
  WJ70: { pre: async (page, h) => h.mutate(page, api('/admin/agents'), emptyList) },
  WJ72: {
    // the default agent cannot be deleted (its menu entry is disabled): open the menu of another one
    steps: [{ login: 'owner' }, { goto: '/admin/agents' }, { run: (page) => page.getByRole('button', { name: /Hành động khác cho Trợ lý nội bộ/ }).first().click() }, { text: 'Xóa agent' }],
  },
  WJ75: {
    // the inventory expects the validation sentence of "Số bước tối đa" (1 - 30); the other half of the entry (the tools
    // block failing to load) is a state of the same page this frame does not show
    after: async (page, h) => {
      await (await h.field(page, 'Số bước tối đa')).fill('99');
      await h.ready(page, 250);
    },
  },
  WJ76: {
    // the mock's default agent is "cskh-da-lieu"; the inventory's "default" is an id this mock does not have (see WJ77)
    steps: [{ login: 'owner' }, { goto: '/admin/agents/cskh-da-lieu' }],
  },
  WJ78: {
    steps: [{ login: 'owner' }, { goto: '/admin/agents/cskh-da-lieu' }, { run: (page) => page.locator('#ag-d-ten').fill('CSKH Da liễu (đang sửa)') }, { button: 'Quay lại' }],
  },

  // ===================================================================================================================
  // WJ  /admin/tools
  // ===================================================================================================================
  WJ80: { pre: async (page, h) => h.mutate(page, api('/admin/accounts'), emptyList) },
  WJ81: { pre: async (page, h) => h.mutate(page, api('/admin/agents'), () => h.failWith(500, 'internal', 'Không tải được danh sách agent.')) },
  WJ82: { steps: [{ login: 'owner' }, { goto: '/admin/tools' }, { run: (page) => inToolRow(page, 'web_search', 'Settings') }] },
  WJ83: { steps: [{ login: 'owner' }, { goto: '/admin/tools' }, { run: (page) => inToolRow(page, 'web_fetch', 'Settings') }] },
  WJ84: {
    pre: async (page, h) =>
      h.mutate(page, api('/admin/tools/web_search'), (j) => ({
        ...j,
        brave_api_key_set: true,
        steps: (j.steps || []).map((x) => (x.id === 'brave' ? { ...x, enabled: true } : x)),
      })),
    steps: [{ login: 'owner' }, { goto: '/admin/tools' }, { run: (page) => inToolRow(page, 'web_search', 'Settings') }, { button: 'Xóa key Brave' }],
  },
  WJ85: { steps: [{ login: 'owner' }, { goto: '/admin/tools' }, { run: (page) => inToolRow(page, 'read_image', 'Settings') }] },
  WJ86: { steps: [{ login: 'owner' }, { goto: '/admin/tools' }, { run: (page) => inToolRow(page, 'create_image', 'Settings') }] },

  // ===================================================================================================================
  // WJ  /admin/mcp
  // ===================================================================================================================
  WJ88: { pre: async (page, h) => h.mutate(page, api('/admin/mcp/servers'), emptyList) },
  WJ89: {
    pre: async (page, h) =>
      h.mutate(page, api('/admin/mcp/servers'), (j) =>
        Array.isArray(j)
          ? j.map((srv, i) => (i === 0 ? { ...srv, status: 'loi', error: 'Không kết nối được tới máy chủ MCP (hết thời gian chờ).' } : i === 1 ? { ...srv, status: 'can_duyet_lai' } : srv))
          : j,
      ),
  },

  // ===================================================================================================================
  // WJ  /admin/traces, /admin/logs
  // ===================================================================================================================
  WJ95: { pre: async (page, h) => h.mutate(page, api('/admin/traces'), (j) => ({ ...j, turns: [], next_cursor: null })) },
  WJ97: { after: async (page) => scrollMainToEnd(page) },
  WJ100: {
    pre: async (page, h) => h.mutate(page, api('/admin/logs/app'), (j) => ({ ...j, entries: [], scopes: [], next_cursor: null, disabled: true, hint: 'Ghi log ra file đang tắt. Bật LOG_TO_FILE=true rồi khởi động lại backend để xem nhật ký ứng dụng ở đây.' })),
  },
  WJ101: { pre: async (page, h) => h.mutate(page, api('/admin/logs/app'), (j) => ({ ...j, entries: [], next_cursor: null })) },

  // ===================================================================================================================
  // WJ  /admin/policy, /admin/tuning
  // ===================================================================================================================
  WJ103: { after: async (page, h) => { await pick(page, /Hồ sơ chính sách của/, 'Trợ lý nội bộ'); await h.ready(page, 300); } },
  WJ104: {
    pre: async (page, h) => {
      await h.mutate(page, api('/admin/accounts'), emptyList);
      await h.mutate(page, api('/admin/agents'), emptyList);
    },
  },
  WJ111: {
    // the reset button is disabled until at least one parameter holds an override of the dashboard
    pre: async (page, h) =>
      h.mutate(page, api('/admin/model/tuning'), (j) => ({
        ...j,
        items: (j.items || []).map((it, i) => (i === 0 ? { ...it, overridden: true, value: 64000 } : it)),
      })),
  },
  WJ113: {
    pre: async (page, h) => h.mutate(page, api('/admin/model/provider'), (j) => ({ ...j, provider: 'openai-compatible', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai' })),
  },
  // ===================================================================================================================
  // WK  /admin/care/*
  // ===================================================================================================================
  WK2: { pre: async (page, h) => h.mutate(page, api('/care/admin/staff'), (j) => ({ ...j, items: [] })) },
  WK5: { pre: async (page, h) => h.mutate(page, api('/care/admin/on-call'), (j) => ({ ...j, items: [], chain_ends_with_on_call: false })) },
  WK6: {
    pre: async (page, h) => h.mutate(page, api('/care/admin/on-call'), (j) => ({ ...j, items: (j.items || []).map((c) => ({ ...c, active: false })), chain_ends_with_on_call: false })),
  },
  WK10: {
    // "approved by the doctor": click the badge button, then confirm in the dialog (the answer is the page's own, see matrixApproval)
    pre: async (page, h) => matrixApproval(page, h, { approved: false }),
    steps: [{ login: 'doctor' }, { goto: '/admin/care/matrix' }, { button: 'Bác sĩ duyệt' }, { run: (page, h) => h.dialog(page).getByRole('button', { name: 'Duyệt', exact: true }).click() }],
    after: async (page, h) => { await page.getByText('Bác sĩ đã duyệt ma trận.').first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {}); await h.ready(page, 300); },
  },
  WK11: { pre: async (page, h) => matrixApproval(page, h, { approved: false, canEdit: false }), after: async () => {} },
  WK13: { pre: async (page, h) => matrixApproval(page, h, { approved: false }) },
  WK14: { pre: async (page, h) => matrixApproval(page, h, { approved: true }) },
  WK16: { pre: async (page, h) => h.mutate(page, api('/care/admin/timing'), (j) => ({ ...j, can_edit: false })) },
  WK19: { pre: async (page, h) => h.mutate(page, api('/care/admin/alerts'), (j) => ({ ...j, items: [] })) },
  WK20: { pre: async (page) => blockStream(page), after: async (page) => waitStreamDown(page) },

  // ===================================================================================================================
  // WK  /care/*
  // ===================================================================================================================
  WK23: { pre: async (page, h) => h.mutate(page, api('/care/handoffs'), (j) => ({ ...j, items: [] })) },
  WK24: {
    pre: async (page, h) =>
      h.mutate(page, api('/care/handoffs'), (j) => ({
        ...j,
        items: (j.items || []).map((it, i) => (i === 0 ? { ...it, urgency: 'urgent', on_call_step: true, reason: 'red_flag', confidence: 0.4 } : it)),
      })),
  },
  WK25: {
    pre: async (page, h) => h.mutate(page, /\/api\/v1\/care\/handoffs\/[^/]+\/accept$/, () => h.failWith(409, 'invalid_state', 'Yêu cầu này đã có người nhận hoặc đã đóng.'), { method: 'POST' }),
    after: async (page, h) => {
      await page.getByRole('button', { name: 'Nhận cuộc trò chuyện' }).first().click();
      await page.getByText('Yêu cầu này đã có người nhận hoặc đã đóng.').first().waitFor({ state: 'visible', timeout: 8000 }).catch(() => {});
      await h.ready(page, 300);
    },
  },
  WK27: { pre: async (page) => blockStream(page), after: async (page) => waitStreamDown(page) },
  WK30: { pre: async (page, h) => h.mutate(page, /\/api\/v1\/care\/patients\/[^/]+\/timeline$/, timelineOf((j) => ({ ...j, control: { ...j.control, state: 'HANDOFF_ROUTING', staff_owner_id: null, staff_owner_name: null }, can_release: false }))) },
  WK31: { pre: async (page, h) => h.mutate(page, /\/api\/v1\/care\/patients\/[^/]+\/timeline$/, timelineOf((j) => ({ ...j, pending_drafts: [], paused_reminders: [], entries: [], memory: [] }))) },
  WK32: { after: async () => {} },
  WK36: { pre: async (page, h) => h.mutate(page, /\/api\/v1\/care\/patients\/[^/]+\/timeline$/, timelineOf((j) => ({ ...j, can_release: false, control: { ...j.control, state: 'STAFF', staff_owner_name: 'Đặng Minh Thư' } }))) },
  WK37: { after: async () => {} },
  WK39: { pre: async (page, h) => h.mutate(page, /\/api\/v1\/care\/patients\/[^/]+\/timeline$/, timelineOf((j) => ({ ...j, memory: [] }))) },

  // ===================================================================================================================
  // WL  sign-in, shell, templates
  // ===================================================================================================================
  WL2: { pre: async (page, h) => h.stall(page, api('/auth/login')) },
  WL6: { pre: async (page, h) => h.mutate(page, api('/admin/templates'), emptyList) },
  WL14: {
    // the mock has no user without permissions: the owner's session, answered by /me as a patient (role patient, no permission)
    steps: [{ login: 'owner' }, { goto: '/today' }],
    pre: async (page, h) =>
      h.mutate(page, api('/me'), (j) => ({ ...j, user: { ...j.user, role: 'patient', display_name: 'Bệnh nhân (mẫu)' }, permissions: [] })),
    after: async () => {},
  },
  WL15: {
    steps: [{ login: 'owner' }, { goto: '/today' }],
    pre: async (page, h) => h.stall(page, api('/me')),
    after: async () => {},
  },
  WL16: {
    steps: [{ login: 'owner' }, { goto: '/today' }],
    pre: async (page, h) => h.mutate(page, api('/me'), () => h.failWith(500, 'internal', 'Máy chủ tạm thời không trả lời. Hãy thử lại sau.')),
    after: async () => {},
  },
};

module.exports = states;
module.exports.helpers = { api, emptyList, within, inRow, pick };

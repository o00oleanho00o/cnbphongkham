// Shared helpers for the Next.js front end (pema-agent/frontend) as the shots (W8) and the snapshot (W9) see it.
// Counterpart of old-web.cjs for the inventory entries with `source: "nextjs"`. Never edits the front end or the mock.
//
// Needs the front end on PEMA_NEXT_BASE (default http://localhost:3480) in front of the mock back end started with
// lib/frozen-time.cjs (see its header). `reach` of an entry is a short description, not a script (catalog-nextjs.cjs):
//   {login: 'owner'}            sign in as the mock user of the role by POST /api/v1/auth/login (cookie lands in the context)
//   {goto: '/path'}             open a route
//   {button: 'Name'}            click the button or link with this accessible name (exact first, then substring)
//   {text: 'Label'}             click the element showing this text (chip, tab, row)
//   {fill: ['Label', 'value']}  fill the field with this label, aria-label or placeholder
//   {wait: 'Text'}              wait until the text is visible
//   {note: '...'}               a state the mock does not give by default: lib/next-states.cjs says how to reach it
// States that need other data or an error answer are described in lib/next-states.cjs, per inventory id. An id that has
// a `note` step and no entry there is reported as unreachable; nothing is faked.

const { FREEZE_CSS, DEFAULT_CLOCK, TIMEZONE, LOCALE } = require('./old-web.cjs');

const BASE = (process.env.PEMA_NEXT_BASE || 'http://localhost:3480').replace(/\/$/, '');
const STEP_TIMEOUT = 10000;

/** The mock cannot give this state: a fact to report, not a flaky step to retry. */
class Unreachable extends Error {}
const PASSWORD = 'demo1234';
const EMAIL = {
  owner: 'owner@pema.test',
  manager: 'manager@pema.test',
  doctor: 'doctor@pema.test',
  cs_staff: 'cs@pema.test',
  reception: 'reception@pema.test',
};

/** Short patient numbers of the inventory ("/care/patients/7/timeline") are the mock's fake uuids (mock/core.ts uuid(n, 2)). */
const patientId = (n) => `00000000-0000-4000-8002-${Number(n).toString(16).padStart(12, '0')}`;

/** New isolated browser context: fixed zone, locale, clock and no animation, like the old-web contexts. */
async function newPage(browser, { viewport, clock = DEFAULT_CLOCK } = {}) {
  const context = await browser.newContext({ viewport, timezoneId: TIMEZONE, locale: LOCALE, deviceScaleFactor: 1, reducedMotion: 'reduce', acceptDownloads: false });
  const page = await context.newPage();
  page.errors = [];
  page.on('pageerror', (e) => page.errors.push(String(e.message || e).slice(0, 200)));
  // a failed request the mock answers with 5xx is a defect; a 4xx is a state of the screen
  page.on('response', (r) => {
    if (r.status() >= 500 && !page.expected5xx) page.errors.push(`http ${r.status()} ${new URL(r.url()).pathname}`);
  });
  await context.clock.setFixedTime(new Date(clock));
  await context.addInitScript((css) => {
    const add = () => {
      const s = document.createElement('style');
      s.textContent = css;
      (document.head || document.documentElement).appendChild(s);
    };
    if (document.head) add();
    else document.addEventListener('DOMContentLoaded', add, { once: true });
  }, FREEZE_CSS + 'nextjs-portal{display:none!important}'); // the dev server's "N" badge is not part of the product
  return page;
}

/** Sign in as the mock user of `role` without the form (the form is WL1-WL3's own business). */
async function login(page, role) {
  const email = EMAIL[role];
  if (!email) throw new Error(`no mock user for role ${role}`);
  const res = await page.context().request.post(`${BASE}/api/v1/auth/login`, { data: { email, password: PASSWORD } });
  if (!res.ok()) throw new Error(`login ${role}: HTTP ${res.status()}`);
}

/**
 * Answer a call of the API with the real answer changed by `fn(json, request)`, or replaced: `fn` may return
 * failWith(...). Only a GET is fetched for real (its answer is the base of the change); any other method is answered
 * without reaching the mock, so a captured "save" never writes to its data (the mock's state stays what every other shot saw).
 */
async function mutate(page, glob, fn, { method = 'GET' } = {}) {
  await page.context().route(glob, async (route) => {
    if (route.request().method() !== method) return route.fallback();
    let response = null;
    let json = null;
    if (method === 'GET') {
      try {
        response = await route.fetch();
      } catch {
        return route.abort();
      }
      try {
        json = await response.json();
      } catch {
        // not JSON: leave it
      }
    }
    // a page navigation that happens to match the glob (not JSON): let it through untouched
    if (method === 'GET' && json === null) return route.fulfill({ response });
    const out = fn(json, route.request());
    if (out && out.__status) {
      page.expected5xx = page.expected5xx || out.__status >= 500;
      return route.fulfill({ status: out.__status, contentType: 'application/json', body: JSON.stringify(out.body) });
    }
    if (!response) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(out) });
    return route.fulfill({ response, json: out });
  });
}

/** Answer a call of the API with a fixed status and the contract's error body. */
const failWith = (status, code, message) => ({ __status: status, body: { error: { code, message, request_id: 'mock-w8' } } });

async function stall(page, glob) {
  await page.context().route(glob, () => {
    // never answered: the screen stays in its loading state
  });
}

/** The page is quiet: no spinner or "Đang tải" left. (networkidle never comes: the live-event stream stays open.) */
async function ready(page, ms = 350) {
  await page.evaluate(() => document.fonts.ready);
  await page
    .waitForFunction(
      () => {
        const t = document.body ? document.body.innerText : '';
        if (/Đang tải|Đang kiểm tra|Đang lấy/.test(t)) return false;
        const spin = [...document.querySelectorAll('.animate-spin, [aria-busy="true"]')].some((e) => e.getClientRects().length);
        return !spin;
      },
      null,
      { timeout: 8000 },
    )
    .catch(() => {});
  await page.waitForTimeout(ms);
}

const pathOf = (p) => p.replace(/\/care\/patients\/(\d+)\//, (_, n) => `/care/patients/${patientId(n)}/`);

function byName(page, name, roles) {
  const loc = [];
  for (const role of roles) {
    loc.push(page.getByRole(role, { name, exact: true }), page.getByRole(role, { name }));
  }
  return loc;
}

async function firstVisible(locators) {
  for (const l of locators) {
    const n = await l.count();
    for (let i = 0; i < n; i++) {
      const el = l.nth(i);
      if (await el.isVisible()) return el;
    }
  }
  return null;
}

async function click(page, label, kind) {
  const roles = kind === 'text' ? ['tab', 'button', 'link', 'radio', 'checkbox'] : ['button', 'link'];
  const found = await firstVisible([...byName(page, label, roles), page.getByText(label, { exact: true }), page.getByText(label)]);
  if (!found) throw new Error(`nothing to click named "${label}"`);
  await found.click({ timeout: STEP_TIMEOUT });
  await ready(page, 250);
}

async function field(page, label) {
  const found = await firstVisible([page.getByLabel(label, { exact: true }), page.getByLabel(label), page.getByPlaceholder(label, { exact: true }), page.getByPlaceholder(label)]);
  if (!found) throw new Error(`no field labelled "${label}"`);
  return found;
}

async function runStep(page, step) {
  if (step.login !== undefined) await login(page, step.login);
  else if (step.goto !== undefined) {
    await page.goto(BASE + pathOf(step.goto), { waitUntil: 'load', timeout: 60000 });
    await ready(page, 500);
  } else if (step.button !== undefined) await click(page, step.button, 'button');
  else if (step.text !== undefined) await click(page, step.text, 'text');
  else if (step.fill !== undefined) {
    const f = await field(page, step.fill[0]);
    await f.fill(step.fill[1], { timeout: STEP_TIMEOUT });
    await ready(page, 250);
  } else if (step.wait !== undefined) await page.getByText(step.wait).first().waitFor({ state: 'visible', timeout: STEP_TIMEOUT });
  else if (step.press !== undefined) {
    await page.keyboard.press(step.press);
    await ready(page, 200);
  } else if (step.select !== undefined) {
    const f = await field(page, step.select[0]);
    await f.selectOption(step.select[1], { timeout: STEP_TIMEOUT });
    await ready(page, 250);
  } else if (step.check !== undefined) {
    const f = await field(page, step.check);
    await f.check({ timeout: STEP_TIMEOUT });
    await ready(page, 150);
  } else if (step.run !== undefined) await step.run(page, { mutate, failWith, stall, ready, click, field, patientId, BASE, dialog: (p) => p.getByRole('dialog').last() });
  else if (step.note !== undefined) throw new Unreachable(`the reach has a note step ("${step.note}") and lib/next-states.cjs has no way to reach it`);
  else throw new Error('unknown reach step ' + JSON.stringify(step));
}

/**
 * Reach one inventory entry on a fresh page. `states` is lib/next-states.cjs: an entry there replaces the inventory reach
 * (`steps`) and may add routes to intercept first (`pre`). Returns the page.
 */
async function open(page, entry, states, viewport) {
  const spec = states[entry.id];
  if (spec && spec.unreachable) throw new Unreachable(spec.unreachable);
  let steps = spec && spec.steps ? spec.steps : entry.reach;
  // `pre` / `after` build the state a `note` step only describes
  if (spec && (spec.pre || spec.after)) steps = steps.filter((s) => s.note === undefined);
  const helpers = { mutate, failWith, stall, ready, click, field, patientId, BASE, viewport, dialog: (p) => p.getByRole('dialog').last() };
  // role first: `pre` hooks may need the session cookie
  const first = steps.find((s) => s.login !== undefined);
  if (first) await login(page, first.login);
  if (spec && spec.pre) await spec.pre(page, helpers);
  for (const step of steps) {
    if (step.login !== undefined) continue;
    try {
      await runStep(page, step);
    } catch (e) {
      if (e instanceof Unreachable) throw e;
      throw new Error(`step ${JSON.stringify(step).slice(0, 120)}: ${String(e.message).split('\n')[0]}`);
    }
  }
  if (spec && spec.after) {
    try {
      await spec.after(page, helpers);
    } catch (e) {
      if (e instanceof Unreachable) throw e;
      throw new Error(`after: ${String(e.message).split('\n')[0]}`);
    }
  }
  return page;
}

/** Check `entry.expect.text` (innerText, case-insensitive: the kit upper-cases eyebrows). Returns '' when met. */
async function verify(page, entry) {
  const ex = entry.expect || {};
  if (!ex.text) return '';
  const text = await page.evaluate(() => document.body.innerText);
  if (text.toLowerCase().includes(ex.text.toLowerCase())) return '';
  const aria = await page.locator(`[aria-label="${ex.text.replace(/"/g, '\\"')}"]`).count();
  return aria ? '' : `text not found: ${ex.text}`;
}

module.exports = { Unreachable, BASE, EMAIL, patientId, newPage, login, mutate, failWith, stall, ready, open, verify, runStep };

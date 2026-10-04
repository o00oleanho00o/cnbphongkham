// Shared helpers for the old Pema web (served read-only on http://127.0.0.1:4173).
// Used by web-inventory (W0), web-shots (W1) and web-snapshot (W2). Never edits the web.
//
// An inventory entry reaches its screen with `reach`, a list of steps run on a fresh page:
//   {"goto": "/clinic-web/?staff={role}"}      path under base_url ({role} = entry.role or inventory.role)
//   {"click": "css"}                           click the first visible match
//   {"clickPopup": "css"}                      click, and continue on the page that opens (window.open)
//   {"main": true}                             go back to the first page after a clickPopup
//   {"fill": ["css", "text"]}                  type text into an input
//   {"press": ["css", "Enter"]}                 press a key in an input (fires its change handler)
//   {"select": ["css", "value"]}               choose an <option> value
//   {"check": "css"}                           tick a checkbox
//   {"wait": "css"}                            wait until visible
//   {"block": "url-glob"}                      abort requests to that URL (network down)
//   {"dialog": "accept"|"dismiss"}             answer the next native confirm()/prompt(); the message is kept in page.dialogs
//   {"hold": "url-glob"}                       never answer requests to that URL (loading state)
//   {"ifVisible": ["css", [steps]]}            run the steps only when the css is visible (idempotent set-up of a state)
//   {"upload": ["css", "png"|"txt"|"big"]}     choose a synthetic file in a file input (png = 1x1 image, txt = not an image,
//                                              big = 2.4 MB image-looking file)
//   {"hookPrint": true}                        count window.print() calls in page.printed instead of opening the print dialog
//   {"key": "Tab"}                             press a key on the page (focus states)
//   {"hover": "css"}                           move the mouse over the first visible match
//   {"setValue": ["css", "value"]}             set a value and fire input + change (date and month inputs)
//   {"gone": "css"}                            wait until nothing visible matches (a transient toast has gone)
//   {"tab": [steps]}                           run the steps in a second tab of the same browser (same storage), close it and
//                                              come back: another window changing the data under an open dialog
// `expect` ({selector, text}) says what must be visible once the steps are done.

const DEFAULT_CLOCK = '2026-09-20T09:00:00+07:00';
const TIMEZONE = 'Asia/Ho_Chi_Minh';
const LOCALE = 'vi-VN';
const STEP_TIMEOUT = 8000;

const FREEZE_CSS =
  '*,*::before,*::after{animation:none!important;transition:none!important;caret-color:transparent!important;scroll-behavior:auto!important}';

/** New isolated browser context: fixed zone, locale, empty storage. */
async function newPage(browser, { viewport = { width: 1440, height: 900 }, clock = DEFAULT_CLOCK } = {}) {
  const context = await browser.newContext({
    viewport,
    timezoneId: TIMEZONE,
    locale: LOCALE,
    deviceScaleFactor: 1,
    reducedMotion: 'reduce',
    acceptDownloads: false,
  });
  const page = await context.newPage();
  await freeze(page, clock);
  return page;
}

/** Fix the clock (whole context, so popups too), stop animations and collect page errors on `page.errors`. */
async function freeze(page, clock = DEFAULT_CLOCK) {
  page.errors = page.errors || [];
  const track = (p) => {
    p.on('pageerror', (e) => page.errors.push(String(e.message || e).slice(0, 200)));
  };
  track(page);
  const context = page.context();
  context.on('page', track);
  await context.clock.setFixedTime(new Date(clock));
  await context.addInitScript((css) => {
    const add = () => {
      const s = document.createElement('style');
      s.textContent = css;
      (document.head || document.documentElement).appendChild(s);
    };
    if (document.head) add();
    else document.addEventListener('DOMContentLoaded', add, { once: true });
  }, FREEZE_CSS);
}

/** Fonts loaded and layout settled; call before any capture or text read. */
async function settle(page, ms = 250) {
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(ms);
}

/** Empty localStorage/sessionStorage of the old web origin without running the app. */
async function clearStorage(page, base) {
  await page.goto(base + '/shared/ui.js');
  await page.evaluate(() => {
    try {
      localStorage.clear();
      sessionStorage.clear();
    } catch {
      // storage can be blocked; the context is fresh anyway
    }
  });
}

function sub(text, vars) {
  return text.replace(/\{(\w+)\}/g, (_, k) => (vars[k] === undefined ? `{${k}}` : vars[k]));
}

/** Locator for the visible elements of a css selector (visible filter applies to the element itself). */
function visible(page, selector) {
  return page.locator(selector).locator('visible=true').first();
}

/** Run one reach step on `state.current`; `state.main` is the first page. */
async function runStep(step, state, { base, vars }) {
  const cur = state.current;
  if (step.goto !== undefined) {
    await cur.goto(base + sub(step.goto, vars), { waitUntil: 'load' });
    await settle(cur, 500);
  } else if (step.click !== undefined) {
    await visible(cur, step.click).click({ timeout: STEP_TIMEOUT });
    await settle(cur, 200);
  } else if (step.clickPopup !== undefined) {
    const [popup] = await Promise.all([
      cur.context().waitForEvent('page', { timeout: STEP_TIMEOUT }),
      visible(cur, step.clickPopup).click({ timeout: STEP_TIMEOUT }),
    ]);
    await popup.waitForLoadState('load');
    state.current = popup;
    await settle(popup, 400);
  } else if (step.main !== undefined) {
    state.current = state.main;
  } else if (step.fill !== undefined) {
    await visible(cur, step.fill[0]).fill(step.fill[1], { timeout: STEP_TIMEOUT });
    await settle(cur, 150);
  } else if (step.select !== undefined) {
    await cur.locator(step.select[0]).first().selectOption(step.select[1], { timeout: STEP_TIMEOUT });
    await settle(cur, 150);
  } else if (step.press !== undefined) {
    await visible(cur, step.press[0]).press(step.press[1], { timeout: STEP_TIMEOUT });
    await settle(cur, 200);
  } else if (step.check !== undefined) {
    await cur.locator(step.check).first().check({ timeout: STEP_TIMEOUT });
  } else if (step.wait !== undefined) {
    await visible(cur, step.wait).waitFor({ timeout: STEP_TIMEOUT });
  } else if (step.block !== undefined) {
    await cur.context().route(step.block, (route) => route.abort());
  } else if (step.dialog !== undefined) {
    cur.once('dialog', (d) => {
      cur.dialogs = cur.dialogs || [];
      cur.dialogs.push({ type: d.type(), message: d.message() });
      return step.dialog === 'accept' ? d.accept('Demo') : d.dismiss();
    });
  } else if (step.hold !== undefined) {
    await cur.context().route(step.hold, () => {
      // never fulfilled: the page stays in its loading state
    });
  } else if (step.ifVisible !== undefined) {
    const shown = await cur.locator(step.ifVisible[0]).locator('visible=true').count();
    if (shown) for (const inner of step.ifVisible[1]) await runStep(inner, state, { base, vars });
  } else if (step.upload !== undefined) {
    await cur.locator(step.upload[0]).first().setInputFiles(syntheticFile(step.upload[1]));
    await settle(cur, 400);
  } else if (step.gone !== undefined) {
    await cur.locator(step.gone).locator('visible=true').first().waitFor({ state: 'detached', timeout: STEP_TIMEOUT }).catch(() => {});
    await settle(cur, 100);
  } else if (step.tab !== undefined) {
    const second = await cur.context().newPage();
    const inner = { main: second, current: second };
    for (const sub of step.tab) await runStep(sub, inner, { base, vars });
    await second.close();
    await cur.bringToFront();
    await settle(cur, 200);
  } else if (step.hookPrint !== undefined) {
    await cur.evaluate(() => {
      window.__printed = 0;
      window.print = () => {
        window.__printed += 1;
      };
    });
  } else if (step.key !== undefined) {
    await cur.keyboard.press(step.key);
    await settle(cur, 150);
  } else if (step.hover !== undefined) {
    await visible(cur, step.hover).hover({ timeout: STEP_TIMEOUT });
    await settle(cur, 150);
  } else if (step.setValue !== undefined) {
    await cur.evaluate(([css, value]) => {
      const el = document.querySelector(css);
      el.value = value;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }, step.setValue);
    await settle(cur, 250);
  } else {
    throw new Error('unknown reach step ' + JSON.stringify(step));
  }
}

// 1x1 transparent PNG and plain text, so no real photo is ever involved
const PNG_1X1 = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
function syntheticFile(kind) {
  if (kind === 'txt') return { name: 'ghi-chu.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image') };
  if (kind === 'big') return { name: 'anh-lon.png', mimeType: 'image/png', buffer: Buffer.concat([PNG_1X1, Buffer.alloc(2_600_000)]) };
  return { name: 'anh-demo.png', mimeType: 'image/png', buffer: PNG_1X1 };
}

/** Steps that only wait or look are safe to run again after a slow first try. */
const RETRY = ['click', 'fill', 'wait'];

/**
 * Reach one inventory entry from a fresh page. Returns the page that shows the screen
 * (a popup page when a step used clickPopup).
 */
async function open(page, entry, { base, role } = {}) {
  const vars = { role: entry.role || role };
  const state = { main: page, current: page };
  await clearStorage(page, base);
  for (const step of entry.reach) {
    try {
      try {
        await runStep(step, state, { base, vars });
      } catch (e) {
        if (!RETRY.some((k) => step[k] !== undefined)) throw e;
        await state.current.waitForTimeout(700);
        await runStep(step, state, { base, vars });
      }
    } catch (e) {
      throw new Error(`step ${JSON.stringify(step)}: ${String(e.message).split('\n')[0]}`);
    }
  }
  return state.current;
}

/** Run extra steps (for example a native-dialog trigger) on a page that `open` already reached. */
async function run(page, steps, { base, role } = {}) {
  const vars = { role };
  const state = { main: page, current: page };
  for (const step of steps) {
    try {
      await runStep(step, state, { base, vars });
    } catch (e) {
      throw new Error(`step ${JSON.stringify(step)}: ${String(e.message).split('\n')[0]}`);
    }
  }
  return state.current;
}

/** Check `entry.expect`; returns '' when satisfied, else a short reason. */
async function verify(page, entry) {
  const ex = entry.expect || {};
  if (ex.selector) {
    const n = await page.locator(ex.selector).locator('visible=true').count();
    if (!n) return `selector not visible: ${ex.selector}`;
  }
  if (ex.text) {
    // innerText follows CSS text-transform (the eyebrows are upper case), so compare without case
    const text = await page.evaluate(() => document.body.innerText);
    if (!text.toLowerCase().includes(ex.text.toLowerCase())) return `text not found: ${ex.text}`;
  }
  return '';
}

/** Close every open dialog, modal and toast of the clinic web. */
async function closeAll(page) {
  await page.keyboard.press('Escape');
  await page.evaluate(() => {
    document.querySelectorAll('.modal-close,[data-close]').forEach((b) => b.offsetParent && b.click());
    document.querySelectorAll('dialog[open]').forEach((d) => d.close());
  });
  await page.waitForTimeout(150);
}

module.exports = {
  DEFAULT_CLOCK,
  TIMEZONE,
  LOCALE,
  FREEZE_CSS,
  newPage,
  freeze,
  settle,
  clearStorage,
  open,
  run,
  verify,
  closeAll,
};

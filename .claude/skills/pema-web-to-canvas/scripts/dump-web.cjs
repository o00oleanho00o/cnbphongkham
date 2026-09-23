// Dumps the visible text of every Pema web screen, tab and dialog so it can be diffed
// against the design canvas. Needs the prototype server: `docker compose up -d pema-prototype`.
// Usage: node dump-web.cjs [outFile] [baseUrl] [--only=prefix,prefix]
//   --only keeps sections whose name starts with a prefix (e.g. clinic:today,dialog:today,p360:);
//   pending.cjs prints the prefixes for the files changed since the last sync.
const fs = require('fs');
const { loadPlaywright } = require('./lib/pw.cjs');

const flags = process.argv.slice(2).filter((a) => a.startsWith('--'));
const args = process.argv.slice(2).filter((a) => !a.startsWith('--'));
const OUT = args[0] || 'web-dump.txt';
const BASE = (args[1] || 'http://127.0.0.1:4173').replace(/\/$/, '');
const ONLY = (flags.find((f) => f.startsWith('--only='))?.slice(7) || '').split(',').filter(Boolean);
const MAX = 1800;
const wanted = (name) => !ONLY.length || ONLY.some((p) => name.startsWith(p));

// Buttons that open a dialog or sub-state from a clinic page: [data-nav, button name].
const CLINIC_DIALOGS = [
  ['patients', 'Hồ sơ mới'],
  ['today', 'Đặt lịch mới'],
  ['today', 'Check-in'],
  ['schedule', 'Đặt lịch'],
  ['crm', 'Xử lý'],
  ['followups', 'Xử lý'],
  ['resources', 'Khóa phòng'],
  ['services', 'Chỉnh dịch vụ'],
  ['cashier', 'Thu tiền'],
  ['cashier', 'Mở form lên đơn nhanh'],
];
// Patient Mobile screens reachable only through a row inside another screen: [tab, link text].
const MOBILE_LINKS = [
  ['profile', 'Tài liệu & hóa đơn'],
  ['profile', 'Chăm sóc tại nhà'],
  ['journey', 'Ảnh trước & sau'],
];

const clean = (s) => s.replace(/\n{2,}/g, '\n').slice(0, MAX);

(async () => {
  const { chromium } = loadPlaywright();
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  let out = `# Web dump ${new Date().toISOString()} · ${BASE}${ONLY.length ? ` · only ${ONLY.join(',')}` : ''}\n`;
  const section = (name, text) => {
    if (wanted(name)) out += `\n\n######## ${name}\n${clean(text)}`;
  };

  const content = () =>
    page.evaluate(() => (document.querySelector('.content') || document.querySelector('#app') || document.body).innerText);
  const openDialog = () =>
    page.evaluate(() => {
      const els = [...document.querySelectorAll('dialog[open], .modal-backdrop, .modal, [role=dialog]')].filter(
        (e) => e.open || e.offsetParent !== null,
      );
      return els.length ? els[els.length - 1].innerText : null;
    });
  const closeAll = async () => {
    await page.keyboard.press('Escape');
    await page.evaluate(() => {
      document.querySelectorAll('.modal-close,[data-close]').forEach((b) => b.offsetParent && b.click());
      document.querySelectorAll('dialog[open]').forEach((d) => d.close());
    });
    await page.waitForTimeout(200);
  };
  const settle = () => page.waitForTimeout(300);

  // Clinic Web: every sidebar page.
  await page.goto(`${BASE}/clinic-web/`);
  await page.waitForTimeout(800);
  const navs = await page.$$eval('[data-nav]', (els) => [...new Set(els.map((e) => e.dataset.nav))]);
  out += `\nCLINIC NAV: ${navs.join(', ')}`;
  for (const nav of navs) {
    try {
      await page.locator(`[data-nav="${nav}"]`).first().click({ timeout: 2000 });
      await settle();
      section(`clinic:${nav}`, await content());
    } catch (e) {
      out += `\n## clinic:${nav} FAILED ${e.message.slice(0, 80)}`;
    }
  }

  // Patient 360: every tab, plus each modal button the first time it is seen.
  await page.locator('[data-nav="patients"]').first().click();
  await page.locator('[data-patient]').first().click();
  await settle();
  const tabs = await page.$$eval('[data-tab]', (els) => [...new Set(els.map((e) => e.dataset.tab))]);
  out += `\nPATIENT 360 TABS: ${tabs.join(', ')}`;
  const seenModals = new Set();
  for (const tab of tabs) {
    try {
      await page.locator(`[data-tab="${tab}"]`).first().click({ timeout: 2000 });
      await settle();
      section(`p360:${tab}`, await content());
      const modals = await page.$$eval('[data-modal]', (els) => [
        ...new Set(els.filter((e) => e.offsetParent).map((e) => e.dataset.modal)),
      ]);
      for (const m of modals.filter((x) => !seenModals.has(x))) {
        seenModals.add(m);
        try {
          await page.locator(`[data-modal="${m}"]:visible`).first().click({ timeout: 1500 });
          await settle();
          section(`modal:${m}`, (await openDialog()) || '(no dialog)');
        } catch {}
        await closeAll();
      }
    } catch (e) {
      out += `\n## p360:${tab} FAILED`;
    }
  }

  for (const [nav, name] of CLINIC_DIALOGS) {
    try {
      await closeAll();
      await page.locator(`[data-nav="${nav}"]`).first().click();
      await settle();
      await page.getByRole('button', { name }).first().click({ timeout: 2500 });
      await settle();
      section(`dialog:${nav} → ${name}`, (await openDialog()) || `(in-page) ${await content()}`);
    } catch (e) {
      out += `\n## dialog:${nav} → ${name} FAILED ${e.message.slice(0, 80)}`;
    }
  }
  await closeAll();

  // Patient Mobile.
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${BASE}/patient-mobile/`);
  await page.waitForTimeout(800);
  const mobileText = () =>
    page.evaluate(() => (document.querySelector('.mobile-content') || document.querySelector('#app')).innerText);
  const screens = await page.$$eval('[data-screen]', (els) => [...new Set(els.map((e) => e.dataset.screen))]);
  out += `\nMOBILE SCREENS: ${screens.join(', ')}`;
  for (const s of screens) {
    await page.evaluate((s) => document.querySelector(`[data-screen="${s}"]`)?.click(), s);
    await settle();
    section(`mobile:${s}`, await mobileText());
  }
  for (const [tab, label] of MOBILE_LINKS) {
    try {
      await page.locator(`[data-screen="${tab}"]`).first().click();
      await settle();
      await page.getByText(label).first().click({ timeout: 2500 });
      await settle();
      section(`mobile:${tab} → ${label}`, await mobileText());
    } catch (e) {
      out += `\n## mobile:${tab} → ${label} FAILED`;
    }
  }

  // Finance (needs `python prototype/finance_server.py` for real numbers; tabs still list without it).
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(`${BASE}/finance/`);
  await page.waitForTimeout(800);
  const finTabs = await page.$$eval('[data-finance-tab]', (els) => [...new Set(els.map((e) => e.dataset.financeTab))]);
  for (const t of finTabs) {
    try {
      await page.locator(`[data-finance-tab="${t}"]`).first().click({ timeout: 2000 });
      await settle();
      section(`finance:${t}`, await content());
    } catch {}
  }

  out += `\n\nPAGE ERRORS: ${errors.join(' | ') || 'none'}\n`;
  fs.writeFileSync(OUT, out);
  await browser.close();
  console.log(`Wrote ${OUT} (${out.length} chars, ${errors.length} page errors)`);
})();

// `tsx scripts/live-real-check.ts`: the REAL two-browser check of live updates and presence against a running
// stack (docker compose in proxy mode behind Caddy, seed_demo data, a Zalo Bot account in webhook mode). Unlike
// presence-check.ts (mock backend) nothing is faked: two staff members in two browser contexts, a real inbound
// webhook, real Redis. It prints one line per observation with the measured time and exits 1 when a check fails.
// It stops and starts the Redis container once (step "redis"), so run it only against a throwaway stack.
//
//   LIVE_BASE_URL=https://localhost:48443 LIVE_PASSWORD=... LIVE_WEBHOOK_SECRET=... LIVE_ACCOUNT_ID=... \
//   LIVE_REDIS_CONTAINER=pema-g2a-redis-1 tsx scripts/live-real-check.ts [presence|inbound|redis]...
//
// Inbound text goes in one of two ways: LIVE_INJECT_URL (a fake Bot API the worker polls: the whole polling path
// runs, worker to Redis to API) or the webhook route with LIVE_WEBHOOK_SECRET = HMAC-SHA256(
// PEMA_SECRET_ENCRYPTION_KEY, "zalo-bot-webhook|<clinic id>|<account id>") (needs the account in webhook mode).
// Every message sent is synthetic.
import { execFileSync } from "node:child_process";

import { chromium, type Browser, type BrowserContext, type Page } from "playwright";

const BASE = process.env.LIVE_BASE_URL ?? "https://localhost:48443";
const PASSWORD = process.env.LIVE_PASSWORD ?? "";
const SECRET = process.env.LIVE_WEBHOOK_SECRET ?? "";
const ACCOUNT = process.env.LIVE_ACCOUNT_ID ?? "";
/** A fake Zalo Bot API the worker polls: POST the inner update here and it comes out of `getUpdates`. */
const INJECT_URL = process.env.LIVE_INJECT_URL ?? "";
const REDIS = process.env.LIVE_REDIS_CONTAINER ?? "";
const STEPS = new Set(
  process.argv.slice(2).length > 0 ? process.argv.slice(2) : ["presence", "inbound"],
);

const failures: string[] = [];

function say(line: string): void {
  process.stdout.write(`${line}\n`);
}

async function timed(
  label: string,
  limitMs: number,
  wait: () => Promise<unknown>,
): Promise<number> {
  const started = Date.now();
  try {
    await wait();
  } catch {
    failures.push(`${label}: not seen within ${limitMs} ms`);
    say(`FAIL ${label}: not seen within ${limitMs} ms`);
    return -1;
  }
  const took = Date.now() - started;
  say(`ok   ${label}: ${took} ms (limit ${limitMs} ms)`);
  return took;
}

type Member = { context: BrowserContext; page: Page; navigations: () => number; errors: string[] };

async function signIn(browser: Browser, email: string, startUrl: string): Promise<Member> {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  const errors: string[] = [];
  let navigations = 0;
  page.on("pageerror", (e) => errors.push(`${email} pageerror: ${e.message}`));
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) navigations += 1;
  });
  await page.goto(`${BASE}/login`);
  await page.fill("#email", email);
  await page.fill("#password", PASSWORD);
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.click("button[type=submit]"),
  ]);
  await page.goto(`${BASE}${startUrl}`, { waitUntil: "load" });
  return { context, page, navigations: () => navigations, errors };
}

async function api<T>(member: Member, path: string): Promise<T> {
  const response = await member.context.request.get(`${BASE}/api/v1${path}`);
  if (!response.ok()) throw new Error(`GET ${path} -> ${response.status()}`);
  return (await response.json()) as T;
}

async function firstConversationId(member: Member): Promise<string> {
  const page = await api<{ items: { id: string }[] }>(member, "/conversations");
  const id = page.items[0]?.id;
  if (!id) throw new Error("no conversation in the demo data");
  return id;
}

const PRESENCE_ANY = (page: Page) => page.getByTestId("presence-line").first();

async function presenceStep(browser: Browser): Promise<void> {
  say("== presence (A = cs.maianh, B = cs.thu)");
  const b = await signIn(browser, "cs.thu@example.test", "/inbox");
  const a = await signIn(browser, "cs.maianh@example.test", "/inbox");
  const conversation = await firstConversationId(b);
  await a.page.goto(`${BASE}/inbox?c=${conversation}`, { waitUntil: "load" });
  await timed("B sees A viewing", 2_500, () =>
    PRESENCE_ANY(b.page).filter({ hasText: "đang xem" }).waitFor({ timeout: 2_500 }),
  );

  await a.page.getByLabel("Nội dung trả lời").fill("Dạ em chào chị ạ, đây là tin thử");
  await timed("B sees A replying", 2_500, () =>
    PRESENCE_ANY(b.page).filter({ hasText: "đang trả lời" }).waitFor({ timeout: 2_500 }),
  );

  // a link click is a client-side navigation: the conversation unmounts and sends the leave call (a full page
  // load, a reload or a closed tab does not, that case is the TTL step below)
  await a.page.locator('a[href="/today"]:visible').first().click();
  await timed("B stops seeing A after A navigates away (leave call)", 5_000, () =>
    PRESENCE_ANY(b.page).waitFor({ state: "detached", timeout: 5_000 }),
  );

  await a.page.goto(`${BASE}/inbox?c=${conversation}`, { waitUntil: "load" });
  await timed("B sees A viewing again", 2_500, () =>
    PRESENCE_ANY(b.page).filter({ hasText: "đang xem" }).waitFor({ timeout: 2_500 }),
  );
  await a.context.close();
  const closedAt = Date.now();
  await timed("B stops seeing A after A's browser vanished (TTL 30 s, no leave call)", 36_000, () =>
    PRESENCE_ANY(b.page).waitFor({ state: "detached", timeout: 36_000 }),
  );
  say(`     (browser closed ${Date.now() - closedAt} ms before the viewer disappeared)`);
  failures.push(...b.errors, ...a.errors);
  await b.context.close();
}

async function injectText(text: string, uid: string): Promise<number> {
  const payload = {
    ok: true,
    result: {
      event_name: "message.text.received",
      message: {
        from: { id: uid, display_name: "Khách Mẫu", is_bot: false },
        chat: { id: uid, chat_type: "PRIVATE" },
        text,
        message_id: `mid-live-${Date.now()}`,
        date: Date.now(),
      },
    },
  };
  if (INJECT_URL) {
    const queued = await fetch(INJECT_URL, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload.result),
    });
    return queued.status;
  }
  const response = await fetch(`${BASE}/api/v1/webhooks/zalo-bot/${ACCOUNT}`, {
    method: "POST",
    headers: { "content-type": "application/json", "X-Bot-Api-Secret-Token": SECRET },
    body: JSON.stringify(payload),
  });
  return response.status;
}

async function inboundStep(browser: Browser): Promise<void> {
  say("== inbound message, review item and CRM task (no manual reload)");
  const marker = `Tin thu truc tiep ${Date.now()}`;
  const a = await signIn(browser, "cs.maianh@example.test", "/inbox");
  const b = await signIn(browser, "cs.thu@example.test", "/inbox");
  const loadsBefore = [a.navigations(), b.navigations()];
  const status = await injectText(marker, "live-uid-001");
  say(`     webhook answered ${status}`);
  if (status !== 200) failures.push(`webhook answered ${status}`);
  await Promise.all([
    timed("A's Inbox shows the new message without reload", 4_000, () =>
      a.page.getByText(marker).first().waitFor({ timeout: 4_000 }),
    ),
    timed("B's Inbox shows the new message without reload", 4_000, () =>
      b.page.getByText(marker).first().waitFor({ timeout: 4_000 }),
    ),
  ]);
  if (a.navigations() !== loadsBefore[0] || b.navigations() !== loadsBefore[1]) {
    failures.push("a page navigated during the inbound check");
  }

  // review queue: a red-flag text goes to the clinicians first (no model call) and creates a triage alert, which
  // only the owner and the doctors see: so this step uses the owner and a doctor (whose stream carries no ids)
  const owner = await signIn(browser, "owner@example.test", "/review");
  const doctor = await signIn(browser, "doctor.mai@example.test", "/review");
  const rowCount = (p: Page) => p.locator("ul > li > button").count();
  const ownerBefore = await rowCount(owner.page);
  const doctorBefore = await rowCount(doctor.page);
  say(`     review rows before: owner ${ownerBefore}, doctor ${doctorBefore}`);
  const redFlag = `Sau laser em sưng nhiều, đau dữ dội và khó thở ${Date.now()}`;
  await injectText(redFlag, "live-uid-002");
  const grows = (page: Page, before: number) => async () => {
    const until = Date.now() + 12_000;
    while ((await rowCount(page)) <= before) {
      if (Date.now() > until) throw new Error("no new row");
      await new Promise((r) => setTimeout(r, 100));
    }
  };
  await Promise.all([
    timed(
      "owner's review queue gains the new item without reload",
      12_000,
      grows(owner.page, ownerBefore),
    ),
    timed(
      "doctor's review queue gains the new item without reload (stream without ids)",
      12_000,
      grows(doctor.page, doctorBefore),
    ),
  ]);
  failures.push(...owner.errors, ...doctor.errors);
  await owner.context.close();
  await doctor.context.close();

  // CRM task: A resolves one through the API, B's "Việc hôm nay" drops it without reload
  await a.page.goto(`${BASE}/today`, { waitUntil: "load" });
  await b.page.goto(`${BASE}/today`, { waitUntil: "load" });
  const cards = (p: Page) => p.locator("article[aria-label]");
  await cards(b.page).first().waitFor({ timeout: 10_000 });
  const countBefore = await cards(b.page).count();
  const tasks = await api<{
    items: { id: string; version: number; status: string; owner_user_id: string }[];
  }>(a, "/crm/tasks?status=open&limit=100");
  const task = tasks.items[0];
  if (!task) throw new Error("no open task in the demo data");
  const resolved = await a.context.request.post(`${BASE}/api/v1/crm/tasks/${task.id}/resolve`, {
    data: {
      version: task.version,
      outcome: "not_needed",
      channel: "phone",
      note: "kiem tra truc tiep (mau)",
      owner_user_id: task.owner_user_id,
    },
  });
  say(`     resolve answered ${resolved.status()} (${countBefore} cards before)`);
  await timed("B's tasks list drops the resolved task without reload", 4_000, async () => {
    const until = Date.now() + 4_000;
    while ((await cards(b.page).count()) >= countBefore) {
      if (Date.now() > until) throw new Error("count unchanged");
      await new Promise((r) => setTimeout(r, 100));
    }
  });
  failures.push(...a.errors, ...b.errors);
  await a.context.close();
  await b.context.close();
}

function dockerStep(action: "stop" | "start"): void {
  execFileSync("docker", [action, REDIS], { stdio: "ignore" });
}

async function redisStep(browser: Browser): Promise<void> {
  say("== Redis stopped and started mid-session");
  if (!REDIS) throw new Error("set LIVE_REDIS_CONTAINER");
  const b = await signIn(browser, "cs.thu@example.test", "/inbox");
  const a = await signIn(browser, "cs.maianh@example.test", "/inbox");
  const conversation = await firstConversationId(b);
  await a.page.goto(`${BASE}/inbox?c=${conversation}`, { waitUntil: "load" });
  await timed("before: B sees A viewing", 2_500, () =>
    PRESENCE_ANY(b.page).filter({ hasText: "đang xem" }).waitFor({ timeout: 2_500 }),
  );
  dockerStep("stop");
  say("     redis stopped");
  await timed("B shows the polling notice (stream down > 10 s)", 40_000, () =>
    b.page
      .getByRole("status")
      .filter({ hasText: "Mất kết nối cập nhật trực tiếp" })
      .waitFor({ timeout: 40_000 }),
  );
  const listStillThere = await b.page.getByRole("button").count();
  say(`     page alive while Redis is down (${listStillThere} buttons on the page), no crash`);
  dockerStep("start");
  say("     redis started");
  await timed("B's polling notice disappears (stream back)", 60_000, () =>
    b.page
      .getByRole("status")
      .filter({ hasText: "Mất kết nối cập nhật trực tiếp" })
      .waitFor({ state: "detached", timeout: 60_000 }),
  );
  await timed("presence recovers: B sees A viewing again", 30_000, () =>
    PRESENCE_ANY(b.page).filter({ hasText: "đang xem" }).waitFor({ timeout: 30_000 }),
  );
  failures.push(...b.errors.filter((e) => !/Failed to fetch|EventSource/.test(e)), ...a.errors);
  await a.context.close();
  await b.context.close();
}

async function main(): Promise<void> {
  if (!PASSWORD) throw new Error("set LIVE_PASSWORD");
  const browser = await chromium.launch();
  try {
    if (STEPS.has("presence")) await presenceStep(browser);
    if (STEPS.has("inbound")) await inboundStep(browser);
    if (STEPS.has("redis")) await redisStep(browser);
  } finally {
    await browser.close();
  }
  say(failures.length === 0 ? "ALL CHECKS PASSED" : `FAILED:\n${failures.join("\n")}`);
  process.exitCode = failures.length === 0 ? 0 : 1;
}

await main();

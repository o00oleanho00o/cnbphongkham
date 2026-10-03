// `pnpm smoke`: every route of the app renders against the mock backend: the main heading is there and the
// primary control of the screen is visible (package U, step U1). It is the cheap proof that a restyle did not
// lose a screen; FEATURE-INVENTORY.md says what each screen must keep, this script only opens them.
//
// Needs the app running against the mock backend:  pnpm dev:mock   (then, in another shell)  pnpm smoke
//   SMOKE_BASE_URL=http://localhost:3000   where the app listens (default)
//   SMOKE_ROUTES=/today,/inbox             limit to some routes (comma separated)
//
// Signs in as the owner (sees every screen). A route that is in the inventory but not in the table below fails,
// so a new screen has to say what its heading and primary control are.
import { fileURLToPath } from "node:url";

import { chromium, type Locator, type Page } from "playwright";

import { concreteRoute, listPageRoutes } from "./app-routes";

const BASE = process.env.SMOKE_BASE_URL ?? "http://localhost:3000";
const APP_DIR = fileURLToPath(new URL("../src/app", import.meta.url));

type Role = "button" | "link" | "textbox";
type Expectation = {
  /** Text of the main heading (substring); empty string: any non-empty heading (a name from the data). */
  heading: string;
  /** The primary control: its role and accessible name (substring). */
  action: { role: Role; name: string };
};

const patientCare = (action: Expectation["action"]): Expectation => ({
  heading: "",
  action,
});

/** Redirect-only pages: where they must land. */
const REDIRECTS: Readonly<Record<string, string>> = {
  "/": "/today",
  "/admin/care": "/admin/care/staff",
  "/care/patients/[id]": "/care/patients/00000000-0000-4000-8002-000000000007/timeline",
};

const EXPECTATIONS: Readonly<Record<string, Expectation>> = {
  "/today": { heading: "Việc hôm nay", action: { role: "button", name: "Việc của tôi" } },
  "/inbox": { heading: "Inbox", action: { role: "textbox", name: "Tìm hội thoại" } },
  "/review": { heading: "Hàng đợi duyệt AI", action: { role: "button", name: "Cần bác sĩ" } },
  "/patients": { heading: "Hồ sơ bệnh nhân", action: { role: "textbox", name: "Tìm bệnh nhân" } },
  "/patients/[id]": { heading: "", action: { role: "link", name: "Danh sách hồ sơ" } },
  "/templates": {
    heading: "Tin nhắn mẫu đã duyệt",
    action: { role: "button", name: "Soạn mẫu mới" },
  },
  "/care/handoffs": {
    heading: "Yêu cầu đang chờ tôi",
    action: { role: "button", name: "Tất cả" },
  },
  "/care/patients/[id]/timeline": patientCare({ role: "link", name: "Dòng thời gian" }),
  "/care/patients/[id]/release": patientCare({ role: "link", name: "Trả lại cho agent" }),
  "/care/patients/[id]/tell-agent": patientCare({ role: "link", name: "Nói với agent" }),
  "/admin/care/staff": {
    heading: "Agent chăm sóc",
    action: { role: "link", name: "Kỹ năng và ca trực" },
  },
  "/admin/care/on-call": {
    heading: "Agent chăm sóc",
    action: { role: "button", name: "Thêm số trực" },
  },
  "/admin/care/matrix": {
    heading: "Agent chăm sóc",
    action: { role: "link", name: "Ma trận ngưỡng" },
  },
  "/admin/care/timing": {
    heading: "Agent chăm sóc",
    action: { role: "link", name: "SLA và khung giờ" },
  },
  "/admin/care/alerts": { heading: "Agent chăm sóc", action: { role: "link", name: "Cảnh báo" } },
  "/admin/users": { heading: "Nhân viên", action: { role: "button", name: "Thêm nhân viên" } },
  "/admin/auth": {
    heading: "Tài khoản của tôi",
    action: { role: "button", name: "Đổi mật khẩu" },
  },
  "/admin/overview": { heading: "Tổng quan", action: { role: "button", name: "" } },
  "/admin/threads": { heading: "Phiên chat AI", action: { role: "button", name: "" } },
  "/admin/contacts": { heading: "Danh bạ", action: { role: "button", name: "" } },
  "/admin/friends": { heading: "Bạn bè", action: { role: "button", name: "" } },
  "/admin/schedules": { heading: "Lịch hẹn", action: { role: "button", name: "" } },
  "/admin/memory": { heading: "Trí nhớ", action: { role: "button", name: "" } },
  "/admin/kb": { heading: "Kho tri thức", action: { role: "button", name: "Thêm nguồn" } },
  "/admin/accounts": { heading: "Tài khoản Zalo", action: { role: "button", name: "" } },
  "/admin/agents": { heading: "Agents", action: { role: "button", name: "Tạo agent" } },
  "/admin/agents/new": { heading: "", action: { role: "button", name: "Tạo agent" } },
  "/admin/agents/[id]": { heading: "", action: { role: "button", name: "Lưu" } },
  "/admin/tools": { heading: "Tools", action: { role: "button", name: "" } },
  "/admin/mcp": { heading: "MCP", action: { role: "button", name: "Thêm" } },
  "/admin/traces": { heading: "Trace agent", action: { role: "button", name: "" } },
  "/admin/logs": { heading: "Logs", action: { role: "button", name: "" } },
  "/admin/policy": { heading: "Hồ sơ chính sách", action: { role: "button", name: "" } },
  "/admin/tuning": { heading: "Cấu hình", action: { role: "textbox", name: "" } },
  "/admin/tuning/[group]": { heading: "Cấu hình", action: { role: "button", name: "" } },
};

/** Routes the smoke test does not open: sign-in has its own form, the kit examples are development only. */
const SKIPPED = ["/login", "/dev/kit"];

async function signIn(page: Page): Promise<void> {
  await page.goto(`${BASE}/login`);
  await page.fill("#email", "owner@pema.test");
  await page.fill("#password", "demo1234");
  await Promise.all([
    page.waitForURL((url) => !url.pathname.startsWith("/login")),
    page.click("button[type=submit]"),
  ]);
}

function actionLocator(page: Page, { role, name }: Expectation["action"]): Locator {
  const main = page.locator("main");
  const candidates = name === "" ? main.getByRole(role) : main.getByRole(role, { name });
  return candidates.filter({ visible: true }).first();
}

/** One line per problem of a route; empty when the route is fine. */
async function problemsOf(page: Page, route: string): Promise<string[]> {
  const target = concreteRoute(route);
  const response = await page.goto(`${BASE}${target}`, { waitUntil: "load" });
  if (response === null || response.status() >= 400)
    return [`${route}: HTTP ${response?.status() ?? "none"}`];

  const redirect = REDIRECTS[route];
  if (redirect !== undefined) {
    await page
      .waitForURL((url) => url.pathname === redirect, { timeout: 15_000 })
      .catch(() => null);
    return new URL(page.url()).pathname === redirect
      ? []
      : [`${route}: expected to land on ${redirect}, is on ${new URL(page.url()).pathname}`];
  }

  const expectation = EXPECTATIONS[route];
  if (expectation === undefined) return [`${route}: no expectation in scripts/route-smoke.ts`];

  const heading = page.locator("main h1").first();
  const headingOk = await heading
    .waitFor({ state: "visible", timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  if (!headingOk) return [`${route}: no main heading`];
  const text = (await heading.innerText()).trim();
  if (!text.includes(expectation.heading)) return [`${route}: heading is "${text}"`];

  const action = actionLocator(page, expectation.action);
  const actionOk = await action
    .waitFor({ state: "visible", timeout: 20_000 })
    .then(() => true)
    .catch(() => false);
  return actionOk
    ? []
    : [
        `${route}: primary control (${expectation.action.role} "${expectation.action.name}") not visible`,
      ];
}

async function main(): Promise<void> {
  const only = process.env.SMOKE_ROUTES?.split(",").filter(Boolean) ?? [];
  const routes = listPageRoutes(APP_DIR).filter((r) => !SKIPPED.includes(r));
  const selected = routes.filter((r) => only.length === 0 || only.includes(r));

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const pageErrors: string[] = [];
  page.on("pageerror", (e) => pageErrors.push(e.message));
  await signIn(page);

  const problems = await selected.reduce<Promise<string[]>>(async (previous, route) => {
    const done = await previous;
    pageErrors.length = 0;
    const found = await problemsOf(page, route);
    return [...done, ...found, ...pageErrors.map((e) => `${route}: page error: ${e}`)];
  }, Promise.resolve([]));
  await browser.close();

  process.stdout.write(`smoke: ${selected.length} routes, ${problems.length} problem(s)\n`);
  problems.forEach((line) => process.stdout.write(`  ${line}\n`));
  process.exitCode = problems.length === 0 ? 0 : 1;
}

await main();

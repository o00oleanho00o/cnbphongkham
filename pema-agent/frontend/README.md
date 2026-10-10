# frontend

One Next.js app (App Router, TypeScript, Tailwind v4, Vietnamese UI, mobile-first) for the whole Pema CSKH agent:

- **Vận hành** (clinic operations): Việc hôm nay, Inbox, Hàng đợi duyệt AI, Hồ sơ bệnh nhân (Patient 360, read only), Tin nhắn mẫu đã duyệt.
- **Tổng quan** (`/dashboard`) and **Điều phối lịch** (`/schedule`, package U step U2): the old Clinic Web's dashboard and schedule on real data. The dashboard shows only what `GET /dashboard/kpis` could count (visits by status, patients seen, CSKH follow-up numbers; no revenue, no invented figure; a rate with nothing to divide by is a dash) for today, this week or this month; a doctor sees their own visits. The schedule is one day or seven days from `GET /appointments/schedule` (columns are doctors; rooms and services come with the resources step) with the reception flow Đặt hẹn, Đã xác nhận, Đang chờ, Đang điều trị, Hoàn tất and the two ways out, Vắng hẹn and Đã hủy (with a reason). Every rule (hours, break, double booking, who may do what) is the backend's and its sentence is shown as it comes; `lib/ops/schedule-view.ts` only decides which buttons to offer. Several desks share the board through the `appointments.changed` live event.
- **Cấu hình danh mục** (package U, step U4): `/services` ("Danh mục dịch vụ": price, minutes of treatment and room preparation, rooms, the history of every price and rate version, and the follow-up protocols the CRM rules read), `/resources` ("Bác sĩ & phòng": doctors with the shift of the day from the care staff profile and the load of the day, rooms, room blocks), `/studio` ("Ảnh trước / sau": the before/after photo studio of one patient, kept in `?patient=&view=`). Everybody who sees the schedule reads the catalog and the resources; the owner and the manager (`admin.rules`) change them, and only they see the commission rate and basis (`rate_bp`, `basis` are `null` for the other roles). A change of price, rate, basis, duration or buffer starts the next terms version on the backend (`/api/v1/services`, `/protocols`, `/resources`, `/rooms`, `/room-blocks`, `/studio/{patient_id}`); the pure rules of the three screens are in `lib/catalog/catalog-view.ts`. The studio shows illustrative placeholders until the Patient 360 step adds the photo store.

- **Thu ngân và đơn thuốc** (package U, step U5): `/cashier` ("Thu ngân": the quick order dialog over the clinic's 115-row product catalog, the order history, `?patient=` opens it from Patient 360), `/orders/[id]` ("Tách đơn": the two A5 sheets, Đơn thuốc and Phiếu tư vấn, approval by the responsible doctor) and `/orders/[id]/print` (A5 print, a draft prints nothing). Reception, manager, doctor and owner make drafts (`order.write`); the doctor of the order or the owner approves (`order.approve`); a saved order keeps the name, unit and price it was saved with, an approved order never changes, and an order with money received cannot be edited. The catalog is loaded once by `pema catalog import <json>` (backend), never read from the prototype at run time. The Kế hoạch tab of Patient 360 gets a card with the patient's orders and the staff preview of what the app will show. The invoice panel of the cashier is step U6 (below). The pure rules of the screens are in `lib/orders/order-view.ts`; the A5 look is `components/orders/order-sheet.css` (named page `order-a5`).

- **Tài chính PB02** (package U, step U6): `/finance` ("Tài chính & tiền thủ thuật") is the old four-tab finance page as routes under one shell (month in `?month=`, "Làm mới"): `/finance` (Tổng quan), `/finance/entries` (Tiền thủ thuật: the form that records a performed procedure, the table with Duyệt and Hủy, "Chốt tháng đã kết thúc" and "Xác nhận đã chi" in dialogs instead of `prompt()`), `/finance/rates` (Chính sách tỷ lệ), `/finance/payments` (Phiếu thu & thông báo) and two screens the old web had no page for: `/finance/periods` (the 12 months with why each cannot close yet) and `/finance/export` (the CSV for Excel). There is no role picker: the projection comes from the session (the accountant, i.e. the manager, sees the clinic; a doctor only own rows with no cash, no debt, no invoices; the owner flips "Toàn phòng khám" and "Cá nhân" with `?scope=own`). Money is whole VND, rates and shares are basis points; every rule (rate snapshot, rounding, immutable closed month, idempotent receipts, no over-collection) is the backend's, the screens only word it. The "Hóa đơn & thanh toán" card of `/cashier` lists the invoices, takes the receipt in the "Thu tiền" dialog and raises the invoice of an order. Pure rules: `lib/finance/finance-view.ts`; components: `components/finance/`; mock: `mock/{data,handlers}/finance.ts`.

It is UI only. Every business rule, permission and audit is the backend's (`backend/apps/api`). The menu is filtered by the permission list of `GET /api/v1/me`, which is a convenience, never a control.

## Run

```
pnpm install
pnpm dev:mock        # mock backend on :4010 plus next dev on :3000 (no other service needed)
pnpm dev             # against the real API (PEMA_API_URL, default http://127.0.0.1:8000)
pnpm build && pnpm start
pnpm lint && pnpm typecheck && pnpm test
pnpm inventory       # FEATURE-INVENTORY.md against the routes and tests on disk (fails when a screen or a test disappears)
pnpm smoke           # Playwright: every route renders, main heading and primary control visible (needs `pnpm dev:mock`)
pnpm visual          # Playwright: every route at the 5 viewports, fails on horizontal overflow (needs `pnpm dev:mock`)
pnpm check           # all of the above in one go (lint, types, format, tests, inventory, then smoke and visual)
pnpm gen:types       # ../backend/apps/api/openapi.json -> src/lib/api/schema.d.ts (never edit by hand)
pnpm shots           # Playwright: every screen at the 5 project viewports into shots/ (needs `pnpm dev:mock` running);
                     # env SHOTS_ROLE=owner|manager|doctor|cs|reception, SHOTS_ROUTES=/today,/inbox. It also fails on
                     # horizontal document overflow, page errors and 5xx answers.
```

The browser talks only to its own origin. `/api/v1/**` and `/healthz` are forwarded to the backend by two route handlers (`src/app/api/[...path]/route.ts`, `src/app/healthz/route.ts`; logic and tests in `src/lib/server/api-proxy.ts`), so the session cookie is first-party and there is no CORS. The handlers read the API address on **every request** from `PEMA_API_INTERNAL_URL` (then `PEMA_API_URL`, then `http://127.0.0.1:8000`): it is a runtime environment variable, not a build argument, so one built image runs against any API (`docker run -e PEMA_API_INTERNAL_URL=http://api:8000 ...`; changing it needs a container restart, not a rebuild). Only `/api/v1/` and `/healthz` are forwarded (a `..` or encoded slash in the path is refused with 400, anything else is 404); hop-by-hop headers and client-supplied `x-forwarded-*`/`forwarded`/`x-real-ip` are dropped; the body and the answer are streamed, never cached, every `Set-Cookie` is kept. Behind the Caddy reverse proxy (`infra/README.md`) `/api/v1` does not even reach this server: Caddy sends it straight to the API. Mock sign-in (fictional users, all with password `demo1234`): `owner@pema.test`, `manager@pema.test`, `doctor@pema.test`, `cs@pema.test`, `reception@pema.test`.

## Mock backend (`mock/`)

`mock/server.ts` serves the paths of `openapi.json` from memory with fictional data. One file per area in `mock/handlers/*.ts`, each exporting `register(router)`; they are discovered by directory listing. `mock/contract.test.ts` fails if the mock does not serve an operation of the contract, or serves one that is not in it, so the mock cannot drift from the typed client. The role to permission table in `mock/auth.ts` is a simulation of ARCH-PB01 (the real one is package B1's).

## Several people at once (live events, presence, assignable staff)

Contract the screens are written against (the backend serves it; the mock serves the same, see `mock/handlers/live.ts` and `mock/live-bus.ts`):

- `GET /api/v1/events` is server-sent events. Each `data:` is JSON `{type, id}`: `type` is `inbox.changed`, `tasks.changed`, `review.changed`, `presence.changed`, `handoff.changed` or `care.changed`, `id` the conversation, task, review item or patient (null: "some"). No message text ever travels on it; a screen reloads its own list through the normal API, so permissions and filters stay the backend's.
- `useLiveEvents` (`src/lib/live/use-live-events.ts`, logic in `live-connection.ts`) opens it with `EventSource`, reconnects by itself, coalesces a burst into one call, and when the stream has been down for more than 10 seconds falls back to a refresh every 30 seconds (a small notice says so) until it is back, then refreshes once for what it missed. Listener and timers are released on unmount. Inbox (`inbox.changed`, `presence.changed`), Việc hôm nay (`tasks.changed`) and Hàng đợi duyệt (`review.changed`) use it through `useLoad().refresh`, the quiet reload: no loading state, selection, scroll and a draft being typed stay; an open review edit is flagged "dựa trên nháp cũ" and cannot be approved if the item changed meanwhile.
- `POST /api/v1/conversations/{id}/presence` body `{state: "viewing" | "replying"}` every 15 seconds while a conversation is open (at once when the state changes; "replying" while a draft is non-empty; nothing while the tab is hidden), `viewers: [{user_id, name, state}]` (the caller excluded) in the conversation list and detail. Shown as "Lan đang xem / đang trả lời" in the list and the thread. A warning only, never a lock.
- `GET /api/v1/staff/assignable` (in the contract and the generated client since ST-S; mock: `mock/handlers/staff.ts`, rule in `mock/assignable.ts`) returns `[{id, name, role}]` of the ACTIVE colleagues who can work conversations and tasks (not reception), for every signed-in staff member. The "Phụ trách" box of the contact form (Việc hôm nay) and of the conversation header (Inbox) lists "Tôi", "Giữ nguyên", "Chưa giao" (Inbox, while somebody owns the conversation) and these people (`lib/ops/assignee-options.ts`, `lib/staff/`). It says when the list is loading or could not be read (with "Thử lại") and still offers "Tôi" and "Giữ nguyên"; the answer is shared for a minute because the route is limited to 60 calls a minute per user. The backend checks the assignee again on save (active, assignable role) and answers 422 otherwise.

All three routes are in `openapi.json` and the generated client (`src/lib/api/schema.d.ts`) since ST-R and ST-S; `mock/contract.test.ts` has no pending list left. `src/lib/live/live-types.ts` keeps only the tolerant parsers (an SSE `data:` line and `viewers` are untrusted runtime input) on top of the generated `Schemas[...]` types, and `live-api.ts` calls presence through `http`. `scripts/presence-check.ts` opens one conversation in two browser contexts against the mock and checks that each sees the other.

`scripts/live-real-check.ts` is the same check against a REAL stack (docker compose behind Caddy, seed demo data, a fake Bot API the worker polls): two staff in two browser contexts, presence both ways, an inbound message, a review item and a resolved task reaching the other screen without a reload, and Redis stopped and started mid-session. Its header lists the environment variables; it stops and starts the Redis container, so use a throwaway stack. Observed timings are in SECURITY-REVIEW-AI01 section 9.

## Layout

```
src/app/layout.tsx, globals.css       root document, Be Vietnam Pro (local, OFL), Pema tokens, theme bootstrap
src/app/login/                        sign-in (email + password, cookie session; one installation is one clinic)
src/app/(admin)/layout.tsx            AppShell: /me, permission-filtered menu, phone tab bar
src/app/(admin)/{today,inbox,patients}/    clinic operations
src/app/(admin)/finance/{,entries,rates,payments,periods,export}/                 finance PB02 (U6)
src/app/(admin)/admin/<area>/page.tsx  AI administration, one route per page of the original dashboard
src/components/admin/<area>/          ported components (paths fixed by docs/PORT-MAP.md)
src/components/ops/                   clinic operation components (new, no zalo-agent original)
src/components/catalog/, src/lib/catalog/   service catalog, protocols, doctors and rooms, photo studio (U4)
src/components/orders/, src/lib/orders/     quick order dialog, A5 sheets, Patient 360 orders card (U5)
src/components/finance/, src/lib/finance/   finance shell pieces, entry form, receipts, invoice panel (U6)
src/lib/admin/<area>/                 ported pure logic and its tests (vitest, same titles as the originals)
src/lib/api/                          client.ts (typed openapi-fetch + ApiError), schema.d.ts (generated)
src/lib/session/, src/lib/nav.tsx     session context, menu and permission filter
mock/                                 mock backend
scripts/port-web-file.mjs             mechanical first pass of the port (see below)
```

Tokens: primary `brand-500` #0B4F94, navy `brand-600`, sky `brand-400` #3CAAE5 (graphics only, never small white text), `canvas` #F4F8FB, `ink` #17324D, `ink-soft` #5D7184, `line` #D9E5EE. The original `zalo-*` colour scale is `brand-*`; `gc-card`, `gc-tile`, `gc-input` keep their names. Light/dark follows the original `use-theme`.

## Porting a file of `web/src` (package E rules)

Reference clone (read only): `E:\Desktop\zalo-agent-ref\web\src`. Target paths of every file: `docs/PORT-MAP.md`, rows owned by `E`. Route pages go at the route given in the layout comment above (one route per original page), not at the single `page.tsx` PORT-MAP lists for several originals.

1. `node scripts/port-web-file.mjs <path under web/src> ...` writes the target with the `// ported from:` header, `"use client"`, the `brand-*` rename and `@/` imports, and prints what is left to do by hand.
2. Keep names, constants, thresholds and the reason comments of the original (they are the specification). Record forced deviations in a comment under the header.
3. API: use `http` and `unwrap` from `@/lib/api/client` and DTO types from `Schemas` in `@/lib/api` (snake_case, English names; the original's Vietnamese-named DTOs no longer exist). Errors arrive as `ApiError` with the BE's Vietnamese message. Never invent an endpoint: if the contract lacks one, show the control disabled or hide it, and list it as an open item.
4. react-router becomes `next/link`, `useRouter`, `usePathname`, `useParams`, `useSearchParams` (wrap in `<Suspense>` in the page). Vite globals (`__APP_VERSION__`, `import.meta`) become `process.env.NEXT_PUBLIC_*`.
5. Tests: `node:test` to vitest with the same titles (`describe`/`it` from `vitest`, `node:assert/strict` may stay); fake timers via `vi.useFakeTimers()`. A screen test is `page.test.tsx` next to the page with `// @vitest-environment jsdom` on its first line (Testing Library, the typed client replaced by a fake).
6. Quality: no `any`, no `console.*`, named imports, hoist constant objects and wrap handlers passed to children in `useCallback`, clean timers and listeners in `useEffect`. Never log or render secrets: keys come back masked (`api_key_masked`), tokens only go up.
7. Mobile first: 390x844 must work with no document-level horizontal scroll (tables scroll inside their card), touch targets of at least 44px on phone widths, text readable without zoom. Desktop uses the width (1920x1020, 1440x900, 1280x720, 1024x768).
8. Mock: add the area's handlers under `mock/handlers/` with fictional Vietnamese data (no real name, phone, token, photo).

## Port notes (what differs from `web/` of zalo-agent, and why)

- **One route per page of the original**, under `/admin/*` (PORT-MAP lists a single `page.tsx` for several originals). Sign-in is `/login`
  (email + password, session cookie; there is no clinic field, the one clinic comes back in `UserSummary.clinic_name` and is shown in the menu), `/admin/auth` is "Tài khoản của tôi" with the change-password form, which is disabled
  because the contract has no such operation.
- **Typed OpenAPI client** replaces `dashboard-api-client.ts`. The DTOs are snake_case and English; where a component was written against
  the original shape a small pure adapter rebuilds it so the ported component and its tests stay as written.
- **Pema-only code** (no original): `components/ops/*`, `lib/ops/*`, the audit log tab,
  the doctor sign-off column and the "Thử tìm" modal of the knowledge base. (The old agent administration pages, the policy page and
  the channel switchboard were removed in plan C: the agent's pages are `components/agent/*`.)
- Removed because the contract has no data for them (open items for the backend packages): token usage per thread and the thread summary,
  contact/memory counts and total messages on the overview, vision `mode` and sidecar test, image-generation test, "also delete memory" when
  clearing a thread, change password, `channel`/`send_mode`/message body on a CRM task.

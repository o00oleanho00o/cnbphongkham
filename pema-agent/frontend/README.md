# frontend

One Next.js app (App Router, TypeScript, Tailwind v4, Vietnamese UI, mobile-first) for the whole Pema CSKH agent:

- **Vận hành** (clinic operations): Việc hôm nay, Inbox, Hàng đợi duyệt AI, Hồ sơ bệnh nhân (Patient 360, read only), Tin nhắn mẫu đã duyệt.
- **Quản trị AI** (owner and manager): the dashboard of `vuhai2002/zalo-agent` translated feature by feature (accounts and QR login, agents and persona, model and tuning, tools, knowledge sources, schedules, MCP servers, usage and traces, logs), plus the kill switch per channel and the policy profile of each account and agent.

It is UI only. Every business rule, permission and audit is the backend's (`backend/apps/api`). The menu is filtered by the permission list of `GET /api/v1/me`, which is a convenience, never a control.

## Run

```
pnpm install
pnpm dev:mock        # mock backend on :4010 plus next dev on :3000 (no other service needed)
pnpm dev             # against the real API (PEMA_API_URL, default http://127.0.0.1:8000)
pnpm build && pnpm start
pnpm lint && pnpm typecheck && pnpm test
pnpm gen:types       # ../backend/apps/api/openapi.json -> src/lib/api/schema.d.ts (never edit by hand)
pnpm shots           # Playwright screenshots at the 5 project viewports (needs `pnpm dev:mock` running)
```

The browser talks only to its own origin; `next.config.ts` rewrites `/api/*` and `/healthz` to the backend, so the session cookie is first-party and there is no CORS. Mock sign-in (fictional users, all with password `demo1234`, clinic `pema-demo`): `owner@pema.test`, `manager@pema.test`, `doctor@pema.test`, `cs@pema.test`, `reception@pema.test`.

## Mock backend (`mock/`)

`mock/server.ts` serves the paths of `openapi.json` from memory with fictional data. One file per area in `mock/handlers/*.ts`, each exporting `register(router)`; they are discovered by directory listing. `mock/contract.test.ts` fails if the mock does not serve an operation of the contract, or serves one that is not in it, so the mock cannot drift from the typed client. The role to permission table in `mock/auth.ts` is a simulation of ARCH-PB01 (the real one is package B1's).

## Layout

```
src/app/layout.tsx, globals.css       root document, Be Vietnam Pro (local, OFL), Pema tokens, theme bootstrap
src/app/login/                        sign-in (clinic + email + password, cookie session)
src/app/(admin)/layout.tsx            AppShell: /me, permission-filtered menu, phone tab bar
src/app/(admin)/{today,inbox,review,patients,templates}/    clinic operations
src/app/(admin)/admin/<area>/page.tsx  AI administration, one route per page of the original dashboard
src/components/admin/<area>/          ported components (paths fixed by docs/PORT-MAP.md)
src/components/ops/                   clinic operation components (new, no zalo-agent original)
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
5. Tests: `node:test` to vitest with the same titles (`describe`/`it` from `vitest`, `node:assert/strict` may stay); fake timers via `vi.useFakeTimers()`.
6. Quality: no `any`, no `console.*`, named imports, hoist constant objects and wrap handlers passed to children in `useCallback`, clean timers and listeners in `useEffect`. Never log or render secrets: keys come back masked (`api_key_masked`), tokens only go up.
7. Mobile first: 390x844 must work with no document-level horizontal scroll (tables scroll inside their card), touch targets of at least 44px on phone widths, text readable without zoom. Desktop uses the width (1920x1020, 1440x900, 1280x720, 1024x768).
8. Mock: add the area's handlers under `mock/handlers/` with fictional Vietnamese data (no real name, phone, token, photo).

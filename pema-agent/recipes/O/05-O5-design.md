# O5 — Design of the shared-inbox screens (screen ids, specs, canvas frames)

## Goal
Give every screen and state that O6 will build a screen id, a spec and a canvas frame in the Next.js web canvas, so
the UI step is design-first as `AGENT.md` ("Web design canvas") requires.

## Read first
1. `PLAN-AI01-O.md` §3–§4; O1–O3 routers and DTOs in `openapi.json` (field names and states come from there).
2. `pema-agent/recipes/W2/00-README.md` (tooling and conventions for Next.js-only ids) and
   `pema-agent/docs/PLAN-AI01-W2.md`; the existing Inbox ids (look up `/inbox` in `design-specs/web/INDEX.md`) and the
   `/admin/accounts` ids; `design-specs/web/BLOCKS.md`; `design-system/`.

## Ingredients
- New group **WM** (shared inbox) in `design-specs/web/inventory.json`, Next.js-only, at least:
  Inbox with account filter and tabs "Chờ nhận / Của tôi / Tất cả"; thread with holder banner and composer locked
  ("<Tên> đang trả lời — Tiếp quản?"); dialogs Nhận, Tiếp quản (reason), Trả lại (to queue / to agent), toast
  "Đã bị tiếp quản"; `/admin/accounts` additions (purpose, per-identity limits, internal notifier status — no
  credential fields); roster screen (week grid per identity, add/edit slot); `/me/notifications` (push status, Zalo
  bell link with code, quiet hours); empty, loading, error, 409 states; 1440 + 1920 + 390 frames for pages.
- Existing Inbox ids keep their ids; a changed screen gets a new state id or a note, not a renumbering.

## Steps
1. Ids and notes (`notes.json`: route, roles, which O API each control calls).
2. Specs with `web-specs.cjs`; frames in `Pema Web redesign canvas/parts/WM.js`; build only
   `Pema Web (Next.js).dc.html` (the old-web canvas stays WA–WI); hub index regenerated.
3. Reuse blocks from `BLOCKS.md`; a new block is added to `blocks.js` and `BLOCKS.md` and gets a component page in
   `design-system/components/`.

## Acceptance
- `web-inventory.cjs --check` 0; `web-specs.cjs --check` 0; `web-canvas.cjs check --file "Pema Web (Next.js).dc.html"
  --complete --viewport=all --frames` 0; old-web canvas unchanged (byte-identical); viewer shows WM under "Màn mới".

## Out of scope
- Frontend code (O6). Publishing to claude.ai/design.

## Report
Use `_REPORT-TEMPLATE.md`; list the WM ids with one line each.

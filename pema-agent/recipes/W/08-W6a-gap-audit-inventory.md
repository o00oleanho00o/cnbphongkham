# W6a — Close every gap in the inventory (Patient Mobile web + every missing state)

## Why
Owner rule (2026-10-04, repeated): **no screen of the old web may be missing**. W0 left out the Patient Mobile web
(`prototype/patient-mobile`, plan §1 said "covered by the app canvas") and it parked some states as `non_screens` or "no
scripted state". All of these are now IN scope. This step makes `design-specs/web/inventory.json` complete. W6b/W6c then build
shots, specs and frames for the new ids only.

## Read first
`pema-agent/docs/PLAN-AI01-W.md` (§1, §2 principle 0), `recipes/W/00-README.md`, `recipes/W/01-W0-inventory.md`, the W0 skill code
(`.claude/skills/pema-web-design/scripts/web-inventory.cjs`, `lib/old-web.cjs`, `lib/catalog.cjs`) and the inventory's
`non_screens` list.

## What to add (append only: never renumber an existing id; new ids go at the end of their group)
1. **New group WI — Patient Mobile web** (`prototype/patient-mobile/index.html`, `shared/patient.js`, `shared/care-finance.js` mobile
   injections). Every `data-screen` (home, appointments, journey, progress, care, send, messages, docs, profile, plus any the code
   defines), every modal/dialog/sheet it opens, every visible state (empty lists, success/error toasts, privacy panel, screens
   reachable only through a row, such as "Tài liệu & hóa đơn", "Chăm sóc tại nhà", "Ảnh trước & sau"), prescription/order cards
   approved vs pending, per-patient variants if the UI has a patient switcher. The web is opened at the five viewports (as W0 does)
   so shots exist for all five; 390×844 is the primary one.
2. **Every state the old web can show** that has no id yet. Start from the lists below, then find more:
   - `non_screens` entries: native `confirm()` / `prompt()` / `print()` flows (reset demo, void a finance entry, close month, pay
     out, print an order) and the native role-picker popup. These cannot be screenshotted as a page: give each an id with
     `kind: "state"` and `native: true`. The W1 shot is the page open right before the native call, and the manifest records
     the captured dialog message; the W3 frame draws the dialog with the exact captured text.
   - Empty or clean states: "Inbox đã sạch. Không có follow-up đang mở.", "Không còn việc CSKH mở", "Đã xếp hết danh sách chờ",
     "Chưa có lịch" (empty day), "Chưa có khách trong nhóm.", the populated results list of WD4, `#crm-error`.
   - Error lines: `#ops-error` in every booking dialog (room/service rules), `#quick-error`, `#crm-error`, finance entry
     validation errors, order-review errors. Reach them by scripting the invalid input, not by editing data.
   - Roles: every role in `staff-context.js` (owner, manager, doctor, care, accountant, reception, any other) on every page its
     `pages` list allows, when the page differs by role (hidden buttons, another KPI set). One id per distinct variant, not per role.
   - Time and state variants: appointment statuses, order draft/approved/unresolved/missing-code, finance period
     open/closed/paid, API down, offline, loading.
   - Dead code is still listed in `non_screens`, but only if no UI path reaches it. Try every path first.
3. **Completeness guard (static).** Extend `web-inventory.cjs` so it fails when any of these is not claimed by an id (or by a
   `non_screens` entry with a reason):
   - every `data-nav`, `data-tab`, `data-modal`, `data-screen`, `data-finance-tab` and `data-action` value, in the live DOM and
     in the HTML strings of `prototype/**/*.js`;
   - every element id ending `-error`, `-empty` or `-toast`;
   - every user-visible string literal that contains "Không có", "Chưa có", "Đã sạch", "Không còn", "Lỗi" or "không thể";
   - every function in `prototype/shared/*.js` and `finance/finance.js` that returns HTML. The director's static scan found
     31 not named in the inventory: `patient.js` home, appointments, journey, progress, messages, docs; `care-finance.js`
     prescriptionPanel, injectMobile; `operations-ui.js` openQuickOrder, printOrder; plus helpers. Helpers go on a short allow-list
     with a reason each.
4. Keep every existing id and its `reach` unchanged. `web-inventory.cjs --check` must still pass twice.

## Acceptance
- `web-inventory.cjs --check` exits 0 twice, and the static guard lists 0 unclaimed items. The report shows the guard's before
  and after (the unclaimed list you started with, then 0).
- The report lists the new ids by group (WI, plus the ids appended in WA–WH) with kind, reach, sources and native flag.
- `non_screens` now holds only items that no UI path reaches, each proven by a search (give the grep).
- Only these files change: `design-specs/web/inventory.json` and `.claude/skills/pema-web-design/scripts/**`.

## Rules
Same as `00-README.md`. The old web (4173) and finance API (4174) are running. Use ONE browser at a time. No git trailers, no AI
attribution. Report at most 35 lines, with real output.

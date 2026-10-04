# W0 — Inventory of the old web and foundation of the `pema-web-design` skill

## Goal
Produce one frozen list of every old-web screen, with a stable id and a recorded way to reach it:
`design-specs/web/inventory.json`. Also produce the shared script plumbing that W1–W4 build on. Every later step
reads this inventory and never walks the web on its own.

**Owner rule (plan §0, principle 0): the result must contain EVERY piece of UI the old web has.** Nothing is filtered. The app design gives the look (tokens, blocks, kit); the old web gives all content.

## Read first
1. `pema-agent/docs/PLAN-AI01-W.md` (§1 scope, §2 principles, §4 groups).
2. `.claude/skills/pema-web-to-canvas/scripts/dump-web.cjs`, which already walks `data-nav`, `data-tab`,
   `data-modal`, `data-screen` and `data-finance-tab`, and the `CLINIC_DIALOGS` list. Reuse its walking logic by
   copying it into the new script. Do not edit the original.
3. `.claude/skills/pema-web-to-canvas/references/coverage.md`: old web → app canvas codes. These become the
   `app_canvas` cross-references.
4. `.claude/skills/pema-web-to-canvas/scripts/lib/pw.cjs`: the Playwright loader to extend.
5. `pema-agent/frontend/FEATURE-INVENTORY.md` and `pema-agent/docs/PLAN-AI01-U.md` §3: the Next.js target route and
   the U step for each old screen.
7. `design-specs/INDEX.md` (which app codes are ported) and, for each mapped code, `design-specs/screens/<code>.md`
   (the app's fields, actions and statuses for that feature).
6. `prototype/shared/staff-context.js` (roles and the demo account picker) and `prototype/shared/data.js` (what date
   the demo treats as "today").

## Ingredients
- `.claude/skills/pema-web-design/SKILL.md`: a stub (name, description, "see PLAN-AI01-W; final text in W4").
- `.claude/skills/pema-web-design/scripts/lib/pw.cjs`: the same contract as the pema-web-to-canvas loader. Order:
  1. `PLAYWRIGHT_MODULE`;
  2. `<repo>/pema-agent/frontend/node_modules/playwright`;
  3. normal `require`;
  4. the npx cache.
- `.claude/skills/pema-web-design/scripts/lib/old-web.cjs`: shared helpers used by W1 and W2.
  - `open(page, entry)` reaches one inventory entry from a fresh page.
  - `freeze(page)` fixes the clock and role, and waits for fonts.
  - `closeAll(page)` closes every open dialog or modal.
- `.claude/skills/pema-web-design/scripts/web-inventory.cjs`.
  - `node web-inventory.cjs` walks the old web (`http://127.0.0.1:4173`) and the finance web, and rewrites
    `inventory.json`.
  - `--check` walks again and fails on any difference.
- `design-specs/web/inventory.json`, shape:
  ```json
  { "generated_from": "<git short hash of prototype/>", "base_url": "http://127.0.0.1:4173",
    "clock": "2026-09-20T09:00:00+07:00", "role": "<role key used for captures>",
    "viewports": [[1920,1020],[1440,900],[1280,720],[1024,768],[390,844]],
    "groups": [{"code":"WA","name":"Khung & điều hướng"}, ...],
    "screens": [{ "id":"WB1", "group":"WB", "name":"Tổng quan", "kind":"page|tab|modal|dialog|state",
      "reach": [{"goto":"/clinic-web/"},{"click":"[data-nav=\"dashboard\"]"}],
      "sources": ["prototype/shared/clinic.js#renderDashboard"],
      "next_route": "/dashboard", "next_status": "built (U2)|planned (U4)|restyle (U1)|none",
      "app_canvas": ["I1","A1"], "legacy_shot": "dashboard", "frames": ["1440x900","1920x1020","390x844"] }] }
  ```
  - `kind: "state"` covers a visible state reachable by the UI only, for example an empty filter result. Do not
    script data into a state.
  - `app_canvas` is a cross-reference only (which app frames to reuse blocks and wording from). An empty list is
    allowed and means "no app counterpart; design it from the old web alone". It never excludes a screen.
  - `legacy_shot` holds the old `review-desktop.cjs` name (the 11 pages and 5 tabs) so W1 can also write the legacy
    file names.

## Steps
1. Serve the old web and the finance API (see 00-README). Read `data.js` and `staff-context.js`.
   - Decide `clock`: the date the demo data is built around. Freeze it with `page.clock.setFixedTime`, and confirm
     the dashboard shows non-empty data.
   - Decide `role`: the role that sees every nav item, normally owner or manager.
   - Record both choices and why in the report.
2. Write `pw.cjs`, `old-web.cjs` and `web-inventory.cjs`. Walk:
   - every `data-nav`;
   - every Patient 360 `data-tab` and `data-modal` on patient `P001`, or the first patient the role can open;
   - every `CLINIC_DIALOGS` button;
   - the 4 finance tabs, including the owner, accountant and doctor projections if the finance UI switches view;
   - `order-review/index.html`;
   - shell states (sidebar collapsed or expanded if toggleable, the role picker open).
   A `FAILED` reach is a bug in the script: fix it, do not drop the screen.
3. Assign ids by group (plan §4), numbered in sidebar order and then in the order a user meets the screens. Write the
   names in the old web's Vietnamese title.
4. Fill `next_route` and `next_status` from FEATURE-INVENTORY and PLAN-AI01-U. Use `none` when no target exists. Fill
   `app_canvas` from `coverage.md`.
5. Completeness pass: compare the walked list with `prototype/clinic-web/index.html`, `prototype/finance/index.html`
   and every `render*`/`open*` function in `prototype/shared/*.js`. Anything a user can see and is not in the list
   is a missing entry: add it. When unsure whether something is a separate screen or a state of another, add it as
   `kind: "state"` and say so in the report.
6. Run `web-inventory.cjs --check` twice. The output must be identical, so the walk is deterministic.

## Acceptance
- `node .claude/skills/pema-web-design/scripts/web-inventory.cjs --check` exits 0, twice in a row.
- Every `data-nav`, `data-tab`, `data-modal`, `data-finance-tab` and `CLINIC_DIALOGS` entry of the old web appears in
  exactly one screen. The report lists the count per kind and per group (expected 45–70 in total).
- The completeness pass found nothing left, or everything it found was added.
- Every entry's `reach` opens the screen from a fresh page with 0 page errors.
- Only these paths changed: `.claude/skills/pema-web-design/**` and `design-specs/web/inventory.json`.

## Out of scope
- Screenshots (W1), DOM snapshot and specs (W2), canvas (W3).
- Patient Mobile web and Next.js-only screens (plan D3).

## Report
Use `_REPORT-TEMPLATE.md`. Also include:
- the chosen clock and role;
- the per-group id table (id, name, kind, app codes);
- what the completeness pass added;
- every screen you could not reach.

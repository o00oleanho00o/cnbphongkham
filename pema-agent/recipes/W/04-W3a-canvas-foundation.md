# W3a — Web design canvas: file, frame template, tokens, blocks, shell and group WB (way 3, part 1)

## Goal
Create `Pema Web redesign canvas/Pema Web.dc.html`, a claude.ai/design canvas of the web screens at web size. Its blocks
map 1:1 to the Next.js kit `pema-agent/frontend/src/ui`, and its tokens come from `tokens.json`. Fill the shell
(group WA, proof only) and operations (group WB, proof only). W3b (eight parallel agents, one per group WA–WH) adds the
data for every group and never touches the template.

**Owner rule (plan §0, principle 0): the result must contain EVERY piece of UI the old web has.** Nothing is filtered. The app design gives the look (tokens, blocks, kit); the old web gives all content. So this canvas is the whole old web, redrawn in the app's design language.

## Read first
1. `PLAN-AI01-W.md` (§2 principle 5, decisions D4 frame sizes and D7).
2. The app canvas, read-only, as the format reference: `Pema App redesign canvas/Pema App.dc.html`.
   - the `<x-dc>` and `<helmet>` structure;
   - the `<script type="text/x-dc" data-dc-script data-props=…>` block with `class Component extends DCLogic { build() }`;
   - the `groups` array;
   - the `KEYS`/`fill` normalisation;
   - the template loops over `groups` / `screens` / `blocks`.
   Also read `support.js`, which the canvas loads.
3. `.claude/skills/pema-web-to-canvas/references/blocks.md` (how app blocks are declared and documented) and
   `scripts/canvas.cjs` (how a canvas is rendered and checked through `design-viewer`).
4. `.claude/skills/pema-canvas-to-kmp-compose/scripts/specs-lib.cjs` › `loadCanvas()`. The web specs must read the web
   canvas the same way, by evaluating `build()` in Node.
5. `design-specs/web/inventory.json`, `design-specs/web/screens/WA*.md` and `WB*.md` (W2), and the W1 screenshots
   `pema-agent/frontend/visual-ref/old/WA*-1440x900.png` and `WB*-1440x900.png`.
6. `pema-agent/frontend/src/ui/*.tsx`, `tokens.css`, `tokens.json`, `README.md`, and `.agents/skills/pema-design/
   references/visual-system.md`.

## Ingredients
- **Parts, so that W3b can run in 6 parallel agents without merge conflicts.** The canvas is one HTML file for
  claude.ai/design, but it is GENERATED:
  - `Pema Web redesign canvas/template.html`: helmet, frame template, block renderers, helpers, props (hand-written
    here in W3a, frozen afterwards).
  - `Pema Web redesign canvas/parts/base.js`: shared sample data (`people`, `doctors`, `rooms`, `services`, `GROUPS`,
    `money()`, `WEB` const) and the helper definitions.
  - `Pema Web redesign canvas/parts/WA.js … WH.js`: each defines `const WX = [ …screens… ];` using the helpers. W3a
    writes `WA.js` and `WB.js` and creates **stub** `WC.js … WH.js` (`const WC = [];`).
  - `.claude/skills/pema-web-design/scripts/web-canvas-build.cjs`: concatenates `base.js` + `WA…WH.js` into the
    `<script type="text/x-dc" data-dc-script>` of `template.html`, adds the `groups` array and the `KEYS`/`fill`
    normalisation, and writes `Pema Web.dc.html`. `--check` fails when the committed `Pema Web.dc.html` differs from
    what the build would write. Output is deterministic.
  - A part may only use the helpers and blocks of `base.js`/the template. A part never edits another part.
  - `web-canvas.cjs check` accepts `--canvas-dir <dir>` and `--viewer-url <url>` so each agent can use its own
    design-viewer. Document how to start one: `cd <main checkout>/design-viewer && DC_CANVAS_DIR=<worktree canvas dir>
    npm run dev -- --port <port>`.
- `Pema Web redesign canvas/support.js`: a byte-identical copy of the app canvas's `support.js`.
  `Pema Web redesign canvas/Pema Web.dc.html`:
  - Helmet: Be Vietnam Pro, Material Symbols, and a `:root` block of CSS variables **generated** from `tokens.json`
    (light) plus a `[data-theme=dark]` block (dark overrides). Blocks use `var(--…)` only.
  - Props (`data-props`): `showNotes` (boolean), `theme` (light/dark), `viewport` (`1440x900` | `1920x1020` |
    `390x844`, default 1440), `group` (filter).
  - Frame template: a browser-like frame of the chosen viewport, holding the AppShell (sidebar with the old web's
    order and groups, header with breadcrumb and search, content area). Dialogs and modals render as an overlay on a
    dimmed page frame. Screen label `ID · name`, and the note under it when `showNotes`.
  - Screen helpers, mirroring the app canvas:
    - `page(id, name, note, navKey, blocks, o?)`;
    - `tab(id, name, note, patientTabKey, blocks, o?)` for Patient 360 with its header and tab bar;
    - `dlg(id, title, note, blocks, o?)` for dialogs and modals;
    - `fin(id, name, note, tabKey, blocks, o?)` for finance.
    `o` may carry `frames: ['1440x900','1920x1020','390x844']` (decision D4: pages get all three; dialogs and modals
    get 1440 only).
  - Content blocks: each is drawn like the app canvas block of the same purpose (`design-specs/BLOCKS.md`: `h`,
    `s`, `m`, `chips`, `fc`, `t`, `notice`, `dd`, `input`, `week`, `photos`, `a5`…) at web size, and renders one kit
    component. Keep the app block's name where one exists. Blocks the old web needs and the app has none for (data
    table, sidebar, week board…) are added and marked `web-only` in `blocks-web.md`. Mapping:

    | Block | Kit component |
    |---|---|
    | `pageHead` | page title, subtitle, actions |
    | `kpis` | KPI tile row, any count, responsive grid |
    | `chips` | filter/status pills |
    | `tabs` | tab bar |
    | `table` | `TableShell`: columns, rows, pinned last column; becomes cards at 390 |
    | `cardGrid` | cards of patients or tasks |
    | `card` | `Card` with title, lines, actions |
    | `form` | `Field`s: text, select, date, textarea, radio, check |
    | `notice` | info / warning / danger box with verbatim text |
    | `statusBars` | the dashboard's "Lịch hẹn theo trạng thái" |
    | `timeline` | |
    | `week` | schedule board: rooms × time |
    | `empty` | `EmptyState` |
    | `badge` | `Badge` (status triples success/info/warning/danger, always with words) |
    | `btn` | `Button` (primary/secondary/ghost/danger) |
    | `photoGrid` | |
    | `a5` | order print preview |
  - Sample data module inside `build()`: `people`, `doctors`, `rooms`, `services`, `money()`.
    - Synthetic, copied from the app canvas `build()`: the same `people`, `GROUPS`, doctors, services and `money()`,
      so both canvases show the same patients and numbers.
    - Do not copy names or numbers from the old web. Labels and texts DO come from the old web (complete coverage).
    - Business-rule sentences stay verbatim.
- `.claude/skills/pema-web-design/references/blocks-web.md`: a table of block → `src/ui` component (file) → KMP
  `core:ui` analogue (from the app `BLOCKS.md`, or "none") → usage rules (max columns, when to use a table and when
  cards).
- `.claude/skills/pema-web-design/scripts/web-canvas.cjs`: the same CLI as `canvas.cjs`.
  - `list [file]` prints `ID · name · note`.
  - `check [file] [groups] [outDir] [--viewport=1440x900]` renders through `design-viewer`. It reports `errors`,
    `unresolved` (`{{ }}`), `overflow` per frame, and `total` against `inventory.json`, and writes one PNG per group.
  - Screen id regex `^W[A-I]\d+$`.
- `web-specs-lib.cjs` changes.
  - When a frame exists, the spec's Layout section is generated from the canvas blocks (block → kit component with
    real text).
  - The snapshot stays as the fallback, and a `## Old web snapshot` appendix stays for comparison.
  - Also generate `design-specs/web/BLOCKS.md` from `blocks-web.md` plus the usage counts.

## Steps
1. Build the template and helmet. Write a token-generation snippet (it may be a small script in the skill) that
   writes the `:root` block from `tokens.json`, so it never drifts. `web-canvas.cjs check` fails when the canvas
   tokens differ from `tokens.json`.
2. Implement every block, and render each once on a scratch screen at the 3 viewports. At 390, tables become cards and
   the sidebar becomes a top bar or drawer, as in the Next.js FE.
3. PROOF ONLY: build exactly two screens end to end, `WA1` (owner shell) and `WB1` (dashboard), to prove every block works
   at 1440, 1920 and 390. The rest of WA and WB is done by the W3b agents. Fill each from
   its spec and screenshot. Every field, action, status, filter and text of the spec appears. Block shapes follow
   the matching app canvas frame when there is one. Each note starts with `WEB + '<nav/tab/modal> · <difference from old web, if any>'`.
4. Run `web-canvas.cjs check "Pema Web.dc.html" WA,WB <tmp>` at 1440, then for pages at 1920 and 390. Open every PNG.
   Compare each frame with `visual-ref/old/<ID>-1440x900.png`: same regions, same order, every label, field, action
   and status present. Then glance at the app canvas frame(s) in `app_canvas`: same block shapes and tokens.
5. Regenerate the specs (`web-specs.cjs`) and confirm that WA and WB specs now show canvas blocks. Run `--check` on
   web and app specs.

## Acceptance
- `node .claude/skills/pema-web-design/scripts/web-canvas.cjs check "Pema Web redesign canvas/Pema Web.dc.html" WA,WB`
  exits 0, with `errors`, `unresolved` and `overflow` empty, and `total` = the WA + WB count in the inventory.
- `web-canvas-build.cjs --check` exits 0, the build is deterministic, and stub parts WC–WH build without error.
- Every block in `blocks-web.md` has a kit component that exists in `pema-agent/frontend/src/ui`. If a kit component
  is missing, the block is marked "kit gap" and listed in the report. Do not add it to the FE in this step.
- No hex colour inside blocks (grep). Tokens equal `tokens.json` (the check).
- `web-specs.cjs --check` and app `design-specs.cjs --check` exit 0. The app canvas is byte-identical.

## Out of scope
- Groups WC–WH content (W3b, six agents). Pushing to claude.ai/design (W5). Adding components to the Next.js kit.

## Report
Use `_REPORT-TEMPLATE.md`. Also include:
- the block list with kit gaps;
- the PNGs you opened, and per WB screen one line "complete vs old web / missing: … / app blocks reused: …".

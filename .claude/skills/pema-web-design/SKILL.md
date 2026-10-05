---
name: pema-web-design
description: Keep the design of the Pema web in step — the frozen inventory of the old web (211 screens: Clinic Web, Finance and the Patient Mobile web, every state), its screenshots, generated screen specs (design-specs/web/, served by the MCP tools get_web_screen / list_web_screens) and the web canvas "Pema Web redesign canvas/Pema Web.dc.html" (web-size frames in the app design language). Use when asked "which web screens are missing from the web canvas", "build / port a Next.js screen from the web canvas" (read the spec first), "refresh old-web screenshots / specs", "add or change a web screen in the web canvas", or when a visible change in pema-agent/frontend needs a log entry (web-design-changes.md). Does not edit the old web (prototype/) or the app canvas; for the app use pema-web-to-canvas and pema-canvas-to-kmp-compose.
---

# Pema web design (old web → inventory → shots → specs → web canvas → Next.js)

Package W built four layers for the old Clinic Web (`prototype/clinic-web`, read-only), the way the app has them:

| Layer | Where | Made by |
|---|---|---|
| Inventory: 211 screen ids `WA1 … WI42`, frozen | `design-specs/web/inventory.json` | `web-inventory.cjs` from `lib/catalog.cjs` |
| Screenshots: 5 viewports per id, git-ignored | `pema-agent/frontend/visual-ref/old/` (+ tracked `manifest.json`) | `web-shots.cjs` |
| Specs: structured snapshot + one spec per id | `design-specs/web/` (`snapshot.json`, `screens/<ID>.md`, `INDEX.md`, `BLOCKS.md`, `index.json`) | `web-snapshot.cjs`, `web-specs.cjs`, hand notes in `notes.json` |
| Web canvas: 1440 / 1920 / 390 frames | `Pema Web redesign canvas/Pema Web.dc.html` (old web, WA-WI) and `Pema Web (Next.js).dc.html` (Next.js-only, WJ-WL), both generated | `web-canvas-build.cjs` from `parts/<group>.js` |

Read first: `AGENT.md` (synthetic data only, AI output is a draft), `pema-agent/docs/PLAN-AI01-W.md` (why and decisions D1–D8), `references/blocks-web.md` (the block manual).

Script paths are relative to the repo root: `S=.claude/skills/pema-web-design/scripts`. Keep temp files (captures, renders) in `%TEMP%` or the scratchpad, never in the repo. Scripts are CommonJS, Node 24, no extra npm dependency. Playwright is loaded only through `scripts/lib/pw.cjs`.

## 1. Setup

| Need | Command | Check |
|---|---|---|
| Old web, port 4173 (read-only) | `python -m http.server 4173 --bind 127.0.0.1 --directory prototype` (or `docker compose up -d pema-prototype`) | http://127.0.0.1:4173/clinic-web/ |
| Finance API, port 4174 (numbers of WG*) | `python prototype/finance_server.py --port 4174 --db "%TEMP%/pema-w-finance.sqlite3"` (a temp DB: the default writes `.local/` in the repo) | http://127.0.0.1:4174 |
| Design viewer for the web canvas | `cd design-viewer && DC_CANVAS_DIR=<repo>/"Pema Web redesign canvas" npm run dev -- --port 4181` | http://localhost:4181 |
| Playwright + Chromium | `export PLAYWRIGHT_MODULE=<repo>/pema-agent/frontend/node_modules/playwright` (Chromium is installed for it) | `web-inventory.cjs` starts without "Playwright not found" |

Notes that cost time before:
- Start the old web and the finance API **once** and share them. Run **one browser at a time** against 4173: `http.server` drops connections above two clients.
- Port 4180 is the app canvas viewer (`canvas.cjs`). `web-canvas.cjs` defaults to **4181**; any other port needs `--viewer-url http://localhost:<port>`. Deps (`npm install`) live in the main checkout's `design-viewer/`; a worktree has no `node_modules`, so run the viewer from the main checkout and point `DC_CANVAS_DIR` at your worktree's canvas folder.
- The captures use a fixed clock (`2026-09-20T09:00:00+07:00`), zone Asia/Ho_Chi_Minh, account `owner-tam` (the inventory `role` overrides it per id) and fresh storage. Never change them for one id.
- Screenshots are git-ignored: a new worktree has only `manifest.json`. Look for the PNGs in the main checkout, or capture with `--out=<dir>`.
- On a Windows working tree with CRLF every `--check` compares line-ending-normalised text, so CRLF alone never fails them. New files you add are LF.

## 2. Where things are

```
.claude/skills/pema-web-design/
  SKILL.md, web-design-changes.md          this file; the change log of the Next.js front end (D6)
  scripts/lib/{pw,old-web,catalog,web-extract,token-map,canvas-layout,web-canvas-lib}.cjs
  scripts/web-inventory.cjs                catalog + live web → inventory.json
  scripts/web-shots.cjs                    inventory → PNGs + manifest.json + gallery index.html
  scripts/web-snapshot.cjs                 inventory → design-specs/web/snapshot.json (text-only DOM)
  scripts/web-specs.cjs, web-specs-lib.cjs snapshot + notes + canvas → design-specs/web/ (INDEX, BLOCKS, index.json, screens/*.md)
  scripts/web-canvas-build.cjs, web-canvas.cjs   parts → canvas; list/check the canvas through design-viewer
  scripts/web-coverage.cjs                 → references/coverage-web.md (one row per id) and the counts table
  scripts/pending-web.cjs                  front-end files changed since the baseline with no log entry
  references/blocks-web.md, coverage-web.md   block manual; old web ↔ web canvas ↔ app canvas ↔ Next.js (generated)
design-specs/web/                          inventory.json, snapshot.json, notes.json (HAND), INDEX.md, BLOCKS.md, index.json, screens/<ID>.md
Pema Web redesign canvas/                  template.html, nodes.html, parts/{base,WA…WH,tail,blocks}.js (HAND), support.js,
                                           Pema Web.dc.html and Pema Web blocks.dc.html (GENERATED)
pema-agent/frontend/visual-ref/old/        <ID>-<W>x<H>.png, <ID>-…-print.png, legacy <W>-<name>.png, manifest.json, README.md
.claude/skills/pema-canvas-to-kmp-compose/mcp/pema-design-mcp.cjs   MCP tools list_web_screens, get_web_screen, get_web_screen_image, record_web_note (prompt port_web_screen)
```

Hand-written: `lib/catalog.cjs`, `notes.json`, `parts/*.js`, `web-design-changes.md`, `references/blocks-web.md`. Everything else is generated: never edit it, regenerate it. Every generator has `--check` (exit 1 when the committed output differs from a fresh run).

Ids come only from `inventory.json` (`^W[A-I]\d+$`), never renumber; a new screen is appended at the end of its group (add it to `lib/catalog.cjs`). Groups: WA shell, WB operations, WC patients and Patient 360, WD CSKH, WE studio/resources/services, WF cashier and orders, WG finance, WH Ask Pema and guide.

**Two canvas files (W10, owner decision 2026-10-05).** `Pema Web.dc.html` holds only WA-WI (211 ids) and never a WJ/WK/WL frame; `Pema Web (Next.js).dc.html` holds WJ/WK/WL (173 ids). Both are built from the same `template.html`, `nodes.html`, `parts/base.js`, `blocks.js` and `tail.js` (`lib/web-canvas-lib.cjs` `OUTPUTS` maps file → groups; a group that is not in a file gets empty parts). `web-canvas-build.cjs` writes and `--check`s both (`--file="<name>"` for one; it fails when the old file holds a WJ/WK/WL frame), `web-canvas.cjs check --file "<name>" [groups] [outDir] --viewport=all --complete --frames` checks one file for its own ids and fails on a "foreign" group (`foreignIds`); specs and coverage read both files (`canvasFile` per screen). In the design viewer a dropdown "Web" (shown when the folder holds both files) switches "Web cũ" (default), "Màn mới" or "Cả hai" (both side by side, hash `#both`).

Package W2 (W7) added the Next.js-only screens, ids `^W[A-L]d+$`: `WJ` agent admin (`/admin/*` except care), `WK` care agent (`/admin/care/*`, `/care/*`), `WL` sign-in, app shell and message templates (`/login`, `/templates`, `(app shell)`). They are hand-kept in `scripts/lib/catalog-nextjs.cjs` (merged by `lib/catalog.cjs`), carry `source: "nextjs"`, are NOT walked against the old web and are validated statically by `web-inventory.cjs` (each `next_route` is a real `page.tsx`; every `page.tsx` of `pema-agent/frontend` is claimed by an entry or by a `non_screens` entry with `route`). Their `reach` uses the Next.js vocabulary listed at the top of `catalog-nextjs.cjs` (login, goto, button, text, fill, wait, note) and runs against `pnpm dev:mock`. Since W9 every one has a spec (`design-specs/web/screens/WJ*.md`, `WK*.md`, `WL*.md`, status shown as `exists (design W2)`): `web-specs.cjs` builds it from the inventory row (the brief of W7), `notes.json` (`groups.<WJ|WK|WL>`, `routes.<route>` with purpose, gate, roles, actions, context, related, and `screens.<ID>` with purpose and related) and a check that every text the brief quotes exists in the front-end source ("Texts to re-check against the code" lists the rest); `web-specs.cjs --check` fails when a route lacks purpose, gate, roles or actions. When `snapshot.json` holds the id (W8), the spec uses the measured layout, tokens and responsive notes instead of the brief; no `snapshot` is required for a Next.js-only id. The Patient Mobile web (WI) is `served by KMP/Zalo` (owner decision 1), not a Next.js target.

## 3. Refresh (old web → inventory → shots → snapshot → specs)

Only needed when the old web changed, a catalog entry was added, or a check says a file is stale. Order matters; run the `--check` of a stage before the next one.

```sh
node $S/web-inventory.cjs --check            # the catalog still reaches every screen; every entry point of the live web is claimed by an id
node $S/web-inventory.cjs                    # rewrite inventory.json (only after a catalog edit)
node $S/web-shots.cjs --only=WB3             # capture these ids x 5 viewports (merges into manifest.json); no --only = all ids, hours
node $S/web-snapshot.cjs --only=WB3          # re-walk these ids into snapshot.json (merges)
node $S/web-specs.cjs                        # regenerate design-specs/web/ (INDEX, BLOCKS, index.json, screens/*.md)
node $S/web-specs.cjs --check                # specs fresh + 0 snapshot items missing from the Layout of any id
node $S/web-coverage.cjs                     # references/coverage-web.md + counts table; --check also verifies shots, specs, frames
```

- `web-shots.cjs --check` and `web-snapshot.cjs --check` re-walk the whole old web (hours). Run them only for a full audit, in `%TEMP%`. For a quick file-set check use `web-coverage.cjs --check --images=<folder with the PNGs>`.
- `web-shots.cjs` writes the images, `manifest.json` (SHA-256 per image; 405 screen + 10 print + 80 legacy-name copies today) and a gallery; open `index.html` of the output folder and look at the changed ids.
- Timing on a normal PC: `web-inventory.cjs --check` about 2 minutes (measured on the first 81 ids), `web-shots.cjs --only=<one id>` about 40 s (5 viewports), `web-snapshot.cjs --only=<one id>` a few seconds, `web-canvas.cjs check` of one group about 20 s.
- `web-shots.cjs --out=<dir>` keeps its `manifest.json` and gallery in `<dir>` and leaves the tracked manifest alone; use it to try a capture. Without `--out` the images go to `visual-ref/old/` (git-ignored) and the tracked `manifest.json` is rewritten (SHA-256 per image may change by anti-aliasing noise on 1024 and 1280 wide captures: commit a manifest change only for ids you really recaptured).
- `web-snapshot.cjs` and `web-specs.cjs` write LF. On a CRLF working tree `git status` then shows the file as modified with no content change; `git checkout <file>` or ignore it.
- A `FAILED` line from `web-inventory.cjs` means a selector or label of the old web changed: fix `lib/catalog.cjs` (do not skip the id). A new button, tab or dialog of the old web fails the "claimed by some `covers`" check until it gets an id.
- The specs read the **built canvas** (`Pema Web.dc.html`), so after `web-snapshot.cjs` regenerate the canvas first if you changed a part (section 4), then `web-specs.cjs`.

### 3a. Shots and snapshots of the Next.js ids (WJ, WK, WL)

These ids (`source: "nextjs"` in `inventory.json`) are shot and snapshotted from `pema-agent/frontend`, not from the old web.
They need the front end with its mock back end, not the old web on 4173:

```sh
cd pema-agent/frontend
MOCK_PORT=4480 MOCK_LIVE_PERIOD_MS=0 NODE_OPTIONS="--require <repo>/.claude/skills/pema-web-design/scripts/lib/frozen-time.cjs" pnpm mock
PEMA_API_URL=http://127.0.0.1:4480 PORT=3480 pnpm dev        # open it as http://localhost:3480 (Next blocks 127.0.0.1 in dev)
node $S/web-shots.cjs    --out=<scratch dir> --only=WJ1,WK3   # PNGs (git-ignored) go to the scratch dir; seed it with a copy of the tracked manifest.json
node $S/web-snapshot.cjs --only=WJ1,WK3
```

- `lib/frozen-time.cjs` freezes the clock of the mock process at the inventory clock (2026-09-20 09:00 +07) so the data and the browser agree and a capture repeats. The mock keeps its state in memory: restart it before a full run (a sign-in updates "last login"), and run the ids in inventory order.
- `lib/next-web.cjs` drives the page (`login`, `goto`, `button`, `text`, `fill`, `wait`); `lib/next-states.cjs` turns the inventory's `note` steps (empty list, error answer, role without permissions, stream down) into code by answering the page's own `/api/v1` calls in the browser. Nothing of the front end or the mock is edited, and no capture writes to the mock (non-GET calls are answered by the capture itself).
- Shots are taken at the entry's `frames` (pages 1440x900, 1920x1020, 390x844; states and dialogs 1440x900; WL18 and WL19 390x844). A state the mock cannot give gets `state_unreachable` in `manifest.json` and no image; do not fake one.
- `web-shots.cjs --check` skips the SHA comparison for Next.js ids (mock data and front end change with every package); it still checks file set, page errors and unmet `expect`.

### 3b. The owner rule (final)

The web canvas, the specs and the shots contain **every** piece of UI of the old web (every page, tab, modal, dialog, visible state, field, action, status, filter, text), drawn in the **app's design language** (tokens, block shapes, sample data). Nothing is filtered out.

| Question | Source that wins |
|---|---|
| Which screens, fields, actions, statuses, texts exist | the old web, completely |
| Colours, type, radius, spacing, shapes of blocks | `pema-agent/frontend/src/ui/tokens.json` and the app canvas blocks |
| Sample data (names, numbers, money) | the canvas `people`, `GROUPS`, `money()`; the old web's demo values are not copied |
| Business-rule sentences, button labels | verbatim from the old web, Vietnamese |

Where the old web and the app disagree on a label, a step or a rule sentence: keep the old web's UI as it is in the frame and spec, and write the app's version under `differences` in `design-specs/web/notes.json` for the owner (decision D8). A screen the app lacks gets `app_canvas: []` and is still built. If in doubt whether something is UI, include it and report it. Never remove UI to match the app.

## 4. Add or change a web screen in the canvas

1. Read what the id must show: `node $S/web-specs.cjs --show=WB3` (or MCP `get_web_screen("WB3")`) and open `visual-ref/old/WB3-1440x900.png` (or MCP `get_web_screen_image`). Check the live list: `node $S/web-canvas.cjs list | grep WB3`.
2. Edit **only** `Pema Web redesign canvas/parts/<group>.js` with the helpers of [references/blocks-web.md](references/blocks-web.md) (`page`, `tab`, `dlg`, `fin`, then blocks). No hex colour, font size or radius in a part. Notes start with `WEB + '<nav/tab/modal> · <difference from the old web>'`. A block that does not exist is an open item (kit gap), not an edit of `template.html`.
3. Build and look:

```sh
node $S/web-canvas-build.cjs                  # parts → Pema Web.dc.html (WA-WI) and Pema Web (Next.js).dc.html (WJ-WL), deterministic; --check compares with the committed files
# viewer running on 4181 (section 1)
node $S/web-canvas.cjs check "Pema Web redesign canvas/Pema Web.dc.html" WB "$TEMP/wb" --viewport=all --frames   # exit 1 on errors
node $S/web-canvas.cjs check --file "Pema Web (Next.js).dc.html" --complete --viewport=all "$TEMP/nx" --frames   # all WJ/WK/WL ids; --frames last
node $S/web-specs.cjs --check --group=WB      # coverage of the group against the old-web snapshot
```

`--viewport=all` writes `web-<group>-all.png` plus one `<ID>-<width>.png` per frame with `--frames`; a single viewport writes `web-<group>-<viewport>.png`. At 1920 and 390 only pages and tabs have frames, so `total` is 25 while `expected` is 81 and `missing` is empty: that is by design (decision D4), only `missing`, not the difference, counts. `check` passes when `errors`, `unresolved` (`{{ }}` left), `overflow`, `badIcons`, `tokens`, `hexInBlocks`, `frameMismatch` and unknown ids are empty and `total` = `expected`. **Then open every `web-<group>-<viewport>.png` and look**: text overflow, wrapped numbers, icon names shown as text. Exit 0 alone is not enough. Frames: pages, tabs and finance get 1440 · 1920 · 390 (decision D4); states, dialogs and modals 1440 only.

4. `node $S/web-canvas-build.cjs && node $S/web-specs.cjs && node $S/web-coverage.cjs`, then `--check` of all three.
5. Unsure about a rule, a difference or a gotcha you learned: write it to `notes.json` (section 5), not into a part.

The block gallery (`web-canvas-build.cjs --blocks`, check `web-canvas.cjs check "Pema Web blocks.dc.html" WA`) shows every block once.

## 5. Build a Next.js screen from a spec

The pattern of `pema-canvas-to-kmp-compose` §1, for `pema-agent/frontend`:

1. `get_web_screen("<ID>")` (MCP `pema-design`, or `design-specs/web/screens/<ID>.md`). **Read the spec instead of `prototype/`.** It gives the logic source, the Next.js route and status, the app canvas cross-reference, the frame, the **Layout** (every field, action, status, filter and notice as `src/ui` component calls, with real text), required text, business rules, differences, gotchas and the old-web snapshot. Open only what the spec lacks.
2. Use the components named in Layout (`AppShell`, `Sidebar`, `TopBar`, `PageHeading`, `Card`, `Tile`, `TableShell`, `Tabs`, `Badge`, `Button`, `Field`, `Dialog`, `Sheet`, `EmptyState`, `GuardedLink` from `src/ui`; shared `Notice` and `FilterChip`). Tokens only (`bg-surface`, `text-ink-soft`, …), never hex. A block marked "kit gap" in `design-specs/web/BLOCKS.md` has no kit component yet: build it next to the page and list it for the director.
3. Compare with the image: `visual-ref/old/<ID>-<W>x<H>.png` against `pnpm visual` output (`visual-ref/new/`). Same structure (sidebar width, header, columns), not pixel equality.
4. Gate in `pema-agent/frontend`: `pnpm lint`, `pnpm vitest run` (count ≥ 820, the U7 baseline), `pnpm inventory`.
5. **Afterwards record what you learned** with MCP `record_web_note(id, key, text)` (`key` = `logic | rules | differences | gotchas | todo`; one short English sentence, UI text stays Vietnamese in quotes) or by editing `design-specs/web/notes.json` and running `web-specs.cjs`. Never edit `screens/*.md`. Then add the entry to `web-design-changes.md` (section 7).

## 6. Push to claude.ai/design

Project: "Pema Web redesign canvas" (decision D7), created by the user. Project id: **not yet created; W5 writes it here**. Never touch the app project `7822035f-ae10-4b1f-a802-ce789b25a393`. The `DesignSync` tool works only inside the `/design-sync` flow the **user** starts; if it has not started, remind them. In that flow update only the files you edited (`Pema Web.dc.html`, `support.js`):

1. `DesignSync get_file` that file. Large results are saved to a JSON file. On a new empty project there is nothing to merge.
2. `node .claude/skills/pema-web-to-canvas/scripts/remote-diff.cjs <JSON file> "Pema Web redesign canvas/Pema Web.dc.html"`. `-` lines are edits made only on claude.ai/design: merge them into the local parts (the canvas file is generated) or ask the user before overwriting. No `-` lines means it is safe.
3. `finalize_plan` with `localDir` = `Pema Web redesign canvas`, `writes: ["Pema Web.dc.html", "support.js"]`, `deletes: []`, then `write_files` with `localPath`.
4. `get_file` again and compare with the local file ignoring CRLF; they must be equal.

Never delete remote files, never create `.design-sync/config.json`, never run the design-system build flow.

## 7. Finish

- **Checks** (all exit 0; the two marked * need the old web, run them only after an old-web or catalog change):
  `web-inventory.cjs --check`*, `web-specs.cjs --check`, `web-canvas-build.cjs --check`, `web-canvas.cjs check … <groups>` at 1440, 1920 and 390, `web-coverage.cjs --check --images=<PNG folder>`, `web-snapshot.cjs --check`*, `node .claude/skills/pema-canvas-to-kmp-compose/scripts/design-specs.cjs --check` (app specs unchanged; it needs the git-ignored `pema-kmp/design-ref/<ID>.png` that `gradlew canvasRefs` makes: without them every spec differs on its "Canvas image" line and the check reports "85 file(s) out of date" although nothing is wrong, so also run `git diff <base> --stat -- design-specs/screens "Pema App redesign canvas/Pema App.dc.html"`, which must be empty), `node .claude/skills/pema-web-to-canvas/scripts/pending.cjs` (the old web is frozen: nothing new may appear; if its baseline commit is not in this clone it stops with `bad revision`, then `git diff <base> --stat -- prototype` must be empty), `node $S/pending-web.cjs` (no `✗ NOT LOGGED`).
- **Change log (decision D6)**: a visible change in `pema-agent/frontend/src/{app,ui,components}` gets an entry under "Pending" in [web-design-changes.md](web-design-changes.md) **in the same commit** (template inside). `pending-web.cjs` lists changed files since the **Sync baseline** and flags `✗ NOT LOGGED` ones (exit 1). When the canvas has been updated for an entry, move it to "Done" with `- Result: <ids/blocks changed>, pushed/not pushed`, set the baseline to the commit you compared against (`git rev-parse --short HEAD`) and rerun `pending-web.cjs`: 0 pending, 0 ✗.
- Update `references/coverage-web.md` with `web-coverage.cjs` (never by hand). Counts must be equal: ids = specs = canvas screens = coverage rows, screenshots = ids × 5 (+ print and legacy copies), snapshot items missing = 0. A mismatch is a defect: report it, do not hide it.
- Append a checkpoint to `SECTION_PROGRESS.md` for UI-only work (what was added, the viewports 1440 · 1920 · 390, how it was checked), keeping its line endings.
- `git diff --check`, commit on the step branch (no AI attribution anywhere in git: no Co-Authored-By, no "Generated with", no tool names). Never commit screenshots, dumps or `.local/`.
- Report: ids changed per group, the `check` results with real numbers, pushed or not pushed to claude.ai/design, what remains.

See also: `pema-web-to-canvas` (old web → app canvas, same change-log pattern), `pema-canvas-to-kmp-compose` (canvas → KMP, same spec-first pattern).

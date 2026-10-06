# W3b — Web design canvas: one group per agent (way 3, part 2)

Run as **eight independent agents in parallel**, one per group: WA, WB, WC, WD, WE, WF, WG, WH. Each takes this recipe with its
group letter. WA and WB already hold the proof screens WA1 and WB1 from W3a; keep them and add the rest. Group scopes:
- WA Shell and navigation;
- WB Operations: dashboard, today, schedule, booking/check-in;
- WC Patients and Patient 360;
- WD CSKH;
- WE Studio, resources and services;
- WF Cashier, orders and A5;
- WG Finance;
- WH Hỏi Pema and Hướng dẫn.

**You own exactly these files and no others:** `Pema Web redesign canvas/parts/<your group>.js`, and the keys of your own
ids in `design-specs/web/notes.json` (add or edit only keys under your ids). Never edit `template.html`, `base.js`, another
group's part, `Pema Web.dc.html` (generated: run `web-canvas-build.cjs` locally to see it, but commit only the part and
notes), inventory, snapshot or specs. If a block or helper is missing, write it under "open items" and skip that screen.
Everywhere below, "groups" means your one group.

## Goal
Give every remaining inventory id a frame in `Pema Web.dc.html`, using only the blocks W3a built. The owner rule
applies: every field, action, status, filter and text of the old screen appears; block shapes and tokens follow the
app design. Groups:
- WC Patients and Patient 360;
- WD CSKH;
- WE Studio, resources and services;
- WF Cashier, orders and A5;
- WG Finance;
- WH Hỏi Pema and Hướng dẫn.

## Read first
1. `PLAN-AI01-W.md`, and the W3a report (block list, kit gaps).
2. `.claude/skills/pema-web-design/references/blocks-web.md` and the WA/WB screens in the canvas, as examples.
3. For each group: `design-specs/web/screens/<ID>.md` (W2) and `visual-ref/old/<ID>-1440x900.png` (W1). Open
   `prototype/` sources only for what the spec lacks, and record what you learned in `design-specs/web/notes.json`.
4. Business rules to keep verbatim: `AGENT.md` (AI drafts need doctor review, PB02 finance rules) and the notices in
   each spec.

## Ingredients
- Data only, in `parts/<group>.js` as `const <G> = [ …screens… ];`, using the helpers defined in W3a.
  **Do not edit the template, the helmet, the block renderers or `base.js`.**
  - If a block is truly missing, stop that screen, write it as an open item and continue with the others. The
    director decides whether W3a must add it.
- Notes: `WEB + '<nav/tab/modal> · <difference>'`. For screens whose Next.js target is `planned (U4)`, `(U5)` or
  `(U6)`, add `· chưa có trên Next.js` to the note.
- Photos (WC photos tab, WE studio): placeholders with consent state only. No real or AI-generated faces, and no
  before/after scoring (plan principle 6, PLAN-AI01-U principle 6).

## Steps
1. Work through your group's ids in inventory order. After every few screens and at the end:
   - run `web-canvas-build.cjs`, then `web-canvas.cjs check … <group> --canvas-dir <your worktree canvas dir> --viewer-url
     http://localhost:<your port>` at 1440, then the pages at 1920 and 390 (start your own design-viewer on your own port);
   - open the group PNG;
   - compare with the old screenshots (everything present) and with the app canvas frames (same block shapes);
   - commit (`design: web canvas group <WX>`): the part file and your notes keys only.
2. Finance (WG). Show the owner, accountant and doctor projections the old finance web shows. Keep the PB02 wording
   on rate snapshots and on "the performing doctor is never assigned from the record owner".
3. Regenerate the specs of your ids if the spec generator reads the canvas (`web-specs.cjs`); run its `--check`.
   The director runs the full cross-group check after merging all six.

## Acceptance
- `web-canvas.cjs check` for your group exits 0 (`errors`, `unresolved`, `overflow` empty); `total` = your group's id count in
  the inventory; the frame count matches D4 (pages × 3, others × 1).
- Every spec's Layout section comes from the canvas (no snapshot fallback left). `web-specs.cjs --check` and app
  `design-specs.cjs --check` exit 0.
- Scope: `git diff --stat feat/web-design` shows only `parts/<your group>.js` and `design-specs/web/notes.json` (and the
  regenerated `Pema Web.dc.html` / specs only if you committed them: do not).

## Out of scope
- New blocks, template changes, push (W5), Next.js code.

## Report
Use `_REPORT-TEMPLATE.md`. Also include:
- the frame count for your group;
- the screens skipped for a missing block;
- one line per group: "complete vs old web / missing: … / app blocks reused: …".

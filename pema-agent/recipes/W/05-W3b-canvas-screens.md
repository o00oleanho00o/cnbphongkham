# W3b — Web design canvas: groups WC–WH (way 3, part 2)

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
- Data only, inside `build()` of `Pema Web.dc.html`, before `const groups = [`, and a `groups` entry per group.
  **Do not edit the template, the helmet or the block renderers.**
  - If a block is truly missing, stop that screen, write it as an open item and continue with the others. The
    director decides whether W3a must add it.
- Notes: `WEB + '<nav/tab/modal> · <difference>'`. For screens whose Next.js target is `planned (U4)`, `(U5)` or
  `(U6)`, add `· chưa có trên Next.js` to the note.
- Photos (WC photos tab, WE studio): placeholders with consent state only. No real or AI-generated faces, and no
  before/after scoring (plan principle 6, PLAN-AI01-U principle 6).

## Steps
1. Work group by group, in the order WC → WD → WE → WF → WG → WH. After each group:
   - run `web-canvas.cjs check … <group>` at 1440, then the pages at 1920 and 390;
   - open the group PNG;
   - compare with the old screenshots (everything present) and with the app canvas frames (same block shapes);
   - commit (`design: web canvas group <WX>`).
2. Finance (WG). Show the owner, accountant and doctor projections the old finance web shows. Keep the PB02 wording
   on rate snapshots and on "the performing doctor is never assigned from the record owner".
3. Regenerate the specs and run both `--check`s.
4. Run the full check: `web-canvas.cjs check "Pema Web.dc.html" WA,WB,WC,WD,WE,WF,WG,WH`.

## Acceptance
- The full `web-canvas.cjs check` exits 0. `total` = inventory id count, and the frame count matches D4 (pages × 3,
  others × 1).
- Every spec's Layout section comes from the canvas (no snapshot fallback left). `web-specs.cjs --check` and app
  `design-specs.cjs --check` exit 0.
- The template is unchanged since W3a: `git diff design/w3a -- "Pema Web redesign canvas/Pema Web.dc.html"` touches
  only `build()` data and `groups`.

## Out of scope
- New blocks, template changes, push (W5), Next.js code.

## Report
Use `_REPORT-TEMPLATE.md`. Also include:
- the frame count per group;
- the screens skipped for a missing block;
- one line per group: "complete vs old web / missing: … / app blocks reused: …".

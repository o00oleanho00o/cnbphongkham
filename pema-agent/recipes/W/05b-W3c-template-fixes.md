# W3c — Template and tooling fixes found by the eight W3b agents (one agent)

## Goal
All 81 inventory ids now have frames (W3b merged). The eight group agents could not edit the shared template, so they
recorded gaps. Fix the shared template, block renderers, helpers and generators once, then make `web-specs.cjs --check`,
`web-canvas.cjs check --complete` and `web-canvas-build.cjs --check` pass for ALL groups with the fewest `demo_data`
exemptions possible.

## Read first
`pema-agent/docs/PLAN-AI01-W.md`, `pema-agent/recipes/W/00-README.md`, `.claude/skills/pema-web-design/references/blocks-web.md`,
and the "open items" below (they come from the W3a/W3b reports). Owner rule stays: nothing of the old web's UI may be
missing; app design language for look.

## You own (and may edit)
`Pema Web redesign canvas/template.html`, `nodes.html`, `parts/base.js`, `parts/tail.js`, and small option changes inside
`parts/W?.js` ONLY where the fix needs a new option (keep each such edit minimal and list it in the report),
`.claude/skills/pema-web-design/scripts/lib/canvas-layout.cjs`, `web-specs-lib.cjs`, `web-canvas.cjs`, `web-canvas-build.cjs`,
`references/blocks-web.md`, `design-specs/web/notes.json` (remove `demo_data` exemptions that become unnecessary; do not
remove other keys). Regenerate and commit `Pema Web.dc.html` and `design-specs/web/screens/*.md`, `INDEX.md`, `BLOCKS.md`,
`index.json`.

## Fixes (each with a before/after check)
1. Bell: draw it only for the roles that have it in the old web (owner, doctor); none for care, accountant (WA2, WA3).
2. Account select: do not truncate its label ("BS. Tâm · Chủ phòng khám", "Kế toán · Đối soát & thu ngân") — widen.
3. Search field: honour the `w` option; keep width when a value is set (WD8).
4. Money must not wrap before "₫" in `bars`, `kpis`, `stat` at 390 (`white-space: nowrap`), checked on WB1 and WG at 390.
5. `hero`: put its actions (e.g. the period badge) on the right, as the old web does (WG1, WG6, WG8, WC4).
6. `dlg`: expose the close button's label "Đóng hộp thoại" (accessible name / `title`, visually still ×) so the coverage check
   sees it; then delete the now-useless `demo_data` exemptions for it in notes.json.
7. `canvas-layout.cjs`: list every distinct row/status/chip of a table, not only the first row; then delete the
   exemptions that existed for it (WD1, WC1 …).
8. `card`: a tint/variant option so per-service colours (WE5, S0–S3) and similar can be drawn; use it in WE.js.
9. `board`: hatched buffer block ("15′ chuẩn bị phòng"), empty-slot "Đặt lịch" buttons, "· +15′ đệm" in the time line; title of
   the buffer must not be cut at 1440 (WB5). Update WB.js to use them.
10. Notice: allow a title and bullet list inside one notice that still matches the coverage text (WH6–WH10 "Điểm cần nhớ");
    restore the bold title and bullets in WH.js.
11. Sidebar badge on "Theo dõi": 5 as in the old shots (base.js).
12. Concatenated old notices (WC2 empty state, WC9 zoom notice, WE1/WE2): make the generator match them to separate blocks, or
    document why not; drop the exemptions if solved.
13. WF2/WF3/WF4/WF9/WF10: after fix 6 they must pass without exemptions.

## Acceptance (run all, real output)
- `web-canvas-build.cjs --check` exit 0.
- `web-canvas.cjs check "Pema Web redesign canvas/Pema Web.dc.html" WA,WB,WC,WD,WE,WF,WG,WH --complete --viewport=all --frames`
  exit 0 with errors/unresolved/overflow/badIcons/tokens/hexInBlocks empty, total 81.
- `web-specs.cjs --check` exit 0 (81 specs, 0 missing, no stale).
- `web-inventory.cjs --check` exit 0 is not required (needs the old web); do not run it.
- Open the PNGs you changed (WA2, WA3, WB5, WD8, WE5, WG1 at 390, WH6, a dialog) and look.
- Scope: only the files listed under "You own". `prototype/`, `pema-kmp/`, `design-specs/screens/`, `pema-agent/frontend` untouched.

## Report
`_REPORT-TEMPLATE.md`; list per fix: done / not done and why; list the remaining exemptions in notes.json with a reason each.

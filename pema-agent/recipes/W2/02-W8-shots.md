# W8 — Shots of the new ids against the mock BE

## Goal
Reference screenshots and structure snapshot for every WJ/WK/WL id at the package-W viewports.

## Read first
1. `recipes/W/02-W1-old-web-shots.md` and `09-W6b-shots-specs-new-ids.md` (how `web-shots.cjs`/`web-snapshot.cjs`
   were driven for the old web, manifest format, PNG policy).
2. `pema-agent/frontend/README.md` (mock BE, dev server, roles/login for the mock), `scripts/visual-check.ts` if U0 exists.

## Ingredients
- `web-shots.cjs` extended with a `nextjs` source (login against the mock, navigate by route, trigger states/dialogs by
  the selectors recorded in W7) — additive change inside `.claude/skills/pema-web-design/scripts/`.
- `manifest.json` entries per id × viewport; PNGs under the scratchpad.
- `snapshot.json` entries (actions/fields/statuses/notices) produced by `web-snapshot.cjs` for the new ids.

## Steps
1. Start FE dev server with the mock BE; verify one admin and one care route render.
2. For each id: reach the state (role switch, click dialog trigger, empty data fixture), shoot 1440×900; pages also
   1920×1020 and 390×844.
3. Snapshot structure for each id; merge into `snapshot.json` with `web-snapshot.cjs --merge`.
4. Record failures per id (selector not found, state unreachable) in the report; do not fake a frame later.

## Acceptance
- `manifest.json` has every new id with its required viewports; snapshot entries exist for all; `--check` still 0.

## Out of scope
- Specs, frames.

## Report
Use `_REPORT-TEMPLATE.md`; list unreachable states.

# Package W recipes — design of the old Pema web (screenshots, screen specs, web canvas)

One file = one step. Template: Goal → Read first → Ingredients → Steps → Acceptance → Out of scope → Report.
A subagent takes **one file** and returns a report using `_REPORT-TEMPLATE.md`.
The source of truth is `pema-agent/docs/PLAN-AI01-W.md`. If a recipe and the plan disagree, follow the plan.

## Order

```
01-W0-inventory ─┬─► 02-W1-old-web-shots ───────────────────────────────┐
                 └─► 03-W2-web-specs ─► 04-W3a-canvas-foundation ─► 05-W3b-canvas-screens ─┴─► 06-W4-skill-docs-audit ─► 07-W5-push-design (director + user)
```

At most 2 subagents run at once (W1 ‖ W2). W5 is not a subagent step.

## Running a step (director)

1. Base branch `feat/web-design`, created from `feat/ui-parity` at `821f813`. Make the worktree by hand: tool-made
   worktrees start from old `master`.
   ```
   git worktree add C:/wt/pema-w1 -b design/w1 feat/web-design
   ```
2. Spawn one `pema-builder` subagent (`run_in_background`). Prompt:
   > Follow `pema-agent/recipes/W/<file>.md` in worktree `C:/wt/pema-<step>` (branch `design/<step>`). Read
   > `pema-agent/docs/PLAN-AI01-W.md` first. `prototype/`, `pema-kmp/`, `Pema App redesign canvas/Pema App.dc.html`
   > and `design-specs/screens/` are read-only. No git trailers and no AI attribution in commits. Commit often.
   > Do not spawn subagents. Return the report in `_REPORT-TEMPLATE.md` format.
3. Shared services. The director starts each one once, and all agents share them.
   - Old web: `python -m http.server 4173 --bind 127.0.0.1 --directory prototype`
   - Finance API: `python prototype/finance_server.py --port 4174 --db "%TEMP%/pema-w-finance.sqlite3"`
   - Design viewer (W3 only): `cd design-viewer && npm install && npm run dev` (port 4180)
4. Environment for every agent:
   `PLAYWRIGHT_MODULE=C:/Users/phanx/Documents/Codex/2026-09-11/create-an-image-of/cnbphongkham/pema-agent/frontend/node_modules/playwright`
   (Chromium is already installed for it).
5. Gate. Run `PLAN-AI01-W.md` §5 in the worktree. Then:
   - merge into `feat/web-design` with `--no-ff`;
   - add one line to the HANDOFF "Package W" progress log;
   - push only when the user says so.

## Common rules

- **Owner rule: complete coverage.** The shots, specs and canvas contain every page, tab, modal, dialog, state,
  field, action, status, filter and text of the old web. Nothing is filtered out.
  - Look (tokens, type, block shapes, sample data) comes from the app design (`tokens.json`, `Pema App.dc.html`).
  - Content comes from the old web, completely.
  - Where the two disagree on wording or a step, keep the old web's UI and record the app's version in
    `design-specs/web/notes.json` under `differences`.
  - If in doubt whether something is UI, include it and report it.
- Read-only: `prototype/**`, `pema-kmp/**`, `Pema App redesign canvas/Pema App.dc.html`, `design-specs/screens/**`,
  `design-specs/{INDEX,BLOCKS}.md`, `design-specs/index.json`, `design-specs/notes.json`, `docs/**`.
- Never start the old web on any port other than 4173, or the finance server on any port other than 4174. If a port is
  taken, ask the director.
- Screen ids come only from `design-specs/web/inventory.json` (`^W[A-H]\d+$`). Never renumber after W0. New ids are
  appended at the end of their group.
- Scripts are CommonJS (`.cjs`), Node 24, no new npm dependency. Load Playwright only through
  `scripts/lib/pw.cjs`.
- Every generator has `--check`: exit 1 when the committed output differs from what it would generate now.
- Temp files (dumps, renders, logs) go in `%TEMP%` or the scratchpad, never in the repo.
- Keep line endings: LF for new files. Preserve CRLF/LF of any existing file you edit.
- Vietnamese UI text stays verbatim. Spec headings and notes are in English.
- Synthetic data only. A real phone number, name or photo in any output means the step has failed.
- Report: at most 30 lines, with real command output (exit codes, counts).

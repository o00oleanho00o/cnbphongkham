# Web design canvas change log

Sync baseline: `c40ba22`

Every time something **visible** in the Next.js front end (`pema-agent/frontend/src/app/**`, `src/ui/**`, `src/components/**`) is added, changed or removed (a page, tab, dialog, field, button, filter, status, flow, business-rule wording, or a design token in `src/ui/tokens.json` or `tokens.css`), add an entry under **Pending** and commit it in the same commit as the code. The `pema-web-design` skill reads these entries and only redraws the affected frames instead of re-checking all 81 screens. This is the Next.js counterpart of `.claude/skills/pema-web-to-canvas/web-changes.md` (which logs the old web `prototype/` for the app canvas); the old web itself is frozen and is not logged here.

**Log**: added or removed page, tab, modal or dialog · added, removed or changed field, button, filter, status · changed flow (which screen a button opens, where saving goes) · changed warning or business-rule wording ("AI chỉ là bản nháp", consent, not an emergency channel…) · changed colour, type or radius token · changed kit component look (`src/ui/*`).
**Do not log**: refactors with no visible change · tests · sample or mock data (unless it adds a new column or status) · fixes with no visible change · routes that only exist in Next.js and are out of the web canvas by decision D3 are still logged, with canvas target "none (D3)".

Template (newest entry on top):

```md
### YYYY-MM-DD · <add|change|remove> · <page/tab/dialog name>
- Where: `pema-agent/frontend/src/app/(admin)/<route>/page.tsx` · route `/<route>` · or `src/ui/<component>.tsx`
- Change: <which field/button/status/sentence/token was added, removed, changed; new flow>
- Web canvas target: <inventory ids, e.g. WB3, WB4 · "block <name>" · "token" · "none (D3)" · "new screen">
- Logged by: <name/agent> · commit/PR if any
```

If unsure of the canvas id, write "unknown"; the skill looks it up in `.claude/skills/pema-web-design/references/coverage-web.md`. Keep Vietnamese UI labels and wording exactly as they appear in the UI. `pending-web.cjs` accepts an entry as the log of a file when the entry names the file path (without `pema-agent/frontend/`) or, for files other than `page.tsx`/`layout.tsx`, its file name.

## Pending

## Done

The skill moves entries from "Pending" down here with their result, then updates **Sync baseline** to the commit it compared against. Keep about the 20 most recent entries; older ones are in git history.

### 2026-10-04 · full sync · baseline
- Package W (W0–W4): inventory of the old web (81 ids), 405 screenshots at 5 viewports, 81 specs in `design-specs/web/`, MCP web tools, web canvas with 81 screens (`Pema Web redesign canvas/Pema Web.dc.html`).
- Result: the log starts here. Baseline `c40ba22` is the commit that holds W0–W3c (the front end was not touched by package W). Not pushed to claude.ai/design yet (W5).

# Report — step <W?> <name>

**Worktree/branch:** <path> / <branch>  
**Recipe:** `recipes/W/<file>.md`  
**Status:** done | partial | blocked  
**Commits:** <short hashes>

## Built
- <scripts, generated files, canvas groups — 3–8 lines>

## Checks run (real results)
- Step checks: `<command>` → exit <n>, <counts: ids / images / specs / frames>
- App specs unchanged: `node .claude/skills/pema-canvas-to-kmp-compose/scripts/design-specs.cjs --check` → <result>
- Web log: `node .claude/skills/pema-web-to-canvas/scripts/pending.cjs` → <0 ✗ files>
- Scope: `git diff --stat feat/web-design` → <only owned paths? list anything else>
- FE (only if `pema-agent/frontend` changed): lint / vitest (N ≥ 820) / inventory → <result>
- Visual review: <which PNGs you opened and what you saw>

## Assumptions
- <behaviour of the old web you inferred; clock, role, data choices>

## Open items
- <ids that could not be reached, FAILED lines, questions for the owner, work for later steps>

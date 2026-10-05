# Report — step <U?> <name>

**Worktree/branch:** <branch>  
**Recipe:** `recipes/U/<file>.md`  
**Status:** done | partial | blocked

## Built
- <routes, components, actions, migrations — 3–8 lines>

## Tests and lint run (real results)
- FE: `pnpm vitest run` → <N passed> (baseline 407, must not drop); `pnpm lint`, `pnpm tsc --noEmit`, `pnpm build` → <result>
- FE visual: `pnpm tsx scripts/visual-check.ts` → <screens × viewports, overflow failures>
- BE: `uv run pytest apps/api/tests/clinic/<...>` → <N passed, M failed>; ruff / pyright / import-linter → <result>
- Inventory: `FEATURE-INVENTORY.md` → <all green | list of red items>

## Assumptions
- <behaviour you inferred from the prototype where docs were silent>
- <seed values marked synthetic>

## Open items
- <changes needed in other steps/packages; prototype behaviour you could not reproduce; product questions>

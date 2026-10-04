# Report — step <M?> <name>

**Worktree/branch:** <branch>  
**Recipe:** `recipes/M/<file>.md`  
**Status:** done | partial | blocked

## Built
- <main modules/files and their role, 3–8 lines>

## Tests and lint run (real results)
- `uv run pytest apps/api/tests/care/<...>` → <N passed, M failed>; failures: <test name + one-line cause>
- `uv run ruff check` / `uv run pyright` → <result>
- <FE: pnpm lint / build if applicable>

## Assumptions
- <Protocols created in ports.py because another package was missing>
- <temporary thresholds/constants; mark "awaiting doctor" where applicable>

## Open items
- <changes needed in other packages; recipe↔plan conflicts; product decisions nobody has made>
